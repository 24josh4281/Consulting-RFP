from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from rfp_tracker.config import load_dotenv, read_json  # noqa: E402
from rfp_tracker.keyword_matcher import assess_g2b_title, excluded_terms  # noqa: E402


BID_PUBLIC_ENDPOINT = (
    "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/"
    "getBidPblancListInfoServcPPSSrch"
)
CONTRACT_PROCESS_ENDPOINT = (
    "https://apis.data.go.kr/1230000/ao/CntrctProcssIntgOpenService/"
    "getCntrctProcssIntgOpenServc"
)
PROCUREMENT_REQUEST_ENDPOINT = (
    "https://apis.data.go.kr/1230000/ao/PrcrmntReqInfoService/"
    "getPrcrmntReqInfoListGnrlServc"
)
PROCUREMENT_REQUEST_TECH_ENDPOINT = (
    "https://apis.data.go.kr/1230000/ao/PrcrmntReqInfoService/"
    "getPrcrmntReqInfoListTechServc"
)
OPENING_COMPANY_ENDPOINT = (
    "https://apis.data.go.kr/1230000/as/ScsbidInfoService/"
    "getOpengResultListInfoOpengCompt"
)

DEFAULT_SEARCH_TERMS = (
    "기후",
    "탄소",
    "온실가스",
    "배출권",
    "외부사업",
    "외부 사업",
    "감축",
    "상쇄",
    "ETS",
)

NOTICE_FIELDS = (
    "record_id",
    "bid_notice_no",
    "bid_notice_order",
    "notice_title",
    "notice_date",
    "notice_year",
    "notice_kind",
    "rebid_yn",
    "notice_agency",
    "demand_agency",
    "bid_method",
    "contract_method",
    "award_method",
    "service_type",
    "budget_amount_krw",
    "estimated_price_krw",
    "vat_amount_krw",
    "bid_start",
    "bid_close",
    "opening_date",
    "participant_limit_yn",
    "joint_contract_method",
    "order_plan_unified_no",
    "pre_spec_registration_no",
    "procurement_request_no",
    "search_terms",
    "categories",
    "relevance_status",
    "relevance_reason",
    "tracker_tier",
    "tracker_score",
    "matched_keywords",
    "winner_count",
    "participant_count",
    "winner_company",
    "winner_business_no",
    "award_amount_krw",
    "award_rate_pct",
    "contract_count",
    "contract_amount_krw",
    "contract_date",
    "procurement_request_name",
    "procurement_request_budget_amount_krw",
    "procurement_request_representative_amount_krw",
    "procurement_request_total_service_budget_amount_krw",
    "procurement_request_current_budget_amount_krw",
    "procurement_request_order_agency",
    "procurement_request_input_date",
    "participant_data_status",
    "award_data_status",
    "contract_data_status",
    "procurement_request_data_status",
    "notice_url",
    "source_dataset",
    "source_url",
)

AWARD_FIELDS = (
    "record_id",
    "bid_notice_no",
    "bid_notice_order",
    "contract_process_item_index",
    "winner_sequence",
    "winner_company",
    "winner_business_no",
    "winner_ceo",
    "award_amount_krw",
    "award_rate_pct",
    "participant_count",
    "opening_date",
    "parse_status",
    "raw_entry",
    "bidwinr_info_list_raw",
    "exact_order_match_yn",
    "link_status",
    "source_dataset",
    "source_url",
)

CONTRACT_FIELDS = (
    "record_id",
    "bid_notice_no",
    "bid_notice_order",
    "contract_process_item_index",
    "contract_sequence",
    "contract_no",
    "contract_name",
    "contract_agency",
    "contract_demand_agency",
    "contract_method",
    "contract_amount_krw",
    "contract_date",
    "parse_status",
    "raw_entry",
    "contract_info_list_raw",
    "exact_order_match_yn",
    "link_status",
    "source_dataset",
    "source_url",
)

PROCUREMENT_REQUEST_FIELDS = (
    "procurement_request_no",
    "linked_record_ids",
    "linked_bid_notice_nos",
    "linked_bid_notice_orders",
    "service_type",
    "request_name",
    "budget_amount_krw",
    "representative_amount_krw",
    "total_service_budget_amount_krw",
    "current_budget_amount_krw",
    "order_agency",
    "input_date",
    "request_data_status",
    "source_operation",
    "source_dataset",
    "source_url",
)

BIDWINNER_LIST_FIELDS = (
    "winner_sequence",
    "winner_company",
    "winner_business_no",
    "winner_ceo",
    "award_amount_krw",
    "award_rate_pct",
    "participant_count",
    "opening_date",
)

CONTRACT_LIST_FIELDS = (
    "contract_sequence",
    "contract_no",
    "contract_name",
    "contract_agency",
    "contract_demand_agency",
    "contract_method",
    "contract_amount_krw",
    "contract_date",
)

CONTRACT_SERVICE_GROUP = "contract_process"
PROCUREMENT_REQUEST_SERVICE_GROUP = "procurement_request"
KST = timezone(timedelta(hours=9))

BIDDER_FIELDS = (
    "record_id",
    "bid_notice_no",
    "bid_notice_order",
    "bid_classification_no",
    "rebid_no",
    "opening_rank",
    "participant_company",
    "participant_business_no",
    "participant_ceo",
    "bid_amount_krw",
    "bid_rate_pct",
    "bid_date",
    "final_winner_yn",
    "source_dataset",
    "source_url",
)

ACCESS_FIELDS = (
    "service_id",
    "service_name",
    "dataset_url",
    "operation",
    "purpose",
    "access_status",
    "error_code",
    "message",
    "checked_at",
    "next_action",
)


class RequestBudgetExceeded(RuntimeError):
    pass


class DailyRequestBudgetExceeded(RequestBudgetExceeded):
    def __init__(self, service_group: str, cap: int) -> None:
        self.service_group = service_group
        self.cap = cap
        super().__init__(
            f"KST daily request limit reached for {service_group} ({cap})"
        )


class CollectionStopped(RuntimeError):
    pass


@dataclass(slots=True)
class ApiResult:
    ok: bool
    result_code: str
    result_message: str
    body: dict[str, Any]
    raw_text: str
    cached: bool = False


@dataclass(slots=True)
class MonthWindow:
    start: datetime
    end: datetime

    @property
    def api_start(self) -> str:
        return self.start.strftime("%Y%m%d%H%M")

    @property
    def api_end(self) -> str:
        return self.end.strftime("%Y%m%d%H%M")

    @property
    def label(self) -> str:
        return f"{self.start:%Y-%m-%d}~{self.end:%Y-%m-%d}"


@dataclass(slots=True)
class EnrichmentOutcome:
    awards: list[dict[str, Any]]
    contracts: list[dict[str, Any]]
    procurement_requests: list[dict[str, Any]]
    summaries: dict[str, dict[str, Any]]
    contract_complete: bool
    procurement_request_complete: bool
    contract_lookups: int
    contract_live_requests: int
    procurement_request_lookups: int
    procurement_request_live_requests: int
    warnings: list[str]


def parse_iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("날짜는 YYYY-MM-DD 형식이어야 합니다.") from exc


def month_windows(start_date: date, end_date: date) -> list[MonthWindow]:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    windows: list[MonthWindow] = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        window_end = min(end_date, next_month - timedelta(days=1))
        windows.append(
            MonthWindow(
                datetime.combine(cursor, datetime.min.time()),
                datetime.combine(window_end, datetime.max.time()).replace(second=0, microsecond=0),
            )
        )
        cursor = next_month
    return windows


def normalize_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    items: Any = body.get("items", [])
    if isinstance(items, dict) and "item" in items:
        items = items.get("item", [])
    if not items:
        return []
    if isinstance(items, dict):
        return [items]
    return [item for item in items if isinstance(item, dict)]


def parse_error_payload(raw_text: str) -> tuple[str, str]:
    text = (raw_text or "").strip()
    if not text:
        return "HTTP_ERROR", "응답 본문이 없습니다."

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return "HTTP_ERROR", text[:300]
        values = {node.tag.split("}")[-1]: (node.text or "").strip() for node in root.iter()}
        return (
            values.get("errMsg") or values.get("resultCode") or values.get("returnReasonCode") or "HTTP_ERROR",
            values.get("returnAuthMsg") or values.get("resultMsg") or values.get("errMsg") or "API 호출 오류",
        )

    if "OpenAPI_ServiceResponse" in payload:
        header = payload["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
        return (
            str(header.get("errMsg") or header.get("returnReasonCode") or "OPENAPI_ERROR"),
            str(header.get("returnAuthMsg") or header.get("errMsg") or "API 호출 오류"),
        )
    if "nkoneps.com.response.ResponseError" in payload:
        header = payload["nkoneps.com.response.ResponseError"].get("header", {})
        return str(header.get("resultCode") or "OPENAPI_ERROR"), str(
            header.get("resultMsg") or "API 호출 오류"
        )
    root = payload.get("response", payload)
    header = root.get("header", {}) if isinstance(root, dict) else {}
    return str(header.get("resultCode") or "OPENAPI_ERROR"), str(
        header.get("resultMsg") or "API 호출 오류"
    )


class ApiCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS api_cache (
                query_key TEXT PRIMARY KEY,
                endpoint TEXT NOT NULL,
                params_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                result_code TEXT NOT NULL,
                result_message TEXT NOT NULL,
                total_count INTEGER,
                response_text TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS api_daily_usage (
                usage_date_kst TEXT NOT NULL,
                service_group TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (usage_date_kst, service_group)
            )
            """
        )
        self.connection.commit()

    @staticmethod
    def query_key(endpoint: str, params: dict[str, str]) -> str:
        safe_params = {key: value for key, value in params.items() if key != "serviceKey"}
        stable = json.dumps(
            {"endpoint": endpoint, "params": safe_params},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()

    def get(self, endpoint: str, params: dict[str, str]) -> ApiResult | None:
        row = self.connection.execute(
            "SELECT * FROM api_cache WHERE query_key = ?",
            (self.query_key(endpoint, params),),
        ).fetchone()
        if not row:
            return None
        raw_text = str(row["response_text"])
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return None
        root = payload.get("response", payload)
        body = root.get("body", {}) if isinstance(root, dict) else {}
        return ApiResult(
            ok=True,
            result_code=str(row["result_code"]),
            result_message=str(row["result_message"]),
            body=body if isinstance(body, dict) else {},
            raw_text=raw_text,
            cached=True,
        )

    def contains(self, endpoint: str, params: dict[str, str]) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM api_cache WHERE query_key = ?",
            (self.query_key(endpoint, params),),
        ).fetchone()
        return row is not None

    @staticmethod
    def kst_date() -> str:
        return datetime.now(KST).date().isoformat()

    def daily_attempts(self, service_group: str) -> int:
        row = self.connection.execute(
            """
            SELECT attempt_count
            FROM api_daily_usage
            WHERE usage_date_kst = ? AND service_group = ?
            """,
            (self.kst_date(), service_group),
        ).fetchone()
        return int(row["attempt_count"]) if row else 0

    def reserve_daily_attempt(self, service_group: str, cap: int) -> bool:
        """Atomically reserve one real HTTP attempt under a KST daily cap."""

        usage_date = self.kst_date()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute(
                """
                SELECT attempt_count
                FROM api_daily_usage
                WHERE usage_date_kst = ? AND service_group = ?
                """,
                (usage_date, service_group),
            ).fetchone()
            current = int(row["attempt_count"]) if row else 0
            if current >= cap:
                self.connection.rollback()
                return False
            self.connection.execute(
                """
                INSERT INTO api_daily_usage (
                    usage_date_kst, service_group, attempt_count, updated_at
                ) VALUES (?, ?, 1, ?)
                ON CONFLICT(usage_date_kst, service_group) DO UPDATE SET
                    attempt_count = attempt_count + 1,
                    updated_at = excluded.updated_at
                """,
                (
                    usage_date,
                    service_group,
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                ),
            )
            self.connection.commit()
            return True
        except Exception:
            self.connection.rollback()
            raise

    def put(self, endpoint: str, params: dict[str, str], result: ApiResult) -> None:
        if not result.ok:
            return
        total_count = to_int(result.body.get("totalCount"))
        safe_params = {key: value for key, value in params.items() if key != "serviceKey"}
        self.connection.execute(
            """
            INSERT OR REPLACE INTO api_cache (
                query_key, endpoint, params_json, fetched_at, result_code,
                result_message, total_count, response_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.query_key(endpoint, params),
                endpoint,
                json.dumps(safe_params, ensure_ascii=False, sort_keys=True),
                datetime.now().astimezone().isoformat(timespec="seconds"),
                result.result_code,
                result.result_message,
                total_count,
                result.raw_text,
            ),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


class G2BClient:
    def __init__(
        self,
        service_key: str,
        cache: ApiCache,
        *,
        delay_seconds: float = 0.15,
        max_live_requests: int = 800,
        refresh: bool = False,
        daily_group_caps: dict[str, int] | None = None,
    ) -> None:
        self.service_key = service_key
        self.cache = cache
        self.delay_seconds = max(0.0, delay_seconds)
        self.max_live_requests = max_live_requests
        self.refresh = refresh
        self.daily_group_caps = dict(daily_group_caps or {})
        self.live_requests = 0
        self.cache_hits = 0
        self.live_requests_by_endpoint: dict[str, int] = {}

    def is_cached(self, endpoint: str, params: dict[str, str]) -> bool:
        if self.refresh:
            return False
        return self.cache.contains(endpoint, {**params, "serviceKey": self.service_key})

    @staticmethod
    def service_group(endpoint: str) -> str:
        if endpoint == CONTRACT_PROCESS_ENDPOINT:
            return CONTRACT_SERVICE_GROUP
        if endpoint in {PROCUREMENT_REQUEST_ENDPOINT, PROCUREMENT_REQUEST_TECH_ENDPOINT}:
            return PROCUREMENT_REQUEST_SERVICE_GROUP
        return ""

    def daily_attempts(self, service_group: str) -> int:
        return self.cache.daily_attempts(service_group)

    def get(
        self,
        endpoint: str,
        params: dict[str, str],
        *,
        use_cache: bool = True,
        live_request_budget: int | None = None,
    ) -> ApiResult:
        params = {**params, "serviceKey": self.service_key}
        if use_cache and not self.refresh:
            cached = self.cache.get(endpoint, params)
            if cached is not None:
                self.cache_hits += 1
                return cached

        last_result: ApiResult | None = None
        additional_live_requests = 0
        for attempt in range(1, 4):
            if self.live_requests >= self.max_live_requests:
                raise RequestBudgetExceeded(
                    f"live request limit reached ({self.max_live_requests})"
                )
            if (
                live_request_budget is not None
                and additional_live_requests >= live_request_budget
            ):
                raise RequestBudgetExceeded(
                    f"endpoint live request limit reached ({live_request_budget})"
                )
            service_group = self.service_group(endpoint)
            daily_cap = self.daily_group_caps.get(service_group)
            if (
                service_group
                and daily_cap is not None
                and not self.cache.reserve_daily_attempt(service_group, daily_cap)
            ):
                raise DailyRequestBudgetExceeded(service_group, daily_cap)
            self.live_requests += 1
            additional_live_requests += 1
            self.live_requests_by_endpoint[endpoint] = (
                self.live_requests_by_endpoint.get(endpoint, 0) + 1
            )
            last_result = self._request(endpoint, params)
            if last_result.ok:
                if use_cache:
                    self.cache.put(endpoint, params, last_result)
                if self.delay_seconds:
                    time.sleep(self.delay_seconds)
                return last_result
            if last_result.result_code not in {"23", "HTTP_ERROR", "SERVICETIMEOUT_ERROR", "05"}:
                return last_result
            if attempt < 3:
                time.sleep(attempt * 1.5)
        assert last_result is not None
        return last_result

    def _request(self, endpoint: str, params: dict[str, str]) -> ApiResult:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{endpoint}?{query}",
            headers={"User-Agent": "ClimateRfpHistory/1.0 (+local ESG consulting workflow)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw_text = response.read().decode("utf-8-sig", errors="replace")
        except urllib.error.HTTPError as exc:
            raw_text = exc.read().decode("utf-8-sig", errors="replace")
            code, message = parse_error_payload(raw_text)
            return ApiResult(False, code, message, {}, raw_text)
        except (urllib.error.URLError, TimeoutError) as exc:
            return ApiResult(False, "HTTP_ERROR", str(exc.reason if hasattr(exc, "reason") else exc), {}, "")

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            code, message = parse_error_payload(raw_text)
            return ApiResult(False, code, message, {}, raw_text)

        if "OpenAPI_ServiceResponse" in payload or "nkoneps.com.response.ResponseError" in payload:
            code, message = parse_error_payload(raw_text)
            return ApiResult(False, code, message, {}, raw_text)

        root = payload.get("response", payload)
        if not isinstance(root, dict):
            return ApiResult(False, "INVALID_RESPONSE", "응답 구조를 해석할 수 없습니다.", {}, raw_text)
        header = root.get("header", {})
        result_code = str(header.get("resultCode") or "")
        result_message = str(header.get("resultMsg") or "")
        if result_code not in {"", "00", "0"}:
            return ApiResult(False, result_code, result_message or "API 호출 오류", {}, raw_text)
        body = root.get("body", {})
        return ApiResult(
            True,
            result_code or "00",
            result_message or "정상",
            body if isinstance(body, dict) else {},
            raw_text,
        )


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed != parsed.to_integral_value():
        return None
    return int(parsed)


def int_or_blank(value: Any) -> int | str:
    """Preserve a real zero while keeping missing/non-numeric source values blank."""
    parsed = to_int(value)
    return "" if parsed is None else parsed


def decimal_or_blank(value: Any) -> float | str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text == "-":
        return ""
    try:
        return float(text.replace(",", "").replace("%", ""))
    except ValueError:
        return ""


def source_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def source_value(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text == "-" else text


def parse_caret_list(value: Any, field_names: tuple[str, ...]) -> list[dict[str, Any]]:
    """Parse the documented ``[a^b^...] , [a^b^...]`` list without guessing.

    Each returned record retains its exact bracket entry.  Only records with the
    documented field count are marked ``정상``; malformed records stay visible
    for manual review instead of being silently shifted or discarded.
    """

    raw = source_text(value)
    if not raw or raw in {"-", "[]"}:
        return []
    if not (raw.startswith("[") and raw.endswith("]")):
        return [
            {
                **{field: "" for field in field_names},
                "parse_status": "형식불일치—대괄호 목록 아님",
                "raw_entry": raw,
                "field_count": 0,
            }
        ]

    inner = raw[1:-1]
    chunks = re.split(r"\]\s*,\s*\[", inner)
    records: list[dict[str, Any]] = []
    for chunk in chunks:
        parts = chunk.split("^")
        status = "정상" if len(parts) == len(field_names) else (
            f"필드수불일치—예상 {len(field_names)}, 실제 {len(parts)}"
        )
        record = {field: "" for field in field_names}
        if len(parts) == len(field_names):
            record.update(
                {field: source_value(part) for field, part in zip(field_names, parts)}
            )
        record.update(
            {
                "parse_status": status,
                "raw_entry": f"[{chunk}]",
                "field_count": len(parts),
            }
        )
        records.append(record)
    return records


def token_hit(title: str, term: str) -> bool:
    normalized = re.sub(r"\s+", " ", title or "").strip().lower()
    term_normalized = re.sub(r"\s+", " ", term or "").strip().lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9 .-]*", term_normalized):
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(term_normalized)}(?![a-z0-9])",
                normalized,
            )
        )
    return term_normalized in normalized


def classify_title(title: str, keyword_config: dict[str, Any]) -> dict[str, Any]:
    category_terms = {
        "기후변화": (
            "기후변화",
            "기후위기",
            "기후리스크",
            "기후위험",
            "기후적응",
            "기후 적응",
            "기후 시나리오",
            "기후",
        ),
        "온실가스": ("온실가스", "ghg"),
        "배출권거래제": ("배출권거래제", "배출권", "k-ets", "ets"),
        "외부사업": ("외부사업", "외부 사업", "감축실적", "상쇄"),
        "탄소중립·감축": (
            "탄소중립",
            "넷제로",
            "net zero",
            "저탄소",
            "탈탄소",
            "탄소배출",
            "탄소 감축",
            "탄소감축",
            "탄소저감",
            "탄소 발자국",
            "탄소발자국",
            "탄소",
            "감축",
        ),
    }
    categories: list[str] = []
    hits: list[str] = []
    for category, terms in category_terms.items():
        matched = [term for term in terms if token_hit(title, term)]
        if matched:
            categories.append(category)
            hits.extend(matched)

    specific_terms = (
        "기후변화",
        "기후위기",
        "기후리스크",
        "기후적응",
        "온실가스",
        "ghg",
        "배출권",
        "k-ets",
        "탄소중립",
        "넷제로",
        "net zero",
        "저탄소",
        "탈탄소",
        "탄소배출",
        "탄소감축",
        "탄소 감축",
        "탄소저감",
        "탄소발자국",
        "탄소 발자국",
        "감축실적",
    )
    specific_hits = [term for term in specific_terms if token_hit(title, term)]
    exclusions = excluded_terms(title, keyword_config)
    tracker = assess_g2b_title(title, keyword_config)

    if specific_hits:
        status = "핵심"
        reason = "구체적인 기후·온실가스·배출권·탄소중립 용어가 공고명에 있습니다."
    elif categories and not exclusions:
        status = "검토필요"
        reason = "관련 가능성이 있으나 공고명만으로 기후·배출권 업무인지 확정하기 어렵습니다."
    elif categories:
        status = "검토필요"
        reason = "관련 용어와 제외 후보 용어가 함께 있어 원문 확인이 필요합니다."
    else:
        status = "제외권고"
        reason = "검색어에는 잡혔지만 기후·온실가스·배출권 맥락을 확인하지 못했습니다."

    return {
        "categories": sorted(set(categories)),
        "hits": sorted(set(hits)),
        "specific_hits": sorted(set(specific_hits)),
        "exclusions": exclusions,
        "relevance_status": status,
        "relevance_reason": reason,
        "tracker_tier": tracker.tier,
        "tracker_score": tracker.match.score,
        "tracker_keywords": tracker.match.keywords,
    }


def notice_identity(item: dict[str, Any]) -> str:
    bid_no = str(item.get("bidNtceNo") or "").strip()
    bid_order = str(item.get("bidNtceOrd") or "").strip()
    return f"{bid_no}-{bid_order}" if bid_order else bid_no


def canonical_notice_order(value: Any) -> str:
    """Canonicalize numeric order padding solely for joins (e.g. 00 == 000)."""

    text = source_value(value)
    if re.fullmatch(r"\d+", text):
        return str(int(text))
    return text


def merge_notice(
    notices: dict[str, dict[str, Any]],
    item: dict[str, Any],
    search_term: str,
) -> None:
    identity = notice_identity(item)
    if not identity:
        return
    existing = notices.get(identity)
    if existing is None:
        notices[identity] = {"item": item, "search_terms": {search_term}}
        return
    existing["search_terms"].add(search_term)
    existing_item = existing["item"]
    if str(item.get("chgDt") or item.get("rgstDt") or "") > str(
        existing_item.get("chgDt") or existing_item.get("rgstDt") or ""
    ):
        existing["item"] = item


def collect_notices(
    client: G2BClient,
    windows: Iterable[MonthWindow],
    search_terms: Iterable[str],
) -> tuple[dict[str, dict[str, Any]], bool, list[str]]:
    windows = list(windows)
    search_terms = list(search_terms)
    notices: dict[str, dict[str, Any]] = {}
    complete = True
    warnings: list[str] = []
    base_total = len(windows) * len(search_terms)
    completed = 0

    for window in windows:
        for search_term in search_terms:
            page = 1
            while True:
                params = {
                    "pageNo": str(page),
                    "numOfRows": "999",
                    "inqryDiv": "1",
                    "inqryBgnDt": window.api_start,
                    "inqryEndDt": window.api_end,
                    "bidNtceNm": search_term,
                    "type": "json",
                }
                try:
                    result = client.get(BID_PUBLIC_ENDPOINT, params)
                except RequestBudgetExceeded as exc:
                    complete = False
                    warnings.append(str(exc))
                    print(f"[stop] {exc}")
                    return notices, complete, warnings

                if not result.ok:
                    if result.result_code in {"22", "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"}:
                        complete = False
                        warnings.append("공공데이터포털 일일 호출 한도에 도달했습니다.")
                        print("[stop] daily request quota reached; cached progress was preserved")
                        return notices, complete, warnings
                    raise CollectionStopped(
                        f"{window.label} / {search_term}: "
                        f"{result.result_code} {result.result_message}"
                    )

                items = normalize_items(result.body)
                for item in items:
                    merge_notice(notices, item, search_term)
                total_count = to_int(result.body.get("totalCount")) or 0
                page_size = to_int(result.body.get("numOfRows")) or 999
                if page * page_size >= total_count:
                    break
                page += 1

            completed += 1
            if completed == 1 or completed % 10 == 0 or completed == base_total:
                print(
                    "[collect] "
                    f"{completed}/{base_total} window={window.label} keyword={search_term} "
                    f"unique_notices={len(notices)} live_calls={client.live_requests} "
                    f"cache_hits={client.cache_hits}"
                )

    return notices, complete, warnings


def _opening_has_passed(value: Any, *, now: datetime | None = None) -> bool:
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) < 8:
        return False
    current = now or datetime.now()
    try:
        if len(text) >= 12:
            parsed = datetime.strptime(text[:12], "%Y%m%d%H%M")
        else:
            parsed = datetime.strptime(text[:8], "%Y%m%d")
    except ValueError:
        return False
    return parsed <= current


def prioritized_bid_notice_numbers(rows: Iterable[dict[str, Any]]) -> list[str]:
    """Round-robin years while putting core, already-opened notices first."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        bid_no = str(row.get("bid_notice_no") or "").strip()
        if bid_no:
            grouped.setdefault(bid_no, []).append(row)

    buckets: dict[int, list[tuple[str, list[dict[str, Any]]]]] = {}
    for bid_no, group in grouped.items():
        years = [to_int(row.get("notice_year")) for row in group]
        year = max((value for value in years if value is not None), default=0)
        buckets.setdefault(year, []).append((bid_no, group))

    for year, bucket in buckets.items():
        bucket.sort(
            key=lambda pair: (
                any(row.get("relevance_status") == "핵심" for row in pair[1]),
                any(_opening_has_passed(row.get("opening_date")) for row in pair[1]),
                max(str(row.get("notice_date") or "") for row in pair[1]),
                pair[0],
            ),
            reverse=True,
        )

    ordered: list[str] = []
    years_desc = sorted(buckets, reverse=True)
    index = 0
    while True:
        added = False
        for year in years_desc:
            bucket = buckets[year]
            if index < len(bucket):
                ordered.append(bucket[index][0])
                added = True
        if not added:
            break
        index += 1
    return ordered


def _empty_enrichment_summary() -> dict[str, Any]:
    return {
        "contract_lookup_status": "미조회—계약과정 보강 미완료",
        "exact_match": False,
        "winners": [],
        "winner_parse_issue": False,
        "contracts": [],
        "contract_parse_issue": False,
        "requests": {},
    }


def _request_endpoint(service_type: str) -> tuple[str, str]:
    if "기술" in (service_type or ""):
        return PROCUREMENT_REQUEST_TECH_ENDPOINT, "getPrcrmntReqInfoListTechServc"
    return PROCUREMENT_REQUEST_ENDPOINT, "getPrcrmntReqInfoListGnrlServc"


def _request_output_row(
    *,
    request_no: str,
    service_type: str,
    operation: str,
    status: str,
    item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = item or {}
    is_tech = operation == "getPrcrmntReqInfoListTechServc"
    budget_amount = "" if is_tech else int_or_blank(item.get("bdgtAmt"))
    representative_amount = "" if is_tech else int_or_blank(item.get("rprsntAmt"))
    total_service_budget = (
        int_or_blank(item.get("totSrvceBdgtAmt")) if is_tech else ""
    )
    current_budget = int_or_blank(item.get("thtmBdgtAmt")) if is_tech else ""
    numeric_checks = (
        (("totSrvceBdgtAmt", total_service_budget), ("thtmBdgtAmt", current_budget))
        if is_tech
        else (("bdgtAmt", budget_amount), ("rprsntAmt", representative_amount))
    )
    invalid_fields = [
        field
        for field, parsed in numeric_checks
        if source_value(item.get(field)) and parsed == ""
    ]
    if invalid_fields:
        status = f"{status}; 숫자형식확인필요—{', '.join(invalid_fields)}"
    return {
        "procurement_request_no": request_no,
        "linked_record_ids": set(),
        "linked_bid_notice_nos": set(),
        "linked_bid_notice_orders": set(),
        "service_type": service_type,
        "request_name": source_value(item.get("prcrmntReqNm")),
        "budget_amount_krw": budget_amount,
        "representative_amount_krw": representative_amount,
        "total_service_budget_amount_krw": total_service_budget,
        "current_budget_amount_krw": current_budget,
        "order_agency": source_value(item.get("orderInsttNm")),
        "input_date": source_value(item.get("inptDt")),
        "request_data_status": status,
        "source_operation": operation,
        "source_dataset": "조달청 나라장터 조달요청서비스",
        "source_url": "https://www.data.go.kr/data/15129468/openapi.do",
    }


def collect_contract_enrichment(
    client: G2BClient,
    rows: list[dict[str, Any]],
    *,
    max_contract_live_requests: int,
    max_procurement_request_live_requests: int,
) -> EnrichmentOutcome:
    by_key = {
        (
            str(row["bid_notice_no"]),
            canonical_notice_order(row["bid_notice_order"]),
        ): row
        for row in rows
    }
    by_bid_no: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_bid_no.setdefault(str(row["bid_notice_no"]), []).append(row)
    summaries = {
        str(row["record_id"]): _empty_enrichment_summary() for row in rows
    }
    awards: list[dict[str, Any]] = []
    contracts: list[dict[str, Any]] = []
    request_records: dict[tuple[str, str], dict[str, Any]] = {}
    ordered_bid_nos = prioritized_bid_notice_numbers(rows)
    warnings: list[str] = []
    contract_complete = True
    request_complete = True
    contract_lookups = 0
    contract_live_requests = 0
    request_lookups = 0
    request_live_requests = 0
    unmatched_detail_items = 0
    endpoint_counts = getattr(client, "live_requests_by_endpoint", {})
    contract_service_live_requests = int(
        endpoint_counts.get(CONTRACT_PROCESS_ENDPOINT, 0)
    )
    request_service_live_requests = int(
        endpoint_counts.get(PROCUREMENT_REQUEST_ENDPOINT, 0)
    ) + int(endpoint_counts.get(PROCUREMENT_REQUEST_TECH_ENDPOINT, 0))
    request_blocked: dict[str, str] = {}
    permission_codes = {
        "20",
        "30",
        "SERVICE_ACCESS_DENIED_ERROR",
        "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
        "PERMISSION_DENIED",
    }
    quota_codes = {"22", "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"}

    for position, bid_no in enumerate(ordered_bid_nos, start=1):
        group = by_bid_no[bid_no]
        params = {
            "pageNo": "1",
            "numOfRows": "999",
            "inqryDiv": "1",
            "bidNtceNo": bid_no,
            "type": "json",
        }
        cached = client.is_cached(CONTRACT_PROCESS_ENDPOINT, params)
        if (
            not cached
            and contract_service_live_requests >= max_contract_live_requests
        ):
            contract_complete = False
            warnings.append(
                "계약과정 서비스별 신규 호출 상한에 도달했습니다. 같은 명령을 재실행하면 캐시 다음부터 이어집니다."
            )
            break

        before = client.live_requests
        try:
            result = client.get(
                CONTRACT_PROCESS_ENDPOINT,
                params,
                live_request_budget=(
                    None
                    if cached
                    else max_contract_live_requests - contract_service_live_requests
                ),
            )
        except RequestBudgetExceeded as exc:
            live_delta = client.live_requests - before
            contract_live_requests += live_delta
            contract_service_live_requests += live_delta
            contract_complete = False
            warnings.append(str(exc))
            break
        live_delta = client.live_requests - before
        contract_live_requests += live_delta
        contract_service_live_requests += live_delta
        contract_lookups += 1

        if not result.ok:
            contract_complete = False
            status = f"조회오류—{result.result_code} {result.result_message}".strip()
            for row in group:
                summaries[str(row["record_id"])]["contract_lookup_status"] = status
            if result.result_code in permission_codes | quota_codes:
                contract_complete = False
                warnings.append(status)
                break
            continue

        response_items = normalize_items(result.body)
        for row in group:
            summaries[str(row["record_id"])]["contract_lookup_status"] = (
                "조회완료—응답 없음" if not response_items else "조회완료—정확한 차수 응답 없음"
            )

        for item_index, item in enumerate(response_items, start=1):
            response_bid_no = source_value(item.get("bidNtceNo")) or bid_no
            response_order = source_value(item.get("bidNtceOrd"))
            exact_row = by_key.get(
                (response_bid_no, canonical_notice_order(response_order))
            )
            exact_match = exact_row is not None
            if not exact_match and (
                source_text(item.get("bidwinrInfoList"))
                or source_text(item.get("cntrctInfoList"))
            ):
                unmatched_detail_items += 1
            record_id = str(exact_row["record_id"]) if exact_row else ""
            summary = summaries.get(record_id)
            if summary is not None:
                summary["exact_match"] = True
                summary["contract_lookup_status"] = "조회완료—정확한 차수 일치"

            winner_raw = source_text(item.get("bidwinrInfoList"))
            winner_entries = parse_caret_list(
                item.get("bidwinrInfoList"), BIDWINNER_LIST_FIELDS
            )
            for entry in winner_entries:
                normal = entry["parse_status"] == "정상"
                parsed_award_amount = int_or_blank(entry["award_amount_krw"])
                parsed_award_rate = decimal_or_blank(entry["award_rate_pct"])
                parsed_participant_count = int_or_blank(entry["participant_count"])
                numeric_errors: list[str] = []
                if entry["award_amount_krw"] and parsed_award_amount == "":
                    numeric_errors.append("낙찰금액")
                if entry["award_rate_pct"] and parsed_award_rate == "":
                    numeric_errors.append("낙찰률")
                if entry["participant_count"] and parsed_participant_count == "":
                    numeric_errors.append("참여업체수")
                parse_status = entry["parse_status"]
                if normal and numeric_errors:
                    normal = False
                    parse_status = f"숫자형식불일치—{', '.join(numeric_errors)}"
                award_row = {
                    "record_id": record_id,
                    "bid_notice_no": response_bid_no,
                    "bid_notice_order": response_order,
                    "contract_process_item_index": item_index,
                    "winner_sequence": entry["winner_sequence"],
                    "winner_company": entry["winner_company"],
                    "winner_business_no": entry["winner_business_no"],
                    "winner_ceo": entry["winner_ceo"],
                    "award_amount_krw": (
                        parsed_award_amount if normal else ""
                    ),
                    "award_rate_pct": (
                        parsed_award_rate if normal else ""
                    ),
                    "participant_count": (
                        parsed_participant_count if normal else ""
                    ),
                    "opening_date": entry["opening_date"] if normal else "",
                    "parse_status": parse_status,
                    "raw_entry": entry["raw_entry"],
                    "bidwinr_info_list_raw": winner_raw,
                    "exact_order_match_yn": "Y" if exact_match else "N",
                    "link_status": (
                        "연결완료—공고번호·차수 일치"
                        if exact_match
                        else "미연결응답—공고번호 또는 차수 불일치; 감사추적용 보존"
                    ),
                    "source_dataset": "조달청 나라장터 계약과정통합공개서비스",
                    "source_url": "https://www.data.go.kr/data/15129459/openapi.do",
                }
                awards.append(award_row)
                if summary is not None:
                    if normal:
                        summary["winners"].append(award_row)
                    else:
                        summary["winner_parse_issue"] = True

            contract_raw = source_text(item.get("cntrctInfoList"))
            contract_entries = parse_caret_list(
                item.get("cntrctInfoList"), CONTRACT_LIST_FIELDS
            )
            for entry in contract_entries:
                normal = entry["parse_status"] == "정상"
                parsed_contract_amount = int_or_blank(entry["contract_amount_krw"])
                parse_status = entry["parse_status"]
                if normal and entry["contract_amount_krw"] and parsed_contract_amount == "":
                    normal = False
                    parse_status = "숫자형식불일치—계약금액"
                contract_row = {
                    "record_id": record_id,
                    "bid_notice_no": response_bid_no,
                    "bid_notice_order": response_order,
                    "contract_process_item_index": item_index,
                    "contract_sequence": entry["contract_sequence"],
                    "contract_no": entry["contract_no"],
                    "contract_name": entry["contract_name"],
                    "contract_agency": entry["contract_agency"],
                    "contract_demand_agency": entry["contract_demand_agency"],
                    "contract_method": entry["contract_method"],
                    "contract_amount_krw": (
                        parsed_contract_amount if normal else ""
                    ),
                    "contract_date": entry["contract_date"] if normal else "",
                    "parse_status": parse_status,
                    "raw_entry": entry["raw_entry"],
                    "contract_info_list_raw": contract_raw,
                    "exact_order_match_yn": "Y" if exact_match else "N",
                    "link_status": (
                        "연결완료—공고번호·차수 일치"
                        if exact_match
                        else "미연결응답—공고번호 또는 차수 불일치; 감사추적용 보존"
                    ),
                    "source_dataset": "조달청 나라장터 계약과정통합공개서비스",
                    "source_url": "https://www.data.go.kr/data/15129459/openapi.do",
                }
                contracts.append(contract_row)
                if summary is not None:
                    if normal:
                        summary["contracts"].append(contract_row)
                    else:
                        summary["contract_parse_issue"] = True

            request_no = source_value(item.get("prcrmntReqNo"))
            if not request_no or exact_row is None:
                continue
            service_type = str(exact_row.get("service_type") or "")
            request_endpoint, operation = _request_endpoint(service_type)
            request_key = (operation, request_no)
            request_row = request_records.get(request_key)
            if request_row is None:
                if operation in request_blocked:
                    request_complete = False
                    request_row = _request_output_row(
                        request_no=request_no,
                        service_type=service_type,
                        operation=operation,
                        status=request_blocked[operation],
                    )
                else:
                    request_params = {
                        "pageNo": "1",
                        "numOfRows": "100",
                        "inqryDiv": "2",
                        "prcrmntReqNo": request_no,
                        "type": "json",
                    }
                    request_cached = client.is_cached(request_endpoint, request_params)
                    if (
                        not request_cached
                        and request_service_live_requests
                        >= max_procurement_request_live_requests
                    ):
                        request_complete = False
                        if not any("조달요청 서비스별" in warning for warning in warnings):
                            warnings.append(
                                "조달요청 서비스별 신규 호출 상한에 도달했습니다. 같은 명령을 재실행하면 캐시 다음부터 이어집니다."
                            )
                        request_row = _request_output_row(
                            request_no=request_no,
                            service_type=service_type,
                            operation=operation,
                            status="미조회—조달요청 서비스별 신규 호출 상한 도달",
                        )
                    else:
                        request_before = client.live_requests
                        try:
                            request_result = client.get(
                                request_endpoint,
                                request_params,
                                live_request_budget=(
                                    None
                                    if request_cached
                                    else max_procurement_request_live_requests
                                    - request_service_live_requests
                                ),
                            )
                        except RequestBudgetExceeded as exc:
                            live_delta = client.live_requests - request_before
                            request_live_requests += live_delta
                            request_service_live_requests += live_delta
                            request_complete = False
                            if isinstance(exc, DailyRequestBudgetExceeded):
                                blocked_status = (
                                    "미조회—KST 일일 조달요청 호출 하드캡 도달"
                                )
                                request_blocked[
                                    "getPrcrmntReqInfoListGnrlServc"
                                ] = blocked_status
                                request_blocked[
                                    "getPrcrmntReqInfoListTechServc"
                                ] = blocked_status
                                if not any(
                                    "일일 조달요청 호출 하드캡" in warning
                                    for warning in warnings
                                ):
                                    warnings.append(
                                        "KST 일일 조달요청 호출 하드캡에 도달해 일반·기술용역 조회를 모두 중단했습니다."
                                    )
                            request_row = _request_output_row(
                                request_no=request_no,
                                service_type=service_type,
                                operation=operation,
                                status=f"미조회—{exc}",
                            )
                        else:
                            live_delta = client.live_requests - request_before
                            request_live_requests += live_delta
                            request_service_live_requests += live_delta
                            request_lookups += 1
                            if not request_result.ok:
                                request_complete = False
                                status = (
                                    f"조회오류—{request_result.result_code} "
                                    f"{request_result.result_message}"
                                ).strip()
                                request_row = _request_output_row(
                                    request_no=request_no,
                                    service_type=service_type,
                                    operation=operation,
                                    status=status,
                                )
                                if request_result.result_code in permission_codes:
                                    request_blocked[operation] = status
                                elif request_result.result_code in quota_codes:
                                    request_blocked[
                                        "getPrcrmntReqInfoListGnrlServc"
                                    ] = status
                                    request_blocked[
                                        "getPrcrmntReqInfoListTechServc"
                                    ] = status
                                    warnings.append(
                                        "조달요청 서비스 일일 호출 한도 응답으로 일반·기술용역 조회를 모두 중단했습니다."
                                    )
                            else:
                                request_items = normalize_items(request_result.body)
                                exact_request_items = [
                                    request_item
                                    for request_item in request_items
                                    if source_value(request_item.get("prcrmntReqNo"))
                                    == request_no
                                ]
                                if len(exact_request_items) == 1:
                                    request_row = _request_output_row(
                                        request_no=request_no,
                                        service_type=service_type,
                                        operation=operation,
                                        status="조회완료—요청번호 일치",
                                        item=exact_request_items[0],
                                    )
                                elif len(exact_request_items) > 1:
                                    request_row = _request_output_row(
                                        request_no=request_no,
                                        service_type=service_type,
                                        operation=operation,
                                        status=(
                                            f"복수 {len(exact_request_items)}건—원문 캐시 확인 필요"
                                        ),
                                    )
                                else:
                                    request_row = _request_output_row(
                                        request_no=request_no,
                                        service_type=service_type,
                                        operation=operation,
                                        status="조회완료—정확한 요청번호 응답 없음",
                                    )
                request_records[request_key] = request_row

            request_row["linked_record_ids"].add(record_id)
            request_row["linked_bid_notice_nos"].add(response_bid_no)
            request_row["linked_bid_notice_orders"].add(response_order)
            summary["requests"][request_key] = request_row

        if position == 1 or position % 50 == 0 or position == len(ordered_bid_nos):
            print(
                "[enrich] "
                f"contracts={position}/{len(ordered_bid_nos)} "
                f"contract_live={contract_service_live_requests}/{max_contract_live_requests} "
                f"request_live={request_service_live_requests}/{max_procurement_request_live_requests}"
            )

    if contract_complete is False:
        request_complete = False
        completed_bid_nos = {
            bid_no
            for bid_no, group in by_bid_no.items()
            if any(
                summaries[str(row["record_id"])]["contract_lookup_status"]
                != "미조회—계약과정 보강 미완료"
                for row in group
            )
        }
        for bid_no, group in by_bid_no.items():
            if bid_no not in completed_bid_nos:
                for row in group:
                    summaries[str(row["record_id"])]["contract_lookup_status"] = (
                        "미조회—호출 상한 또는 서비스 오류, 재실행 필요"
                    )

    if unmatched_detail_items:
        warnings.append(
            f"미연결 계약과정 응답 {unmatched_detail_items}건을 공고번호·차수 불일치 감사추적용 상세행으로 보존했습니다."
        )

    procurement_requests: list[dict[str, Any]] = []
    for request_row in request_records.values():
        serialized = dict(request_row)
        serialized["linked_record_ids"] = ", ".join(sorted(request_row["linked_record_ids"]))
        serialized["linked_bid_notice_nos"] = ", ".join(
            sorted(request_row["linked_bid_notice_nos"])
        )
        serialized["linked_bid_notice_orders"] = ", ".join(
            sorted(request_row["linked_bid_notice_orders"])
        )
        procurement_requests.append(serialized)
    procurement_requests.sort(
        key=lambda row: (str(row["procurement_request_no"]), str(row["source_operation"]))
    )
    awards.sort(
        key=lambda row: (
            str(row["bid_notice_no"]),
            str(row["bid_notice_order"]),
            str(row["winner_sequence"]),
        )
    )
    contracts.sort(
        key=lambda row: (
            str(row["bid_notice_no"]),
            str(row["bid_notice_order"]),
            str(row["contract_sequence"]),
        )
    )
    return EnrichmentOutcome(
        awards=awards,
        contracts=contracts,
        procurement_requests=procurement_requests,
        summaries=summaries,
        contract_complete=contract_complete,
        procurement_request_complete=request_complete,
        contract_lookups=contract_lookups,
        contract_live_requests=contract_live_requests,
        procurement_request_lookups=request_lookups,
        procurement_request_live_requests=request_live_requests,
        warnings=warnings,
    )


def apply_contract_enrichment(
    rows: list[dict[str, Any]], outcome: EnrichmentOutcome
) -> None:
    for row in rows:
        summary = outcome.summaries[str(row["record_id"])]
        lookup_status = str(summary["contract_lookup_status"])
        winners = summary["winners"]
        contracts = summary["contracts"]
        requests = list(summary["requests"].values())

        if not summary["exact_match"]:
            row["winner_count"] = ""
            row["contract_count"] = ""
            row["participant_data_status"] = lookup_status
            row["award_data_status"] = lookup_status
            row["contract_data_status"] = lookup_status
            row["procurement_request_data_status"] = lookup_status
            continue

        row["winner_count"] = "" if summary["winner_parse_issue"] else len(winners)
        row["contract_count"] = (
            "" if summary["contract_parse_issue"] else len(contracts)
        )

        if summary["winner_parse_issue"]:
            row["participant_data_status"] = "파싱확인필요—낙찰 상세 CSV 원문 참조"
            row["award_data_status"] = "파싱확인필요—낙찰 상세 CSV 원문 참조"
        elif len(winners) == 1:
            winner = winners[0]
            row["participant_count"] = winner["participant_count"]
            row["winner_company"] = winner["winner_company"]
            row["winner_business_no"] = winner["winner_business_no"]
            row["award_amount_krw"] = winner["award_amount_krw"]
            row["award_rate_pct"] = winner["award_rate_pct"]
            row["participant_data_status"] = (
                "수집완료—참여업체수만 제공; 업체별 명단은 낙찰정보서비스 필요"
            )
            row["award_data_status"] = "수집완료—단일 낙찰"
        elif len(winners) > 1:
            row["participant_data_status"] = (
                f"복수 낙찰 {len(winners)}건—참여업체수는 낙찰 상세 CSV 참조"
            )
            row["award_data_status"] = f"복수 {len(winners)}건—낙찰 상세 CSV 참조"
        else:
            row["participant_data_status"] = "조회완료—참여업체수 정보 없음"
            row["award_data_status"] = "조회완료—낙찰정보 없음"

        if summary["contract_parse_issue"]:
            row["contract_data_status"] = "파싱확인필요—계약 상세 CSV 원문 참조"
        elif len(contracts) == 1:
            contract = contracts[0]
            row["contract_amount_krw"] = contract["contract_amount_krw"]
            row["contract_date"] = contract["contract_date"]
            row["contract_data_status"] = "수집완료—단일 계약"
        elif len(contracts) > 1:
            row["contract_data_status"] = (
                f"복수 {len(contracts)}건—계약 상세 CSV 참조; 합산·최신값 대체 안 함"
            )
        else:
            row["contract_data_status"] = "조회완료—계약정보 없음"

        if len(requests) == 1:
            request = requests[0]
            row["procurement_request_no"] = request["procurement_request_no"]
            row["procurement_request_name"] = request["request_name"]
            row["procurement_request_budget_amount_krw"] = request["budget_amount_krw"]
            row["procurement_request_representative_amount_krw"] = request[
                "representative_amount_krw"
            ]
            row["procurement_request_total_service_budget_amount_krw"] = request[
                "total_service_budget_amount_krw"
            ]
            row["procurement_request_current_budget_amount_krw"] = request[
                "current_budget_amount_krw"
            ]
            row["procurement_request_order_agency"] = request["order_agency"]
            row["procurement_request_input_date"] = request["input_date"]
            row["procurement_request_data_status"] = request["request_data_status"]
        elif len(requests) > 1:
            row["procurement_request_data_status"] = (
                f"복수 {len(requests)}건—조달요청 상세 CSV 참조"
            )
        else:
            row["procurement_request_data_status"] = "조회완료—조달요청번호 없음"


def access_row(
    *,
    service_id: str,
    service_name: str,
    dataset_url: str,
    operation: str,
    purpose: str,
    result: ApiResult | None,
    next_action: str,
    static_status: str = "",
    static_message: str = "",
) -> dict[str, str]:
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    if result is None:
        return {
            "service_id": service_id,
            "service_name": service_name,
            "dataset_url": dataset_url,
            "operation": operation,
            "purpose": purpose,
            "access_status": static_status,
            "error_code": "",
            "message": static_message,
            "checked_at": checked_at,
            "next_action": next_action,
        }
    if result.ok:
        status = "사용가능"
    elif result.result_code in {"30", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}:
        status = "활용신청필요"
    elif result.result_code in {"20", "SERVICE_ACCESS_DENIED_ERROR", "PERMISSION_DENIED"}:
        status = "권한확인필요"
    else:
        status = "오류"
    return {
        "service_id": service_id,
        "service_name": service_name,
        "dataset_url": dataset_url,
        "operation": operation,
        "purpose": purpose,
        "access_status": status,
        "error_code": result.result_code,
        "message": result.result_message,
        "checked_at": checked_at,
        "next_action": next_action,
    }


def probe_access(client: G2BClient) -> list[dict[str, str]]:
    sample_bid_no = "R25BK00564916"
    probes = [
        (
            "contract_process",
            "나라장터 계약과정통합공개서비스",
            "https://www.data.go.kr/data/15129459/openapi.do",
            CONTRACT_PROCESS_ENDPOINT,
            {
                "pageNo": "1",
                "numOfRows": "1",
                "inqryDiv": "1",
                "bidNtceNo": sample_bid_no,
                "type": "json",
            },
            "낙찰기업·낙찰금액·계약정보 교차검증",
            "공공데이터포털에서 15129459 활용신청 후 재실행",
        ),
        (
            "procurement_request",
            "나라장터 조달요청서비스",
            "https://www.data.go.kr/data/15129468/openapi.do",
            PROCUREMENT_REQUEST_ENDPOINT,
            {
                "pageNo": "1",
                "numOfRows": "1",
                "inqryDiv": "2",
                "prcrmntReqNo": "0000000000",
                "type": "json",
            },
            "조달요청명·발주기관·예산 보강",
            "공공데이터포털에서 15129468 활용신청 후 재실행",
        ),
        (
            "opening_companies",
            "나라장터 낙찰정보서비스",
            "https://www.data.go.kr/data/15129397/openapi.do",
            OPENING_COMPANY_ENDPOINT,
            {
                "pageNo": "1",
                "numOfRows": "1",
                "bidNtceNo": sample_bid_no,
                "bidNtceOrd": "000",
                "bidClsfcNo": "0",
                "rbidNo": "000",
                "type": "json",
            },
            "개찰 완료 건의 참여기업·투찰금액·개찰순위",
            "공공데이터포털에서 15129397 활용신청 후 재실행",
        ),
    ]
    rows: list[dict[str, str]] = []
    for service_id, name, dataset_url, endpoint, params, purpose, next_action in probes:
        try:
            result = client.get(endpoint, params, use_cache=False)
        except RequestBudgetExceeded:
            result = ApiResult(False, "LOCAL_LIMIT", "로컬 호출 상한에 도달했습니다.", {}, "")
        rows.append(
            access_row(
                service_id=service_id,
                service_name=name,
                dataset_url=dataset_url,
                operation=endpoint.rsplit("/", 1)[-1],
                purpose=purpose,
                result=result,
                next_action=next_action,
            )
        )
    rows.append(
        access_row(
            service_id="bulk_notice_file",
            service_name="조달청 입찰공고 내역",
            dataset_url="https://www.data.go.kr/data/15053346/fileData.do",
            operation="기관 자체 다운로드 보고서",
            purpose="입찰공고 대량 조회",
            result=None,
            next_action="나라장터 SSO 로그인 후 보고서 범위와 실제 CSV 열을 확인",
            static_status="SSO로그인필요",
            static_message="API가 아니라 나라장터 자체 보고서 링크이며 자동 다운로드는 확인하지 않았습니다.",
        )
    )
    return rows


def notice_rows(
    notices: dict[str, dict[str, Any]],
    keyword_config: dict[str, Any],
    access_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    access = {row["service_id"]: row["access_status"] for row in access_rows}
    participant_status = (
        "API 사용가능—이번 1차 실행은 연결 전"
        if access.get("opening_companies") == "사용가능"
        else "미수집—낙찰정보서비스 활용신청 필요"
    )
    award_status = (
        "API 사용가능—이번 1차 실행은 연결 전"
        if access.get("contract_process") == "사용가능"
        else "미수집—계약과정/낙찰정보서비스 활용신청 필요"
    )
    request_status = (
        "API 사용가능—이번 1차 실행은 연결 전"
        if access.get("procurement_request") == "사용가능"
        else "미수집—조달요청서비스 활용신청 필요"
    )

    rows: list[dict[str, Any]] = []
    for record_id, record in notices.items():
        item = record["item"]
        title = str(item.get("bidNtceNm") or "").strip()
        classification = classify_title(title, keyword_config)
        published = str(item.get("bidNtceDt") or "").strip()
        year_match = re.match(r"(\d{4})", published)
        row = {
            "record_id": record_id,
            "bid_notice_no": str(item.get("bidNtceNo") or ""),
            "bid_notice_order": str(item.get("bidNtceOrd") or ""),
            "notice_title": title,
            "notice_date": published,
            "notice_year": int(year_match.group(1)) if year_match else "",
            "notice_kind": str(item.get("ntceKindNm") or ""),
            "rebid_yn": str(item.get("reNtceYn") or ""),
            "notice_agency": str(item.get("ntceInsttNm") or ""),
            "demand_agency": str(item.get("dminsttNm") or ""),
            "bid_method": str(item.get("bidMethdNm") or ""),
            "contract_method": str(item.get("cntrctCnclsMthdNm") or ""),
            "award_method": str(item.get("sucsfbidMthdNm") or ""),
            "service_type": str(item.get("srvceDivNm") or ""),
            "budget_amount_krw": int_or_blank(item.get("asignBdgtAmt")),
            "estimated_price_krw": int_or_blank(item.get("presmptPrce")),
            "vat_amount_krw": int_or_blank(item.get("VAT")),
            "bid_start": str(item.get("bidBeginDt") or ""),
            "bid_close": str(item.get("bidClseDt") or ""),
            "opening_date": str(item.get("opengDt") or ""),
            "participant_limit_yn": str(item.get("bidPrtcptLmtYn") or ""),
            "joint_contract_method": str(item.get("cmmnSpldmdMethdNm") or ""),
            "order_plan_unified_no": str(item.get("orderPlanUntyNo") or ""),
            "pre_spec_registration_no": str(item.get("bfSpecRgstNo") or ""),
            "procurement_request_no": str(item.get("prcrmntReqNo") or ""),
            "search_terms": ", ".join(sorted(record["search_terms"])),
            "categories": ", ".join(classification["categories"]),
            "relevance_status": classification["relevance_status"],
            "relevance_reason": classification["relevance_reason"],
            "tracker_tier": classification["tracker_tier"],
            "tracker_score": classification["tracker_score"],
            "matched_keywords": ", ".join(classification["tracker_keywords"]),
            "winner_count": "",
            "participant_count": "",
            "winner_company": "",
            "winner_business_no": "",
            "award_amount_krw": "",
            "award_rate_pct": "",
            "contract_count": "",
            "contract_amount_krw": "",
            "contract_date": "",
            "procurement_request_name": "",
            "procurement_request_budget_amount_krw": "",
            "procurement_request_representative_amount_krw": "",
            "procurement_request_total_service_budget_amount_krw": "",
            "procurement_request_current_budget_amount_krw": "",
            "procurement_request_order_agency": "",
            "procurement_request_input_date": "",
            "participant_data_status": participant_status,
            "award_data_status": award_status,
            "contract_data_status": award_status,
            "procurement_request_data_status": request_status,
            "notice_url": str(item.get("bidNtceDtlUrl") or item.get("bidNtceUrl") or ""),
            "source_dataset": "조달청 나라장터 입찰공고정보서비스",
            "source_url": "https://www.data.go.kr/data/15129394/openapi.do",
        }
        rows.append(row)
    rows.sort(key=lambda row: (str(row["notice_date"]), str(row["record_id"])), reverse=True)
    return rows


def write_csv(path: Path, fields: Iterable[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="최근 5년 기후·온실가스·배출권·외부사업 나라장터 용역 공고 추출"
    )
    parser.add_argument("--start-date", type=parse_iso_date, default=date(2021, 9, 21))
    parser.add_argument("--end-date", type=parse_iso_date, default=date(2026, 9, 21))
    parser.add_argument(
        "--search-terms",
        default=",".join(DEFAULT_SEARCH_TERMS),
        help="쉼표로 구분한 공고명 검색어",
    )
    parser.add_argument(
        "--cache-db",
        type=Path,
        default=ROOT_DIR / "data" / "climate_procurement_history.db",
    )
    parser.add_argument(
        "--notices-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_notices_5y.csv",
    )
    parser.add_argument(
        "--bidders-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_bidders_5y.csv",
    )
    parser.add_argument(
        "--awards-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_awards_5y.csv",
    )
    parser.add_argument(
        "--contracts-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_contracts_5y.csv",
    )
    parser.add_argument(
        "--procurement-requests-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_requests_5y.csv",
    )
    parser.add_argument(
        "--access-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_access_status.csv",
    )
    parser.add_argument(
        "--max-live-requests",
        type=int,
        default=2500,
        help="이번 실행의 전체 실제 HTTP 시도 상한",
    )
    parser.add_argument(
        "--max-contract-lookups",
        type=int,
        default=850,
        help="계약과정 서비스 KST 일일 실제 HTTP 시도 하드캡(최대 900)",
    )
    parser.add_argument(
        "--max-procurement-request-lookups",
        type=int,
        default=850,
        help="일반·기술 조달요청 서비스 합산 KST 일일 실제 HTTP 시도 하드캡(최대 900)",
    )
    parser.add_argument("--delay-seconds", type=float, default=0.15)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--skip-access-probes", action="store_true")
    parser.add_argument(
        "--enrich-contracts",
        action="store_true",
        help="계약과정 및 연결된 조달요청 정보를 캐시 기반으로 보강",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for option_name, option_value in (
        ("--max-contract-lookups", args.max_contract_lookups),
        ("--max-procurement-request-lookups", args.max_procurement_request_lookups),
    ):
        if not 0 <= option_value <= 900:
            print(
                f"[error] {option_name} 값은 개발계정 안전범위 0~900이어야 합니다.",
                file=sys.stderr,
            )
            return 2
    load_dotenv(ROOT_DIR / ".env")
    service_key = os.environ.get("DATA_GO_KR_SERVICE_KEY", "").strip()
    if not service_key:
        print("[error] DATA_GO_KR_SERVICE_KEY가 없습니다.", file=sys.stderr)
        return 2

    keyword_config = read_json(ROOT_DIR / "configs" / "keywords.json")
    terms = [term.strip() for term in args.search_terms.split(",") if term.strip()]
    windows = month_windows(args.start_date, args.end_date)
    estimated_calls = len(windows) * len(terms)
    print(
        "[plan] "
        f"period={args.start_date}..{args.end_date} windows={len(windows)} "
        f"keywords={len(terms)} estimated_base_calls={estimated_calls} "
        f"max_live_requests={args.max_live_requests}"
    )
    if estimated_calls > args.max_live_requests:
        print(
            "[warning] 기본 예상 호출 수가 로컬 상한보다 큽니다. 캐시를 보존하고 상한에서 중단합니다."
        )

    cache = ApiCache(args.cache_db)
    client = G2BClient(
        service_key,
        cache,
        delay_seconds=args.delay_seconds,
        max_live_requests=args.max_live_requests,
        refresh=args.refresh,
        daily_group_caps={
            CONTRACT_SERVICE_GROUP: args.max_contract_lookups,
            PROCUREMENT_REQUEST_SERVICE_GROUP: args.max_procurement_request_lookups,
        },
    )
    try:
        access_rows = [] if args.skip_access_probes else probe_access(client)
        notices, complete, warnings = collect_notices(client, windows, terms)
        discovery_live_requests = client.live_requests
        discovery_cache_hits = client.cache_hits
        if args.skip_access_probes:
            access_rows = [
                access_row(
                    service_id="contract_process",
                    service_name="나라장터 계약과정통합공개서비스",
                    dataset_url="https://www.data.go.kr/data/15129459/openapi.do",
                    operation="getCntrctProcssIntgOpenServc",
                    purpose="낙찰기업·낙찰금액·계약정보",
                    result=None,
                    next_action="접근상태 미확인",
                    static_status="미확인",
                    static_message="이번 실행에서 접근 진단을 건너뛰었습니다.",
                ),
                access_row(
                    service_id="procurement_request",
                    service_name="나라장터 조달요청서비스",
                    dataset_url="https://www.data.go.kr/data/15129468/openapi.do",
                    operation=(
                        "getPrcrmntReqInfoListGnrlServc / "
                        "getPrcrmntReqInfoListTechServc"
                    ),
                    purpose="조달요청명·발주기관·예산",
                    result=None,
                    next_action="접근상태 미확인",
                    static_status="미확인",
                    static_message="이번 실행에서 접근 진단을 건너뛰었습니다.",
                ),
                access_row(
                    service_id="opening_companies",
                    service_name="나라장터 낙찰정보서비스",
                    dataset_url="https://www.data.go.kr/data/15129397/openapi.do",
                    operation="getOpengResultListInfoOpengCompt",
                    purpose="참여기업·투찰금액·순위",
                    result=None,
                    next_action="접근상태 미확인",
                    static_status="미확인",
                    static_message="이번 실행에서 접근 진단을 건너뛰었습니다.",
                ),
            ]
        rows = notice_rows(notices, keyword_config, access_rows)
        outcome: EnrichmentOutcome | None = None
        if args.enrich_contracts:
            outcome = collect_contract_enrichment(
                client,
                rows,
                max_contract_live_requests=args.max_contract_lookups,
                max_procurement_request_live_requests=(
                    args.max_procurement_request_lookups
                ),
            )
            apply_contract_enrichment(rows, outcome)

        write_csv(args.notices_csv, NOTICE_FIELDS, rows)
        write_csv(args.bidders_csv, BIDDER_FIELDS, [])
        write_csv(
            args.awards_csv,
            AWARD_FIELDS,
            outcome.awards if outcome is not None else [],
        )
        write_csv(
            args.contracts_csv,
            CONTRACT_FIELDS,
            outcome.contracts if outcome is not None else [],
        )
        write_csv(
            args.procurement_requests_csv,
            PROCUREMENT_REQUEST_FIELDS,
            outcome.procurement_requests if outcome is not None else [],
        )
        access_rows.append(
            {
                "service_id": "collection_run",
                "service_name": "최근 5년 공고 수집 실행",
                "dataset_url": "https://www.data.go.kr/data/15129394/openapi.do",
                "operation": "getBidPblancListInfoServcPPSSrch",
                "purpose": f"{args.start_date}~{args.end_date} 공고명 월별 검색",
                "access_status": "완료" if complete else "부분완료",
                "error_code": "",
                "message": (
                    f"고유 공고 {len(rows)}건, live_calls={discovery_live_requests}, "
                    f"cache_hits={discovery_cache_hits}"
                    + (f", warnings={' | '.join(warnings)}" if warnings else "")
                ),
                "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "next_action": "부분완료이면 같은 명령을 재실행하면 캐시 다음부터 이어집니다.",
            }
        )
        if outcome is not None:
            access_rows.extend(
                [
                    {
                        "service_id": "contract_enrichment_run",
                        "service_name": "계약과정·낙찰 보강 실행",
                        "dataset_url": "https://www.data.go.kr/data/15129459/openapi.do",
                        "operation": "getCntrctProcssIntgOpenServc",
                        "purpose": "정확한 공고차수별 낙찰 및 계약 상세 보강",
                        "access_status": (
                            "완료" if outcome.contract_complete else "부분완료"
                        ),
                        "error_code": "",
                        "message": (
                            f"조회 {outcome.contract_lookups}건, "
                            f"신규 HTTP 호출 {outcome.contract_live_requests}회, "
                            f"KST 오늘 누적 {client.daily_attempts(CONTRACT_SERVICE_GROUP)}회, "
                            f"낙찰 상세 {len(outcome.awards)}행, "
                            f"계약 상세 {len(outcome.contracts)}행"
                            + (
                                f", warnings={' | '.join(outcome.warnings)}"
                                if outcome.warnings
                                else ""
                            )
                        ),
                        "checked_at": datetime.now().astimezone().isoformat(
                            timespec="seconds"
                        ),
                        "next_action": (
                            "부분완료이면 동일 명령을 재실행하십시오. 저장된 캐시는 다시 호출하지 않습니다."
                        ),
                    },
                    {
                        "service_id": "procurement_request_enrichment_run",
                        "service_name": "조달요청 보강 실행",
                        "dataset_url": "https://www.data.go.kr/data/15129468/openapi.do",
                        "operation": (
                            "getPrcrmntReqInfoListGnrlServc / "
                            "getPrcrmntReqInfoListTechServc"
                        ),
                        "purpose": "일반·기술용역별 요청명·기관·예산 보강",
                        "access_status": (
                            "완료"
                            if outcome.procurement_request_complete
                            else "부분완료"
                        ),
                        "error_code": "",
                        "message": (
                            f"조회 {outcome.procurement_request_lookups}건, "
                            f"신규 HTTP 호출 {outcome.procurement_request_live_requests}회, "
                            f"KST 오늘 누적 {client.daily_attempts(PROCUREMENT_REQUEST_SERVICE_GROUP)}회, "
                            f"요청 상세 {len(outcome.procurement_requests)}행"
                        ),
                        "checked_at": datetime.now().astimezone().isoformat(
                            timespec="seconds"
                        ),
                        "next_action": (
                            "부분완료이면 동일 명령을 재실행하십시오. 일반·기술용역 호출은 합산 상한을 적용합니다."
                        ),
                    },
                ]
            )
        write_csv(args.access_csv, ACCESS_FIELDS, access_rows)
    except CollectionStopped as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    finally:
        cache.close()

    core_count = sum(1 for row in rows if row["relevance_status"] == "핵심")
    review_count = sum(1 for row in rows if row["relevance_status"] == "검토필요")
    enrichment_complete = (
        outcome is None
        or (outcome.contract_complete and outcome.procurement_request_complete)
    )
    overall_complete = complete and enrichment_complete
    print(
        "[done] "
        f"notices={len(rows)} core={core_count} review={review_count} "
        f"complete={overall_complete} live_calls={client.live_requests} cache_hits={client.cache_hits}"
    )
    print(f"[done] notices_csv={args.notices_csv}")
    print(f"[done] bidders_csv={args.bidders_csv}")
    print(f"[done] awards_csv={args.awards_csv}")
    print(f"[done] contracts_csv={args.contracts_csv}")
    print(f"[done] procurement_requests_csv={args.procurement_requests_csv}")
    print(f"[done] access_csv={args.access_csv}")
    print(f"[done] cache_db={args.cache_db}")
    return 0 if overall_complete else 3


if __name__ == "__main__":
    raise SystemExit(main())
