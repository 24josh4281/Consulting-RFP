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
from zoneinfo import ZoneInfo

from .keyword_matcher import (
    assess_g2b_title,
    extension_from_url,
    has_any_term,
    is_climate_related_title,
    is_excluded,
    normalize_text,
    score_text,
)
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
        notices: list[Notice] = []
        for source in self._source_variants():
            fetcher = self if source is self.source else G2BBidApiFetcher(
                source, self.keyword_config, self.global_config, self.root_dir
            )
            notices.extend(fetcher._fetch_recent(days))
        return self._deduplicate_notices(notices)

    def _fetch_recent(self, days: int) -> list[Notice]:
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

    def fetch_open_notices(
        self,
        *,
        days: int,
        search_terms: list[str],
        max_pages_per_term: int = 3,
        closed_notice_exclusion: str = "Y",
        include_all_notices: bool = False,
        max_pages_per_query: int = 100,
        max_requests: int = 500,
    ) -> list[Notice]:
        """Search all configured G2B procurement types for currently open bids.

        In all-notice mode, the official PPSSrch operations are queried without a title
        filter and every result page is collected (up to the configured safety caps).
        A local deadline check is always applied as a second expired-notice guard.
        """
        notices: list[Notice] = []
        request_budget = {"used": 0, "limit": max(1, int(max_requests))}
        for source in self._source_variants():
            fetcher = self if source is self.source else G2BBidApiFetcher(
                source, self.keyword_config, self.global_config, self.root_dir
            )
            notices.extend(
                fetcher._fetch_open_for_source(
                    days=days,
                    search_terms=search_terms,
                    max_pages_per_term=max_pages_per_term,
                    closed_notice_exclusion=closed_notice_exclusion,
                    include_all_notices=include_all_notices,
                    max_pages_per_query=max_pages_per_query,
                    request_budget=request_budget,
                )
            )
        return self._deduplicate_notices(notices)

    def _fetch_open_for_source(
        self,
        *,
        days: int,
        search_terms: list[str],
        max_pages_per_term: int,
        closed_notice_exclusion: str,
        include_all_notices: bool,
        max_pages_per_query: int,
        request_budget: dict[str, int],
    ) -> list[Notice]:
        env_name = self.source.get("service_key_env", "DATA_GO_KR_SERVICE_KEY")
        service_key = os.environ.get(env_name)
        if not service_key:
            print(f"[skip] {self.source['id']}: 환경변수 {env_name}가 없어 보정 조회를 건너뜁니다.")
            return []

        endpoint = str(self.source.get("endpoint") or "")
        if "PPSSrch" not in endpoint:
            raise ValueError(f"현재공고 검색용 PPSSrch endpoint가 아닙니다: {self.source['id']}")

        timeout = int(self.global_config.get("request_timeout_seconds", 20))
        user_agent = self.global_config.get("user_agent", "ClimateRfpTracker/0.1")
        page_size = int(self.source.get("default_params", {}).get("numOfRows", 100))
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        remaining_days = max(1, days)
        window_end = now.date()
        date_windows: list[tuple[str, str]] = []
        while remaining_days > 0:
            window_days = min(30, remaining_days)
            window_start = window_end - timedelta(days=window_days - 1)
            date_windows.append((window_start.strftime("%Y%m%d"), window_end.strftime("%Y%m%d")))
            remaining_days -= window_days
            window_end = window_start - timedelta(days=1)
        request_delay = float(self.global_config.get("open_reconcile_request_delay_seconds", 0.05))
        notices: list[Notice] = []

        terms = [""] if include_all_notices else list(
            dict.fromkeys(str(value).strip() for value in search_terms if str(value).strip())
        )
        for term in terms:
            for start_date, end_date in date_windows:
                begin = start_date + "0000"
                end = end_date + "2359"
                page_limit = max(1, max_pages_per_query if include_all_notices else max_pages_per_term)
                for page_no in range(1, page_limit + 1):
                    if request_budget["used"] >= request_budget["limit"]:
                        raise RuntimeError(
                            "나라장터 전체공고 조회의 요청 안전한도에 도달했습니다. "
                            "운영 계정의 호출 허용량과 조회기간을 확인하세요."
                        )
                    params = dict(self.source.get("default_params", {}))
                    params.update(
                        {
                            "inqryBgnDt": begin,
                            "inqryEndDt": end,
                            "pageNo": str(page_no),
                            "bidClseExcpYn": closed_notice_exclusion,
                            self.source.get("service_key_param", "serviceKey"): service_key,
                        }
                    )
                    if term:
                        params["bidNtceNm"] = term
                    url = endpoint + "?" + urlencode(params)
                    request_budget["used"] += 1
                    payload = fetch_text(url, timeout=timeout, user_agent=user_agent)
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(f"{self.source['id']} API가 JSON이 아닌 응답을 반환했습니다.") from exc
                    error_response = data.get("nkoneps.com.response.ResponseError", {})
                    service_response = data.get("OpenAPI_ServiceResponse", {}).get("cmmMsgHeader", {})
                    if service_response:
                        result_code = str(service_response.get("returnReasonCode") or "API 오류")
                        result_message = str(service_response.get("errMsg") or "API 응답 오류")
                        raise RuntimeError(f"{self.source['id']} API 오류 {result_code}: {result_message}")
                    if error_response:
                        header = error_response.get("header", {})
                    else:
                        response = data.get("response", {})
                        header = response.get("header", {}) if isinstance(response, dict) else {}
                    result_code = str(header.get("resultCode") or "")
                    if result_code and result_code != "00":
                        result_message = str(header.get("resultMsg") or "API 응답 오류")
                        raise RuntimeError(f"{self.source['id']} API 오류 {result_code}: {result_message}")
                    page_items = self._payload_items(payload)
                    page_notices = self._parse_payload(payload, include_all_notices=include_all_notices)
                    notices.extend(item for item in page_notices if self._is_currently_open(item, now))

                    try:
                        total_count = int(data.get("response", {}).get("body", {}).get("totalCount", 0))
                    except (AttributeError, TypeError, ValueError):
                        total_count = 0
                    if include_all_notices and page_no == 1 and total_count:
                        required_pages = (total_count + page_size - 1) // page_size
                        if required_pages > page_limit:
                            raise RuntimeError(
                                f"{self.source['id']} {start_date}-{end_date} 조회에 {required_pages}페이지가 필요하지만 "
                                f"안전한도는 {page_limit}페이지입니다. 조회를 축소하지 않고 중단했습니다."
                            )
                    if request_delay > 0:
                        time.sleep(request_delay)
                    if not page_items or (total_count and page_no * page_size >= total_count):
                        break

        return notices

    def _source_variants(self) -> list[dict[str, Any]]:
        variants = [self.source]
        for endpoint in self.source.get("additional_endpoints", []):
            variant = dict(self.source)
            variant.pop("additional_endpoints", None)
            variant.update(endpoint)
            variants.append(variant)
        return variants

    @staticmethod
    def _payload_items(payload: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return []
        body = data.get("response", {}).get("body", {})
        items = body.get("items", [])
        if isinstance(items, dict) and "item" in items:
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    @staticmethod
    def _parse_bid_datetime(value: object, now: datetime) -> datetime | None:
        value_text = str(value or "").strip()
        if not value_text:
            return None
        try:
            parsed = datetime.fromisoformat(value_text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=now.tzinfo)
            else:
                parsed = parsed.astimezone(now.tzinfo)
            return parsed
        except ValueError:
            digits = "".join(character for character in value_text if character.isdigit())
            for pattern, length in (("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12), ("%Y%m%d", 8)):
                if len(digits) >= length:
                    try:
                        return datetime.strptime(digits[:length], pattern).replace(tzinfo=now.tzinfo)
                    except ValueError:
                        continue
            return None

    @classmethod
    def _is_currently_open(cls, notice: Notice, now: datetime) -> bool:
        # A future notice is published but is not yet accepting bids.
        begin_at = cls._parse_bid_datetime((notice.raw or {}).get("bidBeginDt"), now)
        if begin_at is not None and begin_at > now:
            return False
        deadline = cls._parse_bid_datetime(notice.deadline_at, now)
        return deadline is None or deadline >= now

    @staticmethod
    def _deduplicate_notices(notices: list[Notice]) -> list[Notice]:
        unique: dict[tuple[str, str], Notice] = {}
        for notice in notices:
            unique[(notice.source_id, notice.external_id)] = notice
        return list(unique.values())

    def _parse_payload(self, payload: str, *, include_all_notices: bool = False) -> list[Notice]:
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
        for item in items:
            title = str(item.get("bidNtceNm") or item.get("bidNm") or item.get("ntceNm") or "").strip()
            if not title:
                continue
            if is_excluded(title, self.keyword_config):
                continue
            assessment = assess_g2b_title(title, self.keyword_config)
            if not is_climate_related_title(title, self.keyword_config):
                continue
            match = assessment.match

            bid_no = str(item.get("bidNtceNo") or item.get("bidNo") or "").strip()
            bid_ord = str(item.get("bidNtceOrd") or item.get("bidOrd") or "").strip()
            external_id = "-".join(part for part in [bid_no, bid_ord] if part) or stable_id(self.source["id"], title)
            url = str(item.get("bidNtceDtlUrl") or item.get("ntceDtlUrl") or item.get("bidNtceUrl") or "").strip()

            attachments = self._extract_attachments(item)
            needs_review = assessment.tier == "needs_review"
            intake_note = (
                "공고명에 강한 기후·온실가스·ETS·환경 컨설팅 신호가 없어 사람 검토가 필요합니다."
                if needs_review
                else ""
            )
            raw = dict(item)
            raw["_tracker_intake"] = {
                "rule": "g2b_all_current_v2_domain_filtered" if include_all_notices else "g2b_title_policy_v1",
                "tier": assessment.tier,
                "title_matched_keywords": match.keywords,
                "strong_keywords": assessment.strong_keywords,
            }
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
                    category="g2b_bid_api_review" if needs_review else "g2b_bid_api",
                    relevance_score=match.score,
                    matched_keywords=match.keywords,
                    attachments=attachments,
                    review_status="needs_review" if needs_review else "new",
                    review_note=intake_note,
                    raw=raw,
                )
            )
        return notices

    def _extract_attachments(self, item: dict[str, Any]) -> list[Attachment]:
        return extract_g2b_spec_attachments(item)


def extract_g2b_spec_attachments(item: dict[str, Any]) -> list[Attachment]:
    """Return direct G2B notice attachments from an API item.

    나라장터의 ``ntceSpecDocUrlN`` download endpoints do not expose a filename
    extension in the URL.  The paired ``ntceSpecFileNmN`` field is therefore the
    authoritative file-type signal.  Keeping this parser outside the fetcher also
    lets existing saved raw API responses be repaired without another API call.
    """
    attachments: list[Attachment] = []
    seen_urls: set[str] = set()

    def add_attachment(label: object, url: object, file_type: str = "") -> None:
        label_text = str(label or "").strip()
        url_text = str(url or "").strip()
        parsed = urlsplit(url_text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or url_text in seen_urls:
            return
        seen_urls.add(url_text)
        attachments.append(
            Attachment(
                label=label_text or "나라장터 첨부",
                url=url_text,
                file_type=(file_type or extension_from_url(label_text) or extension_from_url(url_text)).lower(),
            )
        )

    # The service returns these fields in numbered pairs.  Read the explicit pair
    # first so an extension-less download URL still becomes a usable document link.
    for sequence in range(1, 11):
        document_url = item.get(f"ntceSpecDocUrl{sequence}")
        file_name = item.get(f"ntceSpecFileNm{sequence}")
        if document_url:
            add_attachment(file_name or f"나라장터 첨부 {sequence}", document_url)

    # Retain support for other providers/versions that return an ordinary URL with
    # its extension already visible.  Direct named links above are de-duplicated.
    for key, value in item.items():
        if not value or "url" not in key.lower():
            continue
        value_text = str(value).strip()
        file_type = extension_from_url(value_text)
        if file_type:
            add_attachment(key, value_text, file_type)

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
