from __future__ import annotations

import os
from typing import Any

from rapidfuzz import fuzz

from src.adapters import CompanyContext, SourceResult
from src.cache import get_cached, set_cached
from src.http import HttpClient, sanitize_error


def _text(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, dict):
        for key in ("name", "value", "text", "amount", "display"):
            if val.get(key):
                return str(val.get(key)).strip() or None
        return None
    text = str(val).strip()
    return text or None


def _list_names(val: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(val, list):
        return out
    for item in val:
        name = _text(item.get("name") if isinstance(item, dict) else item)
        if name and name not in out:
            out.append(name)
    return out


def _pick_company(items: list[Any], ctx: CompanyContext) -> dict[str, Any] | None:
    needle = (ctx.domain or ctx.name or ctx.query or "").lower()
    best = None
    best_score = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("companyName") or "").strip()
        domain = str(item.get("domain") or item.get("website") or "").lower()
        score = 0
        if ctx.domain and ctx.domain.lower() in domain:
            score = 100
        elif name:
            score = max(
                fuzz.token_set_ratio(needle, name.lower()),
                fuzz.partial_ratio(needle, name.lower()),
            )
        if score > best_score:
            best_score = score
            best = item
    if best is None or best_score < 55:
        return items[0] if items and isinstance(items[0], dict) else None
    return best


def _map_company(item: dict[str, Any]) -> dict[str, Any]:
    round_info = item.get("latestFundingRound") or item.get("lastFundingRound") or {}
    if not isinstance(round_info, dict):
        round_info = {}
    last_round = _text(round_info.get("name") or round_info.get("stage") or round_info)
    amount = _text(round_info.get("amount") or item.get("totalMoneyRaised") or item.get("totalFunding"))
    return {
        "name": _text(item.get("name") or item.get("companyName")),
        "website": _text(item.get("website") or item.get("domain")),
        "founded": _text(item.get("foundedYear") or item.get("founded")),
        "stage": _text(item.get("stage") or item.get("companyStage") or round_info.get("stage")),
        "total_raised": amount or _text(item.get("totalMoneyRaised")),
        "last_round": last_round,
        "investors": _list_names(item.get("investors") or item.get("investorList") or []),
        "competitors": _list_names(item.get("similarCompanies") or item.get("competitors") or [])[:12],
        "source_url": _text(item.get("profileUrl") or item.get("url")),
    }


async def fetch_tracxn(http: HttpClient, ctx: CompanyContext) -> SourceResult:
    token = os.getenv("TRACXN_ACCESS_TOKEN", "").strip()
    if not token:
        return SourceResult("tracxn", False, error="no_api_key")
    cache_key = (ctx.domain or ctx.name or ctx.query or "").lower()
    if not cache_key:
        return SourceResult("tracxn", False, error="no_query")
    cached = get_cached("tracxn", cache_key, 86400)
    if cached is not None:
        return SourceResult("tracxn", True, data=cached)
    headers = {
        "accessToken": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    name = ctx.name or ctx.query
    filt: dict[str, Any] = {}
    if ctx.domain:
        filt["domain"] = ctx.domain
    elif name:
        filt["companyName"] = name
    body = {"filter": filt, "sort": [], "from": 0, "size": 5}
    try:
        data = None
        for url in (
            "https://platform.tracxn.com/api/3.0/companies",
            "https://platform.tracxn.com/api/2.2/companies",
        ):
            try:
                data = await http.post_json(url, json=body, headers=headers, retries=2, timeout=12.0)
                break
            except Exception:
                data = None
        if not isinstance(data, dict):
            return SourceResult("tracxn", False, error="request_failed")
        items = data.get("result") or data.get("results") or data.get("companies") or data.get("data") or []
        if isinstance(items, dict):
            items = items.get("companies") or items.get("result") or []
        if not isinstance(items, list) or not items:
            return SourceResult("tracxn", False, error="no_match")
        picked = _pick_company(items, ctx)
        if not picked:
            return SourceResult("tracxn", False, error="no_match")
        mapped = _map_company(picked)
        set_cached("tracxn", cache_key, mapped)
        return SourceResult("tracxn", True, data=mapped)
    except Exception as exc:
        return SourceResult("tracxn", False, error=sanitize_error(exc))
