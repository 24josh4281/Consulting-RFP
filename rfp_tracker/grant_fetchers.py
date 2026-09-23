from __future__ import annotations

"""Bounded readers for public, applicant-facing climate equipment grant boards.

Design Ref: official-grant-notice-intake §2 — keep grant parsing separate from G2B bids.
No login, POST, or attachment download is performed here.
"""

import html
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit
from zoneinfo import ZoneInfo

from .fetchers import BaseFetcher, fetch_text, parse_links
from .models import Attachment, Notice


SEOUL = ZoneInfo("Asia/Seoul")
DATE_RE = re.compile(r"(?<!\d)(20\d{2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})(?!\d)")
GRANT_DOMAIN = re.compile(r"탄소중립|배출권거래제|온실가스|탄소감축")
GRANT_SUPPORT = re.compile(r"설비|시설|프로젝트 경매")
GRANT_CALL = re.compile(r"공고|모집")
GRANT_FUNDING = re.compile(r"지원사업|지원\s*사업|경매사업|지원\s*(?:\([^)]*\))?\s*참여기업")
EXCLUDED_ROLE = re.compile(
    r"수행사\s*모집|검증기관\s*모집|원가계산기관\s*모집|선정\s*결과"
    r"|구매\s*입찰|납품\s*입찰|시공\s*입찰|용역\s*입찰"
)


def is_customer_grant_title(title: str) -> bool:
    """Exclude supplier/performer recruitment and unrelated environmental grants."""
    return bool(
        GRANT_DOMAIN.search(title)
        and GRANT_SUPPORT.search(title)
        and GRANT_CALL.search(title)
        and GRANT_FUNDING.search(title)
        and not EXCLUDED_ROLE.search(title)
    )


def _plain(fragment: str) -> str:
    stripped = re.sub(r"(?is)<[^>]+>", " ", fragment)
    return " ".join(html.unescape(stripped).split())


def _normal_date(value: str) -> str:
    match = DATE_RE.search(value)
    if not match:
        return ""
    try:
        return datetime(*(int(group) for group in match.groups())).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _date_time_at(segment: str, match: re.Match[str], *, is_deadline: bool, next_date_start: int | None = None) -> str:
    date = _normal_date(match.group(0))
    if not date:
        return ""
    # Korean boards use both "16:00" and "16시까지" after the weekday marker.
    tail_end = min(match.end() + 28, next_date_start) if next_date_start is not None else match.end() + 28
    tail = segment[match.end():tail_end]
    hour_minute = re.search(r"(?<!\d)(\d{1,2})\s*:\s*(\d{2})(?!\d)", tail)
    hour_only = re.search(r"(?<!\d)(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?", tail)
    if hour_minute:
        hour, minute = int(hour_minute.group(1)), int(hour_minute.group(2))
    elif hour_only:
        hour, minute = int(hour_only.group(1)), int(hour_only.group(2) or 0)
    else:
        hour, minute = (23, 59) if is_deadline else (0, 0)
    if hour > 23 or minute > 59:
        return ""
    return f"{date} {hour:02d}:{minute:02d}"


def application_period(text: str) -> tuple[str, str]:
    """Read only a labelled application/receipt window, never arbitrary dates."""
    normalized = " ".join(html.unescape(text).split())
    label = re.search(r"(?:신청|접수)\s*기간\s*[:：]?\s*", normalized)
    if not label:
        return "", ""
    segment = normalized[label.end():label.end() + 180]
    dates = list(DATE_RE.finditer(segment))
    if not dates:
        return "", ""
    start = _date_time_at(segment, dates[0], is_deadline=False, next_date_start=dates[1].start()) if len(dates) > 1 else ""
    deadline = _date_time_at(segment, dates[1] if len(dates) > 1 else dates[0], is_deadline=True)
    return start, deadline


def _keep_notice(published_at: str, deadline_at: str, days: int, now: datetime) -> bool:
    deadline = _normal_date(deadline_at)
    if deadline and deadline >= now.strftime("%Y-%m-%d"):
        return True
    published = _normal_date(published_at)
    return bool(published and published >= (now - timedelta(days=max(0, days))).strftime("%Y-%m-%d"))


def parse_kosmes_rows(page: str, base_url: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for match in re.finditer(r"(?is)<tr\b[^>]*onclick=[\"']javascript:goDetail\((\d+)\)[\"'][^>]*>(.*?)</tr>", page):
        cells = [_plain(cell) for cell in re.findall(r"(?is)<td\b[^>]*>(.*?)</td>", match.group(2))]
        if len(cells) < 5 or not is_customer_grant_title(cells[1]):
            continue
        start, deadline = application_period("신청기간: " + cells[3])
        rows.append({
            "external_id": match.group(1),
            "title": cells[1],
            "url": urljoin(base_url, "bsnPuanView.do?" + urlencode({
                "bsnDvCd": "CNF", "bsnTrgtCd": "ETR", "bsnPuanId": match.group(1)
            })),
            "published_at": "",  # Listing has no publication date; do not invent one.
            "start_at": start,
            "deadline_at": deadline,
            "source_status": cells[4],
        })
    return rows


def parse_keco_rows(page: str, base_url: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for match in re.finditer(r"(?is)<tr\b[^>]*>(.*?)</tr>", page):
        cells = re.findall(r"(?is)<td\b[^>]*>(.*?)</td>", match.group(1))
        if len(cells) < 5:
            continue
        sequence = re.search(r"article_seq=(\d+)", html.unescape(cells[1]))
        title = _plain(cells[1])
        if not sequence or not is_customer_grant_title(title):
            continue
        rows.append({
            "external_id": sequence.group(1),
            "title": title,
            "url": urljoin(base_url, "view.do?article_seq=" + sequence.group(1)),
            "published_at": _normal_date(_plain(cells[4])),
            "start_at": "",
            "deadline_at": "",
            "source_status": "",
        })
    return rows


def parse_kea_rows(page: str, base_url: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for match in re.finditer(r"(?is)<a\b[^>]*href=[\"']([^\"']*/notice/view\.do\?seq=(\d+))[^\"']*[\"'][^>]*>(.*?)</a>", page):
        title_match = re.search(r"(?is)<[^>]*class=[\"']board_title[\"'][^>]*>(.*?)</", match.group(3))
        date_match = re.search(r"(?is)<[^>]*class=[\"']board_col\s+board_col_date[\"'][^>]*>(.*?)</", match.group(3))
        title = _plain(title_match.group(1)) if title_match else ""
        if not is_customer_grant_title(title):
            continue
        rows.append({
            "external_id": match.group(2),
            "title": title,
            "url": urljoin(base_url, html.unescape(match.group(1))),
            "published_at": _normal_date(_plain(date_match.group(1))) if date_match else "",
            "start_at": "",
            "deadline_at": "",
            "source_status": "",
        })
    if "/etsa/ia/" in base_url:
        # The auction board uses a simple table, unlike the ETSG card list.
        for match in re.finditer(r"(?is)<tr\b[^>]*>(.*?)</tr>", page):
            cells = re.findall(r"(?is)<td\b[^>]*>(.*?)</td>", match.group(1))
            if len(cells) < 4:
                continue
            link = re.search(r"(?is)<a\b[^>]*href=[\"']([^\"']*/notice/view\.do\?seq=(\d+))[^\"']*[\"'][^>]*>(.*?)</a>", cells[1])
            if not link:
                continue
            title = _plain(link.group(3))
            if not is_customer_grant_title(title):
                continue
            rows.append({
                "external_id": link.group(2),
                "title": title,
                "url": urljoin(base_url, html.unescape(link.group(1))),
                "published_at": _normal_date(_plain(cells[3])),
                "start_at": "",
                "deadline_at": "",
                "source_status": "",
            })
    return rows


def public_attachments(page: str, detail_url: str, board: str) -> list[Attachment]:
    if board not in {"kosmes", "keco"}:
        return []  # KEA's fileUserDown(...) is not a public direct URL.
    marker = "download.act" if board == "kosmes" else "/download.do"
    allowed_host = OfficialGrantFetcher.HOSTS[board]
    result: list[Attachment] = []
    seen: set[str] = set()
    for link in parse_links(page, detail_url):
        url = link["url"]
        parsed = urlsplit(url)
        if marker not in url or url in seen or parsed.scheme != "https" or parsed.hostname != allowed_host:
            continue
        seen.add(url)
        label = link["text"] or "공고 첨부자료"
        extension = re.search(r"\.(pdf|hwp|hwpx|xlsx|xls|zip)\b", label, flags=re.I)
        result.append(Attachment(label=label, url=url, file_type=extension.group(1).lower() if extension else ""))
    return result


class OfficialGrantFetcher(BaseFetcher):
    """Small, allowlisted official support-board reader; no login or file fetch."""

    HOSTS = {
        "kosmes": "esg.kosmes.or.kr",
        "keco": "www.keco.or.kr",
        "kea": "min24.energy.or.kr",
    }

    def __init__(self, source: dict[str, Any], keyword_config: dict[str, Any], global_config: dict[str, Any], root_dir: Path) -> None:
        super().__init__(source, keyword_config, global_config, root_dir)
        board = str(source.get("board") or "")
        parsed = urlsplit(str(source.get("url") or ""))
        if board not in self.HOSTS or parsed.scheme != "https" or parsed.hostname != self.HOSTS[board]:
            raise ValueError(f"허용되지 않은 공식 지원사업 출처: {source.get('id')}")
        self.board = board

    def fetch(self, days: int) -> list[Notice]:
        timeout = int(self.global_config.get("request_timeout_seconds", 20))
        agent = str(self.global_config.get("user_agent") or "ClimateRfpTracker/0.1")
        base_url = str(self.source["url"])
        max_pages = min(3, max(1, int(self.source.get("max_pages", 2))))
        max_details = min(12, max(1, int(self.source.get("max_detail_pages", 8))))
        delay = max(0.1, float(self.source.get("detail_delay_seconds", 0.25)))
        candidates: dict[str, dict[str, str]] = {}
        if self.board == "kosmes":
            listing = fetch_text(base_url, timeout, agent)
            for row in parse_kosmes_rows(listing, base_url):
                candidates[row["external_id"]] = row
        elif self.board == "keco":
            for term in ("탄소중립설비", "감축설비"):
                for page_number in range(1, max_pages + 1):
                    query = urlencode({"condition": "TITLE", "keyword": term, "cpage": page_number})
                    listing = fetch_text(base_url + ("&" if "?" in base_url else "?") + query, timeout, agent)
                    rows = parse_keco_rows(listing, base_url)
                    for row in rows:
                        candidates[row["external_id"]] = row
                    if not rows:
                        break
                    time.sleep(delay)
        else:
            listing = fetch_text(base_url, timeout, agent)
            for row in parse_kea_rows(listing, base_url):
                candidates[row["external_id"]] = row

        now = datetime.now(SEOUL)
        notices: list[Notice] = []
        for row in list(candidates.values())[:max_details]:
            # KOSMES exposes the official deadline/status in the list. Closed old
            # calls need no extra requests on the 3-day scheduled cycle.
            if self.board == "kosmes" and not _keep_notice(row["start_at"], row["deadline_at"], days, now):
                continue
            detail = fetch_text(row["url"], timeout, agent)
            if self.board != "kosmes":
                start, deadline = application_period(_plain(detail))
                row["start_at"] = start
                row["deadline_at"] = deadline
            if row["published_at"] and row["deadline_at"] and row["deadline_at"][:10] < row["published_at"]:
                # Source text inconsistent with publication chronology; do not
                # present a stale or contradictory grant as an opportunity.
                continue
            if not _keep_notice(row["published_at"] or row["start_at"], row["deadline_at"], days, now):
                continue
            notices.append(Notice(
                source_id=str(self.source["id"]),
                source_name=str(self.source["name"]),
                external_id=row["external_id"],
                title=row["title"],
                url=row["url"],
                published_at=row["published_at"],
                deadline_at=row["deadline_at"],
                buyer=str(self.source.get("operator") or self.source["name"]),
                procurement_method="고객사 지원사업 신청",
                category="grant_application",
                relevance_score=8,
                matched_keywords=[term for term in ("탄소중립", "배출권거래제", "온실가스", "설비") if term in row["title"]],
                attachments=public_attachments(detail, row["url"], self.board),
                raw={
                    "source_type": "official_grant_board",
                    "source_url": base_url,
                    "application_start_at": row["start_at"],
                    "application_status": row["source_status"],
                    "fetched_at": now.isoformat(timespec="seconds"),
                },
            ))
            time.sleep(delay)
        return notices
