from __future__ import annotations

import re

from src.adapters import CompanyContext
from src.adapters.yahoo import is_india_symbol

_INDIA_HINT = re.compile(
    r"\b(india|indian|mumbai|delhi|bengaluru|bangalore|chennai|hyderabad|pune|kolkata|"
    r"ahmedabad|gurgaon|gurugram|noida|jaipur|kochi|indore|pvt|private limited|llp)\b|\.in\b",
    re.I,
)
_CLEARLY_FOREIGN = re.compile(
    r"\b(united states|usa|u\.s\.a?|united kingdom|england|scotland|germany|france|"
    r"japan|china|canada|australia|singapore|uae|dubai|netherlands|sweden|switzerland)\b",
    re.I,
)


def looks_india(ctx: CompanyContext) -> bool:
    if is_india_symbol(ctx.ticker):
        return True
    blob = " ".join(
        str(x)
        for x in (ctx.country, ctx.city, ctx.name, ctx.query, ctx.website, ctx.domain)
        if x
    )
    if _INDIA_HINT.search(blob):
        return True
    country = (ctx.country or "").strip()
    if country and _CLEARLY_FOREIGN.search(country):
        return False
    if not country:
        return True
    return False


BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


async def fetch_html_browser(url: str, wait_ms: int = 1500) -> str:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return ""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=BROWSER_UA, locale="en-US")
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            html = ""
            for _ in range(15):
                await page.wait_for_timeout(max(wait_ms, 1000) if _ == 0 else 1500)
                html = await page.content()
                low = (html or "").lower()
                if "verifying connection" in low or "just a moment" in low:
                    continue
                if len(html) > 5000:
                    break
            await browser.close()
            return html or ""
    except Exception:
        return ""
