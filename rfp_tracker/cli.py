from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .api_keys import get_api_key_status
from .companies import (
    discover_company_portals,
    fetch_krx_listed_companies,
    generate_homepage_sources,
    read_companies_csv,
    write_companies_csv,
    write_portal_candidates_csv,
)
from .config import enabled_sources, read_json
from .documents import (
    DOCUMENT_KIND_LABELS,
    list_document_rows,
    render_documents_report,
    write_documents_csv,
)
from .fetchers import build_fetcher
from .render import render_dashboard
from .storage import (
    connect,
    finish_run,
    list_notices,
    review_stats,
    start_run,
    update_notice_review,
    upsert_notice,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT_DIR / "configs" / "sources.example.json"
DEFAULT_KEYWORDS = ROOT_DIR / "configs" / "keywords.json"
DEFAULT_API_KEYS = ROOT_DIR / "configs" / "api_keys.example.json"
DEFAULT_COMPANY_UNIVERSE = ROOT_DIR / "data" / "krx_listed_companies.csv"
VALID_REVIEW_STATUSES = {
    "new",
    "watch",
    "interesting",
    "not_relevant",
    "submitted",
    "won",
    "lost",
    "closed",
}


def sync_command(args: argparse.Namespace) -> int:
    source_config = read_json(args.config)
    keyword_config = read_json(args.keywords)
    sources = enabled_sources(source_config)
    global_config = source_config.get("global", {})

    connection = connect(args.db)
    run_id = start_run(connection, len(sources))
    all_notices = []
    inserted_count = 0
    status = "success"
    message = ""

    try:
        for source in sources:
            fetcher = build_fetcher(source, keyword_config, global_config, ROOT_DIR)
            notices = fetcher.fetch(days=args.days)
            print(f"[sync] {source['id']}: 후보 {len(notices)}건")
            for notice in notices:
                inserted = upsert_notice(connection, notice)
                if inserted:
                    inserted_count += 1
            all_notices.extend(notices)
    except Exception as exc:  # noqa: BLE001 - CLI는 사용자에게 명확히 보여주는 것이 중요합니다.
        status = "failed"
        message = str(exc)
        finish_run(connection, run_id, len(all_notices), inserted_count, status=status, message=message)
        print(f"[error] {message}", file=sys.stderr)
        return 1

    finish_run(connection, run_id, len(all_notices), inserted_count, status=status, message=message)
    print(f"[done] 수집 후보 {len(all_notices)}건, 신규 {inserted_count}건")
    return 0


def render_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    rows = list_notices(connection)
    render_dashboard(rows, args.out)
    print(f"[done] 대시보드 생성: {args.out} ({len(rows)}건)")
    return 0


def export_csv_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    rows = list_notices(connection)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "source_name",
                "notice_id",
                "review_status",
                "title",
                "url",
                "buyer",
                "published_at",
                "deadline_at",
                "procurement_method",
                "budget",
                "relevance_score",
                "matched_keywords",
                "review_note",
                "first_seen_at",
                "last_seen_at",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["source_name"],
                    row["id"],
                    row["review_status"],
                    row["title"],
                    row["url"],
                    row["buyer"],
                    row["published_at"],
                    row["deadline_at"],
                    row["procurement_method"],
                    row["budget"],
                    row["relevance_score"],
                    row["matched_keywords"],
                    row["review_note"],
                    row["first_seen_at"],
                    row["last_seen_at"],
                ]
            )
    print(f"[done] CSV 생성: {out_path} ({len(rows)}건)")
    return 0


def rfp_documents_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    rows = list_document_rows(
        connection,
        kind=args.kind,
        status=args.status,
        min_score=args.min_score,
        include_missing=not args.hide_missing,
    )
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("[documents] No document rows found.")
        return 0

    for row in rows:
        document_url = row["document_url"] or "MISSING"
        print(
            f"[notice={row['notice_id']}] kind={row['document_kind']} "
            f"status={row['review_status']} score={row['relevance_score']} "
            f"title={row['notice_title']} document={row['document_label'] or document_url}"
        )
    return 0


def render_documents_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    rows = list_document_rows(
        connection,
        kind=args.kind,
        status=args.status,
        min_score=args.min_score,
        include_missing=not args.hide_missing,
    )
    render_documents_report(rows, args.html)
    write_documents_csv(rows, args.csv)
    print(f"[done] RFP document HTML: {args.html} ({len(rows)} rows)")
    print(f"[done] RFP document CSV: {args.csv} ({len(rows)} rows)")
    return 0


def sources_command(args: argparse.Namespace) -> int:
    source_config = read_json(args.config)
    for source in source_config.get("sources", []):
        state = "ON " if source.get("enabled") else "OFF"
        print(f"[{state}] {source['id']} - {source['name']} ({source['type']})")
    return 0


def list_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    rows = list_notices(
        connection,
        status=args.status,
        min_score=args.min_score,
        limit=args.limit,
    )
    if not rows:
        print("[list] No notices found.")
        return 0
    for row in rows:
        print(
            f"[{row['id']}] score={row['relevance_score']} "
            f"status={row['review_status']} source={row['source_name']} title={row['title']}"
        )
    return 0


def review_command(args: argparse.Namespace) -> int:
    if args.status not in VALID_REVIEW_STATUSES:
        allowed = ", ".join(sorted(VALID_REVIEW_STATUSES))
        print(f"[error] Unknown status: {args.status}. Allowed: {allowed}", file=sys.stderr)
        return 2

    connection = connect(args.db)
    updated = update_notice_review(connection, args.id, args.status, args.note)
    if not updated:
        print(f"[error] Notice id not found: {args.id}", file=sys.stderr)
        return 1
    print(f"[done] Notice {args.id} marked as {args.status}")
    return 0


def stats_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    rows = review_stats(connection)
    total = sum(int(row["count"]) for row in rows)
    print(f"total={total}")
    for row in rows:
        print(f"{row['review_status']}={row['count']}")
    return 0


def api_keys_command(args: argparse.Namespace) -> int:
    key_config = read_json(args.config)
    statuses = get_api_key_status(key_config)
    for status in statuses:
        state = "PRESENT" if status.present else "MISSING"
        required_for = "; ".join(status.required_for)
        print(f"[{state}] {status.env} - {status.name}")
        print(f"  required_for: {required_for}")
        print(f"  apply_url: {status.apply_url}")
        if status.notes:
            print(f"  notes: {status.notes}")
    return 0


def companies_fetch_krx_command(args: argparse.Namespace) -> int:
    companies = fetch_krx_listed_companies(timeout=args.timeout)
    write_companies_csv(companies, args.out)
    with_homepage = sum(1 for company in companies if company.homepage)
    print(f"[done] KRX listed companies: {len(companies)} rows")
    print(f"[done] Companies with homepage: {with_homepage} rows")
    print(f"[done] Output: {args.out}")
    print("[note] Asset >= 2T filtering requires OPENDART_API_KEY or validated KIND financial extract.")
    return 0


def company_sources_command(args: argparse.Namespace) -> int:
    companies = read_companies_csv(args.input)
    limit = None if args.limit <= 0 else args.limit
    generate_homepage_sources(companies, args.out, limit=limit)
    print(f"[done] Company homepage source config generated: {args.out}")
    if limit:
        print(f"[note] Limited to first {limit} companies with homepage.")
    else:
        print("[note] Generated for all companies with homepage in input CSV.")
    return 0


def portal_discover_command(args: argparse.Namespace) -> int:
    companies = read_companies_csv(args.input)
    candidates = discover_company_portals(companies, limit=args.limit, timeout=args.timeout)
    write_portal_candidates_csv(candidates, args.out)
    status_counts: dict[str, int] = {}
    for candidate in candidates:
        status_counts[candidate.status] = status_counts.get(candidate.status, 0) + 1
    print(f"[done] Portal discovery output: {args.out}")
    for status, count in sorted(status_counts.items()):
        print(f"{status}={count}")
    print("[note] Results are candidates only. Confirm site terms and permissions before enabling crawling.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Climate/GHG/ETS consulting RFP tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync", help="출처에서 공고 후보를 수집해 SQLite에 저장")
    sync.add_argument("--config", default=str(DEFAULT_CONFIG))
    sync.add_argument("--keywords", default=str(DEFAULT_KEYWORDS))
    sync.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    sync.add_argument("--days", type=int, default=14)
    sync.set_defaults(func=sync_command)

    render = subparsers.add_parser("render", help="HTML 대시보드 생성")
    render.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    render.add_argument("--out", default=str(ROOT_DIR / "reports" / "dashboard.html"))
    render.set_defaults(func=render_command)

    export_csv = subparsers.add_parser("export-csv", help="Excel 확인용 CSV 생성")
    export_csv.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    export_csv.add_argument("--out", default=str(ROOT_DIR / "reports" / "notices.csv"))
    export_csv.set_defaults(func=export_csv_command)

    rfp_documents = subparsers.add_parser("rfp-documents", help="List collected RFP/document links")
    rfp_documents.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    rfp_documents.add_argument("--kind", choices=sorted(DOCUMENT_KIND_LABELS))
    rfp_documents.add_argument("--status", choices=sorted(VALID_REVIEW_STATUSES))
    rfp_documents.add_argument("--min-score", type=int)
    rfp_documents.add_argument("--limit", type=int, default=50)
    rfp_documents.add_argument("--hide-missing", action="store_true")
    rfp_documents.set_defaults(func=rfp_documents_command)

    render_documents = subparsers.add_parser("render-documents", help="Create RFP/document HTML and CSV reports")
    render_documents.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    render_documents.add_argument("--html", default=str(ROOT_DIR / "reports" / "rfp_documents.html"))
    render_documents.add_argument("--csv", default=str(ROOT_DIR / "reports" / "rfp_documents.csv"))
    render_documents.add_argument("--kind", choices=sorted(DOCUMENT_KIND_LABELS))
    render_documents.add_argument("--status", choices=sorted(VALID_REVIEW_STATUSES))
    render_documents.add_argument("--min-score", type=int)
    render_documents.add_argument("--hide-missing", action="store_true")
    render_documents.set_defaults(func=render_documents_command)

    sources = subparsers.add_parser("sources", help="수집 출처 목록 확인")
    sources.add_argument("--config", default=str(DEFAULT_CONFIG))
    sources.set_defaults(func=sources_command)

    list_parser = subparsers.add_parser("list", help="수집된 공고 후보 목록 확인")
    list_parser.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    list_parser.add_argument("--status", choices=sorted(VALID_REVIEW_STATUSES))
    list_parser.add_argument("--min-score", type=int)
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(func=list_command)

    review = subparsers.add_parser("review", help="공고 후보의 검토 상태와 메모 업데이트")
    review.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    review.add_argument("--id", type=int, required=True)
    review.add_argument("--status", required=True)
    review.add_argument("--note")
    review.set_defaults(func=review_command)

    stats = subparsers.add_parser("stats", help="검토 상태별 공고 수 요약")
    stats.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    stats.set_defaults(func=stats_command)

    api_keys = subparsers.add_parser("api-keys", help="외부 API 키 환경변수 상태 확인")
    api_keys.add_argument("--config", default=str(DEFAULT_API_KEYS))
    api_keys.set_defaults(func=api_keys_command)

    companies_fetch_krx = subparsers.add_parser(
        "companies-fetch-krx",
        help="KRX 공개 상장법인 목록을 CSV로 저장",
    )
    companies_fetch_krx.add_argument("--out", default=str(DEFAULT_COMPANY_UNIVERSE))
    companies_fetch_krx.add_argument("--timeout", type=int, default=30)
    companies_fetch_krx.set_defaults(func=companies_fetch_krx_command)

    company_sources = subparsers.add_parser(
        "company-sources",
        help="회사 홈페이지 CSV에서 비활성 generic_html 소스 설정 생성",
    )
    company_sources.add_argument("--input", default=str(DEFAULT_COMPANY_UNIVERSE))
    company_sources.add_argument("--out", default=str(ROOT_DIR / "configs" / "company_homepages.generated.json"))
    company_sources.add_argument("--limit", type=int, default=100)
    company_sources.set_defaults(func=company_sources_command)

    portal_discover = subparsers.add_parser(
        "portal-discover",
        help="공개 회사 홈페이지에서 구매/입찰/협력사 링크 후보 탐색",
    )
    portal_discover.add_argument("--input", default=str(DEFAULT_COMPANY_UNIVERSE))
    portal_discover.add_argument("--out", default=str(ROOT_DIR / "reports" / "portal_candidates.csv"))
    portal_discover.add_argument("--limit", type=int, default=20)
    portal_discover.add_argument("--timeout", type=int, default=15)
    portal_discover.set_defaults(func=portal_discover_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
