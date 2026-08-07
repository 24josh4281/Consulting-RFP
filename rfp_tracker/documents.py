from __future__ import annotations

import csv
import html
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from .keyword_matcher import extension_from_url, normalize_text


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


def list_document_rows(
    connection: sqlite3.Connection,
    *,
    kind: str | None = None,
    status: str | None = None,
    min_score: int | None = None,
    include_missing: bool = True,
) -> list[dict[str, object]]:
    """Return one row per collected document link, plus optional gap rows for notices without documents."""
    where_clauses = []
    params: list[object] = []
    if status:
        where_clauses.append("n.review_status = ?")
        params.append(status)
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


def summarize_document_rows(rows: list[dict[str, object]]) -> dict[str, int]:
    summary = {kind: 0 for kind in DOCUMENT_KIND_LABELS}
    for row in rows:
        summary[str(row["document_kind"])] = summary.get(str(row["document_kind"]), 0) + 1
    return summary


def write_documents_csv(rows: list[dict[str, object]], out_path: str | Path) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "document_kind",
        "document_kind_label",
        "document_label",
        "document_url",
        "file_type",
        "notice_id",
        "review_status",
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
        if document_url:
            document_link = (
                f'<a href="{html.escape(document_url)}" target="_blank" rel="noopener">'
                f'{html.escape(str(row["document_label"] or document_url))}</a>'
            )
        else:
            document_link = '<span class="missing">No RFP/document link collected yet</span>'

        notice_url = str(row["notice_url"] or "#")
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
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #e5e8e8; padding: 10px; vertical-align: top; }}
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
    Rows marked as "No document link collected" mean the notice was collected, but the RFP/task document link is not yet available from the source parser or requires a separate permission/login flow.
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
