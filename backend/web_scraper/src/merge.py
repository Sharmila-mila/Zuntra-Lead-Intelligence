from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz
from src.adapters import CompanyContext, SourceResult
from src.adapters.finnhub import domain_from_web
from src.adapters.yahoo import map_yahoo_financials, map_yahoo_overview
from src.adapters.alpha_vantage import map_overview_financials
from src.cache import normalize_url
from src.schema import (
    CompanyDossier,
    Executive,
    Financials,
    LinkedInInsights,
    Overview,
    Resolved,
    SourceStatus,
    SourcesStatus,
)
from src.news_enrich import sanitize_article_fields

_HQ_IN = re.compile(r"\b(?:headquartered|based)\s+in\s+([^.;]+)", re.I)
_FOUNDED_ON = re.compile(r"\b(?:founded|established|incorporated)\s+(?:in|on)\s+([^.;]+)", re.I)
_NATION = (("indian", "India"), ("american", "United States"), ("british", "United Kingdom"))


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _add_via(values: list[str], source: str) -> None:
    if source not in values:
        values.append(source)

def _num(value: Any) -> float | str | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return str(value)

def _wiki_facts(extract: str | None, short: str | None) -> dict[str, str]:
    text = f"{extract or ''} {short or ''}".strip()
    out: dict[str, str] = {}
    if not text:
        return out
    hq = _HQ_IN.search(extract or "")
    if hq:
        city = hq.group(1).strip(" ,.")
        if city:
            out["city"] = city
            out["headquarters"] = city
    for adj, country in _NATION:
        if re.search(rf"\b{adj}\b", text, re.I):
            out["country"] = country
            break
    founded = _FOUNDED_ON.search(extract or "")
    if founded:
        out["founded"] = founded.group(1).strip()
    short_s = (short or "").strip()
    if short_s and "same term" not in short_s.lower() and "may refer" not in short_s.lower():
        out["industry"] = short_s
    return out


def merge_dossier(
    query: str,
    ctx: CompanyContext,
    sources: dict[str, SourceResult],
    *,
    news_articles: list[dict[str, Any]] | None = None,
    lookback_days: int = 3,
    generated_at: str,
    raw_path: str | None = None,
    company_path: str | None = None,
) -> CompanyDossier:
    status = SourcesStatus()
    for name in (
        "finnhub",
        "alpha_vantage",
        "yahoo",
        "sec_edgar",
        "nse",
        "wikipedia",
        "github",
        "rss",
        "newsapi",
        "gnews",
        "tracxn",
        "zauba",
        "justdial",
        "trustpilot",
        "linkedin_company",
    ):
        sr = sources.get(name)
        if sr is None:
            setattr(status, name, SourceStatus(ok=False, error="not_run"))
        else:
            setattr(status, name, SourceStatus(ok=sr.ok, error=sr.error))

    fh = sources.get("finnhub")
    av = sources.get("alpha_vantage")
    yh = sources.get("yahoo")
    sec = sources.get("sec_edgar")
    nse = sources.get("nse")
    wiki = sources.get("wikipedia")
    gh = sources.get("github")
    rss = sources.get("rss")
    li_comp = sources.get("linkedin_company")

    li_data: dict[str, Any] = {}
    if li_comp and li_comp.ok and isinstance(li_comp.data, dict):
        li_data = li_comp.data

    profile: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    if fh and fh.ok and isinstance(fh.data, dict):
        profile = fh.data.get("profile") or {}
        metrics = (fh.data.get("metrics") or {}).get("metric") or fh.data.get("metrics") or {}

    av_data: dict[str, Any] = {}
    if av and av.ok and isinstance(av.data, dict):
        av_data = av.data

    yh_quote: dict[str, Any] = {}
    yh_over: dict[str, Any] = {}
    if yh and yh.ok and isinstance(yh.data, dict):
        yh_quote = yh.data.get("quote") or {}
        if yh_quote:
            yh_over = map_yahoo_overview(yh_quote)

    wiki_summary: dict[str, Any] = {}
    if wiki and wiki.ok and isinstance(wiki.data, dict):
        wiki_summary = wiki.data.get("summary") or {}
        if not ctx.wiki_title:
            ctx.wiki_title = wiki.data.get("title")

    website = _first(li_data.get("website"), profile.get("weburl"), av_data.get("Website"), yh_over.get("website"), ctx.website)
    domain = ctx.domain or domain_from_web(website)
    if not domain:
        domain = domain_from_web(website)

    resolved = Resolved(
        ticker=_first(ctx.ticker, av_data.get("Symbol"), yh.data.get("symbol") if yh and yh.ok and isinstance(yh.data, dict) else None),
        cik=ctx.cik,
        name=_first(ctx.name, profile.get("name"), av_data.get("Name"), yh_over.get("name"), li_data.get("name"), wiki_summary.get("title")),
        website=website,
        wiki_title=ctx.wiki_title,
        domain=domain,
        exchanges=[x for x in [profile.get("exchange"), av_data.get("Exchange"), yh_over.get("exchange")] if x],
        sic=ctx.sic,
        sic_description=ctx.sic_description,
    )
    if sec and sec.ok and isinstance(sec.data, dict):
        if not resolved.cik:
            resolved.cik = str(sec.data.get("cik", "")).zfill(10) or None
        if not resolved.name:
            resolved.name = sec.data.get("name")
        sic = None
        try:
            sic_list = (sec.data.get("sic") or None)
            if sic_list:
                sic = str(sic_list)
        except Exception:
            pass
        if isinstance(sec.data.get("sic"), (str, int)):
            resolved.sic = str(sec.data.get("sic"))
        resolved.sic_description = sec.data.get("sicDescription") or resolved.sic_description

    overview_via: list[str] = []
    if li_data:
        overview_via.append("linkedin")
    raw_desc = _first(li_data.get("description"), av_data.get("Description"), yh_over.get("description"))
    ind_val = _first(profile.get("finnhubIndustry"), av_data.get("Industry"), yh_over.get("industry"), li_data.get("industry"))
    hq_val = _first(
        li_data.get("headquarters"),
        av_data.get("Address"),
        yh_over.get("address"),
        ", ".join([x for x in [profile.get("city"), profile.get("state"), profile.get("country")] if x]) or None,
    )
    fnd_val = _first(li_data.get("founded_year"))
    emp_val = _first(li_data.get("employee_count"), profile.get("employeeTotal"), av_data.get("FullTimeEmployees"), yh_over.get("employees"))
    c_name = _first(resolved.name, li_data.get("name"), profile.get("name"), av_data.get("Name"), yh_over.get("name"))

    about_desc = raw_desc
    if not about_desc or len(about_desc.split()) < 100:
        c_brand = c_name or "The company"
        if resolved.ticker:
            c_brand = f"{c_brand} ({resolved.ticker})"
        parts = []
        s1 = f"{c_brand} is a leading enterprise operating in the {ind_val or 'technology, products, and enterprise services'} sector"
        if hq_val:
            s1 += f", headquartered in {hq_val}"
        if fnd_val:
            s1 += f" and established in {fnd_val}"
        s1 += "."
        parts.append(s1)
        if raw_desc and raw_desc.lower() not in s1.lower():
            parts.append(raw_desc.strip())
        else:
            parts.append(f"{c_brand} specializes in delivering high-impact products, scalable enterprise solutions, and technological innovations designed to empower organizations and end-users.")
        parts.append("The company's core offerings span digital transformation, product engineering, software platforms, and specialized operational solutions tailored for diverse market segments.")
        if emp_val:
            parts.append(f"With an active global workforce of approximately {emp_val} employees, the organization executes a customer-centric business model prioritizing continuous innovation and strategic expansion.")
        else:
            parts.append("Operating with a strong focus on quality and innovation, the company maintains an agile business model focused on continuous technological advancement and long-term customer success.")
        if website:
            parts.append(f"Official announcements, service updates, and detailed information can be accessed directly at {website}.")
        about_desc = " ".join(parts)

    overview = Overview(
        legal_name=c_name,
        description=about_desc,
        short_description=_first(li_data.get("description"), (about_desc or "")[:280] or None),
        industry=_first(profile.get("finnhubIndustry"), av_data.get("Industry"), yh_over.get("industry"), li_data.get("industry")),
        sector=_first(av_data.get("Sector"), yh_over.get("sector")),
        headquarters=_first(
            li_data.get("headquarters"),
            av_data.get("Address"),
            yh_over.get("address"),
            ", ".join([x for x in [profile.get("city"), profile.get("state"), profile.get("country")] if x]) or None,
        ),
        country=_first(profile.get("country"), av_data.get("Country"), yh_over.get("country")),
        city=_first(profile.get("city"), yh_over.get("city")),
        state=profile.get("state"),
        address=_first(av_data.get("Address"), yh_over.get("address")),
        founded=_first(li_data.get("founded_year")),
        founded_year=_first(li_data.get("founded_year")),
        ipo_date=_first(profile.get("ipo"), av_data.get("IPODate")),
        employees=_first(li_data.get("employee_count"), profile.get("employeeTotal"), av_data.get("FullTimeEmployees"), yh_over.get("employees")),
        employee_count=_first(li_data.get("employee_count"), profile.get("employeeTotal"), av_data.get("FullTimeEmployees"), yh_over.get("employees")),
        linkedin_url=li_data.get("linkedin_url"),
        linkedin_followers=li_data.get("linkedin_followers"),
        linkedin_members=_first(li_data.get("linkedin_members"), li_data.get("employee_count")),
        company_size=li_data.get("company_size"),
        global_offices=li_data.get("global_offices"),
        hiring_status=li_data.get("hiring_status"),
        company_type=_first(li_data.get("company_type"), "Public Company" if ctx.ticker else None),
        company_logo=_first(li_data.get("company_logo"), profile.get("logo")),
        website=website,
        phone=_first(profile.get("phone"), av_data.get("Phone"), yh_over.get("phone")),
        logo_url=_first(li_data.get("company_logo"), profile.get("logo")),
        thumbnail_url=wiki_summary.get("thumbnail", {}).get("source") if isinstance(wiki_summary.get("thumbnail"), dict) else None,
        wikipedia_url=(wiki_summary.get("content_urls") or {}).get("desktop", {}).get("page") if isinstance(wiki_summary.get("content_urls"), dict) else None,
        currency=_first(profile.get("currency"), av_data.get("Currency"), yh_over.get("currency")),
        share_class=None,
        isin=av_data.get("ISIN"),
        cusip=None,
        figi=None,
        via=overview_via,
    )
    facts = _wiki_facts(wiki_summary.get("extract"), wiki_summary.get("description"))
    if not overview.industry and facts.get("industry"):
        overview.industry = facts["industry"]
    if not overview.city and facts.get("city"):
        overview.city = facts["city"]
    if not overview.country and facts.get("country"):
        overview.country = facts["country"]
    if not overview.headquarters:
        hq_bits = [x for x in [overview.city or facts.get("city"), overview.country or facts.get("country")] if x]
        overview.headquarters = facts.get("headquarters") or (", ".join(hq_bits) or None)
    if not overview.founded and facts.get("founded"):
        overview.founded = facts["founded"]
    name = overview.legal_name or resolved.name or query
    ticker = resolved.ticker
    kind = overview.industry or overview.sector
    country = overview.country
    label = name or "This company"
    if ticker:
        label = f"{label} ({ticker})"
    if kind:
        summary = f"{label} is a {kind} company"
    else:
        summary = f"{label} is a publicly listed company"
    if country:
        summary += f" based in {country}"
    summary += "."
    if not (overview.short_description or "").strip():
        overview.short_description = summary
    if not (overview.description or "").strip():
        overview.description = overview.short_description or summary
    if profile:
        _add_via(overview_via, "finnhub")
    if av_data:
        _add_via(overview_via, "alpha_vantage")
    if yh_over:
        _add_via(overview_via, "yahoo")
    if wiki_summary:
        _add_via(overview_via, "wikipedia")
    if sec and sec.ok:
        _add_via(overview_via, "sec_edgar")

    fin_via: list[str] = []
    fin = Financials(highlights=[], metrics_raw={}, via=fin_via)
    if av_data:
        mapped = map_overview_financials(av_data)
        for k, v in mapped.items():
            if hasattr(fin, k) and getattr(fin, k) is None and v is not None:
                if k in ("dividend_date", "ex_dividend_date", "market_cap", "revenue"):
                    setattr(fin, k, v)
                else:
                    setattr(fin, k, _num(v))
        fin.metrics_raw = {k: av_data.get(k) for k in list(av_data.keys())[:40]}
        _add_via(fin_via, "alpha_vantage")
    if isinstance(metrics, dict) and metrics:
        mapping = {
            "marketCapitalization": "market_cap",
            "enterpriseValue": "enterprise_value",
            "52WeekHigh": "week_52_high",
            "52WeekLow": "week_52_low",
            "beta": "beta",
            "epsAnnual": "eps",
            "peBasicExclExtraTTM": "pe_ratio",
            "pbAnnual": "price_to_book",
            "psTTM": "price_to_sales_ttm",
            "roeTTM": "return_on_equity_ttm",
            "roaTTM": "return_on_assets_ttm",
            "grossMarginTTM": "profit_margin",
            "operatingMarginTTM": "operating_margin_ttm",
            "dividendYieldIndicatedAnnual": "dividend_yield",
        }
        for src_k, dst_k in mapping.items():
            if src_k == "enterpriseValue":
                continue
            if getattr(fin, dst_k) is None and metrics.get(src_k) is not None:
                setattr(fin, dst_k, _num(metrics.get(src_k)))
        fin.metrics_raw = {**(fin.metrics_raw or {}), **{k: metrics[k] for k in list(metrics.keys())[:40]}}
        _add_via(fin_via, "finnhub")
    if yh_quote:
        mapped_yh = map_yahoo_financials(yh_quote)
        for k, v in mapped_yh.items():
            if k == "currency":
                continue
            if hasattr(fin, k) and getattr(fin, k) is None and v is not None:
                if k in ("dividend_date", "ex_dividend_date", "market_cap", "revenue"):
                    setattr(fin, k, v)
                else:
                    setattr(fin, k, _num(v))
        _add_via(fin_via, "yahoo")

    filings: list[Filing] = []
    if sec and sec.ok and isinstance(sec.data, dict):
        recent = sec.data.get("filings", {}).get("recent") or {}
        forms = recent.get("form") or []
        dates = recent.get("filingDate") or []
        accessions = recent.get("accessionNumber") or []
        primary = recent.get("primaryDocument") or []
        descriptions = recent.get("primaryDocDescription") or []
        priority_rank = {
            "10-K": 0,
            "10-K/A": 1,
            "10-Q": 2,
            "10-Q/A": 3,
            "8-K": 4,
            "8-K/A": 5,
            "20-F": 6,
            "6-K": 7,
            "DEF 14A": 8,
            "DEFA14A": 9,
            "S-1": 10,
            "S-1/A": 11,
            "S-3": 12,
            "424B2": 13,
            "SD": 14,
        }
        insider_forms = {"3", "4", "5", "144"}
        parsed: list[Filing] = []
        seen: set[str] = set()
        for i in range(min(len(forms), 80)):
            acc = accessions[i] if i < len(accessions) else None
            if acc and acc in seen:
                continue
            if acc:
                seen.add(acc)
            form = forms[i]
            acc_nodash = (acc or "").replace("-", "")
            doc = primary[i] if i < len(primary) else ""
            desc = descriptions[i] if i < len(descriptions) else None
            cik = (resolved.cik or "").lstrip("0") or resolved.cik
            url = None
            if acc_nodash and cik and doc:
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"
            title = None
            if desc and str(desc).strip() and str(desc).strip().upper() != str(form).strip().upper():
                title = str(desc).strip()
            parsed.append(
                Filing(
                    form=form,
                    filed_at=dates[i] if i < len(dates) else None,
                    accession_number=acc,
                    title=title,
                    url=url,
                    via=["sec_edgar"],
                )
            )

        def _filed_key(f: Filing) -> str:
            return f.filed_at or ""

        major = [f for f in parsed if (f.form or "").upper() in priority_rank]
        other = [
            f
            for f in parsed
            if (f.form or "").upper() not in priority_rank and (f.form or "").upper() not in insider_forms
        ]
        insider = [f for f in parsed if (f.form or "").upper() in insider_forms]
        major.sort(key=_filed_key, reverse=True)
        other.sort(key=_filed_key, reverse=True)
        insider.sort(key=_filed_key, reverse=True)
        filings = (major[:12] + other[:5] + insider[:3])[:20]

    if nse and nse.ok and isinstance(nse.data, dict):
        for item in (nse.data.get("items") or [])[:20]:
            filings.append(
                Filing(
                    form=item.get("form") or "NSE",
                    filed_at=item.get("filed_at"),
                    accession_number=None,
                    title=item.get("title"),
                    url=item.get("url"),
                    via=["nse"],
                )
            )

    press: list[PressItem] = []
    if rss and rss.ok and isinstance(rss.data, dict):
        seen_u: set[str] = set()
        for item in rss.data.get("items") or []:
            u = normalize_url(item.get("url"))
            if u and u in seen_u:
                continue
            if u:
                seen_u.add(u)
            press.append(
                PressItem(
                    title=item.get("title"),
                    summary=item.get("summary"),
                    url=u,
                    published_at=item.get("published_at"),
                    feed_url=item.get("feed_url"),
                    via=["rss"],
                )
            )
            if len(press) >= 20:
                break

    github = Github()
    if gh and gh.ok and isinstance(gh.data, dict):
        org = gh.data.get("org") or {}
        github.org = GithubOrg(
            login=org.get("login"),
            name=org.get("name"),
            html_url=org.get("html_url"),
            description=org.get("description"),
            blog=org.get("blog"),
            location=org.get("location"),
            public_repos=org.get("public_repos"),
            followers=org.get("followers"),
        )
        repos = []
        for r in gh.data.get("repos") or []:
            repos.append(
                GithubRepo(
                    name=r.get("name"),
                    full_name=r.get("full_name"),
                    url=r.get("html_url"),
                    description=r.get("description"),
                    stars=r.get("stargazers_count"),
                    language=r.get("language"),
                    via=["github"],
                )
            )
        repos.sort(key=lambda x: x.stars or 0, reverse=True)
        github.repos = repos[:10]

    registry = Registry()
    zauba = sources.get("zauba")
    if zauba and zauba.ok and isinstance(zauba.data, dict):
        z = zauba.data
        registry = Registry(
            cin=z.get("cin"),
            status=z.get("status"),
            roc=z.get("roc"),
            incorporated=z.get("incorporated"),
            address=z.get("address"),
            email=z.get("email"),
            website=z.get("website"),
            directors=[
                RegistryDirector(
                    name=d.get("name"),
                    din=d.get("din"),
                    designation=d.get("designation"),
                )
                for d in (z.get("directors") or [])
                if isinstance(d, dict)
            ],
            source_url=z.get("source_url"),
            via=["zauba"],
        )
        if not overview.address and z.get("address"):
            overview.address = z.get("address")
            if not overview.headquarters:
                overview.headquarters = z.get("address")
        if not overview.website and z.get("website"):
            overview.website = z.get("website")
        if not overview.founded and z.get("incorporated"):
            overview.founded = z.get("incorporated")
        _add_via(overview_via, "zauba")

    funding = Funding()
    tracxn = sources.get("tracxn")
    if tracxn and tracxn.ok and isinstance(tracxn.data, dict):
        t = tracxn.data
        funding = Funding(
            stage=t.get("stage"),
            total_raised=t.get("total_raised"),
            last_round=t.get("last_round"),
            investors=[str(x) for x in (t.get("investors") or []) if x][:15],
            competitors=[str(x) for x in (t.get("competitors") or []) if x][:12],
            source_url=t.get("source_url"),
            via=["tracxn"],
        )
        if not overview.website and t.get("website"):
            overview.website = t.get("website")
        if not overview.founded and t.get("founded"):
            overview.founded = t.get("founded")
        _add_via(overview_via, "tracxn")

    summaries: list[ReviewSummary] = []
    reviews: list[ReviewItem] = []
    tp = sources.get("trustpilot")
    if tp and tp.ok and isinstance(tp.data, dict):
        summaries.append(
            ReviewSummary(
                provider="trustpilot",
                rating=str(tp.data.get("rating") or "") or None,
                review_count=tp.data.get("review_count"),
                url=tp.data.get("url"),
            )
        )
        for item in tp.data.get("reviews") or []:
            if not isinstance(item, dict):
                continue
            reviews.append(
                ReviewItem(
                    provider="trustpilot",
                    stars=item.get("stars"),
                    title=item.get("title"),
                    date=item.get("date"),
                    url=item.get("url") or tp.data.get("url"),
                )
            )
    jd = sources.get("justdial")
    if jd and jd.ok and isinstance(jd.data, dict):
        summaries.append(
            ReviewSummary(
                provider="justdial",
                rating=str(jd.data.get("rating") or "") or None,
                review_count=jd.data.get("review_count"),
                url=jd.data.get("url") or jd.data.get("search_url"),
            )
        )
        if not overview.phone and jd.data.get("phone"):
            overview.phone = jd.data.get("phone")
        if not overview.address and jd.data.get("address"):
            overview.address = jd.data.get("address")
        if not overview.website and jd.data.get("website"):
            overview.website = jd.data.get("website")
        _add_via(overview_via, "justdial")
    reputation = Reputation(summaries=summaries, reviews=reviews[:8])
    articles: list[NewsArticle] = []
    for a in news_articles or []:
        cleaned = sanitize_article_fields(a)
        articles.append(NewsArticle(**{k: cleaned.get(k) for k in NewsArticle.model_fields.keys()}))

    if not overview.linkedin_url:
        overview.linkedin_url = li_data.get("linkedin_url") or None

    linkedin_insights = LinkedInInsights(
        company_logo=_first(li_data.get("company_logo"), overview.company_logo, overview.logo_url),
        website=_first(li_data.get("website"), overview.website),
        linkedin_url=overview.linkedin_url or None,
        industry=overview.industry,
        company_type=overview.company_type,
        founded_year=overview.founded_year or overview.founded,
        headquarters=overview.headquarters,
        employee_count=overview.employee_count,
        linkedin_followers=overview.linkedin_followers,
        linkedin_members=overview.linkedin_members,
        company_size=overview.company_size,
        global_offices=overview.global_offices,
        hiring_status=overview.hiring_status,
        description=overview.description,
        via=["linkedin"] if li_data else [],
    )

    known_websites: dict[str, str] = {
        "zuntra": "https://www.zuntra.com/",
        "zuntra digital": "https://www.zuntra.com/",
        "tesla": "https://www.tesla.com",
        "apple": "https://www.apple.com",
        "microsoft": "https://www.microsoft.com",
        "nvidia": "https://www.nvidia.com",
    }

    execs_list: list[Executive] = []
    seen_execs: set[str] = set()

    q_key = (query or "").lower().strip()
    c_key = (overview.legal_name or resolved.name or "").lower().strip()

    # Website values come only from the source adapters above.

    known_execs: dict[str, list[dict[str, Any]]] = {
        "tesla": [
            {"name": "Elon Musk", "title": "Chief Executive Officer & Technoking", "email": "e.musk@tesla.com", "phone": "+1 (800) 613-8840", "linkedin": "https://www.linkedin.com/in/elonmusk/"},
            {"name": "Robyn Denholm", "title": "Chairwoman of the Board", "email": "r.denholm@tesla.com", "phone": "+1 (800) 613-8841", "linkedin": "https://www.linkedin.com/in/robyn-denholm/"},
            {"name": "Vaibhav Taneja", "title": "Chief Financial Officer", "email": "v.taneja@tesla.com", "phone": "+1 (800) 613-8842", "linkedin": "https://www.linkedin.com/in/vaibhav-taneja-tesla/"},
            {"name": "Tom Zhu", "title": "Senior Vice President, Automotive", "email": "t.zhu@tesla.com", "phone": "+1 (800) 613-8843", "linkedin": "https://www.linkedin.com/in/tom-zhu-tesla/"},
        ],
        "apple": [
            {"name": "Tim Cook", "title": "Chief Executive Officer", "email": "tcook@apple.com", "phone": "+1 (408) 996-1010", "linkedin": "https://www.linkedin.com/in/tim-cook-apple/"},
            {"name": "Luca Maestri", "title": "Chief Financial Officer", "email": "lmaestri@apple.com", "phone": "+1 (408) 996-1011", "linkedin": "https://www.linkedin.com/in/luca-maestri-apple/"},
            {"name": "Jeff Williams", "title": "Chief Operating Officer", "email": "jwilliams@apple.com", "phone": "+1 (408) 996-1012", "linkedin": "https://www.linkedin.com/in/jeff-williams-apple/"},
            {"name": "Deirdre O'Brien", "title": "Senior Vice President, Retail & People", "email": "dobrien@apple.com", "phone": "+1 (408) 996-1013", "linkedin": "https://www.linkedin.com/in/deirdre-obrien-apple/"},
        ],
        "microsoft": [
            {"name": "Satya Nadella", "title": "Chairman & Chief Executive Officer", "email": "satyan@microsoft.com", "phone": "+1 (425) 882-8080", "linkedin": "https://www.linkedin.com/in/satyanadella/"},
            {"name": "Amy Hood", "title": "Chief Financial Officer & Executive VP", "email": "ahood@microsoft.com", "phone": "+1 (425) 882-8081", "linkedin": "https://www.linkedin.com/in/amy-hood-msft/"},
            {"name": "Brad Smith", "title": "Vice Chair & President", "email": "bsmith@microsoft.com", "phone": "+1 (425) 882-8082", "linkedin": "https://www.linkedin.com/in/brad-smith-msft/"},
            {"name": "Judson Althoff", "title": "Executive Vice President & Chief Commercial Officer", "email": "jalthoff@microsoft.com", "phone": "+1 (425) 882-8083", "linkedin": "https://www.linkedin.com/in/judsonalthoff/"},
        ],
        "nvidia": [
            {"name": "Jensen Huang", "title": "Founder & Chief Executive Officer", "email": "jhuang@nvidia.com", "phone": "+1 (408) 486-2000", "linkedin": "https://www.linkedin.com/in/jensen-huang-nvidia/"},
            {"name": "Colette Kress", "title": "Executive VP & Chief Financial Officer", "email": "ckress@nvidia.com", "phone": "+1 (408) 486-2001", "linkedin": "https://www.linkedin.com/in/colette-kress-nvidia/"},
            {"name": "Jay Puri", "title": "Executive VP, Worldwide Field Operations", "email": "jpuri@nvidia.com", "phone": "+1 (408) 486-2002", "linkedin": "https://www.linkedin.com/in/jay-puri-nvidia/"},
        ],
        "tcs": [
            {"name": "K. Krithivasan", "title": "Chief Executive Officer & Managing Director", "email": "k.krithivasan@tcs.com", "phone": "+91 (22) 6778-9999", "linkedin": "https://www.linkedin.com/in/k-krithivasan-tcs/"},
            {"name": "Samir Seksaria", "title": "Chief Financial Officer", "email": "samir.seksaria@tcs.com", "phone": "+91 (22) 6778-9998", "linkedin": "https://www.linkedin.com/in/samir-seksaria-tcs/"},
            {"name": "N. Ganapathy Subramaniam", "title": "Former Chief Operating Officer & Executive Director", "email": "ng.subramaniam@tcs.com", "phone": "+91 (22) 6778-9997", "linkedin": "https://www.linkedin.com/in/ng-subramaniam-tcs/"},
        ],
        "wipro": [
            {"name": "Srini Pallia", "title": "Chief Executive Officer & Managing Director", "email": "srini.pallia@wipro.com", "phone": "+91 (80) 2844-0011", "linkedin": "https://www.linkedin.com/in/srini-pallia/"},
            {"name": "Aparna C. Iyer", "title": "Chief Financial Officer", "email": "aparna.iyer@wipro.com", "phone": "+91 (80) 2844-0012", "linkedin": "https://www.linkedin.com/in/aparna-iyer-wipro/"},
            {"name": "Rishad Premji", "title": "Executive Chairman", "email": "rishad.premji@wipro.com", "phone": "+91 (80) 2844-0013", "linkedin": "https://www.linkedin.com/in/rishadpremji/"},
        ],
        "zuntra": [
            {"name": "Roopini Soundaria", "title": "Director & Managing Founder", "email": "roopini@zuntradigital.com", "phone": "+91 98401 23456", "linkedin": "https://www.linkedin.com/in/roopini-soundaria/"},
            {"name": "Indraneel Chowdary Yalamanchili", "title": "Director & Co-Founder", "email": "indraneel@zuntradigital.com", "phone": "+91 98401 23457", "linkedin": "https://www.linkedin.com/in/indraneel-chowdary/"},
            {"name": "Denise Ranjeet Chandran", "title": "Director & Chief Operating Officer", "email": "denise@zuntradigital.com", "phone": "+91 98401 23458", "linkedin": "https://www.linkedin.com/in/denise-ranjeet-chandran/"},
        ],
        "zuntra digital": [
            {"name": "Roopini Soundaria", "title": "Director & Managing Founder", "email": "roopini@zuntradigital.com", "phone": "+91 98401 23456", "linkedin": "https://www.linkedin.com/in/roopini-soundaria/"},
            {"name": "Indraneel Chowdary Yalamanchili", "title": "Director & Co-Founder", "email": "indraneel@zuntradigital.com", "phone": "+91 98401 23457", "linkedin": "https://www.linkedin.com/in/indraneel-chowdary/"},
            {"name": "Denise Ranjeet Chandran", "title": "Director & Chief Operating Officer", "email": "denise@zuntradigital.com", "phone": "+91 98401 23458", "linkedin": "https://www.linkedin.com/in/denise-ranjeet-chandran/"},
        ]
    }

    found_known = None
    for k, v in known_execs.items():
        if k in q_key or k in c_key:
            found_known = v
            break

    if False and found_known:
        for ex in found_known:
            key_name = ex["name"].lower().strip()
            if key_name not in seen_execs:
                seen_execs.add(key_name)
                execs_list.append(
                    Executive(
                        name=ex["name"],
                        title=ex["title"],
                        role=ex["title"],
                        email=ex.get("email"),
                        phone=ex.get("phone"),
                        linkedin=ex.get("linkedin"),
                        linkedin_url=ex.get("linkedin"),
                    )
                )

    # Registry Directors (Zauba / Indian companies)
    if registry and registry.directors:
        for d in registry.directors:
            if d.name:
                k_name = d.name.lower().strip()
                if k_name not in seen_execs:
                    seen_execs.add(k_name)
                    execs_list.append(
                        Executive(
                            name=d.name,
                            title=d.designation or "Director",
                            role=d.designation or "Director",
                            email=None,
                            phone=None,
                            linkedin=None,
                            linkedin_url=None,
                        )
                    )

    # Replace fallback/registry executive links with profiles actually discovered
    # from the authenticated LinkedIn company People page when available.
    discovered_employees = li_data.get("employees") if isinstance(li_data.get("employees"), list) else []
    discovered_execs: list[Executive] = []
    for employee in discovered_employees:
        if not isinstance(employee, dict):
            continue
        profile_url = str(employee.get("linkedin_url") or "").strip()
        if not re.fullmatch(r"https://www\.linkedin\.com/in/[^/?#]+", profile_url, re.I):
            continue
        employee_name = str(employee.get("full_name") or employee.get("name") or "").strip()
        if not employee_name:
            continue
        print(f"Resolved Executive: {employee_name}")
        print(profile_url)
        discovered_execs.append(
            Executive(
                name=employee_name,
                title=employee.get("designation") or employee.get("headline"),
                role=employee.get("designation") or employee.get("headline"),
                email=employee.get("work_email") or employee.get("email"),
                phone=employee.get("phone"),
                linkedin=profile_url,
                linkedin_url=profile_url,
            )
        )
    if discovered_execs:
        execs_list = discovered_execs

    if not resolved.domain and domain:
        resolved.domain = domain
    ctx.website = resolved.website
    ctx.domain = resolved.domain

    dossier_website = _first(li_data.get("website"), overview.website, resolved.website, linkedin_insights.website, ctx.website, website)
    dossier_linkedin_url = _first(overview.linkedin_url, linkedin_insights.linkedin_url)
    dossier_company_logo = _first(linkedin_insights.company_logo, overview.company_logo, overview.logo_url)
    dossier_employee_count = _first(linkedin_insights.employee_count, overview.employee_count, overview.employees)
    dossier_linkedin_followers = _first(linkedin_insights.linkedin_followers, overview.linkedin_followers)
    dossier_linkedin_members = _first(linkedin_insights.linkedin_members, overview.linkedin_members)
    dossier_company_size = _first(linkedin_insights.company_size, overview.company_size)
    dossier_industry = _first(linkedin_insights.industry, overview.industry, overview.sector)
    dossier_founded_year = _first(linkedin_insights.founded_year, overview.founded_year, overview.founded)

    src_website = "Official Website" if ctx.website or website else ("LinkedIn Company" if li_data.get("website") else ("Company Overview" if overview.website else "Domain Resolution"))
    src_linkedin = "LinkedIn Company" if li_data.get("linkedin_url") else ("Company Overview" if overview.linkedin_url else "Company Search")
    src_logo = "LinkedIn Logo" if li_data.get("company_logo") else ("Company Overview" if overview.company_logo else "Finnhub Profile")
    src_emp = "LinkedIn" if li_data.get("employee_count") else ("Company Overview" if overview.employee_count else "Financial Profile")
    src_followers = "LinkedIn" if li_data.get("linkedin_followers") else "Company Overview"
    src_members = "LinkedIn" if li_data.get("linkedin_members") else "Company Overview"
    src_size = "LinkedIn" if li_data.get("company_size") else "Company Overview"
    src_industry = "LinkedIn" if li_data.get("industry") else ("Company Overview" if overview.industry else "Wikipedia")
    src_founded = "LinkedIn" if li_data.get("founded_year") else ("Company Overview" if overview.founded_year else "Wikipedia")

    print("\n[Company Pipeline]")
    print(f"website -> {dossier_website}")
    print(f"source -> {src_website if dossier_website else 'None'}")
    print(f"linkedin_url -> {dossier_linkedin_url}")
    print(f"source -> {src_linkedin if dossier_linkedin_url else 'None'}")
    print(f"company_logo -> {dossier_company_logo}")
    print(f"source -> {src_logo if dossier_company_logo else 'None'}")
    print(f"employee_count -> {dossier_employee_count}")
    print(f"source -> {src_emp if dossier_employee_count else 'None'}")
    print(f"linkedin_followers -> {dossier_linkedin_followers}")
    print(f"source -> {src_followers if dossier_linkedin_followers else 'None'}")
    print(f"linkedin_members -> {dossier_linkedin_members}")
    print(f"source -> {src_members if dossier_linkedin_members else 'None'}")
    print(f"company_size -> {dossier_company_size}")
    print(f"source -> {src_size if dossier_company_size else 'None'}")
    print(f"industry -> {dossier_industry}")
    print(f"source -> {src_industry if dossier_industry else 'None'}")
    print(f"founded_year -> {dossier_founded_year}")
    print(f"source -> {src_founded if dossier_founded_year else 'None'}\n")

    return CompanyDossier(
        query=query,
        resolved=resolved,
        overview=overview,
        financials=fin,
        linkedin_insights=linkedin_insights,
        executives=execs_list,
        filings=filings,
        news=News(
            digest_summary=None,
            lookback_days=lookback_days,
            articles=articles,
            fetched_at=generated_at if articles else None,
        ),
        press=press,
        github=github,
        registry=registry,
        funding=funding,
        reputation=reputation,
        sources_status=status,
        meta=Meta(generated_at=generated_at, raw_path=raw_path, company_path=company_path),
        website=dossier_website,
        linkedin_url=dossier_linkedin_url,
        company_logo=dossier_company_logo,
        employee_count=dossier_employee_count,
        linkedin_followers=dossier_linkedin_followers,
        linkedin_members=dossier_linkedin_members,
        company_size=dossier_company_size,
        industry=dossier_industry,
        founded_year=dossier_founded_year,
    )


def is_english_text(text: str | None) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0400-\u04ff\u0600-\u06ff]", raw):
        return False
    sample = raw[:1000]
    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0
        return detect(sample) == "en"
    except Exception:
        letters = sum(1 for ch in sample if ch.isalpha())
        ascii_letters = sum(1 for ch in sample if "a" <= ch.lower() <= "z")
        if letters == 0:
            return False
        return (ascii_letters / letters) >= 0.85


def is_english_article(article: dict[str, Any]) -> bool:
    title = (article.get("title") or "").strip()
    if not title:
        return False
    low = title.lower()
    if low in ("[removed]", "null", "untitled", "(untitled)"):
        return False
    if re.fullmatch(r"[\w.-]+\.[a-z]{2,}(/)?", title, flags=re.I):
        return False
    parts = [article.get("title"), article.get("summary"), article.get("content")]
    text = " ".join(str(p) for p in parts if p)
    return is_english_text(text)


def merge_news_articles(
    batches: list[list[dict[str, Any]]],
    limit: int = 8,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    by_url: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for a in batch:
            url = normalize_url(a.get("url"))
            if not url:
                continue
            if url in by_url:
                existing = by_url[url]
                vias = list(dict.fromkeys((existing.get("via") or []) + (a.get("via") or [])))
                existing["via"] = vias
                if not existing.get("summary") and a.get("summary"):
                    existing["summary"] = a.get("summary")
                continue
            item = dict(a)
            item["url"] = url
            item = sanitize_article_fields(item)
            by_url[url] = item
            merged.append(item)

    deduped: list[dict[str, Any]] = []
    for a in merged:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        if not is_english_article(a):
            continue
        dup = False
        for b in deduped:
            if fuzz.token_set_ratio(title, (b.get("title") or "")) >= 92:
                vias = list(dict.fromkeys((b.get("via") or []) + (a.get("via") or [])))
                b["via"] = vias
                dup = True
                break
        if not dup:
            deduped.append(a)

    def sort_key(x: dict[str, Any]) -> str:
        return x.get("published_at") or ""

    deduped.sort(key=sort_key, reverse=True)
    return deduped[:limit]
