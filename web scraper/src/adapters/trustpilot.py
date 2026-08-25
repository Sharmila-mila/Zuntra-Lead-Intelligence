from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any

from src.adapters import CompanyContext, SourceResult
from src.adapters.geo import BROWSER_UA
from src.cache import get_cached, set_cached
from src.http import HttpClient, sanitize_error

_TAG_RE = re.compile(r"<[^>]+>")
_NEXT_DATA = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.I | re.S,
)
_JSON_LD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)

_EXTRACT_JS = """() => {
  const out = { rating: null, review_count: null, reviews: [], title: document.title || '' };
  const next = document.getElementById('__NEXT_DATA__');
  if (next && next.textContent) {
    try {
      const data = JSON.parse(next.textContent);
      const blob = JSON.stringify(data);
      const ts = blob.match(/"trustScore":([0-9.]+)/);
      if (ts) out.rating = ts[1];
      const tot = blob.match(/"numberOfReviews":\\{"total":(\\d+)/) || blob.match(/"total":(\\d+)/);
      if (tot) out.review_count = tot[1];
      const walk = (node) => {
        if (!node || out.reviews.length >= 5) return;
        if (Array.isArray(node)) { node.forEach(walk); return; }
        if (typeof node !== 'object') return;
        const title = node.title || node.headline || node.text;
        const stars = node.stars != null ? node.stars : (node.rating != null ? node.rating : null);
        const date = (node.dates && (node.dates.publishedDate || node.dates.experiencedDate))
          || node.createdAt || node.publishedDate || null;
        if (title && String(title).length >= 8 && (stars != null || true)) {
          out.reviews.push({
            title: String(title).slice(0, 180),
            stars: stars != null ? String(stars) : null,
            date: date ? String(date) : null,
          });
        }
        Object.values(node).forEach(walk);
      };
      walk(data);
    } catch (e) {}
  }
  if (!out.rating) {
    const el = document.querySelector('[class*="trustScore"]');
    if (el) {
      const m = (el.textContent || '').match(/([0-9]+(?:\\.[0-9]+)?)/);
      if (m) out.rating = m[1];
    }
  }
  if (!out.review_count) {
    const body = document.body ? document.body.innerText : '';
    const m = body.match(/([\\d,]+)\\s+reviews?/i);
    if (m) out.review_count = m[1].replace(/,/g, '');
  }
  return out;
}"""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", text))).strip()


def _domain(ctx: CompanyContext) -> str | None:
    raw = (ctx.domain or "").strip().lower()
    if not raw and ctx.website:
        raw = re.sub(r"^https?://", "", ctx.website.strip(), flags=re.I)
        raw = raw.split("/")[0]
    raw = raw.removeprefix("www.")
    if raw and "." in raw:
        return raw
    name = (ctx.name or ctx.query or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "", name)
    if not slug:
        return None
    return f"{slug}.com"


def _num(val: Any) -> str | None:
    if val is None:
        return None
    text = str(val).strip().replace(",", "")
    return text or None


def _scrape_map(html: str, domain: str, page_url: str, extracted: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rating = None
    count = None
    reviews: list[dict[str, Any]] = []
    if isinstance(extracted, dict):
        rating = _num(extracted.get("rating"))
        count = _num(extracted.get("review_count"))
        for item in extracted.get("reviews") or []:
            if not isinstance(item, dict):
                continue
            title = _clean(str(item.get("title") or ""))
            if not title:
                continue
            reviews.append(
                {
                    "provider": "trustpilot",
                    "title": title[:180],
                    "stars": _num(item.get("stars")),
                    "date": _num(item.get("date")),
                    "url": page_url,
                }
            )
            if len(reviews) >= 5:
                break
    if html:
        low = html.lower()
        if "verifying connection" in low or "just a moment" in low:
            if not rating and not reviews:
                return None
        if re.search(r"page not found|we can.?t find|businessprofile-notfound", low):
            return None
        if not rating or not count or not reviews:
            match = _NEXT_DATA.search(html)
            if match:
                blob = match.group(1)
                if not rating:
                    m = re.search(r'"trustScore"\s*:\s*([0-9.]+)', blob)
                    if m:
                        rating = m.group(1)
                if not count:
                    m = re.search(r'"numberOfReviews"\s*:\s*\{\s*"total"\s*:\s*(\d+)', blob) or re.search(
                        r'"total"\s*:\s*(\d+)', blob
                    )
                    if m:
                        count = m.group(1)
                if not reviews:
                    for title, stars in re.findall(
                        r'"title"\s*:\s*"([^"\\]{8,180})".{0,240}?"stars"\s*:\s*(\d+)',
                        blob,
                        re.S,
                    )[:5]:
                        reviews.append(
                            {
                                "provider": "trustpilot",
                                "title": _clean(title),
                                "stars": stars,
                                "date": None,
                                "url": page_url,
                            }
                        )
        if not rating:
            m = re.search(r'trustScore__[^>]*>([0-9.]+)', html) or re.search(
                r'"ratingValue"\s*:\s*"?([0-9.]+)"?', html
            )
            if m:
                rating = m.group(1)
        if not count:
            m = re.search(r'"reviewCount"\s*:\s*"?(\d+)"?', html)
            if m:
                count = m.group(1)
        if not reviews:
            for match in _JSON_LD.finditer(html):
                try:
                    data = json.loads(match.group(1).strip())
                except Exception:
                    continue
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    for rev in item.get("review") or []:
                        if not isinstance(rev, dict):
                            continue
                        stars = None
                        if isinstance(rev.get("reviewRating"), dict):
                            stars = rev["reviewRating"].get("ratingValue")
                        title = _clean(str(rev.get("headline") or rev.get("name") or rev.get("reviewBody") or ""))
                        if not title:
                            continue
                        reviews.append(
                            {
                                "provider": "trustpilot",
                                "title": title[:180],
                                "stars": _num(stars),
                                "date": _num(rev.get("datePublished")),
                                "url": page_url,
                            }
                        )
                        if len(reviews) >= 5:
                            break
    if not rating and not count and not reviews:
        return None
    return {
        "domain": domain,
        "rating": rating,
        "review_count": count,
        "url": page_url,
        "reviews": reviews[:5],
    }


async def _scrape_browser(page_url: str) -> tuple[str, dict[str, Any] | None]:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return "", None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=BROWSER_UA, locale="en-US")
            page = await context.new_page()
            await page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
            extracted = None
            html = ""
            for _ in range(15):
                await page.wait_for_timeout(1500)
                title = (await page.title()) or ""
                html = await page.content()
                low = html.lower()
                if "verifying connection" in low or "just a moment" in low or not title:
                    continue
                try:
                    extracted = await page.evaluate(_EXTRACT_JS)
                except Exception:
                    extracted = None
                if isinstance(extracted, dict) and (extracted.get("rating") or extracted.get("reviews")):
                    break
                if "__NEXT_DATA__" in html and len(html) > 20000:
                    break
            await browser.close()
            return html or "", extracted if isinstance(extracted, dict) else None
    except Exception:
        return "", None


async def fetch_trustpilot(http: HttpClient, ctx: CompanyContext) -> SourceResult:
    domain = _domain(ctx)
    if not domain:
        return SourceResult("trustpilot", False, error="no_domain")
    cached = get_cached("trustpilot", domain, 86400)
    if cached is not None:
        return SourceResult("trustpilot", True, data=cached)
    page_url = f"https://www.trustpilot.com/review/{domain}"
    try:
        html, extracted = await _scrape_browser(page_url)
        mapped = _scrape_map(html, domain, page_url, extracted)
        if not mapped:
            return SourceResult("trustpilot", False, error="no_match")
        set_cached("trustpilot", domain, mapped)
        return SourceResult("trustpilot", True, data=mapped)
    except Exception as exc:
        return SourceResult("trustpilot", False, error=sanitize_error(exc))
