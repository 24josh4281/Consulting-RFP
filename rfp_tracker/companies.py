from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .fetchers import parse_links


KRX_LISTED_COMPANIES_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
PORTAL_TERMS = [
    "입찰",
    "구매",
    "조달",
    "협력",
    "협력사",
    "전자구매",
    "공급망",
    "supplier",
    "procurement",
    "purchase",
    "bidding",
    "bid",
    "partner",
    "vendor",
]


@dataclass(slots=True)
class Company:
    name: str
    ticker: str = ""
    market: str = ""
    industry: str = ""
    main_product: str = ""
    listing_date: str = ""
    fiscal_month: str = ""
    ceo: str = ""
    homepage: str = ""
    region: str = ""
    asset_total_krw: str = ""
    asset_source: str = ""


@dataclass(slots=True)
class PortalCandidate:
    company_name: str
    ticker: str
    homepage: str
    candidate_url: str
    label: str
    reason: str
    status: str


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            value = " ".join(part.strip() for part in self._cell if part.strip())
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(cell.strip() for cell in self._row):
                self.rows.append(self._row)
            self._row = None


def normalize_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        return "https:" + value
    parsed = urlparse(value)
    if parsed.scheme:
        return value
    if value.startswith("www."):
        return "https://" + value
    return value


def fetch_krx_listed_companies(timeout: int = 30) -> list[Company]:
    request = Request(KRX_LISTED_COMPANIES_URL, headers={"User-Agent": "ClimateRfpTracker/0.1"})
    with urlopen(request, timeout=timeout) as response:
        html = response.read().decode("euc-kr", errors="replace")

    parser = TableParser()
    parser.feed(html)
    if not parser.rows:
        return []

    header = [cell.strip() for cell in parser.rows[0]]
    companies: list[Company] = []
    for row in parser.rows[1:]:
        record = {header[i]: row[i].strip() for i in range(min(len(header), len(row)))}
        name = record.get("회사명", "")
        if not name:
            continue
        ticker = record.get("종목코드", "")
        if ticker.isdigit():
            ticker = ticker.zfill(6)
        companies.append(
            Company(
                name=name,
                ticker=ticker,
                market=record.get("시장구분", ""),
                industry=record.get("업종", ""),
                main_product=record.get("주요제품", ""),
                listing_date=record.get("상장일", ""),
                fiscal_month=record.get("결산월", ""),
                ceo=record.get("대표자명", ""),
                homepage=normalize_url(record.get("홈페이지", "")),
                region=record.get("지역", ""),
                asset_source="KRX company list; asset filter requires OpenDART or KIND financial data validation",
            )
        )
    return companies


def write_companies_csv(companies: Iterable[Company], path: str | Path) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "name",
        "ticker",
        "market",
        "industry",
        "main_product",
        "listing_date",
        "fiscal_month",
        "ceo",
        "homepage",
        "region",
        "asset_total_krw",
        "asset_source",
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for company in companies:
            writer.writerow({field: getattr(company, field) for field in fieldnames})


def read_companies_csv(path: str | Path) -> list[Company]:
    in_path = Path(path)
    with in_path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = csv.DictReader(file)
        return [Company(**{field: row.get(field, "") for field in Company.__dataclass_fields__}) for row in rows]


def generate_homepage_sources(companies: Iterable[Company], out_path: str | Path, limit: int | None = None) -> None:
    sources = []
    count = 0
    for company in companies:
        if not company.homepage:
            continue
        sources.append(
            {
                "id": f"company_homepage_{company.ticker or count + 1}",
                "name": f"{company.name} 홈페이지 후보",
                "type": "generic_html",
                "enabled": False,
                "url": company.homepage,
                "company_name": company.name,
                "ticker": company.ticker,
                "source_scope": "company_homepage_candidate",
                "notes": "공개 홈페이지 후보입니다. 실제 입찰/구매 포털 여부는 portal discovery 결과 확인 후 활성화하세요.",
            }
        )
        count += 1
        if limit is not None and count >= limit:
            break

    out = {
        "global": {
            "request_timeout_seconds": 20,
            "user_agent": "ClimateRfpTracker/0.1 (+company portal discovery)",
            "max_pages": 1,
        },
        "sources": sources,
    }
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_public_html(url: str, timeout: int = 15) -> tuple[str, str]:
    request = Request(url, headers={"User-Agent": "ClimateRfpTracker/0.1"})
    with urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        charset = response.headers.get_content_charset() or "utf-8"
        html = response.read().decode(charset, errors="replace")
    return final_url, html


def discover_company_portals(companies: Iterable[Company], limit: int = 20, timeout: int = 15) -> list[PortalCandidate]:
    candidates: list[PortalCandidate] = []
    checked = 0
    for company in companies:
        if not company.homepage:
            continue
        if checked >= limit:
            break
        checked += 1
        try:
            final_url, html = fetch_public_html(company.homepage, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - discovery report should keep moving.
            candidates.append(
                PortalCandidate(
                    company_name=company.name,
                    ticker=company.ticker,
                    homepage=company.homepage,
                    candidate_url=company.homepage,
                    label="",
                    reason=f"homepage_check_failed: {exc}",
                    status="failed",
                )
            )
            continue

        links = parse_links(html, final_url)
        hit_count = 0
        for link in links:
            label = link["text"] or link["url"]
            haystack = f"{label} {link['url']}".lower()
            matched_terms = [term for term in PORTAL_TERMS if term.lower() in haystack]
            if not matched_terms:
                continue
            candidates.append(
                PortalCandidate(
                    company_name=company.name,
                    ticker=company.ticker,
                    homepage=company.homepage,
                    candidate_url=urljoin(final_url, link["url"]),
                    label=label,
                    reason=", ".join(matched_terms),
                    status="candidate",
                )
            )
            hit_count += 1
            if hit_count >= 5:
                break
        if hit_count == 0:
            candidates.append(
                PortalCandidate(
                    company_name=company.name,
                    ticker=company.ticker,
                    homepage=company.homepage,
                    candidate_url=final_url,
                    label="",
                    reason="no procurement-like link found on homepage",
                    status="no_candidate",
                )
            )
    return candidates


def write_portal_candidates_csv(candidates: Iterable[PortalCandidate], path: str | Path) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "company_name",
        "ticker",
        "homepage",
        "candidate_url",
        "label",
        "reason",
        "status",
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow({field: getattr(candidate, field) for field in fieldnames})
