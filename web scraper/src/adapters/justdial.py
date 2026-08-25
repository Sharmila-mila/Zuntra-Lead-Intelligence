from __future__ import annotations

import html as html_lib
import re
from urllib.parse import quote

from src.adapters import CompanyContext, SourceResult
from src.adapters.geo import BROWSER_UA, fetch_html_browser, looks_india
from src.cache import get_cached, set_cached
from src.http import HttpClient, sanitize_error

_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml",
}
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", text))).strip()


def _city_slug(ctx: CompanyContext) -> str:
    city = (ctx.city or "").split(",")[0].strip()
    if not city:
        return "India"
    return re.sub(r"[^A-Za-z0-9]+", "-", city).strip("-") or "India"


def _query_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")


def _parse_listing(html: str, name: str) -> dict | None:
    low = html.lower()
    if "just a moment" in low or "access denied" in low:
        return None
    href = None
    match = re.search(r'href=["\']([^"\']+/[A-Za-z0-9_-]+_[A-Za-z0-9]+)["\']', html)
    if match:
        href = match.group(1)
        if href.startswith("/"):
            href = "https://www.justdial.com" + href
    rating = None
    rmatch = re.search(r'(?:rating|ratingsummary)[^>]*>?\s*([0-9]\.[0-9])', html, re.I)
    if rmatch:
        rating = rmatch.group(1)
    else:
        rmatch = re.search(r'"ratingValue"\s*:\s*"?([0-9.]+)"?', html)
        if rmatch:
            rating = rmatch.group(1)
    count = None
    cmatch = re.search(r'"reviewCount"\s*:\s*"?(\d+)"?', html)
    if cmatch:
        count = cmatch.group(1)
    phone = None
    pmatch = re.search(r'(?:\+91[\s-]?)?[6-9]\d{9}', html)
    if pmatch:
        phone = pmatch.group(0)
    address = None
    amatch = re.search(r'"address"\s*:\s*"([^"]{8,180})"', html)
    if amatch:
        address = _clean(amatch.group(1))
    website = None
    wmatch = re.search(r'"url"\s*:\s*"(https?://(?!www\.justdial\.com)[^"]+)"', html)
    if wmatch:
        website = wmatch.group(1)
    hours = None
    hmatch = re.search(r'(?:open|timing)[^<]{0,40}(\d{1,2}:\d{2}\s*[AP]M[^<]{0,40})', html, re.I)
    if hmatch:
        hours = _clean(hmatch.group(1))
    if not (href or rating or phone or address):
        return None
    return {
        "name": name,
        "url": href,
        "rating": rating,
        "review_count": count,
        "phone": phone,
        "address": address,
        "website": website,
        "hours": hours,
    }


async def fetch_justdial(http: HttpClient, ctx: CompanyContext) -> SourceResult:
    if not looks_india(ctx):
        return SourceResult("justdial", False, error="skipped_not_india")
    name = (ctx.name or ctx.query or "").strip()
    if not name:
        return SourceResult("justdial", False, error="no_query")
    cache_key = f"{_city_slug(ctx)}|{name.lower()}"
    cached = get_cached("justdial", cache_key, 86400)
    if cached is not None:
        return SourceResult("justdial", True, data=cached)
    city = _city_slug(ctx)
    q = _query_slug(name)
    url = f"https://www.justdial.com/{quote(city)}/{quote(q)}"
    try:
        html = ""
        try:
            html = await http.get_text(url, headers=_HEADERS, retries=2, timeout=12.0)
        except Exception as exc:
            err = sanitize_error(exc)
            if "403" not in err and "http_403" not in err:
                raise
            html = ""
        parsed = _parse_listing(html or "", name)
        if parsed is None:
            html = await fetch_html_browser(url)
            parsed = _parse_listing(html or "", name)
        if parsed is None:
            return SourceResult("justdial", False, error="no_match")
        parsed["search_url"] = url
        set_cached("justdial", cache_key, parsed)
        return SourceResult("justdial", True, data=parsed)
    except Exception as exc:
        return SourceResult("justdial", False, error=sanitize_error(exc))
