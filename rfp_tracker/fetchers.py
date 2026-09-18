from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .keyword_matcher import extension_from_url, has_any_term, is_excluded, normalize_text, score_text
from .models import Attachment, Notice


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_dict = {key.lower(): value or "" for key, value in attrs}
        href = attr_dict.get("href", "")
        if href:
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href is not None:
            text = " ".join(part.strip() for part in self._current_text if part.strip())
            self.links.append({"href": self._current_href, "text": text})
            self._current_href = None
            self._current_text = []


def fetch_text(url: str, timeout: int, user_agent: str) -> str:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def parse_links(html: str, base_url: str = "") -> list[dict[str, str]]:
    parser = LinkExtractor()
    parser.feed(html)
    resolved: list[dict[str, str]] = []
    for link in parser.links:
        href = link["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        resolved.append({"url": canonical_url(urljoin(base_url, href)), "text": link["text"].strip()})
    return resolved


def canonical_url(url: str) -> str:
    """Remove volatile servlet session IDs so the same board notice keeps one stable ID."""
    parsed = urlsplit(url)
    path = re.sub(r";jsessionid=[^/?#]+", "", parsed.path, flags=re.IGNORECASE)
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def stable_id(*parts: str) -> str:
    joined = "|".join(parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def has_domain_keyword(match_keywords: list[str], keyword_config: dict[str, Any]) -> bool:
    domain_terms = {
        normalize_text(term)
        for terms in keyword_config.get("keyword_groups", {}).values()
        for term in terms
    }
    return any(normalize_text(keyword) in domain_terms for keyword in match_keywords)


class BaseFetcher:
    def __init__(self, source: dict[str, Any], keyword_config: dict[str, Any], global_config: dict[str, Any], root_dir: Path) -> None:
        self.source = source
        self.keyword_config = keyword_config
        self.global_config = global_config
        self.root_dir = root_dir

    def fetch(self, days: int) -> list[Notice]:
        raise NotImplementedError


class GenericHtmlFetcher(BaseFetcher):
    def fetch(self, days: int) -> list[Notice]:
        html = self._load_html()
        base_url = self.source.get("url", "")
        links = parse_links(html, base_url)
        notices: list[Notice] = []
        min_score = int(self.keyword_config.get("min_relevance_score", 2))
        document_terms = self.keyword_config.get("document_terms", [])
        last_relevant_notice: Notice | None = None

        for link in links:
            title = link["text"] or link["url"]
            file_type = extension_from_url(link["url"]) or extension_from_url(title)
            combined_link_text = f"{title} {link['url']}"
            if is_excluded(combined_link_text, self.keyword_config):
                continue
            match = score_text(combined_link_text, self.keyword_config)
            looks_like_document = bool(file_type) or has_any_term(title, document_terms)
            if file_type and last_relevant_notice is not None:
                last_relevant_notice.attachments.append(
                    Attachment(label=title, url=link["url"], file_type=file_type)
                )
                continue

            if match.score < min_score or not has_domain_keyword(match.keywords, self.keyword_config):
                continue

            attachment = []
            if looks_like_document:
                attachment = [Attachment(label=title, url=link["url"], file_type=file_type)]

            notice = Notice(
                source_id=self.source["id"],
                source_name=self.source["name"],
                external_id=stable_id(self.source["id"], link["url"], title),
                title=title,
                url=link["url"],
                category="generic_html",
                relevance_score=match.score,
                matched_keywords=match.keywords,
                attachments=attachment,
                raw={
                    "source_type": self.source["type"],
                    "source_url": base_url,
                    "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                },
            )
            notices.append(notice)
            last_relevant_notice = notice
        return notices

    def _load_html(self) -> str:
        if self.source["type"] == "sample_html":
            sample_path = self.root_dir / self.source["path"]
            return sample_path.read_text(encoding="utf-8")

        timeout = int(self.global_config.get("request_timeout_seconds", 20))
        user_agent = self.global_config.get("user_agent", "ClimateRfpTracker/0.1")
        return fetch_text(self.source["url"], timeout=timeout, user_agent=user_agent)


class OfficialBoardFetcher(GenericHtmlFetcher):
    """Fetch a public official notice board and its limited detail pages/attachments.

    This adapter intentionally avoids authenticated pages and downloads no files. It only follows
    public notice-detail links and records the public attachment URLs for consultant review.
    """

    def fetch(self, days: int) -> list[Notice]:
        listing_html = self._load_html()
        listing_url = self.source.get("url", "")
        detail_marker = str(self.source.get("detail_url_contains", ""))
        title_prefix = str(self.source.get("detail_title_prefix", ""))
        max_details = int(self.source.get("max_detail_pages", 10))
        min_score = int(self.keyword_config.get("min_relevance_score", 2))
        candidates: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        for link in parse_links(listing_html, listing_url):
            title = link["text"] or link["url"]
            if detail_marker and detail_marker not in link["url"]:
                continue
            if title_prefix and not title.startswith(title_prefix):
                continue
            combined = f"{title} {link['url']}"
            if link["url"] in seen_urls or is_excluded(combined, self.keyword_config):
                continue
            match = score_text(combined, self.keyword_config)
            if match.score < min_score or not has_domain_keyword(match.keywords, self.keyword_config):
                continue
            seen_urls.add(link["url"])
            candidates.append(link)
            if len(candidates) >= max_details:
                break

        notices: list[Notice] = []
        timeout = int(self.global_config.get("request_timeout_seconds", 20))
        user_agent = self.global_config.get("user_agent", "ClimateRfpTracker/0.1")
        for link in candidates:
            detail_html = fetch_text(link["url"], timeout=timeout, user_agent=user_agent)
            detail_text = html_to_text(detail_html)
            metadata = board_metadata(detail_text)
            if not self._within_days(metadata["published_at"], days):
                continue
            combined = f"{link['text']} {detail_text}"
            if is_excluded(combined, self.keyword_config):
                continue
            match = score_text(combined, self.keyword_config)
            if match.score < min_score or not has_domain_keyword(match.keywords, self.keyword_config):
                continue

            notices.append(
                Notice(
                    source_id=self.source["id"],
                    source_name=self.source["name"],
                    external_id=stable_id(self.source["id"], link["url"], link["text"]),
                    title=link["text"],
                    url=link["url"],
                    published_at=metadata["published_at"],
                    buyer=metadata["buyer"],
                    procurement_method=metadata["procurement_method"],
                    category="official_board_html",
                    relevance_score=match.score,
                    matched_keywords=match.keywords,
                    attachments=self._detail_attachments(detail_html, link["url"]),
                    raw={
                        "source_type": self.source["type"],
                        "source_url": listing_url,
                        "detail_url": link["url"],
                        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "detail_sha256": hashlib.sha256(detail_html.encode("utf-8")).hexdigest(),
                    },
                )
            )
            time.sleep(float(self.source.get("detail_delay_seconds", 0.2)))
        return notices

    def _detail_attachments(self, detail_html: str, detail_url: str) -> list[Attachment]:
        attachments: list[Attachment] = []
        seen_urls: set[str] = set()
        for link in parse_links(detail_html, detail_url):
            label = link["text"] or link["url"]
            file_type = extension_from_url(link["url"]) or extension_from_url(label)
            looks_like_document = bool(file_type) or has_any_term(label, self.keyword_config.get("document_terms", []))
            if not looks_like_document or link["url"] in seen_urls:
                continue
            seen_urls.add(link["url"])
            attachments.append(Attachment(label=label, url=link["url"], file_type=file_type))
        return attachments

    @staticmethod
    def _within_days(published_at: str, days: int) -> bool:
        if not published_at:
            return True
        try:
            published = datetime.strptime(published_at, "%Y-%m-%d")
        except ValueError:
            return True
        return (datetime.now() - published).days <= days


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return "\n".join(parser.parts)


def board_metadata(text: str) -> dict[str, str]:
    published_match = re.search(r"등록일\s*[:：]?\s*(20\d{2}[./-]\d{1,2}[./-]\d{1,2})", text)
    buyer_match = re.search(r"등록자\s*[:：]?\s*([^\n]{1,80})", text)
    published_at = published_match.group(1).replace(".", "-").replace("/", "-") if published_match else ""
    buyer = buyer_match.group(1).strip() if buyer_match else ""
    procurement_method = "전자입찰" if "전자입찰" in text else ""
    return {"published_at": published_at, "buyer": buyer, "procurement_method": procurement_method}


class G2BBidApiFetcher(BaseFetcher):
    def fetch(self, days: int) -> list[Notice]:
        env_name = self.source.get("service_key_env", "DATA_GO_KR_SERVICE_KEY")
        service_key = os.environ.get(env_name)
        if not service_key:
            print(f"[skip] {self.source['id']}: 환경변수 {env_name}가 없어 나라장터 API 호출을 건너뜁니다.")
            return []

        max_pages = int(self.source.get("max_pages", self.global_config.get("max_pages", 2)))
        timeout = int(self.global_config.get("request_timeout_seconds", 20))
        user_agent = self.global_config.get("user_agent", "ClimateRfpTracker/0.1")
        now = datetime.now()
        begin = (now - timedelta(days=days)).strftime("%Y%m%d") + "0000"
        end = now.strftime("%Y%m%d") + "2359"

        notices: list[Notice] = []
        for page_no in range(1, max_pages + 1):
            params = dict(self.source.get("default_params", {}))
            params.update(
                {
                    "inqryBgnDt": begin,
                    "inqryEndDt": end,
                    "pageNo": str(page_no),
                    self.source.get("service_key_param", "serviceKey"): service_key,
                }
            )
            url = self.source["endpoint"] + "?" + urlencode(params)
            payload = fetch_text(url, timeout=timeout, user_agent=user_agent)
            page_notices = self._parse_payload(payload)
            if not page_notices:
                break
            notices.extend(page_notices)
            time.sleep(0.2)

        return notices

    def _parse_payload(self, payload: str) -> list[Notice]:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            print("[warn] 나라장터 응답이 JSON 형식이 아닙니다. API키/권한/응답 포맷을 확인하세요.")
            return []

        api_error = data.get("OpenAPI_ServiceResponse", {}).get("cmmMsgHeader", {})
        if api_error:
            reason = str(api_error.get("returnReasonCode") or "unknown")
            message = str(api_error.get("errMsg") or "unknown error")
            print(f"[warn] 나라장터 API 응답 오류({reason}): {message}")
            return []

        items = data.get("response", {}).get("body", {}).get("items", [])
        if isinstance(items, dict) and "item" in items:
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return []
        notices: list[Notice] = []
        min_score = int(self.keyword_config.get("min_relevance_score", 2))

        for item in items:
            title = str(item.get("bidNtceNm") or item.get("bidNm") or item.get("ntceNm") or "").strip()
            if not title:
                continue
            combined_text = " ".join(str(value) for value in item.values() if value is not None)
            if is_excluded(combined_text, self.keyword_config):
                continue
            match = score_text(combined_text, self.keyword_config)
            if match.score < min_score or not has_domain_keyword(match.keywords, self.keyword_config):
                continue

            bid_no = str(item.get("bidNtceNo") or item.get("bidNo") or "").strip()
            bid_ord = str(item.get("bidNtceOrd") or item.get("bidOrd") or "").strip()
            external_id = "-".join(part for part in [bid_no, bid_ord] if part) or stable_id(self.source["id"], title)
            url = str(item.get("bidNtceDtlUrl") or item.get("ntceDtlUrl") or item.get("bidNtceUrl") or "").strip()

            attachments = self._extract_attachments(item)
            notices.append(
                Notice(
                    source_id=self.source["id"],
                    source_name=self.source["name"],
                    external_id=external_id,
                    title=title,
                    url=url,
                    published_at=str(item.get("bidNtceDt") or item.get("ntceDt") or ""),
                    deadline_at=str(item.get("bidClseDt") or item.get("opengDt") or ""),
                    buyer=str(item.get("dminsttNm") or item.get("ntceInsttNm") or ""),
                    budget=str(item.get("asignBdgtAmt") or item.get("presmptPrce") or ""),
                    procurement_method=str(item.get("cntrctCnclsMthdNm") or item.get("bidMethdNm") or ""),
                    category="g2b_bid_api",
                    relevance_score=match.score,
                    matched_keywords=match.keywords,
                    attachments=attachments,
                    raw=item,
                )
            )
        return notices

    def _extract_attachments(self, item: dict[str, Any]) -> list[Attachment]:
        attachments: list[Attachment] = []
        for key, value in item.items():
            if not value:
                continue
            key_lower = key.lower()
            value_text = str(value)
            if "url" in key_lower and extension_from_url(value_text):
                attachments.append(
                    Attachment(label=key, url=value_text, file_type=extension_from_url(value_text))
                )
        return attachments


def build_fetcher(source: dict[str, Any], keyword_config: dict[str, Any], global_config: dict[str, Any], root_dir: Path) -> BaseFetcher:
    source_type = source.get("type")
    if source_type in {"generic_html", "sample_html"}:
        return GenericHtmlFetcher(source, keyword_config, global_config, root_dir)
    if source_type == "official_board_html":
        return OfficialBoardFetcher(source, keyword_config, global_config, root_dir)
    if source_type == "g2b_bid_api":
        return G2BBidApiFetcher(source, keyword_config, global_config, root_dir)
    raise ValueError(f"지원하지 않는 source type입니다: {source_type}")
