from __future__ import annotations

import html
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .briefing import is_notice_active, notice_view, parse_notice_datetime, seoul_now
from .config import read_json, write_json
from .storage import (
    get_notification_setting,
    last_successful_notification_at,
    list_notices,
    list_notices_since,
    list_unnotified_notices,
    notification_delivery_sent,
    record_notification_delivery,
    set_notification_setting,
)
from .tiering import TIER_1, TIER_2, UNCLASSIFIED, tier_label, tier_short_label


BASELINE_SETTING = "notification_baseline_at"
PUBLIC_DASHBOARD_URL = "https://24josh4281.github.io/Consulting-RFP/"
DEFAULT_NOTIFICATION_CONFIG = {
    "recipients": [],
    "min_relevance_score": 3,
    "timezone": "Asia/Seoul",
    "daily_send_times": ["10:00", "17:00"],
    "weekly_send_day": "FRI",
    "weekly_send_at": "18:00",
    "dashboard_url": PUBLIC_DASHBOARD_URL,
}


@dataclass(slots=True)
class SmtpSettings:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    use_ssl: bool = False
    timeout_seconds: int = 90


@dataclass(slots=True)
class EmailPayload:
    notification_type: str
    notification_keys: list[str]
    notice_ids: list[int | None]
    subject: str
    text: str
    html: str


@dataclass(slots=True)
class DispatchResult:
    recipient: str
    mode: str
    planned: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    baseline_initialized: bool = False
    message: str = ""


def _safe_recipients(values: object) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    recipients: list[str] = []
    for value in values:
        address = parseaddr(str(value).strip())[1]
        if address and "@" in address and address not in recipients:
            recipients.append(address)
    return recipients


def _safe_daily_send_times(values: object) -> list[str]:
    """Return unique 24-hour clock slots in the order configured by the operator."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    times: list[str] = []
    for value in values:
        candidate = str(value).strip()
        if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", candidate) and candidate not in times:
            times.append(candidate)
    return times


def _notice_is_not_historical(row: Any, baseline_at: str) -> bool:
    """Keep a post-baseline backfill from looking like a newly published notice.

    ``first_seen_at`` is the right fallback when the source offers no publication date,
    but an older source-provided publication date is stronger evidence.  This prevents a
    broad first collection from mailing July notices merely because they were collected
    after a September notification baseline was created.
    """
    baseline = parse_notice_datetime(baseline_at)
    published_text = str(row["published_at"] or "").strip()
    published = parse_notice_datetime(published_text)
    if baseline is None or published is None:
        return True

    digits = "".join(character for character in published_text if character.isdigit())
    if len(digits) <= 8:
        return published.date() >= baseline.date()
    return published >= baseline


def _active_notice_rows(connection: Any, current: datetime) -> list[Any]:
    """Return all currently open, in-scope rows for digest mail.

    The database is scoped at collection time. This second guard keeps closed or
    expired rows out of the daily/weekly digest while retaining open notices whose
    source did not provide a deadline.
    """
    return [
        row
        for row in list_notices(connection)
        if not str(row["source_id"] or "").casefold().startswith("sample_")
        and str(row["review_status"] or "") not in {"not_relevant", "closed"}
        and is_notice_active(row, current)
    ]


def read_notification_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return dict(DEFAULT_NOTIFICATION_CONFIG)
    payload = dict(DEFAULT_NOTIFICATION_CONFIG)
    configured = read_json(config_path)
    payload.update(configured)
    payload["recipients"] = _safe_recipients(payload.get("recipients", []))
    payload["min_relevance_score"] = int(payload.get("min_relevance_score", 3))
    daily_values = configured.get("daily_send_times")
    if daily_values is None:
        # Keep previously created local files working while moving to multi-slot schedules.
        daily_values = configured.get("daily_send_at", DEFAULT_NOTIFICATION_CONFIG["daily_send_times"])
    payload["daily_send_times"] = _safe_daily_send_times(daily_values)
    if not payload["daily_send_times"]:
        raise ValueError("daily_send_times must include at least one time in HH:MM format.")
    dashboard_url = str(payload.get("dashboard_url") or "").strip()
    parsed_dashboard = urlparse(dashboard_url)
    if parsed_dashboard.scheme != "https" or not parsed_dashboard.netloc:
        raise ValueError("dashboard_url must be a public HTTPS URL.")
    payload["dashboard_url"] = dashboard_url
    payload.pop("daily_send_at", None)
    return payload


def write_notification_config(path: str | Path, recipients: list[str], *, overwrite: bool = False) -> None:
    config_path = Path(path)
    if config_path.exists() and not overwrite:
        raise FileExistsError(f"Notification config already exists: {config_path}")
    payload = dict(DEFAULT_NOTIFICATION_CONFIG)
    payload["recipients"] = _safe_recipients(recipients)
    if not payload["recipients"]:
        raise ValueError("At least one valid recipient address is required.")
    write_json(config_path, payload)


def smtp_readiness() -> dict[str, Any]:
    required = {
        "SMTP_HOST": os.environ.get("SMTP_HOST", "").strip(),
        "SMTP_USERNAME": os.environ.get("SMTP_USERNAME", "").strip(),
        "SMTP_PASSWORD": os.environ.get("SMTP_PASSWORD", "").strip(),
        "SMTP_FROM": os.environ.get("SMTP_FROM", "").strip(),
    }
    missing = [name for name, value in required.items() if not value]
    port_text = os.environ.get("SMTP_PORT", "587").strip() or "587"
    try:
        port = int(port_text)
    except ValueError:
        missing.append("SMTP_PORT(valid integer)")
        port = 0
    return {"ready": not missing, "missing": missing, "port": port}


def load_smtp_settings() -> SmtpSettings:
    readiness = smtp_readiness()
    if not readiness["ready"]:
        raise ValueError("SMTP configuration is incomplete: " + ", ".join(readiness["missing"]))
    use_ssl = os.environ.get("SMTP_USE_SSL", "").strip().lower() in {"1", "true", "yes"}
    timeout_text = os.environ.get("SMTP_TIMEOUT_SECONDS", "90").strip() or "90"
    try:
        timeout_seconds = int(timeout_text)
    except ValueError as exc:
        raise ValueError("SMTP_TIMEOUT_SECONDS must be an integer.") from exc
    return SmtpSettings(
        host=os.environ["SMTP_HOST"].strip(),
        port=int(readiness["port"]),
        username=os.environ["SMTP_USERNAME"].strip(),
        password=os.environ["SMTP_PASSWORD"],
        from_address=os.environ["SMTP_FROM"].strip(),
        use_ssl=use_ssl,
        timeout_seconds=timeout_seconds,
    )


def initialize_baseline(connection: Any, now: datetime | None = None) -> tuple[str, bool]:
    existing = get_notification_setting(connection, BASELINE_SETTING)
    if existing:
        return existing, False
    value = (now or seoul_now()).isoformat(timespec="seconds")
    set_notification_setting(connection, BASELINE_SETTING, value)
    return value, True


TIER_SECTIONS = (
    (
        TIER_1,
        "Tier 1 · 이너젠 직접 컨설팅 검토",
        "이너젠의 기후·GHG·ETS·공시·리스크 컨설팅 범위에 맞는 우선 검토 공고입니다.",
        "#0B5D3B",
        "#E8F3ED",
    ),
    (
        TIER_2,
        "Tier 2 · 고객사 설비·금융지원 추천",
        "고객사가 신청할 수 있는 온실가스 감축·환경설비 보조금, 융자, 금리 또는 설비 지원 모집 공고입니다.",
        "#9A6700",
        "#FFF6DB",
    ),
)


def _display_deadline(item: dict[str, Any]) -> str:
    deadline = str(item["deadline_at"] or "마감일 미수집")
    if item["days_remaining"] is None:
        return deadline
    if item["days_remaining"] < 0:
        return f"{deadline} (마감 경과)"
    return f"{deadline} (D-{item['days_remaining']})"


def _display_budget(item: dict[str, Any]) -> str:
    raw = str(item.get("budget") or "").strip()
    if not raw:
        return "지원 규모는 공고문 확인" if item.get("category") == "grant_application" else "금액 미수집"
    digits = raw.replace(",", "")
    return f"{int(digits):,}원" if digits.isdigit() else raw


def _items_by_tier(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {tier: [] for tier, *_ in TIER_SECTIONS}
    grouped[UNCLASSIFIED] = []
    for item in items:
        grouped.setdefault(str(item.get("business_tier") or UNCLASSIFIED), []).append(item)
    return grouped


def _first_seen_today(item: dict[str, Any], now: datetime) -> bool:
    first_seen = parse_notice_datetime(str(item.get("first_seen_at") or ""))
    return bool(first_seen and first_seen.date() == now.date())


def _daily_sections(items: list[dict[str, Any]], now: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Feature new Tier 1 once; retain every other active Tier 1/2 notice."""
    new_items = [item for item in items if item["business_tier"] == TIER_1 and _first_seen_today(item, now)]
    new_ids = {int(item["id"]) for item in new_items}
    ongoing = [item for item in items if item["business_tier"] in {TIER_1, TIER_2} and int(item["id"]) not in new_ids]
    return new_items, ongoing


def _notice_lines(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- 해당 공고가 없습니다."]
    lines: list[str] = []
    for item in items:
        deadline = _display_deadline(item)
        marker = f"[{item['deadline_priority']}] " if item.get("deadline_priority") else ""
        lines.extend(
            [
                f"- {marker}{item['title']}",
                f"  출처: {item['source_name']} | 발주기관: {item.get('buyer') or '미수집'} | 마감: {deadline}",
                f"  공고 금액: {_display_budget(item)} | 입찰 방식: {item.get('procurement_method') or '미수집'}",
                f"  분류 근거: {item.get('tier_reason') or '원문 확인 필요'}",
                f"  키워드: {', '.join(item['matched_keywords']) or '-'}",
                f"  원문: {item['url'] or '미수집'}",
            ]
        )
        if item["attachments"]:
            links = ", ".join(str(link.get("url", "")) for link in item["attachments"] if link.get("url"))
            if links:
                lines.append(f"  수집 문서: {links}")
        else:
            lines.append("  수집 문서: 아직 링크가 없습니다. 원문에서 RFP/과업지시서를 확인하세요.")
    return lines


def _daily_notice_lines(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- 해당 공고가 없습니다."]
    lines: list[str] = []
    for item in items:
        marker = f"{item['deadline_priority']} · " if item.get("deadline_priority") else ""
        lines.append(
            f"- [{tier_short_label(str(item.get('business_tier') or UNCLASSIFIED))}] "
            f"{marker}{item['title']} | {item.get('buyer') or item['source_name']} | "
            f"{_display_budget(item)} | 마감 {_display_deadline(item)}"
        )
        if item.get("url"):
            lines.append(f"  원문: {item['url']}")
    return lines


def _document_links(item: dict[str, Any]) -> str:
    links: list[str] = []
    for document in item["attachments"][:3]:
        url = str(document.get("url", ""))
        if not url:
            continue
        label = str(document.get("label") or document.get("file_type") or "첨부 문서")
        links.append(
            f'<a href="{html.escape(url, quote=True)}" style="color:#0B5D3B;text-decoration:underline;">'
            f"{html.escape(label)}</a>"
        )
    if links:
        return "<br>".join(links)
    missing = "원문에서 지원사업 공고문 확인" if item.get("category") == "grant_application" else "원문에서 RFP/과업지시서 확인"
    return f'<span style="color:#6B7280;">{missing}</span>'


def _notice_table(items: list[dict[str, Any]], tier: str, accent: str, tint: str) -> str:
    if not items:
        return (
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            'style="border:1px solid #D1D5DB;border-collapse:collapse;background:#FFFFFF;">'
            '<tr><td style="border:1px solid #D1D5DB;padding:14px;color:#6B7280;font-size:13px;">'
            "해당 기간 공고가 없습니다.</td></tr></table>"
        )
    rows: list[str] = []
    for item in items:
        url = str(item["url"])
        link = (
            f'<a href="{html.escape(url, quote=True)}" style="display:inline-block;background:{accent};color:#FFFFFF;'
            'padding:7px 10px;text-decoration:none;font-size:12px;font-weight:700;border:1px solid ' + accent + ';">원문 보기</a>'
            if url
            else '<span style="color:#6B7280;">원문 미수집</span>'
        )
        buyer = html.escape(str(item.get("buyer") or "발주처 미수집"))
        source = html.escape(str(item["source_name"]))
        budget = html.escape(_display_budget(item))
        procurement_method = html.escape(str(item.get("procurement_method") or "입찰 방식 미수집"))
        is_grant = item.get("category") == "grant_application"
        amount_label = "지원 규모" if is_grant else "공고 금액"
        document_label = "공고문·첨부" if is_grant else "RFP·첨부"
        reason = html.escape(str(item.get("tier_reason") or "원문 확인 필요"))
        title = html.escape(str(item["title"]))
        deadline_priority = str(item.get("deadline_priority") or "")
        priority_badge = (
            f'<span style="display:inline-block;margin:0 0 6px 0;padding:3px 7px;border:1px solid {"#C53030" if deadline_priority == "D-3" else "#B7791F"};'
            f'background:{"#FBE7E5" if deadline_priority == "D-3" else "#FFF3D6"};color:{"#8A2A26" if deadline_priority == "D-3" else "#7B5510"};font-size:11px;font-weight:800;">'
            f'{html.escape(deadline_priority)} 중요 마감</span><br>'
            if deadline_priority else ""
        )
        keyword_text = html.escape(", ".join(item["matched_keywords"]) or "-")
        tier_badge = (
            f'<span style="display:inline-block;margin:0 0 6px 0;padding:3px 7px;border:1px solid #B7C9DB;'
            f'background:#EAF2F8;color:#14365D;font-size:11px;font-weight:800;">'
            f'{html.escape(tier_short_label(str(item.get("business_tier") or UNCLASSIFIED)))}</span><br>'
            if tier == "new" else ""
        )
        rows.append(
            "<tr>"
            f'<td width="78%" style="border:1px solid #D1D5DB;padding:14px;vertical-align:top;word-break:break-word;">'
            f'{tier_badge}{priority_badge}<div style="font-size:14px;font-weight:700;line-height:1.45;color:#16231D;">{title}</div>'
            f'<div style="margin-top:6px;color:#4B5563;font-size:12px;">{reason}</div>'
            f'<div style="margin-top:8px;color:#334155;font-size:12px;line-height:1.55;">{source} · {buyer}<br>'
            f'마감: {html.escape(_display_deadline(item))}<br>{amount_label}: {budget} · {procurement_method}</div>'
            f'<div style="margin-top:8px;color:#6B7280;font-size:12px;">키워드: {keyword_text}</div>'
            f'<div style="margin-top:8px;font-size:12px;line-height:1.6;">{document_label}: {_document_links(item)}</div></td>'
            f'<td width="22%" style="border:1px solid #D1D5DB;padding:14px;vertical-align:top;text-align:center;">{link}</td>'
            "</tr>"
        )
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="border:1px solid #D1D5DB;border-collapse:collapse;background:#FFFFFF;font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;">'
        "<thead><tr>"
        f'<th width="78%" style="border:1px solid #D1D5DB;padding:10px;background:{tint};color:{accent};text-align:left;font-size:12px;">공고 · 기관 · 금액/지원 규모 · 마감 · 자료</th>'
        f'<th width="22%" style="border:1px solid #D1D5DB;padding:10px;background:{tint};color:{accent};text-align:center;font-size:12px;">공식 원문</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _daily_notice_table(items: list[dict[str, Any]], accent: str, tint: str) -> str:
    """Keep the full daily list below common email clipping limits.

    The public dashboard carries the full metadata and attachment links.
    """
    if not items:
        return '<p style="color:#6B7280;font-size:13px;">해당 공고가 없습니다.</p>'
    rows: list[str] = []
    for item in items:
        url = html.escape(str(item.get("url") or ""), quote=True)
        title = html.escape(str(item["title"]))
        linked_title = f'<a href="{url}" style="color:#14365D;">{title}</a>' if url else title
        tier = html.escape(tier_short_label(str(item.get("business_tier") or UNCLASSIFIED)))
        buyer = html.escape(str(item.get("buyer") or item["source_name"]))
        budget = html.escape(_display_budget(item))
        deadline = html.escape(_display_deadline(item))
        priority = html.escape(str(item.get("deadline_priority") or ""))
        priority_text = f' <strong style="color:#A72B22;">{priority}</strong>' if priority else ""
        rows.append(
            '<tr><td style="border:1px solid #D1D5DB;padding:8px;font-size:12px;line-height:1.45;">'
            f'<strong>{linked_title}</strong><br>{tier} · {buyer} · {budget}</td>'
            '<td style="border:1px solid #D1D5DB;padding:8px;font-size:12px;white-space:nowrap;">'
            f'{deadline}{priority_text}</td></tr>'
        )
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="border:1px solid #D1D5DB;border-collapse:collapse;font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;">'
        f'<tr style="background:{tint};color:{accent};"><th align="left" style="border:1px solid #D1D5DB;padding:8px;">공고 · 기관 · 금액/지원 규모</th>'
        '<th align="left" style="border:1px solid #D1D5DB;padding:8px;">마감</th></tr>'
        + "".join(rows) + '</table>'
    )


def _newsletter_html(
    *,
    mode: str,
    subject: str,
    intro: str,
    items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
    ongoing_items: list[dict[str, Any]],
    include_all_tiers: bool,
    generated_at: datetime,
    dashboard_url: str,
) -> str:
    grouped = _items_by_tier(ongoing_items if mode == "daily" else items)
    sections = TIER_SECTIONS[:2] if mode == "daily" else (TIER_SECTIONS if include_all_tiers else (TIER_SECTIONS[0],))
    summary_cells = []
    if mode == "daily":
        summary_cells.append(
            '<td width="33.33%" style="border:1px solid #D1D5DB;background:#E8F0FE;padding:12px;vertical-align:top;">'
            '<div style="font-size:12px;font-weight:700;color:#1F6FEB;">오늘 신규 Tier 1</div>'
            f'<div style="font-size:24px;font-weight:800;color:#16231D;margin-top:3px;">{len(new_items)}</div></td>'
        )
    for tier, title, _description, accent, tint in sections:
        summary_cells.append(
            f'<td width="33.33%" style="border:1px solid #D1D5DB;background:{tint};padding:12px;vertical-align:top;">'
            f'<div style="font-size:12px;font-weight:700;color:{accent};">{html.escape(tier_short_label(tier))}{" 진행 중" if mode == "daily" else ""}</div>'
            f'<div style="font-size:24px;font-weight:800;color:#16231D;margin-top:3px;">{len(grouped[tier])}</div>'
            f'<div style="font-size:11px;color:#4B5563;margin-top:2px;">{html.escape(tier_label(tier).split(" · ", 1)[-1])}</div></td>'
        )

    sections_html = []
    if mode == "daily" or (include_all_tiers and new_items):
        sections_html.append(
            '<tr><td style="padding:0 0 22px 0;">'
            '<div style="border-left:5px solid #1F6FEB;padding:2px 0 2px 10px;margin:0 0 8px 0;">'
            f'<div style="font-size:16px;font-weight:800;color:#1F6FEB;">오늘 신규 추가 · Tier 1 <span style="font-size:13px;font-weight:600;color:#4B5563;">{len(new_items)}건</span></div>'
            '<div style="font-size:12px;color:#4B5563;line-height:1.5;margin-top:3px;">오늘 처음 수집한 Tier 1 접수 공고만 표시합니다.</div></div>'
            f'{_daily_notice_table(new_items, "#1F6FEB", "#E8F0FE") if mode == "daily" else _notice_table(new_items, "new", "#1F6FEB", "#E8F0FE")}'
            '</td></tr>'
        )
    for tier, title, description, accent, tint in sections:
        sections_html.append(
            '<tr><td style="padding:0 0 22px 0;">'
            f'<div style="border-left:5px solid {accent};padding:2px 0 2px 10px;margin:0 0 8px 0;">'
            f'<div style="font-size:16px;font-weight:800;color:{accent};">{html.escape(title)} <span style="font-size:13px;font-weight:600;color:#4B5563;">{len(grouped[tier])}건</span></div>'
            f'<div style="font-size:12px;color:#4B5563;line-height:1.5;margin-top:3px;">{html.escape(description)}</div></div>'
            f'{_daily_notice_table(grouped[tier], accent, tint) if mode == "daily" else _notice_table(grouped[tier], tier, accent, tint)}'
            '</td></tr>'
        )

    generated_label = generated_at.strftime("%Y-%m-%d %H:%M KST")
    safe_dashboard_url = html.escape(dashboard_url, quote=True)
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#F3F6F4;color:#16231D;font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F3F6F4;"><tr><td align="center" style="padding:24px 10px;">
    <table role="presentation" width="680" cellspacing="0" cellpadding="0" style="width:100%;max-width:680px;border:1px solid #C9D4CD;background:#FFFFFF;">
      <tr><td style="background:#0B3D2E;border:1px solid #0B3D2E;padding:24px 26px;color:#FFFFFF;">
        <div style="font-size:11px;letter-spacing:1.1px;font-weight:700;color:#C9E4D5;">INNERGEN CLIMATE INTELLIGENCE</div>
        <div style="font-size:22px;line-height:1.35;font-weight:800;margin-top:7px;">{html.escape(subject)}</div>
        <div style="font-size:12px;line-height:1.5;color:#DCEEE4;margin-top:7px;">기준 시각: {html.escape(generated_label)} · 공고 원문 및 첨부 RFP 확인 필요</div>
      </td></tr>
      <tr><td style="padding:24px 26px 8px 26px;border-left:1px solid #C9D4CD;border-right:1px solid #C9D4CD;">
        <p style="margin:0 0 16px 0;font-size:14px;line-height:1.6;color:#334155;">{html.escape(intro)}</p>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #D1D5DB;border-collapse:collapse;margin:0 0 22px 0;"><tr>{''.join(summary_cells)}</tr></table>
        <p style="margin:0 0 22px 0;"><a href="{safe_dashboard_url}" style="display:inline-block;padding:12px 18px;background:#14365D;color:#FFFFFF;font-size:14px;font-weight:700;text-decoration:none;border:1px solid #14365D;">대시보드에서 한 번에 확인하기</a></p>
      </td></tr>
      <tr><td style="padding:0 26px;border-left:1px solid #C9D4CD;border-right:1px solid #C9D4CD;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">{''.join(sections_html)}</table>
      </td></tr>
      <tr><td style="padding:16px 26px 22px 26px;background:#F8FAF9;border:1px solid #C9D4CD;color:#526058;font-size:12px;line-height:1.65;">
        <strong style="color:#274234;">운영 안내</strong><br>
        Tier는 공고 제목·수집 메타데이터를 기준으로 한 자동 보조 분류입니다. 실제 제안 여부는 원문 공고, RFP/과업지시서, 입찰 자격 및 수행 가능성을 사람이 확인한 뒤 결정하세요.
      </td></tr>
    </table>
  </td></tr></table>
</body></html>"""


def _email_payload(
    mode: str,
    items: list[dict[str, Any]],
    now: datetime,
    *,
    daily_slot: str = "17:00",
    deadline_alerts: list[dict[str, Any]] | None = None,
    dashboard_url: str = PUBLIC_DASHBOARD_URL,
) -> EmailPayload | None:
    items = [item for item in items if item.get("business_tier") in {TIER_1, TIER_2}]
    deadline_alerts = [
        item for item in (deadline_alerts or []) if item.get("business_tier") in {TIER_1, TIER_2}
    ]
    date_label = now.strftime("%Y-%m-%d")
    if mode == "immediate" and not items:
        return None
    if mode == "immediate":
        subject = f"[INNERGEN Climate RFP] Tier 1 신규 공고 {len(items)}건"
        notification_type = "immediate"
        keys = [str(item["id"]) for item in items]
        notice_ids = [int(item["id"]) for item in items]
        intro = "이너젠의 직접 컨설팅 범위에 맞는 Tier 1 신규 공고입니다. 원문과 RFP를 우선 확인하세요."
    elif mode == "daily":
        subject = f"[INNERGEN Climate Intelligence] 일일 입찰 브리핑 ({date_label} {daily_slot})"
        notification_type = "daily"
        keys = [f"{date_label}-{daily_slot.replace(':', '')}"]
        notice_ids = [None]
        intro = ""
    elif mode == "weekly":
        week_key = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
        subject = f"[INNERGEN Climate Intelligence] 주간 입찰 브리핑 ({week_key})"
        notification_type = "weekly"
        keys = [week_key]
        notice_ids = [None]
        intro = f"현재 접수 중인 관련 공고 {len(items)}건을 정리했습니다. Tier 1·2를 먼저 확인하세요."
    else:
        raise ValueError(f"Unsupported notification mode: {mode}")

    grouped = _items_by_tier(items)
    new_items, ongoing_items = _daily_sections(items, now) if mode == "daily" else (
        [item for item in items if item["business_tier"] == TIER_1 and _first_seen_today(item, now)], items
    )
    if mode == "daily":
        intro = (
            f"오늘 {daily_slot} 기준 신규 Tier 1 공고 {len(new_items)}건과 "
            f"그 밖의 접수 중인 Tier 1·2 공고 {len(ongoing_items)}건입니다."
        )
    text_lines = [subject, "", intro, ""]
    if mode == "weekly" and deadline_alerts:
        alert_groups = _items_by_tier(deadline_alerts)
        text_lines.append("[D-7 / D-3 중요 마감 · Tier 1/2]")
        for tier in (TIER_1, TIER_2):
            if alert_groups[tier]:
                text_lines.extend(
                    [f"[{tier_label(tier)}] {len(alert_groups[tier])}건", *_notice_lines(alert_groups[tier])]
                )
        text_lines.append("")
    if mode == "daily":
        text_lines.extend([f"[오늘 신규 추가 · Tier 1] {len(new_items)}건", *_daily_notice_lines(new_items), ""])
        ongoing_by_tier = _items_by_tier(ongoing_items)
        for tier, title, _description, _accent, _tint in TIER_SECTIONS[:2]:
            text_lines.extend([f"[현재 접수 중 {title}] {len(ongoing_by_tier[tier])}건", *_daily_notice_lines(ongoing_by_tier[tier]), ""])
    else:
        if mode == "weekly" and new_items:
            text_lines.extend(["[오늘 신규 추가 · Tier 1]", *_notice_lines(new_items), ""])
        sections = TIER_SECTIONS if mode == "weekly" else (TIER_SECTIONS[0],)
        for tier, title, description, _accent, _tint in sections:
            text_lines.extend([f"[{title}] {len(grouped[tier])}건", description, *_notice_lines(grouped[tier]), ""])
    text_lines.extend(["대시보드에서 한 번에 확인: " + dashboard_url, ""])
    text_lines.append("원문과 첨부 RFP/과업지시서를 확인한 뒤 입찰 가능 여부를 판단하세요.")
    text = "\n".join(text_lines)
    html_body = _newsletter_html(
        mode=mode,
        subject=subject,
        intro=intro,
        items=items,
        new_items=new_items,
        ongoing_items=ongoing_items,
        include_all_tiers=mode in {"daily", "weekly"},
        generated_at=now,
        dashboard_url=dashboard_url,
    )
    if mode == "weekly" and deadline_alerts:
        alert_groups = _items_by_tier(deadline_alerts)
        alert_sections = []
        for tier, title, _description, accent, tint in TIER_SECTIONS[:2]:
            if not alert_groups[tier]:
                continue
            alert_sections.append(
                '<div style="margin-top:12px;">'
                f'<div style="font-size:13px;font-weight:800;color:{accent};margin:0 0 6px 0;">{html.escape(title)} · {len(alert_groups[tier])}건</div>'
                f'{_notice_table(alert_groups[tier], tier, accent, tint)}</div>'
            )
        alert_html = (
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td style="padding:0 26px 22px 26px;">'
            '<div style="border-left:5px solid #C53030;padding:2px 0 2px 10px;margin:0 0 8px 0;">'
            f'<div style="font-size:16px;font-weight:800;color:#8A2A26;">D-7 / D-3 중요 마감 <span style="font-size:13px;color:#4B5563;">{len(deadline_alerts)}건</span></div>'
            '<div style="font-size:12px;color:#4B5563;line-height:1.5;margin-top:3px;">Tier 1/2 공고 중 마감일까지 정확히 7일 또는 3일 남은 건입니다.</div></div>'
            f'{"".join(alert_sections)}</td></tr></table>'
        )
        footer_marker = '<tr><td style="padding:16px 26px 22px 26px;background:#F8FAF9;'
        html_body = html_body.replace(footer_marker, f'{alert_html}{footer_marker}', 1)
    return EmailPayload(notification_type, keys, notice_ids, subject, text, html_body)


def _test_payload(now: datetime) -> EmailPayload:
    key = now.strftime("%Y%m%d%H%M%S")
    subject = "[Climate RFP] 이메일 발송 설정 테스트"
    text = "Climate RFP Tracker의 SMTP 설정 테스트 메일입니다. 이 메일을 받았다면 발송 연결이 정상입니다."
    html_body = "<html><body><h1>Climate RFP 이메일 설정 테스트</h1><p>이 메일을 받았다면 발송 연결이 정상입니다.</p></body></html>"
    return EmailPayload("test", [key], [None], subject, text, html_body)


def _send_smtp(settings: SmtpSettings, recipient: str, payload: EmailPayload) -> None:
    message = EmailMessage()
    message["Subject"] = payload.subject
    message["From"] = settings.from_address
    message["To"] = recipient
    message.set_content(payload.text)
    message.add_alternative(payload.html, subtype="html")
    context = ssl.create_default_context()
    if settings.use_ssl:
        with smtplib.SMTP_SSL(settings.host, settings.port, timeout=settings.timeout_seconds, context=context) as server:
            server.login(settings.username, settings.password)
            server.send_message(message)
        return
    with smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout_seconds) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(settings.username, settings.password)
        server.send_message(message)


def _record_payload(connection: Any, recipient: str, payload: EmailPayload, *, status: str, error: str = "") -> None:
    for key, notice_id in zip(payload.notification_keys, payload.notice_ids, strict=True):
        record_notification_delivery(
            connection,
            notification_type=payload.notification_type,
            notification_key=key,
            recipient=recipient,
            subject=payload.subject,
            notice_id=notice_id,
            status=status,
            error=error,
        )


def dispatch_notifications(
    connection: Any,
    *,
    recipients: list[str],
    mode: str,
    min_score: int = 3,
    daily_slot: str | None = None,
    send: bool = False,
    sender: Callable[[str, EmailPayload], None] | None = None,
    now: datetime | None = None,
    dashboard_url: str = PUBLIC_DASHBOARD_URL,
) -> list[DispatchResult]:
    current = now or seoul_now()
    normalized_daily_slot = ""
    if mode == "daily":
        daily_slots = _safe_daily_send_times(daily_slot)
        if len(daily_slots) != 1:
            raise ValueError("daily_slot must be one time in HH:MM format for a daily briefing.")
        normalized_daily_slot = daily_slots[0]
    if mode in {"test", "pilot"}:
        baseline_at = get_notification_setting(connection, BASELINE_SETTING) or ""
        baseline_initialized = False
    else:
        baseline_at, baseline_initialized = initialize_baseline(connection, current)
    if baseline_initialized:
        return [
            DispatchResult(
                recipient=recipient,
                mode=mode,
                baseline_initialized=True,
                message="첫 실행 기준시각을 저장했습니다. 기존 공고는 신규 알림으로 보내지 않습니다.",
            )
            for recipient in recipients
        ]

    results: list[DispatchResult] = []
    for recipient in recipients:
        if mode == "test":
            payload = _test_payload(current)
        elif mode == "pilot":
            active_items = [notice_view(row, current) for row in _active_notice_rows(connection, current)]
            items = [item for item in active_items if item["business_tier"] in {TIER_1, TIER_2}]
            digest = _email_payload(
                "daily",
                items,
                current,
                daily_slot=current.strftime("%H:%M"),
                dashboard_url=dashboard_url,
            )
            pilot_subject = f"[파일럿] {digest.subject}"
            pilot_note = "파일럿 확인용 메일입니다. 10시·17시 정규 브리핑 발송 기록과는 별개입니다."
            pilot_banner = (
                '<div style="padding:10px 16px;background:#E8F3EF;color:#174B43;'
                'font-weight:700;text-align:center;">' + pilot_note + "</div>"
            )
            payload = EmailPayload(
                "pilot",
                [current.strftime("%Y%m%dT%H%M%S%f%z")],
                [None],
                pilot_subject,
                digest.text.replace(digest.subject, pilot_subject, 1) + "\n\n" + pilot_note,
                re.sub(
                    r"(<body\b[^>]*>)",
                    lambda match: match.group(1) + pilot_banner,
                    digest.html,
                    count=1,
                    flags=re.IGNORECASE,
                ),
            )
        elif mode == "immediate":
            items = [
                notice_view(row, current)
                for row in list_unnotified_notices(
                    connection,
                    recipient=recipient,
                    baseline_at=baseline_at,
                    min_score=min_score,
                    business_tiers=(TIER_1,),
                )
                if _notice_is_not_historical(row, baseline_at)
                and not str(row["source_id"] or "").casefold().startswith("sample_")
            ]
            payload = _email_payload(mode, items, current, dashboard_url=dashboard_url)
        elif mode in {"daily", "weekly"}:
            key = (
                f"{current.strftime('%Y-%m-%d')}-{normalized_daily_slot.replace(':', '')}"
                if mode == "daily"
                else f"{current.isocalendar().year}-W{current.isocalendar().week:02d}"
            )
            if notification_delivery_sent(connection, mode, key, recipient):
                results.append(DispatchResult(recipient=recipient, mode=mode, skipped=1, message="이미 발송된 집계 기간입니다."))
                continue
            active_items = [notice_view(row, current) for row in _active_notice_rows(connection, current)]
            items = [item for item in active_items if item["business_tier"] in {TIER_1, TIER_2}]
            deadline_alerts = (
                [item for item in active_items if item["deadline_priority"] and item["business_tier"] in {TIER_1, TIER_2}]
                if mode == "weekly" else []
            )
            payload = _email_payload(
                mode,
                items,
                current,
                daily_slot=normalized_daily_slot,
                deadline_alerts=deadline_alerts,
                dashboard_url=dashboard_url,
            )
        else:
            raise ValueError("mode must be immediate, daily, weekly, pilot, or test")

        if payload is None:
            results.append(DispatchResult(recipient=recipient, mode=mode, message="새로 알릴 공고가 없습니다."))
            continue

        result = DispatchResult(recipient=recipient, mode=mode, planned=len(payload.notification_keys))
        if not send:
            result.message = f"dry-run: {payload.subject}"
            results.append(result)
            continue

        if sender is None:
            settings = load_smtp_settings()
            sender = lambda destination, email: _send_smtp(settings, destination, email)
        try:
            sender(recipient, payload)
        except Exception as exc:  # noqa: BLE001 - operator needs a retryable delivery result.
            safe_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            _record_payload(connection, recipient, payload, status="failed", error=safe_error)
            result.failed = len(payload.notification_keys)
            result.message = "메일 전송 실패. 설정을 확인한 뒤 같은 주기로 재시도할 수 있습니다."
        else:
            _record_payload(connection, recipient, payload, status="sent")
            result.sent = len(payload.notification_keys)
            result.message = f"sent: {payload.subject}"
        results.append(result)
    return results


def notification_status(connection: Any, config: dict[str, Any]) -> dict[str, Any]:
    readiness = smtp_readiness()
    return {
        "recipients": _safe_recipients(config.get("recipients", [])),
        "min_relevance_score": int(config.get("min_relevance_score", 3)),
        "daily_send_times": _safe_daily_send_times(config.get("daily_send_times", [])),
        "weekly_send_day": str(config.get("weekly_send_day", "FRI")),
        "weekly_send_at": str(config.get("weekly_send_at", "18:00")),
        "dashboard_url": str(config.get("dashboard_url") or PUBLIC_DASHBOARD_URL),
        "baseline_at": get_notification_setting(connection, BASELINE_SETTING),
        "data_go_kr_service_key_ready": bool(os.getenv("DATA_GO_KR_SERVICE_KEY", "").strip()),
        "smtp_ready": readiness["ready"],
        "smtp_missing": readiness["missing"],
    }
