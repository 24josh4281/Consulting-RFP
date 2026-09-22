from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .api_keys import get_api_key_status
from .briefing import (
    build_briefing,
    deadline_priority_label,
    parse_notice_datetime,
    render_briefing_html,
    seoul_now,
    write_briefing_markdown,
)
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
    backfill_g2b_attachments,
    build_public_workbench_payload,
    build_workbench_payload,
    extract_document_insights,
    list_document_rows,
    render_documents_report,
    write_workbench_json,
    write_documents_csv,
)
from .fetchers import build_fetcher
from .keyword_matcher import assess_g2b_title, is_climate_related_title
from .notifications import (
    dispatch_notifications,
    initialize_baseline,
    notification_status,
    read_notification_config,
    write_notification_config,
)
from .render import render_workbench_dashboard
from .storage import (
    VALID_BID_DECISIONS,
    VALID_CONSULTING_FITS,
    connect,
    delete_notices,
    finish_run,
    get_bid_fit_review,
    finish_g2b_open_reconciliation,
    list_bid_fit_reviews,
    list_notices,
    review_stats,
    start_run,
    start_g2b_open_reconciliation,
    tier_stats,
    update_notice_tier,
    update_notice_review,
    upsert_bid_fit_review,
    upsert_notice,
)
from .tiering import VALID_BUSINESS_TIERS, assess_innergen_tier, tier_label


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT_DIR / "configs" / "sources.example.json"
DEFAULT_LOCAL_CONFIG = ROOT_DIR / "configs" / "sources.local.json"
DEFAULT_KEYWORDS = ROOT_DIR / "configs" / "keywords.json"
DEFAULT_API_KEYS = ROOT_DIR / "configs" / "api_keys.example.json"
DEFAULT_COMPANY_UNIVERSE = ROOT_DIR / "data" / "krx_listed_companies.csv"
DEFAULT_NOTIFICATION_CONFIG = ROOT_DIR / "configs" / "notifications.local.json"
VALID_REVIEW_STATUSES = {
    "new",
    "needs_review",
    "watch",
    "interesting",
    "not_relevant",
    "submitted",
    "won",
    "lost",
    "closed",
}


SEOUL_TZ = ZoneInfo("Asia/Seoul")


def reconcile_open_g2b_command(args: argparse.Namespace) -> int:
    source_config = read_json(args.config)
    keyword_config = read_json(args.keywords)
    global_config = source_config.get("global", {})
    g2b_sources = [
        source
        for source in enabled_sources(source_config)
        if source.get("type") == "g2b_bid_api"
    ]
    if not g2b_sources:
        print("[skip] 활성화된 나라장터 API 출처가 없습니다.")
        return 0

    run_date = datetime.now(SEOUL_TZ).date().isoformat()
    connection = connect(args.db)
    if not start_g2b_open_reconciliation(connection, run_date, force=args.force):
        if not args.quiet_if_done:
            print(f"[skip] {run_date} 나라장터 현재공고 보정 조회는 이미 완료했거나 진행 중입니다.")
        connection.close()
        return 0

    candidate_count = 0
    inserted_count = 0
    try:
        days = args.days or int(global_config.get("g2b_open_reconcile_days", 90))
        max_pages = int(global_config.get("g2b_open_reconcile_max_pages_per_term", 3))
        collect_all_current = bool(global_config.get("g2b_open_collect_all_current", False))
        max_pages_per_query = int(global_config.get("g2b_open_unfiltered_max_pages_per_query", 100))
        max_requests = int(global_config.get("g2b_open_reconcile_max_requests", 500))
        terms = list(global_config.get("g2b_open_search_terms", []))
        closed_exclusion = str(
            global_config.get("g2b_open_reconcile_closed_notice_exclusion", "Y")
        )
        for source in g2b_sources:
            fetcher = build_fetcher(source, keyword_config, global_config, ROOT_DIR)
            notices = fetcher.fetch_open_notices(
                days=days,
                search_terms=terms,
                max_pages_per_term=max_pages,
                closed_notice_exclusion=closed_exclusion,
                include_all_notices=collect_all_current,
                max_pages_per_query=max_pages_per_query,
                max_requests=max_requests,
            )
            print(f"[reconcile] {source['id']}: 현재 유효 후보 {len(notices)}건")
            for notice in notices:
                assessment = assess_innergen_tier(notice.title, category=notice.category)
                notice.business_tier = assessment.tier
                notice.tier_reason = assessment.reason
                notice.tier_source = "automatic"
                if upsert_notice(connection, notice):
                    inserted_count += 1
                candidate_count += 1
        finish_g2b_open_reconciliation(
            connection,
            run_date,
            candidate_count=candidate_count,
            inserted_count=inserted_count,
            status="success",
            message="",
        )
        print(
            f"[done] 나라장터 현재공고 보정 조회: {candidate_count}개 후보, "
            f"신규 {inserted_count}건, 기간 {days}일, "
            f"조회범위={'전체 현재공고' if collect_all_current else '검색어 일치'}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - 기록된 에러는 예외 종류만 보여 줍니다.
        finish_g2b_open_reconciliation(
            connection,
            run_date,
            candidate_count=candidate_count,
            inserted_count=inserted_count,
            status="failed",
            message=type(exc).__name__,
        )
        print(f"[warn] 나라장터 현재공고 보정 조회 실패 ({type(exc).__name__}).")
        return 0 if args.best_effort else 1
    finally:
        connection.close()


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
                assessment = assess_innergen_tier(
                    notice.title,
                    category=notice.category,
                )
                notice.business_tier = assessment.tier
                notice.tier_reason = assessment.reason
                notice.tier_source = "automatic"
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
    payload = build_workbench_payload(connection)
    render_workbench_dashboard(payload, args.out)
    print(f"[done] 공고 작업대 생성: {args.out} ({len(payload['notices'])}건)")
    return 0


def extract_documents_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    outcomes = extract_document_insights(
        connection,
        cache_dir=args.cache_dir,
        limit=args.limit,
        file_type=args.file_type,
    )
    counts: dict[str, int] = {}
    for outcome in outcomes:
        status = str(outcome["extraction_status"])
        counts[status] = counts.get(status, 0) + 1
    print(f"[done] 문서 추출 상태 갱신: {len(outcomes)}건")
    for status, count in sorted(counts.items()):
        print(f"{status}={count}")
    print("[note] 원문 공고, 첨부, 검토/Tier, 알림 발송 기록은 변경하지 않았습니다.")
    return 0


def backfill_g2b_attachments_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    summary = backfill_g2b_attachments(connection)
    print(
        "[done] 나라장터 저장 응답의 명시적 첨부 링크 복원: "
        f"processed={summary['processed_notices']} "
        f"with_links={summary['with_explicit_attachments']} "
        f"added={summary['added']} updated={summary['updated']} "
        f"deduplicated={summary['deduplicated']}"
    )
    if summary["invalid_raw_json"]:
        print(f"[warn] raw JSON을 읽지 못한 공고: {summary['invalid_raw_json']}건")
    if summary["without_explicit_attachments"]:
        print(f"[note] 명시적 첨부 URL이 없던 공고: {summary['without_explicit_attachments']}건")
    print("[note] 원문 공고, 검토 상태, Tier, 기존 문서 요약·금액 근거는 변경하지 않았습니다.")
    return 0


def render_workbench_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    payload = build_public_workbench_payload(connection) if args.public else build_workbench_payload(connection)
    render_workbench_dashboard(payload, args.out, public=args.public)
    scope = "공개용 공고 작업대" if args.public else "공고 작업대"
    print(f"[done] {scope} 생성: {args.out} ({len(payload['notices'])}건)")
    return 0


def export_workbench_json_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    payload = build_workbench_payload(connection)
    write_workbench_json(payload, args.out)
    print(f"[done] Excel 입력 JSON 생성: {args.out}")
    print(f"[note] notices={len(payload['notices'])}, documents={len(payload['documents'])}")
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
                "business_tier",
                "tier_reason",
                "tier_source",
                "title",
                "url",
                "buyer",
                "published_at",
                "deadline_at",
                "deadline_priority",
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
                    row["business_tier"],
                    row["tier_reason"],
                    row["tier_source"],
                    row["title"],
                    row["url"],
                    row["buyer"],
                    row["published_at"],
                    row["deadline_at"],
                    deadline_priority_label(
                        (deadline.date() - seoul_now().date()).days
                        if (deadline := parse_notice_datetime(row["deadline_at"]))
                        else None
                    ),
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
        business_tier=args.tier,
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
            f"tier={row['business_tier']} status={row['review_status']} score={row['relevance_score']} "
            f"title={row['notice_title']} document={row['document_label'] or document_url}"
        )
    return 0


def render_documents_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    rows = list_document_rows(
        connection,
        kind=args.kind,
        status=args.status,
        business_tier=args.tier,
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
    print(f"daily_send_times={', '.join(status['daily_send_times'])} KST")
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

    daily_slot = None
    if args.mode == "daily":
        configured_slots = list(config["daily_send_times"])
        daily_slot = args.daily_slot
        if not daily_slot:
            if len(configured_slots) == 1:
                daily_slot = configured_slots[0]
            else:
                print(
                    "[error] Choose a configured daily slot, for example: --daily-slot 10:00",
                    file=sys.stderr,
                )
                return 2
        if daily_slot not in configured_slots:
            print(
                "[error] daily slot must be listed in notification config: " + ", ".join(configured_slots),
                file=sys.stderr,
            )
            return 2
    elif args.daily_slot:
        print("[error] --daily-slot can only be used with --mode daily.", file=sys.stderr)
        return 2

    connection = connect(args.db)
    try:
        results = dispatch_notifications(
            connection,
            recipients=recipients,
            mode=args.mode,
            min_score=args.min_score if args.min_score is not None else int(config["min_relevance_score"]),
            daily_slot=daily_slot,
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
        business_tier=args.tier,
        min_score=args.min_score,
        limit=args.limit,
    )
    if not rows:
        print("[list] No notices found.")
        return 0
    for row in rows:
        print(
            f"[{row['id']}] score={row['relevance_score']} "
            f"tier={row['business_tier']} status={row['review_status']} "
            f"source={row['source_name']} title={row['title']}"
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


def tier_command(args: argparse.Namespace) -> int:
    if args.tier not in VALID_BUSINESS_TIERS:
        allowed = ", ".join(sorted(VALID_BUSINESS_TIERS))
        print(f"[error] Unknown tier: {args.tier}. Allowed: {allowed}", file=sys.stderr)
        return 2
    reason = (args.reason or "").strip()
    if not reason:
        print("[error] A short manual tier reason is required.", file=sys.stderr)
        return 2

    connection = connect(args.db)
    updated = update_notice_tier(connection, args.id, args.tier, reason, tier_source="manual")
    if not updated:
        print(f"[error] Notice id not found: {args.id}", file=sys.stderr)
        return 1
    print(f"[done] Notice {args.id} classified as {args.tier} (manual): {tier_label(args.tier)}")
    return 0


def fit_review_set_command(args: argparse.Namespace) -> int:
    provided = [
        args.consulting_fit,
        args.qualifications,
        args.team,
        args.decision,
        args.risks,
        args.note,
    ]
    if not any(value is not None for value in provided):
        print("[error] 저장할 적합성 검토 항목을 하나 이상 입력하세요.", file=sys.stderr)
        return 2
    connection = connect(args.db)
    existing = get_bid_fit_review(connection, args.id)
    defaults = {
        "consulting_fit": "not_reviewed",
        "qualification_requirements": "",
        "proposed_team": "",
        "bid_decision": "pending",
        "key_risks": "",
        "decision_note": "",
    }
    current = {
        key: str(existing[key] or default) if existing else default
        for key, default in defaults.items()
    }
    values = {
        "consulting_fit": args.consulting_fit if args.consulting_fit is not None else current["consulting_fit"],
        "qualification_requirements": args.qualifications if args.qualifications is not None else current["qualification_requirements"],
        "proposed_team": args.team if args.team is not None else current["proposed_team"],
        "bid_decision": args.decision if args.decision is not None else current["bid_decision"],
        "key_risks": args.risks if args.risks is not None else current["key_risks"],
        "decision_note": args.note if args.note is not None else current["decision_note"],
    }
    try:
        updated = upsert_bid_fit_review(connection, notice_id=args.id, **values)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    if not updated:
        print(f"[error] Notice id not found: {args.id}", file=sys.stderr)
        return 1
    print(
        f"[done] Notice {args.id} bid-fit review saved: "
        f"fit={values['consulting_fit']} decision={values['bid_decision']}"
    )
    print("[note] 원문 공고, 첨부, 금액 근거, 검토 상태, Tier는 변경하지 않았습니다.")
    return 0


def fit_review_list_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    rows = list_bid_fit_reviews(connection)
    if not rows:
        print("[fit-review] 저장된 입찰 적합성 검토표가 없습니다.")
        return 0
    for row in rows:
        print(
            f"[notice={row['notice_id']}] tier={row['business_tier']} "
            f"fit={row['consulting_fit']} decision={row['bid_decision']} "
            f"title={row['notice_title']}"
        )
    return 0


def tier_audit_command(args: argparse.Namespace) -> int:
    """Preview or backfill automatic business tiers without changing raw notices."""
    connection = connect(args.db)
    rows = list_notices(connection)
    counts = {tier: 0 for tier in VALID_BUSINESS_TIERS}
    automatic_rows = 0
    manual_preserved = 0
    changed = 0

    for row in rows:
        if str(row["tier_source"] or "automatic") == "manual":
            manual_preserved += 1
            counts[str(row["business_tier"] or "unclassified")] = (
                counts.get(str(row["business_tier"] or "unclassified"), 0) + 1
            )
            continue

        automatic_rows += 1
        assessment = assess_innergen_tier(
            str(row["title"] or ""),
            category=str(row["category"] or ""),
        )
        counts[assessment.tier] = counts.get(assessment.tier, 0) + 1
        is_changed = (
            str(row["business_tier"] or "unclassified") != assessment.tier
            or str(row["tier_reason"] or "") != assessment.reason
            or str(row["tier_source"] or "automatic") != "automatic"
        )
        if args.apply and is_changed:
            update_notice_tier(
                connection,
                int(row["id"]),
                assessment.tier,
                assessment.reason,
                tier_source="automatic",
            )
            changed += 1

    print(
        "[tier-audit] "
        f"total={len(rows)} automatic={automatic_rows} manual_preserved={manual_preserved} "
        f"tier_1={counts.get('tier_1', 0)} tier_2={counts.get('tier_2', 0)} "
        f"tier_3={counts.get('tier_3', 0)} unclassified={counts.get('unclassified', 0)} "
        f"applied={changed}"
    )
    if not args.apply:
        print("[note] No notice changed. Re-run with --apply to save only automatic Tier metadata.")
    else:
        print("[note] Raw source text, review status, attachments, and notification delivery records were preserved.")
    return 0


def g2b_title_audit_command(args: argparse.Namespace) -> int:
    """Safely quarantine existing broad G2B matches without deleting source data."""
    keyword_config = read_json(args.keywords)
    connection = connect(args.db)
    rows = connection.execute(
        """
        SELECT id, title, review_status
        FROM notices
        WHERE substr(source_id, 1, 4) = 'g2b_'
        ORDER BY id ASC
        """
    ).fetchall()
    tier_counts = {"strong": 0, "needs_review": 0, "ignore": 0}
    candidates: list[int] = []
    for row in rows:
        assessment = assess_g2b_title(str(row["title"]), keyword_config)
        tier_counts[assessment.tier] = tier_counts.get(assessment.tier, 0) + 1
        if assessment.tier != "strong" and str(row["review_status"]) == "new":
            candidates.append(int(row["id"]))

    changed = 0
    if args.apply:
        for notice_id in candidates:
            update_notice_review(
                connection,
                notice_id,
                "needs_review",
                "공고명 기준 관련성이 불확실하여 자동 알림에서 제외했습니다. 원문을 확인해 검토 상태를 변경하세요.",
            )
            changed += 1

    print(
        "[g2b-title-audit] "
        f"total={len(rows)} strong={tier_counts['strong']} "
        f"needs_review={tier_counts['needs_review']} ignore={tier_counts['ignore']} "
        f"eligible_for_quarantine={len(candidates)} applied={changed}"
    )
    if not args.apply:
        print("[note] No notice changed. Re-run with --apply to mark only current new items as needs_review.")
    else:
        print("[note] Source text and delivery records were preserved; only review status/note changed.")
    return 0


def prune_non_climate_command(args: argparse.Namespace) -> int:
    """Remove stored notices outside the configured climate/environment scope."""
    keyword_config = read_json(args.keywords)
    connection = connect(args.db)
    rows = connection.execute(
        "SELECT id, source_id, title, business_tier, review_status FROM notices ORDER BY id ASC"
    ).fetchall()
    remove_ids: list[int] = []
    reason_counts = {"excluded_term": 0, "no_domain_signal": 0}
    for row in rows:
        title = str(row["title"] or "")
        if not is_climate_related_title(title, keyword_config):
            remove_ids.append(int(row["id"]))
            if any(term.casefold() in title.casefold() for term in keyword_config.get("exclude_terms", [])):
                reason_counts["excluded_term"] += 1
            else:
                reason_counts["no_domain_signal"] += 1

    print(
        "[prune-non-climate] "
        f"total={len(rows)} remove={len(remove_ids)} keep={len(rows) - len(remove_ids)} "
        f"excluded_term={reason_counts['excluded_term']} "
        f"no_domain_signal={reason_counts['no_domain_signal']}"
    )
    if not args.apply:
        print("[note] No notice changed. Re-run with --apply after reviewing the counts.")
        return 0

    deleted = delete_notices(connection, remove_ids)
    print(f"[done] 비관련 공고 삭제: {deleted}건")
    print("[note] 첨부·문서 추출·입찰 적합성 기록은 해당 공고와 함께 삭제되며, 메일 발송 이력은 보존됩니다.")
    return 0


def stats_command(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    rows = review_stats(connection)
    total = sum(int(row["count"]) for row in rows)
    print(f"total={total}")
    for row in rows:
        print(f"{row['review_status']}={row['count']}")
    print("tiers:")
    for row in tier_stats(connection):
        print(f"{row['business_tier']}={row['count']}")
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

    reconcile_open_g2b = subparsers.add_parser(
        "reconcile-open-g2b",
        help="나라장터 90일 범위의 기한 미경과 기후·환경 입찰을 하루 한 번 보정 수집",
    )
    reconcile_open_g2b.add_argument("--config", default=str(DEFAULT_LOCAL_CONFIG))
    reconcile_open_g2b.add_argument("--keywords", default=str(DEFAULT_KEYWORDS))
    reconcile_open_g2b.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker_official.db"))
    reconcile_open_g2b.add_argument("--days", type=int, help="기본값은 source config의 G2B 보정 조회 기간입니다.")
    reconcile_open_g2b.add_argument("--force", action="store_true", help="오늘 실행 기록이 있어도 다시 조회합니다.")
    reconcile_open_g2b.add_argument("--best-effort", action="store_true", help="실패해도 주기 수집을 계속할 수 있도록 종료 코드를 0으로 반환합니다.")
    reconcile_open_g2b.add_argument("--quiet-if-done", action="store_true", help="오늘 이미 처리했다면 출력 없이 종료합니다.")
    reconcile_open_g2b.set_defaults(func=reconcile_open_g2b_command)

    render = subparsers.add_parser("render", help="전체 공고 작업대 HTML 생성")
    render.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    render.add_argument("--out", default=str(ROOT_DIR / "reports" / "dashboard.html"))
    render.set_defaults(func=render_command)

    extract_documents = subparsers.add_parser(
        "extract-documents",
        help="수집된 직접 공개 문서에서 과업 요약과 금액 근거를 추출",
    )
    extract_documents.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    extract_documents.add_argument(
        "--cache-dir",
        default=str(ROOT_DIR / "data" / "document_cache"),
        help="공개 원문 cache 폴더. 원문 공고/첨부 DB 값은 변경하지 않습니다.",
    )
    extract_documents.add_argument("--limit", type=int, help="처리할 문서 행 수 제한")
    extract_documents.add_argument(
        "--file-type",
        help="특정 확장자의 직접 공개 문서만 처리합니다. 예: hwpx",
    )
    extract_documents.set_defaults(func=extract_documents_command)

    backfill_g2b = subparsers.add_parser(
        "backfill-g2b-attachments",
        help="저장된 나라장터 API 원본에서 명시적 RFP·과업지시서 첨부 링크 복원",
    )
    backfill_g2b.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    backfill_g2b.set_defaults(func=backfill_g2b_attachments_command)

    render_workbench = subparsers.add_parser(
        "render-workbench",
        help="Tier·문서·금액 근거를 포함한 전체 공고 작업대 HTML 생성",
    )
    render_workbench.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    render_workbench.add_argument(
        "--out",
        default=str(ROOT_DIR / "reports" / "rfp_workbench.html"),
    )
    render_workbench.add_argument(
        "--public",
        action="store_true",
        help="사람 검토·Tier·로컬 경로를 제외한 공개용 정적 작업대를 만듭니다.",
    )
    render_workbench.set_defaults(func=render_workbench_command)

    export_workbench_json = subparsers.add_parser(
        "export-workbench-json",
        help="Excel 작업대 생성을 위한 비밀 없는 JSON 데이터 생성",
    )
    export_workbench_json.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    export_workbench_json.add_argument(
        "--out",
        default=str(ROOT_DIR / "reports" / "rfp_workbench_data.json"),
    )
    export_workbench_json.set_defaults(func=export_workbench_json_command)

    export_csv = subparsers.add_parser("export-csv", help="Excel 확인용 CSV 생성")
    export_csv.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    export_csv.add_argument("--out", default=str(ROOT_DIR / "reports" / "notices.csv"))
    export_csv.set_defaults(func=export_csv_command)

    rfp_documents = subparsers.add_parser("rfp-documents", help="List collected RFP/document links")
    rfp_documents.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    rfp_documents.add_argument("--kind", choices=sorted(DOCUMENT_KIND_LABELS))
    rfp_documents.add_argument("--status", choices=sorted(VALID_REVIEW_STATUSES))
    rfp_documents.add_argument("--tier", choices=sorted(VALID_BUSINESS_TIERS))
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
    render_documents.add_argument("--tier", choices=sorted(VALID_BUSINESS_TIERS))
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
    notifications_dispatch.add_argument(
        "--daily-slot",
        help="Configured daily briefing slot in HH:MM format, for example 10:00.",
    )
    notifications_dispatch.add_argument("--min-score", type=int)
    notifications_dispatch.add_argument("--send", action="store_true", help="Actually send mail through configured SMTP")
    notifications_dispatch.set_defaults(func=notifications_dispatch_command)

    sources = subparsers.add_parser("sources", help="수집 출처 목록 확인")
    sources.add_argument("--config", default=str(DEFAULT_CONFIG))
    sources.set_defaults(func=sources_command)

    list_parser = subparsers.add_parser("list", help="수집된 공고 후보 목록 확인")
    list_parser.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    list_parser.add_argument("--status", choices=sorted(VALID_REVIEW_STATUSES))
    list_parser.add_argument("--tier", choices=sorted(VALID_BUSINESS_TIERS))
    list_parser.add_argument("--min-score", type=int)
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(func=list_command)

    review = subparsers.add_parser("review", help="공고 후보의 검토 상태와 메모 업데이트")
    review.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    review.add_argument("--id", type=int, required=True)
    review.add_argument("--status", required=True)
    review.add_argument("--note")
    review.set_defaults(func=review_command)

    tier = subparsers.add_parser("tier", help="공고의 이너젠 사업 적합 Tier를 수동 보정")
    tier.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    tier.add_argument("--id", type=int, required=True)
    tier.add_argument("--tier", choices=sorted(VALID_BUSINESS_TIERS), required=True)
    tier.add_argument("--reason", required=True, help="수동 분류 근거")
    tier.set_defaults(func=tier_command)

    fit_review = subparsers.add_parser(
        "fit-review",
        help="공고 원문과 분리된 입찰 적합성 검토표를 기록하거나 확인",
    )
    fit_review_commands = fit_review.add_subparsers(dest="fit_review_command", required=True)
    fit_review_set = fit_review_commands.add_parser("set", help="공고 한 건의 적합성 검토 항목 저장")
    fit_review_set.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    fit_review_set.add_argument("--id", type=int, required=True)
    fit_review_set.add_argument("--consulting-fit", choices=sorted(VALID_CONSULTING_FITS))
    fit_review_set.add_argument("--qualifications", help="필요 자격·등록·실적")
    fit_review_set.add_argument("--team", help="예상 투입인력 또는 역할")
    fit_review_set.add_argument("--decision", choices=sorted(VALID_BID_DECISIONS))
    fit_review_set.add_argument("--risks", help="핵심 위험·확인 필요사항")
    fit_review_set.add_argument("--note", help="입찰 검토 메모")
    fit_review_set.set_defaults(func=fit_review_set_command)
    fit_review_list = fit_review_commands.add_parser("list", help="저장된 적합성 검토표 목록")
    fit_review_list.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    fit_review_list.set_defaults(func=fit_review_list_command)

    tier_audit = subparsers.add_parser(
        "tier-audit",
        help="기존 공고를 삭제 없이 이너젠 사업 적합 Tier로 분류",
    )
    tier_audit.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    tier_audit.add_argument("--apply", action="store_true", help="자동 분류 결과를 저장합니다. 수동 Tier는 보존합니다.")
    tier_audit.set_defaults(func=tier_audit_command)

    g2b_title_audit = subparsers.add_parser(
        "g2b-title-audit",
        help="공고명 기준으로 기존 나라장터 후보를 안전하게 검토 대기열로 분류",
    )
    g2b_title_audit.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    g2b_title_audit.add_argument("--keywords", default=str(DEFAULT_KEYWORDS))
    g2b_title_audit.add_argument(
        "--apply",
        action="store_true",
        help="강한 공고명 신호가 없는 현재 new 항목만 needs_review로 표시합니다.",
    )
    g2b_title_audit.set_defaults(func=g2b_title_audit_command)

    prune_non_climate = subparsers.add_parser(
        "prune-non-climate",
        help="기후·온실가스·배출권·환경 범위 밖의 저장 공고를 정리",
    )
    prune_non_climate.add_argument("--db", default=str(ROOT_DIR / "data" / "rfp_tracker.db"))
    prune_non_climate.add_argument("--keywords", default=str(DEFAULT_KEYWORDS))
    prune_non_climate.add_argument("--apply", action="store_true", help="비관련 공고를 실제 삭제합니다.")
    prune_non_climate.set_defaults(func=prune_non_climate_command)

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
