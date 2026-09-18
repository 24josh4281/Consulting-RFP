from __future__ import annotations

import html
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Callable

from .briefing import notice_view, parse_notice_datetime, seoul_now
from .config import read_json, write_json
from .storage import (
    get_notification_setting,
    last_successful_notification_at,
    list_notices_since,
    list_unnotified_notices,
    notification_delivery_sent,
    record_notification_delivery,
    set_notification_setting,
)


BASELINE_SETTING = "notification_baseline_at"
DEFAULT_NOTIFICATION_CONFIG = {
    "recipients": [],
    "min_relevance_score": 3,
    "timezone": "Asia/Seoul",
    "daily_send_at": "17:00",
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


def read_notification_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return dict(DEFAULT_NOTIFICATION_CONFIG)
    payload = dict(DEFAULT_NOTIFICATION_CONFIG)
    payload.update(read_json(config_path))
    payload["recipients"] = _safe_recipients(payload.get("recipients", []))
    payload["min_relevance_score"] = int(payload.get("min_relevance_score", 3))
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


def _notice_lines(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- 신규 기준 공고가 없습니다."]
    lines: list[str] = []
    for item in items:
        deadline = item["deadline_at"] or "마감일 미수집"
        if item["days_remaining"] is not None:
            deadline = f"{deadline} (D-{item['days_remaining']})"
        lines.extend(
            [
                f"- {item['title']}",
                f"  출처: {item['source_name']} | 점수: {item['relevance_score']} | 마감: {deadline}",
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


def _notice_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<p>신규 기준 공고가 없습니다.</p>"
    rows: list[str] = []
    for item in items:
        url = str(item["url"])
        link = f'<a href="{html.escape(url, quote=True)}">원문 열기</a>' if url else "원문 미수집"
        document_count = item["document_count"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item['title']))}</td>"
            f"<td>{html.escape(str(item['source_name']))}</td>"
            f"<td>{html.escape(str(item['deadline_at'] or '미수집'))}</td>"
            f"<td>{item['relevance_score']}</td>"
            f"<td>{document_count}</td>"
            f"<td>{link}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>공고</th><th>출처</th><th>마감</th><th>점수</th><th>문서 수</th><th>원문</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _email_payload(
    mode: str,
    items: list[dict[str, Any]],
    now: datetime,
    *,
    daily_send_at: str = "17:00",
) -> EmailPayload | None:
    date_label = now.strftime("%Y-%m-%d")
    if mode == "immediate" and not items:
        return None
    if mode == "immediate":
        subject = f"[Climate RFP] 신규 공고 {len(items)}건"
        notification_type = "immediate"
        keys = [str(item["id"]) for item in items]
        notice_ids = [int(item["id"]) for item in items]
        intro = "새로 수집된 기후·GHG·ETS 관련 공고입니다."
    elif mode == "daily":
        subject = f"[Climate RFP] 일일 공고 브리핑 ({date_label})"
        notification_type = "daily"
        keys = [date_label]
        notice_ids = [None]
        intro = f"오늘 {daily_send_at} 기준으로 지난 일일 발송 이후 확인된 공고는 {len(items)}건입니다."
    elif mode == "weekly":
        week_key = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
        subject = f"[Climate RFP] 주간 공고 브리핑 ({week_key})"
        notification_type = "weekly"
        keys = [week_key]
        notice_ids = [None]
        intro = f"지난 주간 발송 이후 확인된 공고는 {len(items)}건입니다."
    else:
        raise ValueError(f"Unsupported notification mode: {mode}")

    text = "\n".join([subject, "", intro, "", *_notice_lines(items), "", "원문과 첨부 RFP/과업지시서를 확인한 뒤 입찰 가능 여부를 판단하세요."])
    html_body = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
body{{font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;color:#172025;line-height:1.5}} table{{border-collapse:collapse;width:100%;font-size:14px}} th,td{{border:1px solid #d9e2dc;padding:8px;text-align:left;vertical-align:top}} th{{background:#edf5ef}} a{{color:#166534}}
</style></head><body><h1>{html.escape(subject)}</h1><p>{html.escape(intro)}</p>{_notice_table(items)}<p>원문과 첨부 RFP/과업지시서를 확인한 뒤 입찰 가능 여부를 판단하세요.</p></body></html>"""
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
    daily_send_at: str = "17:00",
    send: bool = False,
    sender: Callable[[str, EmailPayload], None] | None = None,
    now: datetime | None = None,
) -> list[DispatchResult]:
    current = now or seoul_now()
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
                )
                if _notice_is_not_historical(row, baseline_at)
            ]
            payload = _email_payload(mode, items, current, daily_send_at=daily_send_at)
        elif mode in {"daily", "weekly"}:
            key = current.strftime("%Y-%m-%d") if mode == "daily" else f"{current.isocalendar().year}-W{current.isocalendar().week:02d}"
            if notification_delivery_sent(connection, mode, key, recipient):
                results.append(DispatchResult(recipient=recipient, mode=mode, skipped=1, message="이미 발송된 집계 기간입니다."))
                continue
            since_at = last_successful_notification_at(connection, mode, recipient) or baseline_at
            items = [
                notice_view(row, current)
                for row in list_notices_since(connection, since_at, min_score=min_score)
                if _notice_is_not_historical(row, baseline_at)
            ]
            payload = _email_payload(mode, items, current, daily_send_at=daily_send_at)
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
        "daily_send_at": str(config.get("daily_send_at", "17:00")),
        "weekly_send_day": str(config.get("weekly_send_day", "FRI")),
        "weekly_send_at": str(config.get("weekly_send_at", "18:00")),
        "baseline_at": get_notification_setting(connection, BASELINE_SETTING),
        "smtp_ready": readiness["ready"],
        "smtp_missing": readiness["missing"],
    }
