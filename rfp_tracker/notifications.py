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
from .tiering import TIER_1, TIER_2, TIER_3, UNCLASSIFIED, tier_label, tier_short_label


BASELINE_SETTING = "notification_baseline_at"
DEFAULT_NOTIFICATION_CONFIG = {
    "recipients": [],
    "min_relevance_score": 3,
    "timezone": "Asia/Seoul",
    "daily_send_times": ["10:00", "17:00"],
    "weekly_send_day": "FRI",
    "weekly_send_at": "18:00",
}


@dataclass(slots=True)
class SmtpSettings:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    use_ssl: bool = False
    timeout_seconds: int = 30


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
        if str(row["review_status"] or "") not in {"not_relevant", "closed"}
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
    timeout_text = os.environ.get("SMTP_TIMEOUT_SECONDS", "30").strip() or "30"
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
        "Tier 2 · 고객사 추천 가능 사업",
        "기후·환경 설비, 시설, 시스템 또는 기술 지원으로 고객사 추천 가능성을 확인할 공고입니다.",
        "#9A6700",
        "#FFF6DB",
    ),
    (
        TIER_3,
        "Tier 3 · 참고 / 직접 컨설팅 비적합",
        "관련 키워드는 있으나 행사·투자·영상·순수 과학 등 이너젠 직접 컨설팅과 거리가 있는 공고입니다.",
        "#5B6470",
        "#F1F3F5",
    ),
)


def _display_deadline(item: dict[str, Any]) -> str:
    deadline = str(item["deadline_at"] or "마감일 미수집")
    if item["days_remaining"] is None:
        return deadline
    if item["days_remaining"] < 0:
        return f"{deadline} (마감 경과)"
    return f"{deadline} (D-{item['days_remaining']})"


def _items_by_tier(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {tier: [] for tier, *_ in TIER_SECTIONS}
    grouped[UNCLASSIFIED] = []
    for item in items:
        grouped.setdefault(str(item.get("business_tier") or UNCLASSIFIED), []).append(item)
    return grouped


def _notice_lines(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- 신규 기준 공고가 없습니다."]
    lines: list[str] = []
    for item in items:
        deadline = _display_deadline(item)
        marker = f"[{item['deadline_priority']}] " if item.get("deadline_priority") else ""
        lines.extend(
            [
                f"- {marker}{item['title']}",
                f"  출처: {item['source_name']} | 점수: {item['relevance_score']} | 마감: {deadline}",
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
    return '<span style="color:#6B7280;">원문에서 RFP/과업지시서 확인</span>'


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
        rows.append(
            "<tr>"
            f'<td style="border:1px solid #D1D5DB;padding:12px;vertical-align:top;">'
            f'{priority_badge}<div style="font-size:14px;font-weight:700;line-height:1.45;color:#16231D;">{title}</div>'
            f'<div style="margin-top:6px;color:#4B5563;font-size:12px;">{reason}</div>'
            f'<div style="margin-top:6px;color:#6B7280;font-size:12px;">키워드: {keyword_text}</div></td>'
            f'<td style="border:1px solid #D1D5DB;padding:12px;vertical-align:top;font-size:13px;">{source}<br>'
            f'<span style="color:#6B7280;">{buyer}</span></td>'
            f'<td style="border:1px solid #D1D5DB;padding:12px;vertical-align:top;font-size:13px;white-space:nowrap;">'
            f"{html.escape(_display_deadline(item))}<br><span style=\"color:#6B7280;\">점수 {item['relevance_score']}</span></td>"
            f'<td style="border:1px solid #D1D5DB;padding:12px;vertical-align:top;font-size:12px;">{_document_links(item)}</td>'
            f'<td style="border:1px solid #D1D5DB;padding:12px;vertical-align:top;text-align:center;">{link}</td>'
            "</tr>"
        )
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="border:1px solid #D1D5DB;border-collapse:collapse;background:#FFFFFF;font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;">'
        "<thead><tr>"
        f'<th style="border:1px solid #D1D5DB;padding:10px;background:{tint};color:{accent};text-align:left;font-size:12px;">공고 / 분류 근거</th>'
        f'<th style="border:1px solid #D1D5DB;padding:10px;background:{tint};color:{accent};text-align:left;font-size:12px;">출처 / 발주처</th>'
        f'<th style="border:1px solid #D1D5DB;padding:10px;background:{tint};color:{accent};text-align:left;font-size:12px;">마감 / 점수</th>'
        f'<th style="border:1px solid #D1D5DB;padding:10px;background:{tint};color:{accent};text-align:left;font-size:12px;">RFP·첨부</th>'
        f'<th style="border:1px solid #D1D5DB;padding:10px;background:{tint};color:{accent};text-align:center;font-size:12px;">원문</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _newsletter_html(
    *,
    subject: str,
    intro: str,
    items: list[dict[str, Any]],
    include_all_tiers: bool,
    generated_at: datetime,
) -> str:
    grouped = _items_by_tier(items)
    sections = TIER_SECTIONS if include_all_tiers else (TIER_SECTIONS[0],)
    summary_cells = []
    for tier, title, _description, accent, tint in TIER_SECTIONS:
        summary_cells.append(
            f'<td width="33.33%" style="border:1px solid #D1D5DB;background:{tint};padding:12px;vertical-align:top;">'
            f'<div style="font-size:12px;font-weight:700;color:{accent};">{html.escape(tier_short_label(tier))}</div>'
            f'<div style="font-size:24px;font-weight:800;color:#16231D;margin-top:3px;">{len(grouped[tier])}</div>'
            f'<div style="font-size:11px;color:#4B5563;margin-top:2px;">{html.escape(tier_label(tier).split(" · ", 1)[-1])}</div></td>'
        )

    sections_html = []
    for tier, title, description, accent, tint in sections:
        sections_html.append(
            '<tr><td style="padding:0 0 22px 0;">'
            f'<div style="border-left:5px solid {accent};padding:2px 0 2px 10px;margin:0 0 8px 0;">'
            f'<div style="font-size:16px;font-weight:800;color:{accent};">{html.escape(title)} <span style="font-size:13px;font-weight:600;color:#4B5563;">{len(grouped[tier])}건</span></div>'
            f'<div style="font-size:12px;color:#4B5563;line-height:1.5;margin-top:3px;">{html.escape(description)}</div></div>'
            f'{_notice_table(grouped[tier], tier, accent, tint)}'
            '</td></tr>'
        )

    if include_all_tiers and grouped[UNCLASSIFIED]:
        sections_html.append(
            '<tr><td style="padding:0 0 22px 0;">'
            '<div style="border-left:5px solid #6B7280;padding:2px 0 2px 10px;margin:0 0 8px 0;">'
            f'<div style="font-size:16px;font-weight:800;color:#374151;">미분류 · 원문 확인 필요 <span style="font-size:13px;font-weight:600;color:#4B5563;">{len(grouped[UNCLASSIFIED])}건</span></div>'
            '<div style="font-size:12px;color:#4B5563;line-height:1.5;margin-top:3px;">자동 Tier 근거가 부족한 공고입니다. 원문을 확인한 뒤 수동 보정하세요.</div></div>'
            f'{_notice_table(grouped[UNCLASSIFIED], UNCLASSIFIED, "#6B7280", "#F3F4F6")}'
            '</td></tr>'
        )

    generated_label = generated_at.strftime("%Y-%m-%d %H:%M KST")
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
) -> EmailPayload | None:
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
        intro = f"오늘 {daily_slot} 기준으로 현재 접수 중인 관련 공고 {len(items)}건을 정리했습니다. Tier 1·2를 먼저 확인하세요."
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
    text_lines = [subject, "", intro, ""]
    if mode in {"daily", "weekly"} and deadline_alerts:
        alert_groups = _items_by_tier(deadline_alerts)
        text_lines.append("[D-7 / D-3 중요 마감 · Tier 1/2]")
        for tier in (TIER_1, TIER_2):
            if alert_groups[tier]:
                text_lines.extend(
                    [f"[{tier_label(tier)}] {len(alert_groups[tier])}건", *_notice_lines(alert_groups[tier])]
                )
        text_lines.append("")
    sections = TIER_SECTIONS if mode in {"daily", "weekly"} else (TIER_SECTIONS[0],)
    for tier, title, description, _accent, _tint in sections:
        text_lines.extend([f"[{title}] {len(grouped[tier])}건", description, *_notice_lines(grouped[tier]), ""])
    if mode in {"daily", "weekly"} and grouped[UNCLASSIFIED]:
        text_lines.extend(["[미분류 · 원문 확인 필요]", *_notice_lines(grouped[UNCLASSIFIED]), ""])
    text_lines.append("원문과 첨부 RFP/과업지시서를 확인한 뒤 입찰 가능 여부를 판단하세요.")
    text = "\n".join(text_lines)
    html_body = _newsletter_html(
        subject=subject,
        intro=intro,
        items=items,
        include_all_tiers=mode in {"daily", "weekly"},
        generated_at=now,
    )
    if mode in {"daily", "weekly"} and deadline_alerts:
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
            '<div style="font-size:12px;color:#4B5563;line-height:1.5;margin-top:3px;">Tier 1/2 공고 중 마감일까지 정확히 7일 또는 3일 남은 건입니다. Tier 3도 공고 목록에서 마감 배지로 확인할 수 있습니다.</div></div>'
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
) -> list[DispatchResult]:
    current = now or seoul_now()
    normalized_daily_slot = ""
    if mode == "daily":
        daily_slots = _safe_daily_send_times(daily_slot)
        if len(daily_slots) != 1:
            raise ValueError("daily_slot must be one time in HH:MM format for a daily briefing.")
        normalized_daily_slot = daily_slots[0]
    if mode == "test":
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
            ]
            payload = _email_payload(mode, items, current)
        elif mode in {"daily", "weekly"}:
            key = (
                f"{current.strftime('%Y-%m-%d')}-{normalized_daily_slot.replace(':', '')}"
                if mode == "daily"
                else f"{current.isocalendar().year}-W{current.isocalendar().week:02d}"
            )
            if notification_delivery_sent(connection, mode, key, recipient):
                results.append(DispatchResult(recipient=recipient, mode=mode, skipped=1, message="이미 발송된 집계 기간입니다."))
                continue
            # Daily/weekly digests are an operational snapshot: include every
            # currently active in-scope notice, not only rows first seen since the
            # previous send. This prevents an open Tier 1/2 bid from disappearing
            # from the user's morning/evening briefing after its first appearance.
            items = [notice_view(row, current) for row in _active_notice_rows(connection, current)]
            deadline_alerts = []
            for row in _active_notice_rows(connection, current):
                view = notice_view(row, current)
                if view["deadline_priority"] and view["business_tier"] in {TIER_1, TIER_2}:
                    deadline_alerts.append(view)
            payload = _email_payload(
                mode,
                items,
                current,
                daily_slot=normalized_daily_slot,
                deadline_alerts=deadline_alerts,
            )
        else:
            raise ValueError("mode must be immediate, daily, weekly, or test")

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
        "baseline_at": get_notification_setting(connection, BASELINE_SETTING),
        "smtp_ready": readiness["ready"],
        "smtp_missing": readiness["missing"],
    }
