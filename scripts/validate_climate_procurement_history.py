from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]

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

REQUEST_FIELDS = (
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

NOTICE_AMOUNT_FIELDS = (
    "budget_amount_krw",
    "estimated_price_krw",
    "vat_amount_krw",
    "award_amount_krw",
    "contract_amount_krw",
    "procurement_request_budget_amount_krw",
    "procurement_request_representative_amount_krw",
    "procurement_request_total_service_budget_amount_krw",
    "procurement_request_current_budget_amount_krw",
)

EXPECTED_ACCESS_SERVICES = (
    "contract_process",
    "procurement_request",
    "opening_companies",
    "bulk_notice_file",
    "collection_run",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="최근 5개년 기후·온실가스 조달 추출 CSV의 보수적 QA"
    )
    parser.add_argument(
        "--notices-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_notices_5y_enriched.csv",
    )
    parser.add_argument(
        "--awards-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_awards_5y_enriched.csv",
    )
    parser.add_argument(
        "--contracts-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_contracts_5y_enriched.csv",
    )
    parser.add_argument(
        "--requests-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_requests_5y_enriched.csv",
    )
    parser.add_argument(
        "--bidders-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_bidders_5y_enriched.csv",
    )
    parser.add_argument(
        "--access-csv",
        type=Path,
        default=ROOT_DIR / "reports" / "climate_procurement_access_status_enriched.csv",
    )
    parser.add_argument("--start-date", required=True, help="포함 시작일(YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="포함 종료일(YYYY-MM-DD)")
    return parser


def parse_cli_date(value: str, label: str, fatal_errors: list[str]) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        fatal_errors.append(f"{label} 값이 YYYY-MM-DD 형식이 아닙니다: {value!r}")
        return None


def read_csv_file(
    path: Path,
    label: str,
    required_fields: Iterable[str],
    fatal_errors: list[str],
) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        fatal_errors.append(f"{label} CSV를 찾을 수 없습니다: {path}")
        return [], []

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fields = list(reader.fieldnames or [])
            if not fields:
                fatal_errors.append(f"{label} CSV에 헤더가 없습니다: {path}")
                return [], []
            duplicate_headers = sorted(
                field for field, count in Counter(fields).items() if count > 1
            )
            if duplicate_headers:
                fatal_errors.append(
                    f"{label} CSV에 중복 헤더가 있습니다: {', '.join(duplicate_headers)}"
                )
            missing = [field for field in required_fields if field not in fields]
            if missing:
                fatal_errors.append(
                    f"{label} CSV 필수 열 누락: {', '.join(missing)}"
                )
            rows = [
                {key: (value if value is not None else "") for key, value in row.items()}
                for row in reader
            ]
            return fields, rows
    except (OSError, UnicodeError, csv.Error) as exc:
        fatal_errors.append(f"{label} CSV를 읽을 수 없습니다: {path} ({exc})")
        return [], []


def parse_data_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None

    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass

    compact_formats = (
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y%m%d",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y.%m.%d",
    )
    for fmt in compact_formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_amount(value: str) -> tuple[str, Decimal | None]:
    text = value.strip()
    if not text:
        return "blank", None
    normalized = text.replace(",", "").replace("₩", "").strip()
    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return "invalid", None
    if not amount.is_finite():
        return "invalid", None
    return ("negative" if amount < 0 else "ok"), amount


def clean_value(value: str) -> str:
    return value.strip() or "(빈값)"


def sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def status_means_collected(value: str) -> bool:
    normalized = re.sub(r"[\s_\-—:]+", "", value).casefold()
    if not normalized:
        return False
    blockers = (
        "미수집",
        "부분완료",
        "미확인",
        "연결전",
        "필요",
        "오류",
        "notcollected",
        "pending",
        "partial",
    )
    if any(token in normalized for token in blockers):
        return False
    exact_statuses = {
        "완료",
        "수집완료",
        "수집됨",
        "complete",
        "completed",
        "collected",
        "success",
    }
    return (
        normalized in exact_statuses
        or "수집완료" in normalized
        or "completed" in normalized
        or "collected" in normalized
    )


def sample_ids(rows: Iterable[dict[str, str]], limit: int = 5) -> list[str]:
    samples: list[str] = []
    for row in rows:
        identifier = row.get("record_id", "").strip()
        if not identifier:
            identifier = row.get("bid_notice_no", "").strip() or "(식별자 없음)"
        if identifier not in samples:
            samples.append(identifier)
        if len(samples) >= limit:
            break
    return samples


def add_warning(
    warnings: list[dict[str, Any]],
    code: str,
    message: str,
    count: int = 1,
    samples: Iterable[str] | None = None,
) -> None:
    item: dict[str, Any] = {"code": code, "count": count, "message": message}
    if samples:
        item["samples"] = list(samples)[:5]
    warnings.append(item)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fatal_errors: list[str] = []
    warnings: list[dict[str, Any]] = []

    start_date = parse_cli_date(args.start_date, "start-date", fatal_errors)
    end_date = parse_cli_date(args.end_date, "end-date", fatal_errors)
    if start_date and end_date and start_date > end_date:
        fatal_errors.append(
            f"start-date({start_date})가 end-date({end_date})보다 늦습니다."
        )

    notice_fields, notices = read_csv_file(
        args.notices_csv, "공고", NOTICE_FIELDS, fatal_errors
    )
    award_fields, awards = read_csv_file(
        args.awards_csv, "낙찰결과", AWARD_FIELDS, fatal_errors
    )
    contract_fields, contracts = read_csv_file(
        args.contracts_csv, "계약결과", CONTRACT_FIELDS, fatal_errors
    )
    request_fields, requests = read_csv_file(
        args.requests_csv, "조달요청", REQUEST_FIELDS, fatal_errors
    )
    bidder_fields, bidders = read_csv_file(
        args.bidders_csv, "참여기업", BIDDER_FIELDS, fatal_errors
    )
    access_fields, access_rows = read_csv_file(
        args.access_csv, "접근상태", ACCESS_FIELDS, fatal_errors
    )

    notice_schema_ok = bool(notice_fields) and set(NOTICE_FIELDS).issubset(notice_fields)
    award_schema_ok = bool(award_fields) and set(AWARD_FIELDS).issubset(award_fields)
    contract_schema_ok = bool(contract_fields) and set(CONTRACT_FIELDS).issubset(contract_fields)
    request_schema_ok = bool(request_fields) and set(REQUEST_FIELDS).issubset(request_fields)
    bidder_schema_ok = bool(bidder_fields) and set(BIDDER_FIELDS).issubset(bidder_fields)
    access_schema_ok = bool(access_fields) and set(ACCESS_FIELDS).issubset(access_fields)

    duplicate_record_count = 0
    blank_bid_notice_count = 0
    outside_period_count = 0
    invalid_date_count = 0
    chronology_violation_count = 0
    invalid_amount_count = 0
    negative_amount_count = 0
    false_complete_participant_count = 0
    false_complete_award_count = 0
    false_complete_contract_count = 0
    false_complete_request_count = 0
    orphan_award_count = 0
    orphan_contract_count = 0
    request_orphan_link_count = 0
    request_data_without_number_count = 0
    award_count_mismatch_count = 0
    contract_count_mismatch_count = 0
    unsafe_multiple_summary_count = 0
    orphan_bidder_count = 0

    relevance_counts: Counter[str] = Counter()
    year_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()

    notice_ids: set[str] = set()
    bidder_rows_by_record: dict[str, list[dict[str, str]]] = defaultdict(list)
    award_rows_by_record: dict[str, list[dict[str, str]]] = defaultdict(list)
    contract_rows_by_record: dict[str, list[dict[str, str]]] = defaultdict(list)
    if bidder_schema_ok:
        for row in bidders:
            bidder_rows_by_record[row["record_id"].strip()].append(row)
    if award_schema_ok:
        for row in awards:
            award_rows_by_record[row["record_id"].strip()].append(row)
    if contract_schema_ok:
        for row in contracts:
            contract_rows_by_record[row["record_id"].strip()].append(row)

    if notice_schema_ok:
        record_counts = Counter(row["record_id"].strip() for row in notices)
        duplicate_ids = sorted(
            record_id
            for record_id, count in record_counts.items()
            if record_id and count > 1
        )
        duplicate_record_count = sum(record_counts[item] - 1 for item in duplicate_ids)
        if duplicate_ids:
            add_warning(
                warnings,
                "duplicate_record_id",
                "같은 record_id의 공고가 중복되어 있습니다.",
                duplicate_record_count,
                duplicate_ids,
            )

        blank_record_rows = [row for row in notices if not row["record_id"].strip()]
        if blank_record_rows:
            add_warning(
                warnings,
                "blank_record_id",
                "record_id가 빈 공고가 있습니다.",
                len(blank_record_rows),
                sample_ids(blank_record_rows),
            )

        blank_bid_rows = [row for row in notices if not row["bid_notice_no"].strip()]
        blank_bid_notice_count = len(blank_bid_rows)
        if blank_bid_rows:
            add_warning(
                warnings,
                "blank_bid_notice_no",
                "입찰공고번호가 빈 공고가 있습니다.",
                blank_bid_notice_count,
                sample_ids(blank_bid_rows),
            )

        date_field_errors: list[str] = []
        outside_period_rows: list[dict[str, str]] = []
        chronology_rows: list[dict[str, str]] = []
        amount_errors: list[str] = []
        negative_amounts: list[str] = []
        year_mismatches: list[str] = []
        award_count_mismatches: list[str] = []
        contract_count_mismatches: list[str] = []
        unsafe_multiple_summaries: list[str] = []
        request_data_without_number: list[str] = []

        for row in notices:
            record_id = row["record_id"].strip()
            if record_id:
                notice_ids.add(record_id)

            relevance_counts[clean_value(row["relevance_status"])] += 1
            year_counts[clean_value(row["notice_year"])] += 1
            categories = [
                part.strip()
                for part in re.split(r"[,;|]", row["categories"])
                if part.strip()
            ]
            if categories:
                category_counts.update(categories)
            else:
                category_counts["(빈값)"] += 1

            parsed_dates: dict[str, datetime | None] = {}
            for field in ("notice_date", "bid_close", "opening_date"):
                raw_value = row[field].strip()
                parsed_dates[field] = parse_data_datetime(raw_value)
                if (field == "notice_date" and not raw_value) or (
                    raw_value and parsed_dates[field] is None
                ):
                    date_field_errors.append(f"{record_id or '(식별자 없음)'}:{field}")

            notice_dt = parsed_dates["notice_date"]
            close_dt = parsed_dates["bid_close"]
            opening_dt = parsed_dates["opening_date"]
            if notice_dt and start_date and end_date:
                if not (start_date <= notice_dt.date() <= end_date):
                    outside_period_rows.append(row)
            if notice_dt and close_dt and notice_dt > close_dt:
                chronology_rows.append(row)
            elif close_dt and opening_dt and close_dt > opening_dt:
                chronology_rows.append(row)

            if notice_dt and row["notice_year"].strip():
                if row["notice_year"].strip() != str(notice_dt.year):
                    year_mismatches.append(record_id or "(식별자 없음)")

            for field in NOTICE_AMOUNT_FIELDS:
                amount_status, _ = parse_amount(row[field])
                if amount_status == "invalid":
                    amount_errors.append(f"{record_id or '(식별자 없음)'}:{field}")
                elif amount_status == "negative":
                    negative_amounts.append(f"{record_id or '(식별자 없음)'}:{field}")

            linked_bidders = bidder_rows_by_record.get(record_id, [])
            participant_present = bool(row["participant_count"].strip()) or any(
                item["participant_company"].strip() for item in linked_bidders
            )
            if status_means_collected(row["participant_data_status"]) and not participant_present:
                false_complete_participant_count += 1

            award_present = any(
                row[field].strip()
                for field in ("winner_company", "winner_business_no", "award_amount_krw")
            )
            if status_means_collected(row["award_data_status"]) and not award_present:
                false_complete_award_count += 1

            contract_present = any(
                row[field].strip()
                for field in ("contract_amount_krw", "contract_date")
            )
            if status_means_collected(row["contract_data_status"]) and not contract_present:
                detail_present = any(
                    item["parse_status"].strip() == "정상"
                    for item in contract_rows_by_record.get(record_id, [])
                )
                if not detail_present:
                    false_complete_contract_count += 1

            request_present = any(
                row[field].strip()
                for field in (
                    "procurement_request_no",
                    "procurement_request_name",
                    "procurement_request_budget_amount_krw",
                    "procurement_request_representative_amount_krw",
                    "procurement_request_total_service_budget_amount_krw",
                    "procurement_request_current_budget_amount_krw",
                )
            )
            if status_means_collected(row["procurement_request_data_status"]) and not request_present:
                false_complete_request_count += 1
            request_detail_present = any(
                row[field].strip()
                for field in (
                    "procurement_request_name",
                    "procurement_request_budget_amount_krw",
                    "procurement_request_representative_amount_krw",
                    "procurement_request_total_service_budget_amount_krw",
                    "procurement_request_current_budget_amount_krw",
                    "procurement_request_order_agency",
                    "procurement_request_input_date",
                )
            )
            if request_detail_present and not row["procurement_request_no"].strip():
                request_data_without_number.append(record_id or "(식별자 없음)")

            normal_awards = [
                item
                for item in award_rows_by_record.get(record_id, [])
                if item["parse_status"].strip() == "정상"
            ]
            normal_contracts = [
                item
                for item in contract_rows_by_record.get(record_id, [])
                if item["parse_status"].strip() == "정상"
            ]
            winner_count_text = row["winner_count"].strip()
            contract_count_text = row["contract_count"].strip()
            if winner_count_text.isdigit() and int(winner_count_text) != len(normal_awards):
                award_count_mismatches.append(record_id or "(식별자 없음)")
            if contract_count_text.isdigit() and int(contract_count_text) != len(normal_contracts):
                contract_count_mismatches.append(record_id or "(식별자 없음)")

            if len(normal_awards) == 1:
                detail = normal_awards[0]
                for summary_field, detail_field in (
                    ("winner_company", "winner_company"),
                    ("winner_business_no", "winner_business_no"),
                    ("award_amount_krw", "award_amount_krw"),
                    ("participant_count", "participant_count"),
                ):
                    if row[summary_field].strip() != detail[detail_field].strip():
                        award_count_mismatches.append(record_id or "(식별자 없음)")
                        break
            elif len(normal_awards) > 1 and any(
                row[field].strip()
                for field in ("winner_company", "winner_business_no", "award_amount_krw")
            ):
                unsafe_multiple_summaries.append(f"{record_id}:복수낙찰")

            if len(normal_contracts) == 1:
                detail = normal_contracts[0]
                if (
                    row["contract_amount_krw"].strip() != detail["contract_amount_krw"].strip()
                    or row["contract_date"].strip() != detail["contract_date"].strip()
                ):
                    contract_count_mismatches.append(record_id or "(식별자 없음)")
            elif len(normal_contracts) > 1 and any(
                row[field].strip() for field in ("contract_amount_krw", "contract_date")
            ):
                unsafe_multiple_summaries.append(f"{record_id}:복수계약")

        invalid_date_count = len(date_field_errors)
        if date_field_errors:
            add_warning(
                warnings,
                "invalid_date_value",
                "공고일이 비어 있거나 해석할 수 없는 날짜/시간이 있습니다.",
                invalid_date_count,
                date_field_errors,
            )
        outside_period_count = len(outside_period_rows)
        if outside_period_rows:
            add_warning(
                warnings,
                "notice_date_outside_period",
                "요청한 기간 밖의 공고일이 있습니다.",
                outside_period_count,
                sample_ids(outside_period_rows),
            )
        chronology_violation_count = len(chronology_rows)
        if chronology_rows:
            add_warning(
                warnings,
                "date_chronology_violation",
                "공고일 ≤ 마감일 ≤ 개찰일 순서를 위반한 공고가 있습니다.",
                chronology_violation_count,
                sample_ids(chronology_rows),
            )
        if year_mismatches:
            add_warning(
                warnings,
                "notice_year_mismatch",
                "notice_year와 공고일의 연도가 일치하지 않습니다.",
                len(year_mismatches),
                year_mismatches,
            )

        invalid_amount_count = len(amount_errors)
        if amount_errors:
            add_warning(
                warnings,
                "non_numeric_amount",
                "값은 있으나 숫자로 해석할 수 없는 금액이 있습니다.",
                invalid_amount_count,
                amount_errors,
            )
        negative_amount_count = len(negative_amounts)
        if negative_amounts:
            add_warning(
                warnings,
                "negative_amount",
                "음수 금액이 있습니다. 원본을 자동 수정하지 않았습니다.",
                negative_amount_count,
                negative_amounts,
            )

        if false_complete_participant_count:
            add_warning(
                warnings,
                "participant_status_without_data",
                "참여기업 값은 비어 있는데 참여기업 상태가 수집완료로 표시된 공고가 있습니다.",
                false_complete_participant_count,
            )
        if false_complete_award_count:
            add_warning(
                warnings,
                "award_status_without_data",
                "낙찰기업·낙찰금액은 비어 있는데 낙찰 상태가 수집완료로 표시된 공고가 있습니다.",
                false_complete_award_count,
            )
        if false_complete_contract_count:
            add_warning(
                warnings,
                "contract_status_without_data",
                "계약값과 정상 상세행은 비어 있는데 계약 상태가 수집완료로 표시된 공고가 있습니다.",
                false_complete_contract_count,
            )
        if false_complete_request_count:
            add_warning(
                warnings,
                "request_status_without_data",
                "조달요청 값은 비어 있는데 조달요청 상태가 수집완료로 표시된 공고가 있습니다.",
                false_complete_request_count,
            )
        request_data_without_number_count = len(set(request_data_without_number))
        if request_data_without_number:
            add_warning(
                warnings,
                "procurement_request_data_without_number",
                "조달요청 상세값은 있으나 조달요청번호가 비어 있어 추적 연결이 끊긴 공고가 있습니다.",
                request_data_without_number_count,
                sorted(set(request_data_without_number)),
            )
        award_count_mismatch_count = len(set(award_count_mismatches))
        if award_count_mismatches:
            add_warning(
                warnings,
                "award_detail_summary_mismatch",
                "공고의 낙찰 건수·단일 요약값이 낙찰 상세와 일치하지 않습니다.",
                award_count_mismatch_count,
                sorted(set(award_count_mismatches)),
            )
        contract_count_mismatch_count = len(set(contract_count_mismatches))
        if contract_count_mismatches:
            add_warning(
                warnings,
                "contract_detail_summary_mismatch",
                "공고의 계약 건수·단일 요약값이 계약 상세와 일치하지 않습니다.",
                contract_count_mismatch_count,
                sorted(set(contract_count_mismatches)),
            )
        unsafe_multiple_summary_count = len(set(unsafe_multiple_summaries))
        if unsafe_multiple_summaries:
            add_warning(
                warnings,
                "multiple_result_summarized_unsafely",
                "복수 낙찰·복수 계약 공고에 단일 기업 또는 금액이 채워져 있습니다. 임의 대표값·합산 여부를 확인하세요.",
                unsafe_multiple_summary_count,
                sorted(set(unsafe_multiple_summaries)),
            )

        if not notices:
            add_warning(
                warnings,
                "empty_notice_data",
                "공고 CSV에 데이터 행이 없습니다.",
            )

    if bidder_schema_ok:
        bidder_amount_errors: list[str] = []
        bidder_negative_amounts: list[str] = []
        for row in bidders:
            amount_status, _ = parse_amount(row["bid_amount_krw"])
            identifier = row["record_id"].strip() or row["bid_notice_no"].strip()
            if amount_status == "invalid":
                bidder_amount_errors.append(f"{identifier or '(식별자 없음)'}:bid_amount_krw")
            elif amount_status == "negative":
                bidder_negative_amounts.append(
                    f"{identifier or '(식별자 없음)'}:bid_amount_krw"
                )

        invalid_amount_count += len(bidder_amount_errors)
        negative_amount_count += len(bidder_negative_amounts)
        if bidder_amount_errors:
            add_warning(
                warnings,
                "non_numeric_bid_amount",
                "참여기업 CSV에 숫자로 해석할 수 없는 투찰금액이 있습니다.",
                len(bidder_amount_errors),
                bidder_amount_errors,
            )
        if bidder_negative_amounts:
            add_warning(
                warnings,
                "negative_bid_amount",
                "참여기업 CSV에 음수 투찰금액이 있습니다. 원본을 자동 수정하지 않았습니다.",
                len(bidder_negative_amounts),
                bidder_negative_amounts,
            )

        if notice_schema_ok:
            orphan_bidders = [
                row
                for row in bidders
                if row["record_id"].strip()
                and row["record_id"].strip() not in notice_ids
            ]
            orphan_bidder_count = len(orphan_bidders)
            if orphan_bidders:
                add_warning(
                    warnings,
                    "orphan_bidder_row",
                    "공고 CSV에 대응하는 record_id가 없는 참여기업 행이 있습니다.",
                    orphan_bidder_count,
                    sample_ids(orphan_bidders),
                )

    if award_schema_ok:
        award_keys = [
            (
                row["record_id"].strip(),
                row["contract_process_item_index"].strip(),
                row["winner_sequence"].strip(),
                row["raw_entry"].strip(),
            )
            for row in awards
        ]
        duplicate_award_keys = [key for key, count in Counter(award_keys).items() if count > 1]
        if duplicate_award_keys:
            add_warning(
                warnings,
                "duplicate_award_detail",
                "동일한 낙찰 상세행이 중복되어 있습니다.",
                len(duplicate_award_keys),
                ["|".join(key[:3]) for key in duplicate_award_keys],
            )
        orphan_awards = [
            row for row in awards
            if row["record_id"].strip() and row["record_id"].strip() not in notice_ids
        ]
        orphan_award_count = len(orphan_awards)
        if orphan_awards:
            add_warning(
                warnings,
                "orphan_award_row",
                "공고 CSV에 대응하는 record_id가 없는 낙찰 상세행이 있습니다.",
                orphan_award_count,
                sample_ids(orphan_awards),
            )
        award_amount_errors: list[str] = []
        award_negative_amounts: list[str] = []
        award_rate_errors: list[str] = []
        malformed_without_raw: list[str] = []
        order_mismatch_rows: list[str] = []
        for row in awards:
            identifier = row["record_id"].strip() or row["bid_notice_no"].strip()
            amount_status, _ = parse_amount(row["award_amount_krw"])
            if amount_status == "invalid":
                award_amount_errors.append(f"{identifier}:award_amount_krw")
            elif amount_status == "negative":
                award_negative_amounts.append(f"{identifier}:award_amount_krw")
            rate_status, rate = parse_amount(row["award_rate_pct"])
            if rate_status in {"invalid", "negative"} or (rate is not None and rate > 100):
                award_rate_errors.append(f"{identifier}:award_rate_pct")
            if row["parse_status"].strip() != "정상" and not row["raw_entry"].strip():
                malformed_without_raw.append(identifier or "(식별자 없음)")
            if row["exact_order_match_yn"].strip().upper() not in {"Y", ""}:
                order_mismatch_rows.append(identifier or "(식별자 없음)")
        invalid_amount_count += len(award_amount_errors)
        negative_amount_count += len(award_negative_amounts)
        if award_amount_errors:
            add_warning(
                warnings,
                "invalid_award_amount",
                "낙찰 상세에 숫자로 해석할 수 없는 낙찰금액이 있습니다.",
                len(award_amount_errors),
                award_amount_errors,
            )
        if award_negative_amounts:
            add_warning(
                warnings,
                "negative_award_amount",
                "낙찰 상세에 음수 낙찰금액이 있습니다. 원본을 자동 수정하지 않았습니다.",
                len(award_negative_amounts),
                award_negative_amounts,
            )
        if award_rate_errors:
            add_warning(
                warnings,
                "invalid_award_rate",
                "낙찰률이 숫자가 아니거나 0~100 범위를 벗어난 상세행이 있습니다.",
                len(award_rate_errors),
                award_rate_errors,
            )
        if malformed_without_raw:
            add_warning(
                warnings,
                "award_parse_error_without_raw",
                "낙찰 파싱 오류행인데 원문 항목이 보존되지 않았습니다.",
                len(malformed_without_raw),
                malformed_without_raw,
            )
        if order_mismatch_rows:
            add_warning(
                warnings,
                "award_order_not_exact",
                "공고차수 정확매칭이 아닌 낙찰행이 연결되어 있습니다.",
                len(order_mismatch_rows),
                order_mismatch_rows,
            )

    if contract_schema_ok:
        contract_keys = [
            (
                row["record_id"].strip(),
                row["contract_process_item_index"].strip(),
                row["contract_sequence"].strip(),
                row["raw_entry"].strip(),
            )
            for row in contracts
        ]
        duplicate_contract_keys = [
            key for key, count in Counter(contract_keys).items() if count > 1
        ]
        if duplicate_contract_keys:
            add_warning(
                warnings,
                "duplicate_contract_detail",
                "동일한 계약 상세행이 중복되어 있습니다.",
                len(duplicate_contract_keys),
                ["|".join(key[:3]) for key in duplicate_contract_keys],
            )
        orphan_contracts = [
            row for row in contracts
            if row["record_id"].strip() and row["record_id"].strip() not in notice_ids
        ]
        orphan_contract_count = len(orphan_contracts)
        if orphan_contracts:
            add_warning(
                warnings,
                "orphan_contract_row",
                "공고 CSV에 대응하는 record_id가 없는 계약 상세행이 있습니다.",
                orphan_contract_count,
                sample_ids(orphan_contracts),
            )
        contract_amount_errors: list[str] = []
        contract_negative_amounts: list[str] = []
        contract_malformed_without_raw: list[str] = []
        contract_order_mismatch_rows: list[str] = []
        for row in contracts:
            identifier = row["record_id"].strip() or row["bid_notice_no"].strip()
            amount_status, _ = parse_amount(row["contract_amount_krw"])
            if amount_status == "invalid":
                contract_amount_errors.append(f"{identifier}:contract_amount_krw")
            elif amount_status == "negative":
                contract_negative_amounts.append(f"{identifier}:contract_amount_krw")
            if row["parse_status"].strip() != "정상" and not row["raw_entry"].strip():
                contract_malformed_without_raw.append(identifier or "(식별자 없음)")
            if row["exact_order_match_yn"].strip().upper() not in {"Y", ""}:
                contract_order_mismatch_rows.append(identifier or "(식별자 없음)")
        invalid_amount_count += len(contract_amount_errors)
        negative_amount_count += len(contract_negative_amounts)
        if contract_amount_errors:
            add_warning(
                warnings,
                "invalid_contract_amount",
                "계약 상세에 숫자로 해석할 수 없는 계약금액이 있습니다.",
                len(contract_amount_errors),
                contract_amount_errors,
            )
        if contract_negative_amounts:
            add_warning(
                warnings,
                "negative_contract_amount",
                "계약 상세에 음수 계약금액이 있습니다. 원본을 자동 수정하지 않았습니다.",
                len(contract_negative_amounts),
                contract_negative_amounts,
            )
        if contract_malformed_without_raw:
            add_warning(
                warnings,
                "contract_parse_error_without_raw",
                "계약 파싱 오류행인데 원문 항목이 보존되지 않았습니다.",
                len(contract_malformed_without_raw),
                contract_malformed_without_raw,
            )
        if contract_order_mismatch_rows:
            add_warning(
                warnings,
                "contract_order_not_exact",
                "공고차수 정확매칭이 아닌 계약행이 연결되어 있습니다.",
                len(contract_order_mismatch_rows),
                contract_order_mismatch_rows,
            )

    if request_schema_ok:
        request_keys = [
            (
                row["procurement_request_no"].strip(),
                row["source_operation"].strip(),
            )
            for row in requests
        ]
        duplicate_requests = [
            key
            for key, count in Counter(request_keys).items()
            if key[0] and count > 1
        ]
        if duplicate_requests:
            add_warning(
                warnings,
                "duplicate_procurement_request",
                "같은 조달요청번호가 상세 CSV에 중복되어 있습니다.",
                len(duplicate_requests),
                ["|".join(key) for key in duplicate_requests],
            )
        blank_requests = [row for row in requests if not row["procurement_request_no"].strip()]
        if blank_requests:
            add_warning(
                warnings,
                "blank_procurement_request_no",
                "조달요청번호가 빈 상세행이 있습니다.",
                len(blank_requests),
            )
        request_amount_errors: list[str] = []
        request_negative_amounts: list[str] = []
        orphan_request_links: list[str] = []
        for row in requests:
            request_no = row["procurement_request_no"].strip() or "(번호 없음)"
            for field in (
                "budget_amount_krw",
                "representative_amount_krw",
                "total_service_budget_amount_krw",
                "current_budget_amount_krw",
            ):
                amount_status, _ = parse_amount(row[field])
                if amount_status == "invalid":
                    request_amount_errors.append(f"{request_no}:{field}")
                elif amount_status == "negative":
                    request_negative_amounts.append(f"{request_no}:{field}")
            linked_ids = [
                item.strip()
                for item in re.split(r"[|;,]", row["linked_record_ids"])
                if item.strip()
            ]
            orphan_request_links.extend(
                f"{request_no}:{record_id}"
                for record_id in linked_ids
                if record_id not in notice_ids
            )
        invalid_amount_count += len(request_amount_errors)
        negative_amount_count += len(request_negative_amounts)
        if request_amount_errors:
            add_warning(
                warnings,
                "invalid_procurement_request_amount",
                "조달요청 상세에 숫자로 해석할 수 없는 예산값이 있습니다.",
                len(request_amount_errors),
                request_amount_errors,
            )
        if request_negative_amounts:
            add_warning(
                warnings,
                "negative_procurement_request_amount",
                "조달요청 상세에 음수 예산값이 있습니다. 원본을 자동 수정하지 않았습니다.",
                len(request_negative_amounts),
                request_negative_amounts,
            )
        request_orphan_link_count = len(orphan_request_links)
        if orphan_request_links:
            add_warning(
                warnings,
                "orphan_procurement_request_link",
                "조달요청 상세의 연결 공고ID가 공고 CSV에 없습니다.",
                request_orphan_link_count,
                orphan_request_links,
            )

    access_status_counts: Counter[str] = Counter()
    api_services: list[dict[str, str]] = []
    collection_run_status = "(확인불가)"
    if access_schema_ok:
        service_counts = Counter(row["service_id"].strip() for row in access_rows)
        duplicate_service_ids = sorted(
            service_id
            for service_id, count in service_counts.items()
            if service_id and count > 1
        )
        if duplicate_service_ids:
            add_warning(
                warnings,
                "duplicate_access_service",
                "접근상태 CSV에 같은 service_id가 중복되어 있습니다.",
                len(duplicate_service_ids),
                duplicate_service_ids,
            )

        present_services = {row["service_id"].strip() for row in access_rows}
        missing_services = [
            service for service in EXPECTED_ACCESS_SERVICES if service not in present_services
        ]
        if missing_services:
            add_warning(
                warnings,
                "missing_access_service",
                "예상한 API/파일 접근상태 행이 없습니다.",
                len(missing_services),
                missing_services,
            )

        blocked_rows: list[str] = []
        for row in access_rows:
            service_id = row["service_id"].strip() or "(빈 service_id)"
            status = clean_value(row["access_status"])
            access_status_counts[status] += 1
            api_services.append(
                {
                    "service_id": service_id,
                    "service_name": row["service_name"].strip(),
                    "access_status": status,
                    "error_code": row["error_code"].strip(),
                }
            )
            if service_id == "collection_run":
                collection_run_status = status
            if status in {
                "활용신청필요",
                "권한확인필요",
                "오류",
                "미확인",
                "부분완료",
                "SSO로그인필요",
                "(빈값)",
            }:
                blocked_rows.append(f"{service_id}:{status}")

        if collection_run_status == "(확인불가)":
            add_warning(
                warnings,
                "missing_collection_run_status",
                "전체 공고 수집 완료 여부를 확인할 collection_run 행이 없습니다.",
            )
        elif collection_run_status != "완료":
            add_warning(
                warnings,
                "collection_not_complete",
                f"공고 수집 상태가 완료가 아닙니다: {collection_run_status}",
            )
        if blocked_rows:
            add_warning(
                warnings,
                "api_access_attention",
                "활용신청·권한확인·재수집 등이 필요한 접근상태가 있습니다.",
                len(blocked_rows),
                blocked_rows,
            )

    summary: dict[str, Any] = {
        "ok": not fatal_errors,
        "period": {
            "start_date": start_date.isoformat() if start_date else args.start_date,
            "end_date": end_date.isoformat() if end_date else args.end_date,
        },
        "files": {
            "notices_csv": str(args.notices_csv.resolve()),
            "awards_csv": str(args.awards_csv.resolve()),
            "contracts_csv": str(args.contracts_csv.resolve()),
            "requests_csv": str(args.requests_csv.resolve()),
            "bidders_csv": str(args.bidders_csv.resolve()),
            "access_csv": str(args.access_csv.resolve()),
        },
        "counts": {
            "notices": len(notices),
            "awards": len(awards),
            "contracts": len(contracts),
            "procurement_requests": len(requests),
            "bidders": len(bidders),
            "access_rows": len(access_rows),
            "duplicate_record_rows": duplicate_record_count,
            "blank_bid_notice_no": blank_bid_notice_count,
            "notice_date_outside_period": outside_period_count,
            "invalid_date_values": invalid_date_count,
            "chronology_violations": chronology_violation_count,
            "invalid_amount_values": invalid_amount_count,
            "negative_amount_values": negative_amount_count,
            "participant_status_without_data": false_complete_participant_count,
            "award_status_without_data": false_complete_award_count,
            "contract_status_without_data": false_complete_contract_count,
            "request_status_without_data": false_complete_request_count,
            "award_detail_summary_mismatch": award_count_mismatch_count,
            "contract_detail_summary_mismatch": contract_count_mismatch_count,
            "unsafe_multiple_summary": unsafe_multiple_summary_count,
            "orphan_award_rows": orphan_award_count,
            "orphan_contract_rows": orphan_contract_count,
            "orphan_procurement_request_links": request_orphan_link_count,
            "procurement_request_data_without_number": request_data_without_number_count,
            "orphan_bidder_rows": orphan_bidder_count,
        },
        "distributions": {
            "relevance_status": sorted_counter(relevance_counts),
            "notice_year": sorted_counter(year_counts),
            "categories": sorted_counter(category_counts),
            "access_status": sorted_counter(access_status_counts),
        },
        "api": {
            "collection_run_status": collection_run_status,
            "services": api_services,
        },
        "fatal_errors": fatal_errors,
        "warnings": warnings,
    }

    print("[QA] 최근 5개년 기후·온실가스 조달 추출 결과")
    print(
        f"[QA] 기간: {summary['period']['start_date']} ~ {summary['period']['end_date']}"
    )
    print(
        f"[QA] 행수: 공고 {len(notices):,}건 / 낙찰 {len(awards):,}건 / "
        f"계약 {len(contracts):,}건 / 조달요청 {len(requests):,}건 / "
        f"참여기업 {len(bidders):,}건 / 접근상태 {len(access_rows):,}건"
    )
    print(
        "[QA] 핵심 이상 건수: "
        f"중복 {duplicate_record_count:,}, 기간외 {outside_period_count:,}, "
        f"일자순서 {chronology_violation_count:,}, 금액형식 {invalid_amount_count:,}, "
        f"음수금액 {negative_amount_count:,}"
    )
    print(f"[QA] 상태별: {json.dumps(sorted_counter(relevance_counts), ensure_ascii=False)}")
    print(f"[QA] 연도별: {json.dumps(sorted_counter(year_counts), ensure_ascii=False)}")
    print(f"[QA] 분류별: {json.dumps(sorted_counter(category_counts), ensure_ascii=False)}")
    print(
        f"[QA] API: 수집상태={collection_run_status}, "
        f"접근상태={json.dumps(sorted_counter(access_status_counts), ensure_ascii=False)}"
    )
    for error in fatal_errors:
        print(f"[치명] {error}")
    for warning in warnings:
        suffix = ""
        if warning.get("samples"):
            suffix = f" 예시={', '.join(warning['samples'])}"
        print(
            f"[경고] {warning['message']} (건수={warning['count']}){suffix}"
        )
    if fatal_errors:
        print(f"[QA] 결론: 구조적 치명 오류 {len(fatal_errors)}건 — 입력 파일/열을 확인하세요.")
    else:
        print(
            f"[QA] 결론: 구조적 치명 오류 없음, 경고 그룹 {len(warnings)}개. "
            "수치값은 자동 수정하지 않았습니다."
        )
    print("QA_JSON=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 1 if fatal_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
