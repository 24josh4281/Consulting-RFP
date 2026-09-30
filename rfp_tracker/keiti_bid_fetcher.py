from __future__ import annotations

"""Read the public KEITI bid category without treating grant calls as bids."""

import html
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit
from zoneinfo import ZoneInfo

from .fetchers import BaseFetcher, fetch_text, has_domain_keyword
from .grant_fetchers import public_attachments
from .keyword_matcher import is_excluded, score_text
from .models import Notice


BOARD_HOST = "www.keiti.re.kr"
BOARD_PATH = "/site/keiti/ex/board/List.do"
SKIP_TITLE = re.compile(r"기술평가\s*결과|평가결과|선정\s*결과|낙찰|개찰|유찰|사전규격|사전\s*공개")
CARD = re.compile(
    r'<a\b[^>]*href=["\']([^"\']*View\.do\?[^"\']*\bbcIdx=(\d+)[^"\']*)["\'][^>]*>(.*?)</a>',
    re.I | re.S,
)


def _card_text(card: str, name: str) -> str:
    match = re.search(rf'<span\b[^>]*class=["\']{name}["\'][^>]*>(.*?)</span>', card, re.I | re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", match.group(1))).split()) if match else ""


def parse_keiti_bid_rows(page: str) -> list[dict[str, str]]:
    """Accept only cards explicitly labelled 입찰 in the official list."""
    rows = []
    for match in CARD.finditer(page):
        card = match.group(3)
        title = _card_text(card, "subject")
        published = _card_text(card, "date")
        if _card_text(card, "cateName") != "입찰" or not title or SKIP_TITLE.search(title):
            continue
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", published):
            continue
        url = html.unescape(match.group(1))
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/site/keiti/ex/board/View.do"):
            continue
        query = parse_qs(parsed.query)
        if query.get("cbIdx") != ["277"] or query.get("bcIdx") != [match.group(2)]:
            continue
        rows.append({
            "external_id": match.group(2), "title": title,
            "url": "https://" + BOARD_HOST + parsed.path + "?" + urlencode({"cbIdx": "277", "bcIdx": match.group(2)}),
            "published_at": published,
        })
    return rows


class KeitiBidFetcher(BaseFetcher):
    def __init__(self, source: dict[str, Any], keyword_config: dict[str, Any], global_config: dict[str, Any], root_dir: Path) -> None:
        super().__init__(source, keyword_config, global_config, root_dir)
        parsed = urlsplit(str(source.get("url") or ""))
        if (parsed.scheme != "https" or parsed.hostname != BOARD_HOST or parsed.path != BOARD_PATH
                or parse_qs(parsed.query).get("cbIdx") != ["277"]):
            raise ValueError("허용되지 않은 KEITI 입찰 게시판 주소")

    def fetch(self, days: int) -> list[Notice]:
        timeout = int(self.global_config.get("request_timeout_seconds", 20))
        agent = str(self.global_config.get("user_agent") or "ClimateRfpTracker/0.1")
        base_url = str(self.source["url"])
        pages = min(3, max(1, int(self.source.get("max_pages", 2))))
        max_details = min(12, max(1, int(self.source.get("max_detail_pages", 8))))
        delay = max(0.1, float(self.source.get("detail_delay_seconds", 0.25)))
        cutoff = (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=max(0, days))).date().isoformat()
        candidates: dict[str, dict[str, str]] = {}
        for page_number in range(1, pages + 1):
            url = base_url + "&" + urlencode({"searchExt1": "24000300", "pageIndex": page_number})
            listing = fetch_text(url, timeout, agent)
            rows = parse_keiti_bid_rows(listing)
            for row in rows:
                if row["published_at"] >= cutoff:
                    candidates[row["external_id"]] = row
            # Result announcements can fill an entire page. Use all card dates
            # for the date boundary, not only accepted bid rows.
            card_dates = [_card_text(card.group(3), "date") for card in CARD.finditer(listing)]
            if not card_dates or all(date < cutoff for date in card_dates):
                break
            time.sleep(delay)

        notices = []
        for row in list(candidates.values())[:max_details]:
            title = row["title"]
            if is_excluded(title, self.keyword_config):
                continue
            match = score_text(title, self.keyword_config)
            if match.score < int(self.keyword_config.get("min_relevance_score", 2)) or not has_domain_keyword(match.keywords, self.keyword_config):
                continue
            detail = fetch_text(row["url"], timeout, agent)
            notices.append(Notice(
                source_id=str(self.source["id"]), source_name=str(self.source["name"]),
                external_id=row["external_id"], title=title, url=row["url"],
                published_at=row["published_at"], buyer="한국환경산업기술원",
                category="official_board_html", relevance_score=match.score,
                matched_keywords=match.keywords,
                attachments=public_attachments(detail, row["url"], "keiti"),
                raw={"source_type": "keiti_bid_board", "source_url": base_url,
                     "fetched_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")},
            ))
            time.sleep(delay)
        return notices
