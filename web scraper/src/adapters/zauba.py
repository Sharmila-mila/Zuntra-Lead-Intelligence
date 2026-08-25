from __future__ import annotations

import html as html_lib
import re
from typing import Any
from urllib.parse import quote_plus, urlparse

from rapidfuzz import fuzz

from src.adapters import CompanyContext, SourceResult
from src.adapters.geo import BROWSER_UA, looks_india
from src.cache import get_cached, set_cached
from src.http import HttpClient, sanitize_error

_CIN_RE = re.compile(r"\b([UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)

_SEARCH_LINKS_JS = """() => Array.from(document.querySelectorAll('a'))
  .map(a => ({href: a.href || '', text: (a.innerText || '').trim()}))
  .filter(a => {
    try {
      const u = new URL(a.href);
      if (!/zaubacorp\\.com$/i.test(u.hostname.replace(/^www\\./,''))) return false;
      const path = u.pathname.replace(/^\\//,'');
      if (!path || path.includes('/')) return false;
      if (/^(companysearch|login|pricing|company-research)/i.test(path)) return false;
      return /(?:[UL]\\d{5}[A-Z]{2}\\d{4}[A-Z]{3}\\d{6}|LLP-[A-Z]{3}-\\d{4})$/i.test(path);
    } catch (e) { return false; }
  })
"""

_PAGE_JS = """() => {
  const text = document.body ? (document.body.innerText || '') : '';
  const rows = Array.from(document.querySelectorAll('table tr')).map(r =>
    Array.from(r.querySelectorAll('td')).map(td => (td.innerText || '').trim()).filter(Boolean)
  ).filter(r => r.length >= 3);
  return { text, rows, title: document.title || '' };
}"""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", text))).strip()


def _best_company_url(links: list[dict[str, str]], query: str) -> str | None:
    best = None
    best_score = 0
    for item in links:
        href = (item.get("href") or "").strip()
        text = (item.get("text") or "").strip()
        if not href:
            continue
        slug = urlparse(href).path.strip("/").replace("-", " ")
        score = max(
            fuzz.token_set_ratio(query.lower(), text.lower()) if text else 0,
            fuzz.token_set_ratio(query.lower(), slug.lower()),
        )
        if score > best_score:
            best_score = score
            best = href
    if best and best_score >= 35:
        return best
    return links[0].get("href") if links else None


def _parse_directors(rows: list[list[str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        din = None
        name = None
        designation = None
        for cell in row:
            if re.fullmatch(r"\d{8}", cell):
                din = cell
            elif din and name is None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cell) and cell != "-":
                name = cell
            elif din and name and designation is None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cell) and cell != "-":
                designation = cell
                break
        if not din or not name or din in seen:
            continue
        seen.add(din)
        out.append({"name": name, "din": din, "designation": designation})
        if len(out) >= 12:
            break
    return out


def _parse_company(text: str, rows: list[list[str]], source_url: str) -> dict[str, Any] | None:
    blob = text or ""
    cin_m = re.search(r"CIN[:\s]+([UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})", blob, re.I)
    cin = (cin_m.group(1) if cin_m else None) or (_CIN_RE.search(blob).group(1) if _CIN_RE.search(blob) else None)
    if not cin:
        return None
    status_m = re.search(r"Company Status[:\s]+([A-Za-z \-]+)", blob, re.I)
    status = status_m.group(1).strip() if status_m else None
    if status:
        status = status.split("\n")[0].strip()[:48]
    incorporated_m = re.search(r"incorporated on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})", blob, re.I)
    incorporated = incorporated_m.group(1).strip() if incorporated_m else None
    roc_m = re.search(r"Registrar of Companies,\s*([A-Za-z ]+)", blob, re.I)
    roc = roc_m.group(1).strip().rstrip(".") if roc_m else None
    email = None
    email_m = re.search(r"Email address\s*-\s*(" + _EMAIL_RE.pattern + r")", blob, re.I)
    if email_m:
        email = email_m.group(1).rstrip(".")
    else:
        email_m = _EMAIL_RE.search(blob)
        if email_m:
            email = email_m.group(0).rstrip(".")
    address = None
    addr_m = re.search(
        r"Registered address of .+? is\s+(.+?)(?:\.\s|\n|Contact Details|$)",
        blob,
        re.I | re.S,
    )
    if addr_m:
        address = _clean(addr_m.group(1))[:240]
    website = None
    web_m = re.search(r"Website[:\s]+(https?://\S+|www\.\S+)", blob, re.I)
    if web_m:
        website = web_m.group(1).rstrip(".")
    return {
        "cin": cin.upper(),
        "status": status,
        "roc": roc,
        "incorporated": incorporated,
        "address": address,
        "email": email,
        "website": website,
        "directors": _parse_directors(rows),
        "source_url": source_url,
    }


async def _wait_ready(page) -> str:
    html = ""
    for _ in range(16):
        await page.wait_for_timeout(1500)
        title = ((await page.title()) or "").strip()
        html = await page.content()
        low = (html or "").lower()
        if "verifying connection" in low or title.lower() == "just a moment...":
            continue
        if title and len(html) > 5000:
            return html
    return html or ""


async def _extract_page(page) -> dict[str, Any] | None:
    for _ in range(12):
        await page.wait_for_timeout(1200)
        title = ((await page.title()) or "").strip()
        low = ((await page.content()) or "").lower()
        if "verifying connection" in low or title.lower() == "just a moment..." or not title:
            continue
        try:
            extracted = await page.evaluate(_PAGE_JS)
        except Exception:
            extracted = None
        if isinstance(extracted, dict) and extracted.get("text") and _CIN_RE.search(extracted["text"]):
            return extracted
    return None


async def _scrape_browser(name: str) -> dict[str, Any] | None:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None
    search_url = "https://www.zaubacorp.com/companysearchresults/" + quote_plus(name)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=BROWSER_UA, locale="en-US")
            page = await context.new_page()
            await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            await _wait_ready(page)
            links: list[dict[str, str]] = []
            try:
                links = await page.evaluate(_SEARCH_LINKS_JS)
            except Exception:
                links = []
            if not links:
                html = await page.content()
                for m in re.finditer(
                    r"https?://(?:www\.)?zaubacorp\.com/[A-Za-z0-9\-]+-(?:[UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}|[A-Z]{3}-\d{4})",
                    html,
                    re.I,
                ):
                    links.append({"href": m.group(0), "text": ""})
            company_url = _best_company_url(links, name)
            await browser.close()
            if not company_url:
                return None

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=BROWSER_UA, locale="en-US")
            page = await context.new_page()
            await page.goto(company_url, wait_until="domcontentloaded", timeout=60000)
            await _wait_ready(page)
            extracted = await _extract_page(page)
            final_url = page.url or company_url
            await browser.close()
            if not isinstance(extracted, dict):
                return None
            return _parse_company(
                str(extracted.get("text") or ""),
                list(extracted.get("rows") or []),
                final_url,
            )
    except Exception:
        return None


async def fetch_zauba(http: HttpClient, ctx: CompanyContext) -> SourceResult:
    if not looks_india(ctx):
        return SourceResult("zauba", False, error="skipped_not_india")
    name = (ctx.name or ctx.query or "").strip()
    if not name:
        return SourceResult("zauba", False, error="no_query")
    cache_key = name.lower()
    cached = get_cached("zauba", cache_key, 86400)
    if cached is not None:
        return SourceResult("zauba", True, data=cached)
    try:
        mapped = await _scrape_browser(name)
        if not mapped or not mapped.get("cin"):
            return SourceResult("zauba", False, error="no_match")
        set_cached("zauba", cache_key, mapped)
        return SourceResult("zauba", True, data=mapped)
    except Exception as exc:
        return SourceResult("zauba", False, error=sanitize_error(exc))
