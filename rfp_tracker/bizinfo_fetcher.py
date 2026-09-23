from __future__ import annotations

"""Official Bizinfo support-call API reader (disabled until own key/rights are ready).

Design Ref: innergen-source-expansion §4 — use the documented Bizinfo endpoint,
not the unrelated G2B service key. Never retain the credential or API response.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

from .fetchers import BaseFetcher, fetch_text
from .grant_fetchers import DATE_RE, _keep_notice, _normal_date, is_customer_portfolio_grant
from .models import Notice


SEOUL = ZoneInfo("Asia/Seoul")
OFFICIAL_ENDPOINT = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"


def _official_detail_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not (host == "bizinfo.go.kr" or host.endswith(".bizinfo.go.kr")):
        return ""
    return url


def bizinfo_application_window(value: object) -> tuple[str, str]:
    """Return date-only evidence from a two-date official application range."""
    text = str(value or "")
    dates = [_normal_date(match.group(0)) for match in DATE_RE.finditer(text)]
    if len(dates) < 2:
        dates = []
        for compact in re.findall(r"(?<!\d)20\d{6}(?!\d)", text):
            try:
                dates.append(datetime.strptime(compact, "%Y%m%d").strftime("%Y-%m-%d"))
            except ValueError:
                return "", ""
    if len(dates) < 2 or not dates[0] or not dates[1] or dates[0] > dates[1]:
        return "", ""
    return dates[0], dates[1]


def parse_bizinfo_items(payload: object, source: dict[str, Any], days: int, now: datetime) -> list[Notice]:
    if not isinstance(payload, dict):
        raise ValueError("기업마당 API 응답 형식 오류")
    body = payload.get("jsonArray")
    if not isinstance(body, dict):
        raise ValueError("기업마당 API 권한 또는 응답 형식 확인 필요")
    items = body.get("item", [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise ValueError("기업마당 API 공고 목록 형식 오류")
    notices: list[Notice] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("pblancNm") or item.get("title") or "").strip()
        external_id = str(item.get("pblancId") or item.get("seq") or "").strip()
        url = _official_detail_url(item.get("pblancUrl") or item.get("link"))
        if not (external_id and url and is_customer_portfolio_grant(title)):
            continue
        published_at = _normal_date(str(item.get("creatPnttm") or item.get("pubDate") or ""))
        start_at, deadline_at = bizinfo_application_window(item.get("reqstBeginEndDe") or item.get("reqstDt"))
        if not _keep_notice(published_at, deadline_at, days, now):
            continue
        if published_at and deadline_at and deadline_at < published_at:
            continue
        notices.append(Notice(
            source_id=str(source["id"]), source_name=str(source["name"]),
            external_id=external_id, title=title, url=url,
            published_at=published_at, deadline_at=deadline_at,
            buyer=str(item.get("excInsttNm") or item.get("jrsdInsttNm") or item.get("author") or ""),
            procurement_method="고객사 지원사업 신청", category="grant_application",
            relevance_score=8,
            matched_keywords=[term for term in ("온실가스", "배출권", "탄소중립", "CBAM", "국제감축") if term.casefold() in title.casefold()],
            raw={
                "source_type": "bizinfo_grant_api",
                "source_url": "https://bizinfo.go.kr/apiDetail.do?id=bizinfoApi",
                "application_start_at": start_at,
                "fetched_at": now.isoformat(timespec="seconds"),
            },
        ))
    return notices


class BizinfoGrantApiFetcher(BaseFetcher):
    def __init__(self, source: dict[str, Any], keyword_config: dict[str, Any], global_config: dict[str, Any], root_dir: Path) -> None:
        super().__init__(source, keyword_config, global_config, root_dir)
        if source.get("endpoint") != OFFICIAL_ENDPOINT:
            raise ValueError("허용되지 않은 기업마당 API 주소")

    def fetch(self, days: int) -> list[Notice]:
        key = os.getenv(str(self.source.get("service_key_env") or "BIZINFO_API_KEY"), "").strip()
        if not key:
            raise ValueError("기업마당 전용 API 키가 설정되지 않음")
        timeout = int(self.global_config.get("request_timeout_seconds", 20))
        agent = str(self.global_config.get("user_agent") or "ClimateRfpTracker/0.1")
        page_size = min(100, max(1, int(self.source.get("page_size", 100))))
        max_pages = min(3, max(1, int(self.source.get("max_pages", 2))))
        now = datetime.now(SEOUL)
        unique: dict[str, Notice] = {}
        for page_index in range(1, max_pages + 1):
            query = urlencode({
                "crtfcKey": key, "dataType": "json", "searchCnt": page_size * max_pages,
                "pageUnit": page_size, "pageIndex": page_index,
            })
            try:
                response = fetch_text(OFFICIAL_ENDPOINT + "?" + query, timeout, agent)
                payload = json.loads(response)
            except Exception as exc:
                # The request URL includes a credential; never expose its exception text.
                raise RuntimeError(f"기업마당 API 요청 또는 JSON 해석 실패 ({type(exc).__name__})") from None
            parsed = parse_bizinfo_items(payload, self.source, days, now)
            for notice in parsed:
                unique[notice.external_id] = notice
            body = payload.get("jsonArray") if isinstance(payload, dict) else None
            raw_items = body.get("item", []) if isinstance(body, dict) else []
            if not isinstance(raw_items, (list, dict)):
                raise ValueError("기업마당 API 공고 목록 형식 오류")
            if isinstance(raw_items, dict) or len(raw_items) < page_size:
                break
        return list(unique.values())
