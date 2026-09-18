from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .api_keys import get_api_key_status
from .briefing import build_briefing, render_briefing_html, write_briefing_markdown
from .companies import (
    discover_company_portals,
    fetch_krx_listed_companies,
    generate_homepage_sources,
    read_companies_csv,
    write_companies_csv,
    write_portal_candidates_csv,
)
from .config import enabled_sources, load_dotenv, read_json, set_source_enabled, write_json
from .documents import (
    DOCUMENT_KIND_LABELS,
    list_document_rows,
    render_documents_report,
    write_documents_csv,
)
from .fetchers import build_fetcher
from .notifications import (
    dispatch_notifications,
    initialize_baseline,
    notification_status,
    read_notification_config,
    write_notification_config,
)
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
DEFAULT_LOCAL_CONFIG = ROOT_DIR / "configs" / "sources.local.json"
DEFAULT_KEYWORDS = ROOT_DIR / "configs" / "keywords.json"
DEFAULT_API_KEYS = ROOT_DIR / "configs" / "api_keys.example.json"
DEFAULT_COMPANY_UNIVERSE = ROOT_DIR / "data" / "krx_listed_companies.csv"
DEFAULT_NOTIFICATION_CONFIG = ROOT_DIR / "configs" / "notifications.local.json"
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


def briefing_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    briefing = build_briefing(
        connection,
        due_days=args.due_days,
        min_score=args.min_score,
        limit=args.limit,
    )
    render_briefing_html(briefing, args.html)
    write_briefing_markdown(briefing, args.markdown)
    summary = briefing["summary"]
    print(f"[done] 브리핑 HTML: {args.html}")
    print(f"[done] 브리핑 Markdown: {args.markdown}")
    print(
        "[summary] "
        f"전체={summary['total_notices']} 기준점수이상={summary['eligible_notices']} "
        f"오늘신규={summary['new_today']} D-{args.due_days}이내={summary['urgent']} "
        f"문서미수집={summary['missing_documents']}"
    )
    return 0


def _notification_recipients(args: argparse.Namespace, config: dict) -> list[str]:
    explicit = getattr(args, "recipient", None)
    return explicit if explicit else list(config.get("recipients", []))


def notifications_status_command(args: argparse.Namespace) -> int:
    config = read_notification_config(args.config)
    connection = connect(args.db)
    status = notification_status(connection, config)
    print("Climate RFP email notification readiness")
    print(f"config={args.config}")
    print(f"recipients={', '.join(status['recipients']) or 'MISSING'}")
    print(f"baseline_at={status['baseline_at'] or 'NOT_INITIALIZED'}")
    print(f"daily_send_at={status['daily_send_at']} KST")
    print(f"weekly={status['weekly_send_day']} {status['weekly_send_at']} KST")
    smtp_state = "READY" if status["smtp_ready"] else "MISSING"
    print(f"smtp={smtp_state}")
    if status["smtp_missing"]:
        print("smtp_missing=" + ", ".join(status["smtp_missing"]))
    if args.strict and (not status["recipients"] or not status["smtp_ready"]):
        return 1
    return 0


def notifications_init_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    baseline_at, created = initialize_baseline(connection)
    state = "created" if created else "already_exists"
    print(f"[done] notification baseline {state}: {baseline_at}")
    print("[note] 이 시각 이전에 수집된 공고는 신규 즉시알림으로 보내지지 않습니다.")
    return 0


def notifications_setup_command(args: argparse.Namespace) -> int:
    try:
        write_notification_config(args.out, args.recipient, overwrite=args.overwrite)
    except (FileExistsError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    print(f"[done] Local notification config created: {args.out}")
    print("[note] SMTP credential values still belong in .env and are not written to this file.")
    return 0


def notifications_dispatch_command(args: argparse.Namespace) -> int:
    config = read_notification_config(args.config)
    recipients = _notification_recipients(args, config)
    if not recipients:
        print("[error] No valid email recipient. Run notifications setup or pass --recipient.", file=sys.stderr)
        return 2

    connection = connect(args.db)
    try:
        results = dispatch_notifications(
            connection,
            recipients=recipients,
            mode=args.mode,
            min_score=args.min_score if args.min_score is not None else int(config["min_relevance_score"]),
            daily_send_at=str(config["daily_send_at"]),
            send=args.send,
        )
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    failed = False
    for result in results:
        print(
            f"[notification] recipient={result.recipient} mode={result.mode} "
            f"planned={result.planned} sent={result.sent} skipped={result.skipped} failed={result.failed} "
            f"baseline_initialized={result.baseline_initialized} message={result.message}"
        )
        failed = failed or bool(result.failed)
    return 1 if failed else 0


def sources_command(args: argparse.Namespace) -> int:
    source_config = read_json(args.config)
    for source in source_config.get("sources", []):
        state = "ON " if source.get("enabled") else "OFF"
        metadata = []
        if source.get("priority"):
            metadata.append(f"priority={source['priority']}")
        if source.get("authority"):
            metadata.append(f"authority={source['authority']}")
        suffix = f" | {', '.join(metadata)}" if metadata else ""
        print(f"[{state}] {source['id']} - {source['name']} ({source['type']}){suffix}")
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


def doctor_command(args: argparse.Namespace) -> int:
    source_config = read_json(args.config)
    key_config = read_json(args.keys)
    sources = source_config.get("sources", [])
    enabled = enabled_sources(source_config)
    key_statuses = get_api_key_status(key_config)
    key_by_env = {status.env: status for status in key_statuses}

    print("Climate RFP Tracker readiness check")
    print(f"config={args.config}")
    print(f"sources_total={len(sources)}")
    print(f"sources_enabled={len(enabled)}")

    has_issue = False
    for source in sources:
        state = "ON " if source.get("enabled") else "OFF"
        print(f"[{state}] {source.get('id')} - {source.get('type')}")
        env_name = source.get("service_key_env")
        if source.get("enabled") and env_name:
            key_status = key_by_env.get(env_name)
            if not key_status or not key_status.present:
                has_issue = True
                print(f"  issue: missing required environment variable {env_name}")

    for status in key_statuses:
        state = "PRESENT" if status.present else "MISSING"
        print(f"[{state}] {status.env}")

    if has_issue:
        print("[ready] NO - fix the issue lines above before live sync.")
        return 1 if args.strict else 0

    print("[ready] YES - enabled sources have the required key configuration.")
    return 0


def source_toggle_command(args: argparse.Namespace) -> int:
    if args.enable == args.disable:
        print("[error] Use either --enable or --disable.", file=sys.stderr)
        return 2

    source_config = read_json(args.config)
    enabled = bool(args.enable)
    updated = set_source_enabled(source_config, args.source_id, enabled)
    if not updated:
        print(f"[error] Source id not found: {args.source_id}", file=sys.stderr)
        return 1

    write_json(args.out, source_config)
    state = "enabled" if enabled else "disabled"
    print(f"[done] Source {args.source_id} {state}")
    print(f"[done] Output config: {args.out}")
    if str(args.out) != str(args.config):
        print("[note] Original config was not overwritten.")
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

    briefing = subparsers.add_parser("briefing", help="Create daily climate RFP briefing HTML and Markdown")
    briefing.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    briefing.add_argument("--html", default=str(ROOT_DIR / "reports" / "briefing.html"))
    briefing.add_argument("--markdown", default=str(ROOT_DIR / "reports" / "briefing.md"))
    briefing.add_argument("--due-days", type=int, default=7)
    briefing.add_argument("--min-score", type=int, default=3)
    briefing.add_argument("--limit", type=int, default=20)
    briefing.set_defaults(func=briefing_command)

    notifications = subparsers.add_parser("notifications", help="Configure, preview, and send email alerts")
    notification_commands = notifications.add_subparsers(dest="notification_command", required=True)

    notifications_status = notification_commands.add_parser("status", help="Check email notification readiness")
    notifications_status.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    notifications_status.add_argument("--config", default=str(DEFAULT_NOTIFICATION_CONFIG))
    notifications_status.add_argument("--strict", action="store_true")
    notifications_status.set_defaults(func=notifications_status_command)

    notifications_init = notification_commands.add_parser("init", help="Set the no-history baseline for new notice alerts")
    notifications_init.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    notifications_init.set_defaults(func=notifications_init_command)

    notifications_setup = notification_commands.add_parser("setup", help="Create a local recipient configuration")
    notifications_setup.add_argument("--out", default=str(DEFAULT_NOTIFICATION_CONFIG))
    notifications_setup.add_argument("--recipient", action="append", required=True)
    notifications_setup.add_argument("--overwrite", action="store_true")
    notifications_setup.set_defaults(func=notifications_setup_command)

    notifications_dispatch = notification_commands.add_parser("dispatch", help="Preview or send immediate/daily/weekly emails")
    notifications_dispatch.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    notifications_dispatch.add_argument("--config", default=str(DEFAULT_NOTIFICATION_CONFIG))
    notifications_dispatch.add_argument("--recipient", action="append")
    notifications_dispatch.add_argument("--mode", choices=["immediate", "daily", "weekly", "test"], required=True)
    notifications_dispatch.add_argument("--min-score", type=int)
    notifications_dispatch.add_argument("--send", action="store_true", help="Actually send mail through configured SMTP")
    notifications_dispatch.set_defaults(func=notifications_dispatch_command)

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

    doctor = subparsers.add_parser("doctor", help="Check whether live sync is ready")
    doctor.add_argument("--config", default=str(DEFAULT_CONFIG))
    doctor.add_argument("--keys", default=str(DEFAULT_API_KEYS))
    doctor.add_argument("--strict", action="store_true", help="Return non-zero when live readiness issues exist")
    doctor.set_defaults(func=doctor_command)

    source_toggle = subparsers.add_parser("source-toggle", help="Enable or disable a source in a copied config file")
    source_toggle.add_argument("--config", default=str(DEFAULT_CONFIG))
    source_toggle.add_argument("--out", default=str(DEFAULT_LOCAL_CONFIG))
    source_toggle.add_argument("--source-id", required=True)
    source_toggle.add_argument("--enable", action="store_true")
    source_toggle.add_argument("--disable", action="store_true")
    source_toggle.set_defaults(func=source_toggle_command)

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
    load_dotenv(ROOT_DIR / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
