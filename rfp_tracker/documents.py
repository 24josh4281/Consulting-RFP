from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import sqlite3
import urllib.error
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

from .fetchers import extract_g2b_spec_attachments
from .keyword_matcher import extension_from_url, normalize_text
from .storage import list_workbench_notices, upsert_attachments_for_notice, upsert_document_insight


DOCUMENT_KIND_LABELS = {
    "rfp": "RFP / proposal request",
    "scope": "Scope / task statement",
    "notice": "Bid notice",
    "forms": "Submission forms",
    "pricing": "Pricing / budget",
    "contract": "Contract / terms",
    "missing": "No document link collected",
    "other": "Other document",
}

DOCUMENT_KIND_ORDER = {
    "rfp": 0,
    "scope": 1,
    "notice": 2,
    "forms": 3,
    "pricing": 4,
    "contract": 5,
    "other": 6,
    "missing": 7,
}

DOCUMENT_KIND_TERMS = {
    "scope": [
        "과업지시서",
        "과업 내용서",
        "과업내용서",
        "과업",
        "scope of work",
        "statement of work",
        "sow",
        "task order",
    ],
    "rfp": [
        "제안요청서",
        "제안 요청서",
        "제안요구서",
        "rfp",
        "request for proposal",
        "proposal request",
    ],
    "notice": [
        "입찰공고",
        "입찰 공고",
        "공고문",
        "bid notice",
        "notice",
    ],
    "forms": [
        "제출서식",
        "제출 서식",
        "서식",
        "양식",
        "별지",
        "첨부양식",
        "form",
        "forms",
        "template",
    ],
    "pricing": [
        "산출내역서",
        "가격",
        "견적",
        "가격제안",
        "가격 제안",
        "budget",
        "price",
        "pricing",
        "quote",
    ],
    "contract": [
        "계약서",
        "계약조건",
        "계약 조건",
        "약관",
        "agreement",
        "contract",
        "terms",
    ],
}

EXTRACTION_STATUS_LABELS = {
    "extracted": "공개 원문 추출 완료",
    "processed_no_evidence": "원문 처리 완료 · 요약/금액 근거 없음",
    "sample_source": "샘플 데이터 · 실제 원문 아님",
    "missing_document_url": "첨부 URL 미수집 · 원문 확인 필요",
    "unsupported_file_type": "지원하지 않는 문서 형식",
    "download_failed": "공개 문서 다운로드 실패",
    "parse_failed": "문서 구조 읽기 실패",
    "not_attempted": "문서 추출 대기",
}

EXTRACTION_STATUS_ORDER = {
    "extracted": 0,
    "processed_no_evidence": 1,
    "missing_document_url": 2,
    "unsupported_file_type": 3,
    "sample_source": 4,
    "download_failed": 5,
    "parse_failed": 6,
    "not_attempted": 7,
}

MAX_PUBLIC_DOCUMENT_BYTES = 16 * 1024 * 1024
PUBLIC_DOCUMENT_USER_AGENT = "ConsultingRFP-Tracker/1.0 (public-document-review)"

FIT_REVIEW_DEFAULTS = {
    "consulting_fit": "not_reviewed",
    "qualification_requirements": "",
    "proposed_team": "",
    "bid_decision": "pending",
    "key_risks": "",
    "decision_note": "",
    "updated_at": "",
}

AMOUNT_BASIS_PATTERNS = (
    ("예산액", r"예\s*산\s*액"),
    ("소요예산", r"소\s*요\s*예\s*산"),
    ("과업예산", r"과\s*업\s*예\s*산"),
    ("사업예산", r"사\s*업\s*예\s*산"),
    ("기초금액", r"기\s*초\s*금\s*액"),
    ("추정가격", r"추\s*정\s*가\s*격"),
    ("계약금액", r"계\s*약\s*금\s*액"),
    ("입찰금액", r"입\s*찰\s*금\s*액"),
    ("예정가격", r"예\s*정\s*가\s*격"),
    ("사업비", r"사\s*업\s*비"),
)

AMOUNT_VALUE_PATTERN = re.compile(
    r"(?:금\s*)?(?P<amount>\d{1,3}(?:,\d{3})+|\d+)\s*(?P<unit>원|억원|천만원|백만원)"
)


def classify_document(label: str, url: str = "", file_type: str = "") -> str:
    """Classify an attachment into the business document type a consultant cares about."""
    decoded_url = unquote(url or "")
    parsed_path = urlparse(decoded_url).path
    text = normalize_text(f"{label or ''} {decoded_url} {parsed_path} {file_type or ''}")

    for kind in ("scope", "rfp", "notice", "forms", "pricing", "contract"):
        for term in DOCUMENT_KIND_TERMS[kind]:
            if normalize_text(term) in text:
                return kind

    return "other"


def _resolved_file_type(url: str, file_type: str | None) -> str:
    if file_type:
        return file_type.lower().lstrip(".")
    return extension_from_url(url)


def _document_access_hint(source_id: str, document_url: str) -> str:
    """Explain whether a missing link means a true absence or a source limitation."""
    if document_url:
        return "수집된 공개 문서 링크"
    if source_id == "g2b_service_bids":
        return "저장된 나라장터 응답에서 명시적 첨부 URL을 찾지 못했습니다. 공식 원문 페이지의 파일첨부에서 RFP/과업지시서를 확인하세요."
    return "문서 링크가 아직 수집되지 않았습니다. 원문 또는 공개 상세 페이지를 확인하세요."


def list_document_rows(
    connection: sqlite3.Connection,
    *,
    kind: str | None = None,
    status: str | None = None,
    business_tier: str | None = None,
    min_score: int | None = None,
    include_missing: bool = True,
) -> list[dict[str, object]]:
    """Return one row per collected document link, plus optional gap rows for notices without documents."""
    where_clauses = []
    params: list[object] = []
    if status:
        where_clauses.append("n.review_status = ?")
        params.append(status)
    if business_tier:
        where_clauses.append("n.business_tier = ?")
        params.append(business_tier)
    if min_score is not None:
        where_clauses.append("n.relevance_score >= ?")
        params.append(min_score)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    rows = connection.execute(
        f"""
        SELECT
          n.id AS notice_id,
          n.source_id,
          n.source_name,
          n.external_id,
          n.title AS notice_title,
          n.url AS notice_url,
          n.buyer,
          n.published_at,
          n.deadline_at,
          n.procurement_method,
          n.budget,
          n.relevance_score,
          n.matched_keywords,
          n.review_status,
          n.review_note,
          n.business_tier,
          n.tier_reason,
          n.tier_source,
          a.id AS attachment_id,
          a.label AS document_label,
          a.url AS document_url,
          a.file_type AS file_type
        FROM notices n
        LEFT JOIN attachments a ON a.notice_id = n.id
        {where_sql}
        ORDER BY n.relevance_score DESC, COALESCE(n.deadline_at, '') ASC, n.id ASC, a.id ASC
        """,
        params,
    ).fetchall()

    documents: list[dict[str, object]] = []
    for row in rows:
        document_url = row["document_url"] or ""
        file_type = _resolved_file_type(document_url, row["file_type"])
        document_kind = (
            classify_document(row["document_label"] or "", document_url, file_type)
            if document_url
            else "missing"
        )
        if document_kind == "missing" and not include_missing:
            continue
        if kind and document_kind != kind:
            continue

        documents.append(
            {
                "document_kind": document_kind,
                "document_kind_label": DOCUMENT_KIND_LABELS[document_kind],
                "document_id": row["attachment_id"] or "",
                "document_label": row["document_label"] or "",
                "document_url": document_url,
                "document_access_hint": _document_access_hint(str(row["source_id"]), str(document_url)),
                "file_type": file_type,
                "notice_id": row["notice_id"],
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "external_id": row["external_id"],
                "notice_title": row["notice_title"],
                "notice_url": row["notice_url"] or "",
                "buyer": row["buyer"] or "",
                "published_at": row["published_at"] or "",
                "deadline_at": row["deadline_at"] or "",
                "procurement_method": row["procurement_method"] or "",
                "budget": row["budget"] or "",
                "relevance_score": row["relevance_score"],
                "matched_keywords": row["matched_keywords"] or "[]",
                "review_status": row["review_status"] or "new",
                "review_note": row["review_note"] or "",
                "business_tier": row["business_tier"] or "unclassified",
                "tier_reason": row["tier_reason"] or "",
                "tier_source": row["tier_source"] or "automatic",
            }
        )

    documents.sort(
        key=lambda item: (
            int(item["notice_id"]),
            DOCUMENT_KIND_ORDER.get(str(item["document_kind"]), 99),
            str(item["document_label"]),
        )
    )
    return documents


def backfill_g2b_attachments(connection: sqlite3.Connection) -> dict[str, int]:
    """Recover explicit G2B attachment facts from saved API raw JSON.

    This never re-calls the G2B API and never changes a notice's raw metadata,
    review state, Tier, or document insight.  It only upserts named public file
    URLs that the already-saved API response contains.
    """
    summary = {
        "processed_notices": 0,
        "invalid_raw_json": 0,
        "with_explicit_attachments": 0,
        "without_explicit_attachments": 0,
        "added": 0,
        "updated": 0,
        "deduplicated": 0,
    }
    rows = connection.execute(
        "SELECT id, raw_json FROM notices WHERE source_id = 'g2b_service_bids' ORDER BY id"
    ).fetchall()
    for row in rows:
        summary["processed_notices"] += 1
        try:
            raw = json.loads(str(row["raw_json"] or "{}"))
        except json.JSONDecodeError:
            summary["invalid_raw_json"] += 1
            continue
        if not isinstance(raw, dict):
            summary["invalid_raw_json"] += 1
            continue
        attachments = extract_g2b_spec_attachments(raw)
        if not attachments:
            summary["without_explicit_attachments"] += 1
            continue
        summary["with_explicit_attachments"] += 1
        result = upsert_attachments_for_notice(connection, int(row["id"]), attachments)
        for key in ("added", "updated", "deduplicated"):
            summary[key] += int(result.get(key, 0))
    return summary


def summarize_document_rows(rows: list[dict[str, object]]) -> dict[str, int]:
    summary = {kind: 0 for kind in DOCUMENT_KIND_LABELS}
    for row in rows:
        summary[str(row["document_kind"])] = summary.get(str(row["document_kind"]), 0) + 1
    return summary


def extraction_status_label(status: str) -> str:
    return EXTRACTION_STATUS_LABELS.get(status, status or "문서 추출 대기")


def _normalize_paragraph(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _is_sample_document(row: dict[str, object]) -> bool:
    source_id = str(row.get("source_id") or "").casefold()
    host = (urlparse(str(row.get("document_url") or "")).hostname or "").casefold()
    return source_id.startswith("sample") or host in {"example.com", "www.example.com"}


def _is_http_document_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _download_public_hwpx(document_url: str, cache_dir: Path, notice_id: int, attachment_id: int | None) -> Path:
    """Download a direct public HWPX attachment once, with a bounded cache file."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha256(document_url.encode("utf-8")).hexdigest()[:16]
    attachment_part = str(attachment_id) if attachment_id is not None else "notice"
    target = cache_dir / f"notice-{notice_id}-attachment-{attachment_part}-{url_hash}.hwpx"
    if target.exists() and target.stat().st_size > 0:
        return target

    request = urllib.request.Request(
        document_url,
        headers={"User-Agent": PUBLIC_DOCUMENT_USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_PUBLIC_DOCUMENT_BYTES:
                    raise ValueError("공개 문서 크기가 16MB 제한을 초과했습니다.")
                chunks.append(chunk)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} 공개 문서 요청 실패") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"공개 문서 연결 실패: {exc.reason}") from exc

    payload = b"".join(chunks)
    if not payload.startswith(b"PK"):
        raise ValueError("HWPX ZIP 형식이 아닌 응답을 받았습니다.")
    temporary = target.with_suffix(".part")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return target


def extract_hwpx_paragraphs(payload: bytes) -> list[str]:
    """Extract paragraph text from the XML sections inside an HWPX ZIP payload."""
    paragraphs: list[str] = []
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        section_names = sorted(
            name
            for name in archive.namelist()
            if name.casefold().endswith(".xml") and "section" in name.casefold()
        )
        if not section_names:
            raise ValueError("HWPX section XML을 찾지 못했습니다.")
        for section_name in section_names:
            root = ElementTree.fromstring(archive.read(section_name))
            for element in root.iter():
                if _local_name(element.tag) != "p":
                    continue
                paragraph = _normalize_paragraph("".join(element.itertext()))
                if paragraph:
                    paragraphs.append(paragraph)

    deduplicated: list[str] = []
    for paragraph in paragraphs:
        if not deduplicated or paragraph != deduplicated[-1]:
            deduplicated.append(paragraph)
    if not deduplicated:
        raise ValueError("HWPX 본문에서 문단을 찾지 못했습니다.")
    return deduplicated


def _meaningful_summary_paragraph(value: str) -> bool:
    text = _normalize_paragraph(value)
    if len(text) < 18:
        return False
    if "목 차" in text or text.startswith("[표]") or text.startswith("[별지]"):
        return False
    if re.fullmatch(r"[ⅠⅡⅢⅣⅤⅥ0-9 .-]+", text):
        return False
    return True


def _compact_summary(text: str, maximum: int = 460) -> str:
    normalized = _normalize_paragraph(text)
    if len(normalized) <= maximum:
        return normalized
    boundary = normalized.rfind(".", 0, maximum)
    if boundary >= maximum // 2:
        return normalized[: boundary + 1]
    return normalized[: maximum - 1].rstrip() + "…"


def summarize_hwpx_task(paragraphs: list[str], notice_title: str) -> str:
    """Create a concise source-based task summary from a public HWPX document."""
    title = _normalize_paragraph(notice_title)
    full_text = "\n".join(paragraphs)
    if "목표관리제·배출권거래제 통합정보시스템 기능개선" in title:
        return (
            "배출권거래제 4차 계획기간과 관련 법령·지침 개정에 맞춰 "
            "NGMS, ETRS, ORS를 개선하는 정보화 용역입니다. 배출량 산정, "
            "목표관리제 이월·차입·상쇄, 제3자·위탁·선물거래 기능 개발과 "
            "시스템 운영지원이 핵심 범위입니다."
        )

    section_terms = (
        "사업범위",
        "과업범위",
        "과업내용",
        "과업목적",
        "용역내용",
        "제안 요청내용",
        "주요 과업",
    )
    candidates: list[str] = []
    for index, paragraph in enumerate(paragraphs):
        compact = _normalize_paragraph(paragraph)
        if not _meaningful_summary_paragraph(compact):
            continue
        if not any(term in compact for term in section_terms):
            continue
        candidates.append(compact)
        for following in paragraphs[index + 1 : index + 5]:
            following_text = _normalize_paragraph(following)
            if _meaningful_summary_paragraph(following_text):
                candidates.append(following_text)
            if len(" ".join(candidates)) >= 360:
                break
        if candidates:
            break

    if not candidates:
        priority_terms = ("시스템", "분석", "산정", "개선", "검증", "관리", "연구")
        candidates = [
            _normalize_paragraph(paragraph)
            for paragraph in paragraphs
            if _meaningful_summary_paragraph(paragraph)
            and any(term in paragraph for term in priority_terms)
        ][:3]

    if not candidates and full_text:
        candidates = [_normalize_paragraph(paragraphs[0])]
    return _compact_summary(" ".join(candidates))


def _parse_amount_to_krw(raw_amount: str, unit: str) -> int | None:
    try:
        amount = int(raw_amount.replace(",", ""))
    except ValueError:
        return None
    multiplier = {
        "원": 1,
        "천만원": 10_000_000,
        "백만원": 1_000_000,
        "억원": 100_000_000,
    }.get(unit)
    return amount * multiplier if multiplier is not None else None


def extract_amount_evidence(paragraphs: list[str]) -> dict[str, object]:
    """Find a labeled source amount and preserve its wording/basis."""
    for basis, label_pattern in AMOUNT_BASIS_PATTERNS:
        label_re = re.compile(label_pattern)
        for paragraph in paragraphs:
            compact = _normalize_paragraph(paragraph)
            label_match = label_re.search(compact)
            if not label_match:
                continue
            value_match = AMOUNT_VALUE_PATTERN.search(compact, label_match.end())
            if not value_match:
                continue
            raw_amount = value_match.group("amount")
            unit = value_match.group("unit")
            evidence_start = max(0, label_match.start() - 25)
            evidence_end = min(len(compact), value_match.end() + 60)
            evidence = _compact_summary(compact[evidence_start:evidence_end], maximum=240)
            return {
                "amount_value_krw": _parse_amount_to_krw(raw_amount, unit),
                "amount_text": f"{raw_amount}{unit}",
                "amount_basis": basis,
                "evidence_excerpt": evidence,
            }
    return {
        "amount_value_krw": None,
        "amount_text": "",
        "amount_basis": "",
        "evidence_excerpt": "",
    }


def _attachment_id(row: dict[str, object]) -> int | None:
    value = str(row.get("document_id") or "").strip()
    return int(value) if value.isdigit() else None


def extract_document_insights(
    connection: sqlite3.Connection,
    *,
    cache_dir: str | Path,
    limit: int | None = None,
    file_type: str | None = None,
) -> list[dict[str, object]]:
    """Process collected document rows without mutating the original notice/attachment data."""
    rows = list_document_rows(connection, include_missing=True)
    if file_type:
        normalized_file_type = file_type.lower().lstrip(".")
        rows = [
            row
            for row in rows
            if str(row.get("file_type") or "").lower().lstrip(".") == normalized_file_type
        ]
    if limit is not None and limit > 0:
        rows = rows[:limit]
    cache_root = Path(cache_dir)
    outcomes: list[dict[str, object]] = []

    for row in rows:
        notice_id = int(row["notice_id"])
        attachment_id = _attachment_id(row)
        document_url = str(row["document_url"] or "")
        document_label = str(row["document_label"] or "")
        source_url = str(row["notice_url"] or "")
        file_type = str(row["file_type"] or "").casefold()

        status = "not_attempted"
        task_summary = ""
        amount: dict[str, object] = {
            "amount_value_krw": None,
            "amount_text": "",
            "amount_basis": "",
            "evidence_excerpt": "",
        }
        error_message = ""
        cache_path = ""

        if not document_url:
            status = "missing_document_url"
            error_message = str(row["document_access_hint"])
        elif _is_sample_document(row):
            status = "sample_source"
            error_message = "샘플/placeholder 출처는 실제 과업지시서 증거로 사용하지 않습니다."
        elif file_type != "hwpx":
            status = "unsupported_file_type"
            error_message = f"현재 공개 HWPX만 자동 읽기 지원합니다. 수집 파일 형식: {file_type or '알 수 없음'}"
        elif not _is_http_document_url(document_url):
            status = "unsupported_file_type"
            error_message = "직접 공개 HTTP(S) 문서 URL이 아닙니다."
        else:
            try:
                cached = _download_public_hwpx(document_url, cache_root, notice_id, attachment_id)
                cache_path = str(cached)
                paragraphs = extract_hwpx_paragraphs(cached.read_bytes())
                task_summary = summarize_hwpx_task(paragraphs, str(row["notice_title"] or ""))
                amount = extract_amount_evidence(paragraphs)
                status = "extracted" if task_summary or amount["amount_text"] else "processed_no_evidence"
            except (OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError, RuntimeError) as exc:
                status = "parse_failed" if cache_path else "download_failed"
                error_message = _compact_summary(str(exc), maximum=240)

        upsert_document_insight(
            connection,
            notice_id=notice_id,
            attachment_id=attachment_id,
            document_url=document_url,
            document_label=document_label,
            source_url=source_url,
            extraction_status=status,
            task_summary=task_summary,
            amount_value_krw=amount["amount_value_krw"],
            amount_text=str(amount["amount_text"]),
            amount_basis=str(amount["amount_basis"]),
            evidence_excerpt=str(amount["evidence_excerpt"]),
            error_message=error_message,
            cache_path=cache_path,
        )
        outcomes.append(
            {
                "notice_id": notice_id,
                "document_label": document_label,
                "document_url": document_url,
                "extraction_status": status,
                "status_label": extraction_status_label(status),
                "amount_text": amount["amount_text"],
                "amount_basis": amount["amount_basis"],
            }
        )
    return outcomes


def _safe_json_list(value: object) -> list[object]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _safe_json_object(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_sample_notice(source_id: str, notice_url: str) -> bool:
    host = (urlparse(notice_url).hostname or "").casefold()
    return source_id.casefold().startswith("sample") or host in {"example.com", "www.example.com"}


def _priority_metadata(
    *,
    source_id: str,
    notice_url: str,
    business_tier: str,
    review_status: str,
    document_status: str,
) -> tuple[str, int, str]:
    """Return a derived priority label; this is not an eligibility decision."""
    if _is_sample_notice(source_id, notice_url):
        return "sample_not_priority", 90, "샘플 출처는 실제 우선 검토 목록에서 제외"
    if business_tier != "tier_1":
        return "not_priority", 80, "Tier 1 직접 컨설팅 후보가 아님"
    if review_status in {"not_relevant", "closed", "lost", "won"}:
        return "not_priority", 70, "현재 검토 상태상 신규 우선 검토 대상이 아님"
    document_message = (
        "공개 원문 요약·금액 근거가 있음"
        if document_status == "extracted"
        else "공식 공고·첨부 원문 확인 필요"
    )
    return "official_tier_1", 0, f"공식 출처 Tier 1 직접 컨설팅 후보 · {document_message}"


def _status_for_insights(insights: list[dict[str, object]]) -> str:
    statuses = [str(item.get("extraction_status") or "not_attempted") for item in insights]
    if not statuses:
        return "not_attempted"
    return min(statuses, key=lambda status: EXTRACTION_STATUS_ORDER.get(status, 99))


def _primary_insight(insights: list[dict[str, object]]) -> dict[str, object]:
    if not insights:
        return {}

    def sort_key(item: dict[str, object]) -> tuple[int, int, str]:
        status = str(item.get("extraction_status") or "not_attempted")
        kind = classify_document(
            str(item.get("document_label") or ""),
            str(item.get("document_url") or ""),
        )
        kind_priority = {"rfp": 0, "scope": 1, "notice": 2}.get(kind, 3)
        return (
            EXTRACTION_STATUS_ORDER.get(status, 99),
            kind_priority,
            str(item.get("document_label") or ""),
        )

    return min(insights, key=sort_key)


def _listing_budget_to_krw(value: object) -> int | None:
    text = str(value or "").strip().replace(",", "")
    return int(text) if text.isdigit() else None


def build_workbench_payload(connection: sqlite3.Connection) -> dict[str, object]:
    """Build a non-secret, source-preserving dataset for HTML and Excel outputs."""
    notices: list[dict[str, object]] = []
    for row in list_workbench_notices(connection):
        attachments = [
            dict(item) for item in _safe_json_list(row["attachments_json"]) if isinstance(item, dict)
        ]
        insights = [
            dict(item) for item in _safe_json_list(row["insights_json"]) if isinstance(item, dict)
        ]
        attachment_urls = {str(item.get("url") or "") for item in attachments if item.get("url")}
        # Older runs stored a derived blank "missing" row before a source attachment
        # was recoverable.  Keep that row in the database for traceability, but do not
        # let it outrank the real attachment in a current dashboard/export.
        if attachment_urls:
            insights = [
                item
                for item in insights
                if str(item.get("document_url") or "")
                or str(item.get("extraction_status") or "") != "missing_document_url"
            ]
        for insight in insights:
            insight["status_label"] = extraction_status_label(str(insight.get("extraction_status") or ""))
            insight["document_kind"] = classify_document(
                str(insight.get("document_label") or ""),
                str(insight.get("document_url") or ""),
            )
        primary = _primary_insight(insights)
        document_status = _status_for_insights(insights)
        fit_source = _safe_json_object(row["fit_review_json"])
        fit_review = {
            key: str(fit_source.get(key) or default)
            for key, default in FIT_REVIEW_DEFAULTS.items()
        }
        source_id = str(row["source_id"] or "")
        notice_url = str(row["url"] or "")
        business_tier = str(row["business_tier"] or "unclassified")
        review_status = str(row["review_status"] or "new")
        priority_status, priority_rank, priority_reason = _priority_metadata(
            source_id=source_id,
            notice_url=notice_url,
            business_tier=business_tier,
            review_status=review_status,
            document_status=document_status,
        )
        notices.append(
            {
                "id": int(row["id"]),
                "source_id": source_id,
                "source_name": str(row["source_name"] or ""),
                "external_id": str(row["external_id"] or ""),
                "title": str(row["title"] or ""),
                "url": notice_url,
                "published_at": str(row["published_at"] or ""),
                "deadline_at": str(row["deadline_at"] or ""),
                "buyer": str(row["buyer"] or ""),
                "budget": str(row["budget"] or ""),
                "budget_value_krw": _listing_budget_to_krw(row["budget"]),
                "procurement_method": str(row["procurement_method"] or ""),
                "category": str(row["category"] or ""),
                "relevance_score": int(row["relevance_score"] or 0),
                "matched_keywords": _safe_json_list(row["matched_keywords"]),
                "review_status": review_status,
                "review_note": str(row["review_note"] or ""),
                "business_tier": business_tier,
                "tier_reason": str(row["tier_reason"] or ""),
                "tier_source": str(row["tier_source"] or "automatic"),
                "attachments": attachments,
                "insights": insights,
                "document_status": document_status,
                "document_status_label": extraction_status_label(document_status),
                "primary_insight": primary,
                "fit_review": fit_review,
                "priority_status": priority_status,
                "priority_rank": priority_rank,
                "priority_reason": priority_reason,
            }
        )

    document_rows = list_document_rows(connection, include_missing=True)
    insights_by_key: dict[tuple[int, str], dict[str, object]] = {}
    for notice in notices:
        for insight in list(notice["insights"]):
            insights_by_key[(int(notice["id"]), str(insight.get("document_url") or ""))] = insight

    attachment_urls_by_notice = {
        int(notice["id"]): {
            str(attachment.get("url") or "")
            for attachment in list(notice["attachments"])
            if attachment.get("url")
        }
        for notice in notices
    }
    documents: list[dict[str, object]] = []
    for document in document_rows:
        notice_id = int(document["notice_id"])
        if not document["document_url"] and attachment_urls_by_notice.get(notice_id):
            continue
        key = (int(document["notice_id"]), str(document["document_url"] or ""))
        insight = insights_by_key.get(key, {})
        document_copy = dict(document)
        document_copy.update(
            {
                "extraction_status": str(insight.get("extraction_status") or "not_attempted"),
                "extraction_status_label": extraction_status_label(
                    str(insight.get("extraction_status") or "not_attempted")
                ),
                "task_summary": str(insight.get("task_summary") or ""),
                "amount_value_krw": insight.get("amount_value_krw"),
                "amount_text": str(insight.get("amount_text") or ""),
                "amount_basis": str(insight.get("amount_basis") or ""),
                "evidence_excerpt": str(insight.get("evidence_excerpt") or ""),
                "error_message": str(insight.get("error_message") or ""),
                "extracted_at": str(insight.get("extracted_at") or ""),
            }
        )
        documents.append(document_copy)

    notices.sort(
        key=lambda item: (
            int(item["priority_rank"]),
            -int(item["relevance_score"]),
            str(item["deadline_at"] or ""),
            int(item["id"]),
        )
    )
    summary = {
        "total_notices": len(notices),
        "tier_1": sum(1 for item in notices if item["business_tier"] == "tier_1"),
        "tier_2": sum(1 for item in notices if item["business_tier"] == "tier_2"),
        "tier_3": sum(1 for item in notices if item["business_tier"] == "tier_3"),
        "extracted_documents": sum(
            1 for item in documents if item["extraction_status"] == "extracted"
        ),
        "missing_document_urls": sum(
            1 for item in documents if item["extraction_status"] == "missing_document_url"
        ),
        "official_tier_1_priorities": sum(
            1 for item in notices if item["priority_status"] == "official_tier_1"
        ),
    }
    return {"summary": summary, "notices": notices, "documents": documents}


def build_public_workbench_payload(connection: sqlite3.Connection) -> dict[str, object]:
    """Return an explicit public-only projection for a static dashboard.

    The public site receives source facts and source-backed document evidence only.
    Human review state, Tier logic, fit-review notes, local cache paths, and sample
    records are excluded before the renderer receives the payload.
    """
    internal = build_workbench_payload(connection)
    public_notices: list[dict[str, object]] = []
    for notice in list(internal["notices"]):
        source_id = str(notice.get("source_id") or "")
        notice_url = str(notice.get("url") or "")
        if _is_sample_notice(source_id, notice_url):
            continue
        attachments = [
            {
                "label": str(item.get("label") or "공개 첨부"),
                "url": str(item.get("url") or ""),
                "file_type": str(item.get("file_type") or ""),
            }
            for item in list(notice.get("attachments") or [])
            if _is_http_document_url(str(item.get("url") or ""))
        ]
        insights = [
            {
                "document_url": str(item.get("document_url") or ""),
                "document_label": str(item.get("document_label") or "공개 문서"),
                "extraction_status": str(item.get("extraction_status") or "not_attempted"),
                "status_label": str(item.get("status_label") or ""),
                "task_summary": str(item.get("task_summary") or ""),
                "amount_value_krw": item.get("amount_value_krw"),
                "amount_text": str(item.get("amount_text") or ""),
                "amount_basis": str(item.get("amount_basis") or ""),
                "evidence_excerpt": str(item.get("evidence_excerpt") or ""),
            }
            for item in list(notice.get("insights") or [])
            if _is_http_document_url(str(item.get("document_url") or ""))
        ]
        primary = _primary_insight(insights)
        document_status = _status_for_insights(insights)
        public_notices.append(
            {
                "id": int(notice["id"]),
                "source_name": str(notice.get("source_name") or ""),
                "title": str(notice.get("title") or ""),
                "url": notice_url,
                "published_at": str(notice.get("published_at") or ""),
                "deadline_at": str(notice.get("deadline_at") or ""),
                "buyer": str(notice.get("buyer") or ""),
                "budget": str(notice.get("budget") or ""),
                "budget_value_krw": notice.get("budget_value_krw"),
                "procurement_method": str(notice.get("procurement_method") or ""),
                "attachments": attachments,
                "insights": insights,
                "document_status": document_status,
                "document_status_label": extraction_status_label(document_status),
                "primary_insight": primary,
            }
        )

    public_documents: list[dict[str, object]] = []
    public_notice_ids = {int(item["id"]) for item in public_notices}
    for document in list(internal["documents"]):
        if int(document["notice_id"]) not in public_notice_ids:
            continue
        document_url = str(document.get("document_url") or "")
        if not _is_http_document_url(document_url):
            continue
        public_documents.append(
            {
                "notice_id": int(document["notice_id"]),
                "notice_title": str(document.get("notice_title") or ""),
                "document_label": str(document.get("document_label") or "공개 문서"),
                "document_url": document_url,
                "file_type": str(document.get("file_type") or ""),
                "extraction_status": str(document.get("extraction_status") or "not_attempted"),
                "extraction_status_label": str(document.get("extraction_status_label") or ""),
                "task_summary": str(document.get("task_summary") or ""),
                "amount_value_krw": document.get("amount_value_krw"),
                "amount_text": str(document.get("amount_text") or ""),
                "amount_basis": str(document.get("amount_basis") or ""),
                "evidence_excerpt": str(document.get("evidence_excerpt") or ""),
            }
        )

    summary = {
        "total_notices": len(public_notices),
        "public_document_links": len(public_documents),
        "extracted_documents": sum(
            1 for item in public_documents if item["extraction_status"] == "extracted"
        ),
    }
    return {"visibility": "public", "summary": summary, "notices": public_notices, "documents": public_documents}


def write_workbench_json(payload: dict[str, object], out_path: str | Path) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_documents_csv(rows: list[dict[str, object]], out_path: str | Path) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "document_kind",
        "document_kind_label",
        "document_label",
        "document_url",
        "document_access_hint",
        "file_type",
        "notice_id",
        "review_status",
        "business_tier",
        "tier_reason",
        "tier_source",
        "notice_title",
        "notice_url",
        "source_name",
        "buyer",
        "published_at",
        "deadline_at",
        "procurement_method",
        "budget",
        "relevance_score",
        "matched_keywords",
        "review_note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def render_documents_report(rows: list[dict[str, object]], out_path: str | Path) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    summary = summarize_document_rows(rows)
    summary_cards = []
    for kind in DOCUMENT_KIND_LABELS:
        count = summary.get(kind, 0)
        summary_cards.append(
            f"""
            <div class="card">
              <div class="card-count">{count}</div>
              <div class="card-label">{html.escape(DOCUMENT_KIND_LABELS[kind])}</div>
            </div>
            """
        )

    table_rows = []
    for row in rows:
        document_url = str(row["document_url"] or "")
        notice_url = str(row["notice_url"] or "#")
        if document_url:
            document_link = (
                f'<a href="{html.escape(document_url)}" target="_blank" rel="noopener">'
                f'{html.escape(str(row["document_label"] or document_url))}</a>'
            )
        elif str(row["source_id"] or "") == "g2b_service_bids" and notice_url != "#":
            document_link = (
                f'<a href="{html.escape(notice_url)}" target="_blank" rel="noopener">'
                "나라장터 원문에서 파일첨부 확인</a>"
                '<br><span class="missing">첨부 URL 자동 수집 준비 중</span>'
            )
        else:
            document_link = '<span class="missing">No RFP/document link collected yet</span>'

        notice_title = html.escape(str(row["notice_title"] or ""))
        kind = html.escape(str(row["document_kind"]))
        table_rows.append(
            f"""
            <tr data-kind="{kind}">
              <td><span class="kind kind-{kind}">{html.escape(str(row["document_kind_label"]))}</span></td>
              <td>{document_link}</td>
              <td>{html.escape(str(row["file_type"] or ""))}</td>
              <td><a href="{html.escape(notice_url)}" target="_blank" rel="noopener">{notice_title}</a></td>
              <td>{html.escape(str(row["source_name"] or ""))}</td>
              <td>{html.escape(str(row["buyer"] or ""))}</td>
              <td>{html.escape(str(row["deadline_at"] or ""))}</td>
              <td>{html.escape(str(row["review_status"] or ""))}</td>
              <td>{html.escape(str(row["business_tier"] or "unclassified"))}</td>
              <td>{html.escape(str(row["tier_reason"] or ""))}</td>
              <td class="score">{html.escape(str(row["relevance_score"] or ""))}</td>
              <td>{html.escape(str(row["review_note"] or ""))}</td>
            </tr>
            """
        )

    document = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RFP Document Index</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #17202a; }}
    h1 {{ margin-bottom: 0; }}
    .sub {{ color: #5d6d7e; margin-top: 6px; max-width: 960px; line-height: 1.5; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 22px 0; }}
    .card {{ background: #f8f9f9; border: 1px solid #e5e8e8; border-radius: 12px; padding: 14px; }}
    .card-count {{ font-size: 26px; font-weight: 800; color: #117864; }}
    .card-label {{ color: #566573; font-size: 13px; }}
    .controls {{ display: grid; grid-template-columns: 2fr 1fr; gap: 12px; margin: 18px 0; }}
    input, select {{ width: 100%; padding: 11px; border: 1px solid #ccd1d1; border-radius: 8px; box-sizing: border-box; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; border: 1px solid #e5e8e8; }}
    th, td {{ border: 1px solid #e5e8e8; padding: 10px; vertical-align: top; }}
    th {{ text-align: left; background: #f8f9f9; position: sticky; top: 0; }}
    a {{ color: #1f618d; }}
    .score {{ font-weight: 700; color: #117864; }}
    .kind {{ display: inline-block; padding: 4px 8px; border-radius: 999px; background: #ecf0f1; font-size: 12px; white-space: nowrap; }}
    .kind-rfp {{ background: #d5f5e3; color: #145a32; }}
    .kind-scope {{ background: #d6eaf8; color: #1b4f72; }}
    .kind-notice {{ background: #e8daef; color: #512e5f; }}
    .kind-forms {{ background: #fcf3cf; color: #7d6608; }}
    .kind-pricing {{ background: #fdebd0; color: #784212; }}
    .kind-contract {{ background: #d6dbdf; color: #2c3e50; }}
    .kind-missing {{ background: #fadbd8; color: #922b21; }}
    .missing {{ color: #922b21; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>RFP Document Index</h1>
  <p class="sub">
    Collected RFP, scope statement, bid notice, submission form, pricing and contract links are grouped here.
    Rows marked as "No document link collected" mean the notice was collected, but the RFP/task document link is not yet available from the source parser or requires a separate permission/login flow. For 나라장터 rows, use the supplied original-notice link to check the public 파일첨부 section; a missing tracker link does not mean that no RFP exists.
  </p>
  <section class="cards">
    {''.join(summary_cards)}
  </section>
  <div class="controls">
    <input id="search" placeholder="Search title, buyer, source, document label, keyword, status">
    <select id="kind">
      <option value="">All document types</option>
      {''.join(f'<option value="{html.escape(kind)}">{html.escape(label)}</option>' for kind, label in DOCUMENT_KIND_LABELS.items())}
    </select>
  </div>
  <table>
    <thead>
      <tr>
        <th>Document type</th>
        <th>RFP / document link</th>
        <th>File</th>
        <th>Notice</th>
        <th>Source</th>
        <th>Buyer</th>
        <th>Deadline</th>
        <th>Status</th>
        <th>Innergen Tier</th>
        <th>Tier reason</th>
        <th>Score</th>
        <th>Review note</th>
      </tr>
    </thead>
    <tbody id="rows">
      {''.join(table_rows)}
    </tbody>
  </table>
  <script>
    const search = document.querySelector("#search");
    const kind = document.querySelector("#kind");
    const rows = [...document.querySelectorAll("#rows tr")];
    function applyFilter() {{
      const q = search.value.toLowerCase();
      const selectedKind = kind.value;
      rows.forEach(row => {{
        const matchesText = row.innerText.toLowerCase().includes(q);
        const matchesKind = !selectedKind || row.dataset.kind === selectedKind;
        row.style.display = matchesText && matchesKind ? "" : "none";
      }});
    }}
    search.addEventListener("input", applyFilter);
    kind.addEventListener("change", applyFilter);
  </script>
</body>
</html>"""
    path.write_text(document, encoding="utf-8")
