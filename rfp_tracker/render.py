from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import urlparse

from .documents import extraction_status_label
from .public_ui import PUBLIC_DASHBOARD_CSS, PUBLIC_DASHBOARD_JS
from .tiering import tier_label, tier_short_label


def render_dashboard(rows: list, out_path: str | Path) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    cards = []
    for row in rows:
        keywords = ", ".join(json.loads(row["matched_keywords"] or "[]"))
        attachments = json.loads(row["attachments_json"] or "[]")
        attachment_links = " ".join(
            f'<a href="{html.escape(item["url"])}" target="_blank">{html.escape(item["label"] or item["file_type"] or "첨부")}</a>'
            for item in attachments
            if item.get("url")
        )
        title = html.escape(row["title"])
        url = html.escape(row["url"] or "#")
        business_tier = str(row["business_tier"] or "unclassified")
        tier_reason = str(row["tier_reason"] or "원문 확인 필요")
        cards.append(
            f"""
            <tr>
              <td class="score">{row["relevance_score"]}</td>
              <td>{row["id"]}</td>
              <td><span class="status status-{html.escape(row["review_status"] or "new")}">{html.escape(row["review_status"] or "new")}</span></td>
              <td><span class="tier tier-{html.escape(business_tier)}" title="{html.escape(tier_label(business_tier), quote=True)}">{html.escape(tier_short_label(business_tier))}</span><br><span class="tier-reason">{html.escape(tier_reason)}</span></td>
              <td><a href="{url}" target="_blank">{title}</a></td>
              <td>{html.escape(row["source_name"] or "")}</td>
              <td>{html.escape(row["buyer"] or "")}</td>
              <td>{html.escape(row["deadline_at"] or "")}</td>
              <td>{html.escape(keywords)}</td>
              <td>{attachment_links}</td>
              <td>{html.escape(row["review_note"] or "")}</td>
            </tr>
            """
        )

    document = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Climate RFP Tracker</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #17202a; }}
    h1 {{ margin-bottom: 0; }}
    .sub {{ color: #5d6d7e; margin-top: 6px; }}
    input {{ width: 100%; padding: 12px; margin: 18px 0; border: 1px solid #ccd1d1; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; border: 1px solid #d8e2db; }}
    th, td {{ border: 1px solid #e5e8e8; padding: 10px; vertical-align: top; }}
    th {{ text-align: left; background: #f8f9f9; position: sticky; top: 0; }}
    .score {{ font-weight: 700; color: #117864; }}
    .status {{ display: inline-block; padding: 3px 8px; border-radius: 999px; background: #ecf0f1; font-size: 12px; }}
    .status-interesting {{ background: #d5f5e3; color: #145a32; }}
    .status-not_relevant {{ background: #fadbd8; color: #922b21; }}
    .status-submitted {{ background: #d6eaf8; color: #1b4f72; }}
    .status-watch {{ background: #fcf3cf; color: #7d6608; }}
    .status-needs_review {{ background: #fce4c3; color: #8a4b08; }}
    .tier {{ display: inline-block; padding: 3px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; white-space: nowrap; }}
    .tier-tier_1 {{ background: #d5f5e3; color: #145a32; }}
    .tier-tier_2 {{ background: #fcf3cf; color: #7d6608; }}
    .tier-unclassified {{ background: #ecf0f1; color: #566573; }}
    .tier-reason {{ display: inline-block; margin-top: 5px; color: #5d6d7e; font-size: 12px; line-height: 1.4; max-width: 220px; }}
    a {{ color: #1f618d; }}
  </style>
</head>
<body>
  <h1>Climate RFP Tracker</h1>
  <p class="sub">기후·온실가스·배출권거래제·ESG 관련 입찰 공고 후보 {len(rows)}건</p>
  <input id="search" placeholder="검색: CDP, 배출권, 온실가스, 기관명 등">
  <table>
    <thead>
      <tr>
        <th>점수</th>
        <th>ID</th>
        <th>검토상태</th>
        <th>이너젠 Tier / 근거</th>
        <th>공고명</th>
        <th>출처</th>
        <th>수요/발주기관</th>
        <th>마감/개찰</th>
        <th>매칭 키워드</th>
        <th>첨부 후보</th>
        <th>검토 메모</th>
      </tr>
    </thead>
    <tbody id="rows">
      {''.join(cards)}
    </tbody>
  </table>
  <script>
    const search = document.querySelector("#search");
    const rows = [...document.querySelectorAll("#rows tr")];
    search.addEventListener("input", () => {{
      const q = search.value.toLowerCase();
      rows.forEach(row => {{
        row.style.display = row.innerText.toLowerCase().includes(q) ? "" : "none";
      }});
    }});
  </script>
</body>
</html>"""
    path.write_text(document, encoding="utf-8")


WORKBENCH_TIER_LABELS = {
    "tier_1": "Tier 1",
    "tier_2": "Tier 2",
    "unclassified": "미분류",
}


def _safe_external_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _external_link(url: object, label: object) -> str:
    safe_url = _safe_external_url(url)
    text = html.escape(" ".join(str(label or "원문 열기").split()))
    if not safe_url:
        return f'<span class="muted">{text}</span>'
    return (
        f'<a href="{html.escape(safe_url, quote=True)}" target="_blank" '
        f'rel="noopener noreferrer">{text}</a>'
    )


def _format_krw(value: object) -> str:
    if value is None or value == "":
        return "금액 미확인"
    try:
        return f"{int(value):,}원"
    except (TypeError, ValueError):
        return html.escape(str(value))


def _write_html(path: Path, content: str) -> None:
    """Write generated static HTML without trailing whitespace or source label noise."""
    normalized = "\n".join(line.rstrip() for line in content.splitlines()).strip() + "\n"
    path.write_text(normalized, encoding="utf-8")


def _fallback_notice_details(notice: dict[str, object]) -> str:
    budget = _format_krw(notice.get("budget_value_krw"))
    if budget == "금액 미확인" and notice.get("budget"):
        budget = html.escape(str(notice.get("budget")))
    attachment_links = [
        _external_link(item.get("url"), item.get("label") or item.get("file_type") or "공개 첨부")
        for item in list(notice.get("attachments") or [])
        if item.get("url")
    ]
    attachments_html = ", ".join(attachment_links) if attachment_links else "첨부 링크 미수집"
    return f'''
      <article class="document-card fallback-card">
        <div class="document-header">
          <span class="document-status status-fallback_notice_info" style="background:#FFF3D6;color:#7B5510;border-color:#E7C66C;">공고정보로 보완</span>
        </div>
        <p><strong>공고 금액:</strong> {budget}</p>
        <p><strong>발주기관:</strong> {html.escape(str(notice.get("buyer") or "미수집"))}</p>
        <p><strong>입찰 방식:</strong> {html.escape(str(notice.get("procurement_method") or "미수집"))}</p>
        <p><strong>마감:</strong> {html.escape(str(notice.get("deadline_at") or "미수집"))}</p>
        <p><strong>공식 공고:</strong> {_external_link(notice.get("url"), "공식 공고 열기")}</p>
        <p><strong>원문 첨부:</strong> {attachments_html}</p>
      </article>
    '''


def _workbench_document_details(notice: dict[str, object]) -> str:
    insights = [
        item
        for item in list(notice.get("insights") or [])
        if str(item.get("extraction_status") or "") == "extracted"
        and any(str(item.get(field) or "").strip() for field in ("task_summary", "amount_text", "evidence_excerpt"))
    ]
    detail_parts: list[str] = []

    for insight in insights:
        label = str(insight.get("document_label") or "수집 문서")
        status = str(insight.get("extraction_status") or "not_attempted")
        summary = str(insight.get("task_summary") or "")
        amount_text = str(insight.get("amount_text") or "")
        amount_basis = str(insight.get("amount_basis") or "")
        evidence = str(insight.get("evidence_excerpt") or "")
        error_message = str(insight.get("error_message") or "")
        amount_html = (
            f'<p><strong>금액:</strong> {html.escape(amount_text)} '
            f'<span class="muted">({html.escape(amount_basis)})</span></p>'
            if amount_text
            else ""
        )
        evidence_html = (
            f'<p><strong>근거:</strong> {html.escape(evidence)}</p>' if evidence else ""
        )
        summary_html = (
            f'<p><strong>과업 요약:</strong> {html.escape(summary)}</p>' if summary else ""
        )
        error_html = (
            f'<p class="warning"><strong>확인 상태:</strong> {html.escape(error_message)}</p>'
            if error_message
            else ""
        )
        detail_parts.append(
            f"""
            <article class="document-card">
              <div class="document-header">
                <span class="document-status status-{html.escape(status, quote=True)}">
                  {html.escape(extraction_status_label(status))}
                </span>
                {_external_link(insight.get("document_url"), label)}
              </div>
              {summary_html}
              {amount_html}
              {evidence_html}
              {error_html}
            </article>
            """
        )

    if not detail_parts:
        return _fallback_notice_details(notice)
    return "".join(detail_parts)


FIT_LABELS = {
    "not_reviewed": "미검토",
    "high": "높음",
    "medium": "보통",
    "low": "낮음",
}

BID_DECISION_LABELS = {
    "pending": "미결정",
    "bid": "입찰 검토",
    "conditional": "조건부 검토",
    "no_bid": "미입찰",
}


def _workbench_fit_review_details(notice: dict[str, object]) -> str:
    review = dict(notice.get("fit_review") or {})
    consulting_fit = FIT_LABELS.get(str(review.get("consulting_fit") or "not_reviewed"), "미검토")
    bid_decision = BID_DECISION_LABELS.get(str(review.get("bid_decision") or "pending"), "미결정")
    qualification = str(review.get("qualification_requirements") or "입력 전")
    team = str(review.get("proposed_team") or "입력 전")
    risks = str(review.get("key_risks") or "원문 확인 후 입력")
    note = str(review.get("decision_note") or "입력 전")
    return f"""
      <section>
        <h3>입찰 적합성 검토표</h3>
        <p><strong>컨설팅 적합성:</strong> {html.escape(consulting_fit)}</p>
        <p><strong>입찰 의견:</strong> {html.escape(bid_decision)}</p>
        <p><strong>필요 자격·등록:</strong> {html.escape(qualification)}</p>
        <p><strong>예상 투입인력:</strong> {html.escape(team)}</p>
        <p><strong>핵심 위험:</strong> {html.escape(risks)}</p>
        <p><strong>검토 메모:</strong> {html.escape(note)}</p>
      </section>
    """


def _priority_card(notice: dict[str, object]) -> str:
    primary = dict(notice.get("primary_insight") or {})
    document_status = str(notice.get("document_status") or "not_attempted")
    deadline = str(notice.get("deadline_at") or "마감일 미수집")
    deadline_priority = str(notice.get("deadline_priority") or "")
    summary = str(primary.get("task_summary") or "공식 첨부 원문을 열어 과업범위와 자격요건을 확인하세요.")
    return f"""
      <article class="priority-card">
        <div class="priority-topline">
          <span class="tier-badge tier-tier_1">Tier 1 · 공식 출처</span>
          <span class="document-status status-{html.escape(document_status, quote=True)}">{html.escape(extraction_status_label(document_status))}</span>
        </div>
        <h3>{_external_link(notice.get("url"), notice.get("title"))}</h3>
        <p class="meta">{html.escape(str(notice.get("source_name") or ""))} · {html.escape(str(notice.get("buyer") or "발주기관 미수집"))} · 마감 {html.escape(deadline)} {_deadline_priority_badge(deadline_priority)}</p>
        <p>{html.escape(summary)}</p>
        <p class="priority-reason">{html.escape(str(notice.get("priority_reason") or ""))}</p>
      </article>
    """


def _deadline_priority_badge(priority: str) -> str:
    if priority not in {"D-7", "D-3"}:
        return ""
    border = "#E2AAA5" if priority == "D-3" else "#E7C66C"
    background = "#FBE7E5" if priority == "D-3" else "#FFF3D6"
    color = "#8A2A26" if priority == "D-3" else "#7B5510"
    return (
        f'<span class="deadline-priority {priority.lower()}" style="border-color:{border};'
        f'background:{background};color:{color};">{priority} 중요</span>'
    )


def _new_notice_rows(notices: list[dict[str, object]]) -> str:
    tier_order = {"tier_1": 0, "tier_2": 1}
    ordered = sorted(
        notices,
        key=lambda item: (
            0 if item.get("is_active") else 1,
            tier_order.get(str(item.get("business_tier") or "unclassified"), 4),
            str(item.get("deadline_at") or ""),
            int(item.get("id") or 0),
        ),
    )
    rows = []
    for notice in ordered:
        tier = str(notice.get("business_tier") or "unclassified")
        tier_text = WORKBENCH_TIER_LABELS.get(tier, tier)
        active_text = "현재 접수 중" if notice.get("is_active") else "마감 경과·확인 필요"
        budget = _format_krw(notice.get("budget_value_krw"))
        if budget == "금액 미확인" and notice.get("budget"):
            budget = html.escape(str(notice.get("budget")))
        rows.append(
            f"""
            <tr>
              <td><span class="tier-badge tier-{html.escape(tier, quote=True)}">{html.escape(tier_text)}</span><br><span class="active-status {'active' if notice.get('is_active') else 'inactive'}">{active_text}</span></td>
              <td class="title-cell">{_external_link(notice.get('url'), notice.get('title'))}<div class="meta">{html.escape(str(notice.get('source_name') or ''))}</div></td>
              <td>{html.escape(str(notice.get('buyer') or '미수집'))}</td>
              <td>{_deadline_priority_badge(str(notice.get('deadline_priority') or ''))}<div>{html.escape(str(notice.get('deadline_at') or '마감일 미수집'))}</div></td>
              <td>{budget}<div class="muted">{html.escape(str(notice.get('procurement_method') or '입찰 방식 미수집'))}</div></td>
              <td>{html.escape(str(notice.get('first_seen_at') or ''))}</td>
            </tr>
            """
        )
    return "".join(rows)


def render_workbench_dashboard(
    payload: dict[str, object],
    out_path: str | Path,
    *,
    public: bool = False,
) -> None:
    """Render a source-preserving, all-notice review dashboard."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if public:
        _render_public_workbench_dashboard(payload, path)
        return
    notices = list(payload.get("notices") or [])
    summary = dict(payload.get("summary") or {})

    source_options = sorted(
        {str(notice.get("source_name") or "") for notice in notices if notice.get("source_name")}
    )
    review_options = sorted(
        {str(notice.get("review_status") or "new") for notice in notices}
    )
    document_options = sorted(
        {str(notice.get("document_status") or "not_attempted") for notice in notices}
    )
    new_notices = [
        notice for notice in notices
        if notice.get("is_new_today") and notice.get("is_active") and notice.get("priority_status") == "official_tier_1"
    ]

    cards = [
        ("전체 공고", summary.get("total_notices", len(notices)), "navy"),
        ("Tier 1", summary.get("tier_1", 0), "green"),
        ("Tier 2", summary.get("tier_2", 0), "amber"),
        ("현재 접수 중", summary.get("active_notices", 0), "blue"),
        ("현재 접수 중 Tier 1", summary.get("active_tier_1", 0), "green"),
        ("현재 접수 중 Tier 2", summary.get("active_tier_2", 0), "amber"),
        ("D-7 중요 마감", summary.get("deadline_d7", 0), "amber"),
        ("D-3 중요 마감", summary.get("deadline_d3", 0), "red"),
        ("공개 원문 추출 완료", summary.get("extracted_documents", 0), "blue"),
        ("첨부 URL 확인 필요", summary.get("missing_document_urls", 0), "red"),
    ]
    card_html = "".join(
        f"""
        <section class="kpi-card {tone}">
          <span>{html.escape(label)}</span>
          <strong>{html.escape(str(value))}</strong>
        </section>
        """
        for label, value, tone in cards
    )
    priority_notices = [
        notice
        for notice in notices
        if str(notice.get("priority_status") or "") == "official_tier_1"
        and notice.get("is_active")
    ]
    priority_html = (
        "".join(_priority_card(notice) for notice in priority_notices)
        if priority_notices
        else '<p class="muted">현재 저장된 공고 중 공식 출처 Tier 1 우선 검토 대상이 없습니다. 샘플·종료·비관련 공고는 이 목록에서 제외합니다.</p>'
    )
    new_notice_html = (
        f"""
        <section class="panel new-panel">
          <div class="priority-heading">
            <div>
              <h2>오늘 신규 추가 · Tier 1</h2>
              <p>오늘 처음 수집했고 현재 접수 중인 Tier 1 후보 {len(new_notices)}건입니다.</p>
            </div>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Tier / 상태</th><th>공고명 / 출처</th><th>발주기관</th><th>마감</th><th>공고 금액 / 방식</th><th>최초 수집시각</th></tr></thead>
              <tbody>{_new_notice_rows(new_notices) or '<tr><td colspan="6" class="muted">오늘 신규 Tier 1 공고가 없습니다.</td></tr>'}</tbody>
            </table>
          </div>
        </section>
        """
    )

    table_rows: list[str] = []
    for notice in notices:
        tier = str(notice.get("business_tier") or "unclassified")
        tier_label_text = WORKBENCH_TIER_LABELS.get(tier, tier)
        review_status = str(notice.get("review_status") or "new")
        source_name = str(notice.get("source_name") or "")
        document_status = str(notice.get("document_status") or "not_attempted")
        priority_status = str(notice.get("priority_status") or "not_priority")
        deadline = str(notice.get("deadline_at") or "")
        deadline_priority = str(notice.get("deadline_priority") or "")
        keywords = notice.get("matched_keywords") or []
        keywords_text = ", ".join(str(item) for item in keywords)
        primary = dict(notice.get("primary_insight") or {})
        primary_summary = str(primary.get("task_summary") or "")
        primary_amount = str(primary.get("amount_text") or "")
        primary_basis = str(primary.get("amount_basis") or "")
        search_text = " ".join(
            [
                str(notice.get("title") or ""),
                str(notice.get("buyer") or ""),
                source_name,
                keywords_text,
                str(notice.get("tier_reason") or ""),
                primary_summary,
            ]
        ).casefold()
        listing_amount = _format_krw(notice.get("budget_value_krw"))
        listing_amount_note = (
            html.escape(str(notice.get("budget") or ""))
            if notice.get("budget") and notice.get("budget_value_krw") is None
            else ""
        )
        primary_summary_html = html.escape(primary_summary) if primary_summary else "문서 요약 미확인"
        primary_amount_html = (
            f'<div class="amount-line">{html.escape(primary_amount)} '
            f'<span class="muted">{html.escape(primary_basis)}</span></div>'
            if primary_amount
            else ""
        )
        table_rows.append(
            f"""
            <tr class="notice-row"
                data-tier="{html.escape(tier, quote=True)}"
                data-active="{'active' if notice.get('is_active') else 'inactive'}"
                data-review="{html.escape(review_status, quote=True)}"
                data-source="{html.escape(source_name, quote=True)}"
                data-document="{html.escape(document_status, quote=True)}"
                data-priority="{html.escape(priority_status, quote=True)}"
                data-deadline-priority="{html.escape(deadline_priority, quote=True)}"
                data-deadline="{html.escape(deadline[:10], quote=True)}"
                data-search="{html.escape(search_text, quote=True)}">
              <td><span class="tier-badge tier-{html.escape(tier, quote=True)}">{html.escape(tier_label_text)}</span></td>
              <td><span class="review-badge">{html.escape(review_status)}</span></td>
              <td class="title-cell">
                {_external_link(notice.get("url"), notice.get("title"))}
                <div class="meta">{html.escape(source_name)} · 점수 {html.escape(str(notice.get("relevance_score") or 0))}</div>
              </td>
              <td>{html.escape(str(notice.get("buyer") or ""))}</td>
              <td>{_deadline_priority_badge(deadline_priority)}<div>{html.escape(deadline or "마감일 미수집")}</div></td>
              <td>
                <div>{listing_amount}</div>
                <div class="muted">{listing_amount_note}</div>
                <div class="muted">{html.escape(str(notice.get("procurement_method") or ""))}</div>
              </td>
              <td>
                <span class="document-status status-{html.escape(document_status, quote=True)}">
                  {html.escape(extraction_status_label(document_status))}
                </span>
                <div class="summary-preview">{primary_summary_html}</div>
                {primary_amount_html}
              </td>
              <td class="detail-cell">
                <details>
                  <summary>공고·과업 상세</summary>
                  <div class="detail-grid">
                    <section>
                      <h3>공고 정보</h3>
                      <p><strong>Tier 근거:</strong> {html.escape(str(notice.get("tier_reason") or "원문 확인 필요"))}</p>
                      <p><strong>매칭 키워드:</strong> {html.escape(keywords_text or "없음")}</p>
                      <p><strong>검토 메모:</strong> {html.escape(str(notice.get("review_note") or "없음"))}</p>
                      <p><strong>원문 공고:</strong> {_external_link(notice.get("url"), "공식 공고 열기")}</p>
                    </section>
                    <section>
                      <h3>RFP · 과업지시서 · 첨부</h3>
                      {_workbench_document_details(notice)}
                    </section>
                    {_workbench_fit_review_details(notice)}
                  </div>
                </details>
              </td>
            </tr>
            """
        )

    source_select = "".join(
        f'<option value="{html.escape(value, quote=True)}">{html.escape(value)}</option>'
        for value in source_options
    )
    review_select = "".join(
        f'<option value="{html.escape(value, quote=True)}">{html.escape(value)}</option>'
        for value in review_options
    )
    document_select = "".join(
        f'<option value="{html.escape(value, quote=True)}">{html.escape(extraction_status_label(value))}</option>'
        for value in document_options
    )

    document = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Innergen Climate Procurement Workbench</title>
  <style>
    :root {{
      --navy: #14365D;
      --teal: #0F6B78;
      --ink: #17202A;
      --muted: #607080;
      --line: #CCD7E3;
      --pale: #F6F9FC;
      --green: #E3F2E7;
      --amber: #FFF3D6;
      --red: #FBE7E5;
      --blue: #EAF2F8;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #F3F6F9; color: var(--ink); font-family: Arial, "Malgun Gothic", sans-serif; }}
    .shell {{ max-width: 1780px; margin: 0 auto; padding: 30px; }}
    .masthead {{ background: var(--navy); color: white; border: 1px solid #0A2747; padding: 22px 26px; }}
    .eyebrow {{ margin: 0 0 5px; font-size: 12px; font-weight: 700; letter-spacing: .08em; color: #BED7EF; }}
    h1 {{ margin: 0; font-size: 26px; }}
    .masthead p {{ margin: 8px 0 0; max-width: 1050px; color: #E2EDF7; line-height: 1.55; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(155px, 1fr)); gap: 12px; margin: 18px 0; }}
    .kpi-card {{ background: white; border: 1px solid var(--line); border-top: 5px solid var(--navy); padding: 14px; min-height: 95px; }}
    .kpi-card span {{ display: block; color: var(--muted); font-size: 13px; }}
    .kpi-card strong {{ display: block; margin-top: 10px; font-size: 29px; color: var(--navy); }}
    .kpi-card.green {{ border-top-color: #2B7A4B; }} .kpi-card.amber {{ border-top-color: #B7791F; }}
    .kpi-card.gray {{ border-top-color: #718096; }} .kpi-card.blue {{ border-top-color: #2B6CB0; }}
    .kpi-card.red {{ border-top-color: #C53030; }}
    .deadline-priority {{ display:inline-block; padding:3px 7px; border:1px solid #E7C66C; background:#FFF3D6; color:#7B5510; font-size:11px; font-weight:800; white-space:nowrap; }}
    .deadline-priority.d-3 {{ border-color:#E2AAA5; background:#FBE7E5; color:#8A2A26; }}
    .panel {{ background: white; border: 1px solid var(--line); padding: 18px; margin-top: 16px; }}
    .priority-panel {{ border-top: 5px solid #2B7A4B; }}
    .priority-heading {{ display: flex; justify-content: space-between; gap: 16px; align-items: center; margin-bottom: 12px; }}
    .priority-heading h2 {{ margin: 0; color: var(--navy); font-size: 18px; }}
    .priority-heading p {{ margin: 5px 0 0; color: var(--muted); font-size: 13px; }}
    .priority-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(310px, 1fr)); gap: 12px; }}
    .priority-card {{ border: 1px solid #A8D0B4; border-left: 5px solid #2B7A4B; padding: 14px; background: #FBFEFC; }}
    .priority-card h3 {{ margin: 10px 0 6px; font-size: 15px; line-height: 1.45; }}
    .priority-card p {{ margin: 8px 0; line-height: 1.5; }}
    .priority-topline {{ display: flex; flex-wrap: wrap; gap: 7px; }}
    .priority-reason {{ color: #205D36; font-size: 12px; font-weight: 700; }}
    .filter-grid {{ display: grid; grid-template-columns: minmax(240px, 2fr) repeat(7, minmax(120px, 1fr)) auto; gap: 10px; align-items: end; }}
    label {{ display: block; color: #405368; font-size: 12px; font-weight: 700; margin-bottom: 5px; }}
    input, select, button {{ width: 100%; min-height: 39px; border: 1px solid #BFCBD7; border-radius: 3px; padding: 8px 10px; background: white; color: var(--ink); }}
    button {{ width: auto; cursor: pointer; background: var(--navy); color: white; border-color: var(--navy); font-weight: 700; }}
    .filter-status {{ margin: 14px 0 0; color: var(--muted); font-size: 13px; }}
    .table-wrap {{ overflow: auto; border: 1px solid var(--line); margin-top: 16px; }}
    table {{ width: 100%; min-width: 1480px; border-collapse: collapse; font-size: 13px; }}
    th {{ position: sticky; top: 0; z-index: 2; padding: 11px 10px; background: var(--teal); color: white; text-align: left; border: 1px solid #D7EDF1; white-space: nowrap; }}
    td {{ padding: 11px 10px; vertical-align: top; border: 1px solid var(--line); background: white; line-height: 1.5; }}
    tr:nth-child(even) td {{ background: #FBFCFE; }}
    a {{ color: #155A8A; font-weight: 700; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .muted, .meta {{ color: var(--muted); font-size: 12px; }}
    .meta {{ margin-top: 4px; }}
    .tier-badge, .review-badge, .document-status {{ display: inline-block; padding: 4px 7px; border: 1px solid transparent; border-radius: 3px; font-size: 12px; font-weight: 700; }}
    .tier-tier_1 {{ background: var(--green); color: #205D36; border-color: #9FCBAE; }}
    .tier-tier_2 {{ background: var(--amber); color: #7B5510; border-color: #E7C66C; }}
    .tier-unclassified {{ background: #EDF1F5; color: #4A5568; border-color: #CCD6E0; }}
    .review-badge {{ background: #EDF2F7; color: #4A5568; border-color: #D2DCE7; }}
    .status-extracted {{ background: var(--green); color: #205D36; border-color: #9FCBAE; }}
    .status-missing_document_url, .status-download_failed, .status-parse_failed {{ background: var(--red); color: #8A2A26; border-color: #E2AAA5; }}
    .active-status {{ display: inline-block; padding: 4px 7px; border: 1px solid #BFCBD7; border-radius: 3px; font-size: 12px; font-weight: 700; white-space: nowrap; }}
    .active-status.active {{ background: var(--green); color: #205D36; border-color: #9FCBAE; }}
    .active-status.inactive {{ background: #EDF1F5; color: #4A5568; }}
    .status-unsupported_file_type, .status-sample_source, .status-processed_no_evidence, .status-not_attempted {{ background: var(--amber); color: #7B5510; border-color: #E7C66C; }}
    .summary-preview {{ margin-top: 8px; max-width: 390px; }}
    .amount-line {{ margin-top: 6px; font-weight: 700; }}
    .detail-cell {{ min-width: 260px; }}
    details summary {{ color: #155A8A; cursor: pointer; font-weight: 700; }}
    .detail-grid {{ display: grid; grid-template-columns: minmax(230px, 1fr) minmax(330px, 1.5fr) minmax(280px, 1.2fr); gap: 14px; margin-top: 11px; }}
    .detail-grid section {{ border: 1px solid var(--line); background: var(--pale); padding: 12px; }}
    .detail-grid h3 {{ margin: 0 0 9px; color: var(--navy); font-size: 13px; }}
    .detail-grid p {{ margin: 7px 0; }}
    .document-card {{ background: white; border: 1px solid #D5DEE8; padding: 10px; margin-top: 9px; }}
    .document-card p {{ margin: 6px 0; }}
    .document-header {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .warning {{ color: #8A2A26; }}
    .method-note {{ margin: 16px 0 0; padding: 12px; background: #FFF9E8; border: 1px solid #E6CE84; color: #624B13; line-height: 1.55; }}
    @media (max-width: 1100px) {{ .kpis {{ grid-template-columns: repeat(3, 1fr); }} .filter-grid {{ grid-template-columns: repeat(2, 1fr); }} .detail-grid {{ grid-template-columns: 1fr; }} }}
    @media (max-width: 680px) {{ .shell {{ padding: 14px; }} .kpis {{ grid-template-columns: 1fr 1fr; }} .filter-grid {{ grid-template-columns: 1fr; }} .detail-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="masthead">
      <p class="eyebrow">INNERGEN CLIMATE INTELLIGENCE</p>
      <h1>나라장터 전체 현재입찰 · 기후·온실가스 공고 작업대</h1>
      <p>나라장터 및 공식 출처의 이너젠 직접 컨설팅(Tier 1)과 고객사 설비·금융지원(Tier 2) 공고만 표시합니다. D-7/D-3 수치는 표시 대상 공고 기준입니다. 자동 요약은 공개 원문에서만 만들며, 최종 입찰 판단은 담당자가 원문으로 확인해야 합니다.</p>
    </header>
    <section class="kpis">{card_html}</section>
    <section class="panel priority-panel">
      <div class="priority-heading">
        <div>
          <h2>Tier 1 우선 검토</h2>
          <p>샘플을 제외한 공식 출처의 Tier 1 후보만 먼저 표시합니다. 이는 입찰 확정이 아니라 원문 우선 검토 순서입니다.</p>
        </div>
        <button id="priority-only" type="button">Tier 1 공식 우선 보기</button>
      </div>
      <div class="priority-grid">{priority_html}</div>
    </section>
    {new_notice_html}
    <section class="panel">
      <div class="filter-grid">
        <div><label for="search">통합 검색</label><input id="search" placeholder="공고명, 기관, 키워드, 과업 요약"></div>
        <div><label for="tier">Tier</label><select id="tier"><option value="">전체</option><option value="tier_1">Tier 1</option><option value="tier_2">Tier 2</option></select></div>
        <div><label for="active">접수 상태</label><select id="active"><option value="">전체</option><option value="active">현재 접수 중</option><option value="inactive">마감 경과·확인 필요</option></select></div>
        <div><label for="priority">우선 검토</label><select id="priority"><option value="">전체</option><option value="official_tier_1">Tier 1 공식 우선</option></select></div>
        <div><label for="deadline-priority">중요 마감</label><select id="deadline-priority"><option value="">전체</option><option value="D-7">D-7</option><option value="D-3">D-3</option></select></div>
        <div><label for="review">검토 상태</label><select id="review"><option value="">전체</option>{review_select}</select></div>
        <div><label for="source">출처</label><select id="source"><option value="">전체</option>{source_select}</select></div>
        <div><label for="document">문서 상태</label><select id="document"><option value="">전체</option>{document_select}</select></div>
        <div><label for="deadline">마감일 이전</label><input id="deadline" type="date"></div>
        <button id="reset" type="button">필터 초기화</button>
      </div>
      <p class="filter-status"><strong id="visible-count">{len(notices)}</strong>건 표시 중</p>
      <p class="method-note">금액 표기: 공고목록 금액은 목록 API가 제공한 값입니다. 문서 추출 금액은 과업지시서/RFP의 라벨과 함께 표시됩니다. 예산액·소요예산·추정가격·입찰금액·계약금액은 서로 다른 개념이므로, 표시된 금액 기준을 반드시 확인하세요.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>적합성</th><th>검토</th><th>공고명 / 출처</th><th>발주기관</th><th>마감</th><th>공고목록 금액 / 방식</th><th>문서·요약</th><th>상세</th></tr></thead>
          <tbody id="notice-rows">{''.join(table_rows)}</tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    const rows = Array.from(document.querySelectorAll(".notice-row"));
    const controls = ["search", "tier", "active", "priority", "deadline-priority", "review", "source", "document", "deadline"].map(id => document.getElementById(id));
    const visibleCount = document.getElementById("visible-count");
    function applyFilters() {{
      const query = document.getElementById("search").value.trim().toLocaleLowerCase();
      const tier = document.getElementById("tier").value;
      const active = document.getElementById("active").value;
      const priority = document.getElementById("priority").value;
      const deadlinePriority = document.getElementById("deadline-priority").value;
      const review = document.getElementById("review").value;
      const source = document.getElementById("source").value;
      const documentStatus = document.getElementById("document").value;
      const deadline = document.getElementById("deadline").value;
      let count = 0;
      rows.forEach(row => {{
        const matchesQuery = !query || row.dataset.search.includes(query);
        const matchesTier = !tier || row.dataset.tier === tier;
        const matchesActive = !active || row.dataset.active === active;
        const matchesPriority = !priority || row.dataset.priority === priority;
        const matchesDeadlinePriority = !deadlinePriority || row.dataset.deadlinePriority === deadlinePriority;
        const matchesReview = !review || row.dataset.review === review;
        const matchesSource = !source || row.dataset.source === source;
        const matchesDocument = !documentStatus || row.dataset.document === documentStatus;
        const matchesDeadline = !deadline || (row.dataset.deadline && row.dataset.deadline <= deadline);
        const visible = matchesQuery && matchesTier && matchesActive && matchesPriority && matchesDeadlinePriority && matchesReview && matchesSource && matchesDocument && matchesDeadline;
        row.style.display = visible ? "" : "none";
        if (visible) count += 1;
      }});
      visibleCount.textContent = String(count);
    }}
    controls.forEach(control => control.addEventListener("input", applyFilters));
    document.getElementById("reset").addEventListener("click", () => {{
      controls.forEach(control => {{ control.value = ""; }});
      applyFilters();
    }});
    document.getElementById("priority-only").addEventListener("click", () => {{
      document.getElementById("priority").value = "official_tier_1";
      document.getElementById("search").value = "";
      applyFilters();
      document.querySelector("#notice-rows").scrollIntoView({{ behavior: "smooth", block: "start" }});
    }});
  </script>
</body>
</html>"""
    _write_html(path, document)


def _render_public_workbench_dashboard(payload: dict[str, object], path: Path) -> None:
    """Render a public static page from a pre-sanitized source-fact payload only."""
    notices = sorted(
        list(payload.get("notices") or []),
        key=lambda item: (
            0 if item.get("is_active") else 1,
            0 if item.get("business_tier") == "tier_1" else 1,
            str(item.get("deadline_at") or "9999-12-31"),
            int(item.get("id") or 0),
        ),
    )
    summary = dict(payload.get("summary") or {})
    source_options = sorted(
        {str(notice.get("source_name") or "") for notice in notices if notice.get("source_name")}
    )
    document_options = sorted(
        {str(notice.get("document_status") or "not_attempted") for notice in notices}
    )
    new_tier_1_items = [item for item in notices if item.get("is_new_tier_1")]
    cards = [
        ("오늘 신규 Tier 1", len(new_tier_1_items), "focus", "#new-tier1"),
        ("접수 중 Tier 1", summary.get("active_tier_1", 0), "active", "#notice-list"),
        ("접수 중 Tier 2", summary.get("active_tier_2", 0), "support", "#notice-list"),
        ("D-7 · D-3 중요 마감", int(summary.get("deadline_d7", 0)) + int(summary.get("deadline_d3", 0)), "urgent", "#notice-list"),
    ]
    card_html = "".join(
        f'<a class="kpi {tone}" href="{href}"><span>{html.escape(label)}</span><strong>{html.escape(str(value))}</strong><small>목록 확인 →</small></a>'
        for label, value, tone, href in cards
    )
    rows: list[str] = []
    for notice in notices:
        tier = str(notice.get("business_tier") or "")
        tier_label_text = "Tier 1 · 직접 컨설팅" if tier == "tier_1" else "Tier 2 · 고객사 지원"
        source_name = str(notice.get("source_name") or "")
        status = str(notice.get("document_status") or "not_attempted")
        deadline = str(notice.get("deadline_at") or "")
        deadline_priority = str(notice.get("deadline_priority") or "")
        primary = dict(notice.get("primary_insight") or {})
        summary_text = str(primary.get("task_summary") or "")
        amount_text = str(primary.get("amount_text") or "")
        amount_basis = str(primary.get("amount_basis") or "")
        search_text = " ".join(
            [str(notice.get("title") or ""), str(notice.get("buyer") or ""), source_name, summary_text]
        ).casefold()
        amount_html = (
            f'<p class="amount"><strong>문서 금액:</strong> {html.escape(amount_text)} <span>{html.escape(amount_basis)}</span></p>'
            if amount_text
            else ""
        )
        summary_html = f'<p><strong>과업 요약:</strong> {html.escape(summary_text)}</p>' if summary_text else ""
        method_html = html.escape(str(notice.get("procurement_method") or "입찰방식 미수집"))
        budget_html = _format_krw(notice.get("budget_value_krw"))
        if budget_html == "금액 미확인" and notice.get("budget"):
            budget_html = html.escape(str(notice["budget"]))
        rows.append(
            f"""
            <tr id="notice-{int(notice['id'])}" class="notice-row" data-tier="{html.escape(tier, quote=True)}" data-active="{'active' if notice.get('is_active') else 'inactive'}" data-source="{html.escape(source_name, quote=True)}" data-document="{html.escape(status, quote=True)}" data-deadline-priority="{html.escape(deadline_priority, quote=True)}" data-deadline="{html.escape(deadline[:10], quote=True)}" data-search="{html.escape(search_text, quote=True)}">
              <td data-label="공고" class="title"><span class="tier-tag {html.escape(tier, quote=True)}">{tier_label_text}</span><div class="notice-title">{_external_link(notice.get('url'), notice.get('title'))}</div><div class="meta">{html.escape(source_name)} · {html.escape(str(notice.get('published_at') or '공고일 미수집'))}</div></td>
              <td data-label="발주기관">{html.escape(str(notice.get('buyer') or '미수집'))}</td>
              <td data-label="마감"><div class="deadline-cell"><span class="active-status {'active' if notice.get('is_active') else 'inactive'}">{'접수 중' if notice.get('is_active') else '접수 종료·확인'}</span>{_deadline_priority_badge(deadline_priority)}<div class="date">{html.escape(deadline or '마감일 미수집')}</div></div></td>
              <td data-label="공고 금액" class="number">{budget_html}</td>
              <td data-label="자료·상세"><details class="row-details"><summary>RFP · 상세 보기</summary><div class="docs"><p><strong>입찰 방식:</strong> {method_html}</p>{summary_html}{amount_html}{_workbench_document_details(notice)}</div></details></td>
            </tr>
            """
        )
    new_public_html = "".join(
        '<li><article class="lead-card">'
        '<span class="eyebrow">NEW · TIER 1</span>'
        f'<h3>{_external_link(item.get("url"), item.get("title"))}</h3>'
        f'<p>{html.escape(str(item.get("buyer") or "발주기관 미수집"))}</p>'
        f'<dl><div><dt>마감</dt><dd>{html.escape(str(item.get("deadline_at") or "미수집"))}</dd></div>'
        f'<div><dt>공고 금액</dt><dd>{_format_krw(item.get("budget_value_krw"))}</dd></div></dl>'
        f'<a class="detail-link" href="#notice-{int(item["id"])}">목록에서 자료 보기 →</a>'
        '</article></li>'
        for item in new_tier_1_items
    ) or '<li class="empty-lead">오늘 새로 수집한 Tier 1 접수 공고는 없습니다. 아래에서 진행 중인 공고를 확인하세요.</li>'
    source_select = "".join(
        f'<option value="{html.escape(value, quote=True)}">{html.escape(value)}</option>'
        for value in source_options
    )
    document_select = "".join(
        f'<option value="{html.escape(value, quote=True)}">{html.escape(extraction_status_label(value))}</option>'
        for value in document_options
    )
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>기후·온실가스 입찰 대시보드</title><style>{PUBLIC_DASHBOARD_CSS}</style></head>
<body><a class="skip-link" href="#notice-list">공고 목록으로 건너뛰기</a><main class="shell">
  <header class="hero">
    <div class="eyebrow">CLIMATE PROCUREMENT INTELLIGENCE</div>
    <h1>기후·온실가스 입찰, 한눈에 검토</h1>
    <p>이너젠 직접 컨설팅 후보(Tier 1)와 고객사가 신청할 수 있는 설비·금융지원 모집(Tier 2)만 모았습니다. 이미 선정된 기업의 장비 구매입찰은 제외합니다. 입찰 자격과 신청 가능 여부는 공식 원문에서 확인하세요.</p>
    <div class="hero-meta"><span>나라장터 및 공식 출처</span><span>마지막 갱신 {html.escape(str(summary.get('generated_at') or '미확인'))}</span><span>공개 스냅샷</span></div>
  </header>
  <section class="kpis" aria-label="핵심 현황">{card_html}</section>
  <section id="new-tier1" class="panel" aria-labelledby="new-heading">
    <div class="section-head"><div><h2 id="new-heading">오늘 신규 Tier 1</h2><p>오늘 처음 수집한 접수 중 직접 컨설팅 후보만 표시합니다.</p></div><span class="section-count">{len(new_tier_1_items)}건</span></div>
    <ul class="lead-list">{new_public_html}</ul>
  </section>
  <section id="notice-list" class="panel" aria-labelledby="list-heading">
    <div class="section-head"><div><h2 id="list-heading">Tier 1·2 공고 탐색</h2><p>접수 중인 Tier 1을 먼저 보여줍니다. 제목을 열면 공식 원문, 자료·상세를 펼치면 공개 RFP를 확인할 수 있습니다.</p></div></div>
    <div class="filters" role="search">
      <div><label for="search">공고 검색</label><input id="search" type="search" placeholder="공고명·기관·과업 키워드"></div>
      <div><label for="tier">업무 적합성</label><select id="tier"><option value="">Tier 1·2 전체</option><option value="tier_1">Tier 1 · 직접 컨설팅</option><option value="tier_2">Tier 2 · 고객사 지원</option></select></div>
      <div><label for="active">접수 상태</label><select id="active"><option value="active" selected>접수 중</option><option value="">전체</option><option value="inactive">마감 경과·확인</option></select></div>
      <div><label for="deadline-priority">중요 마감</label><select id="deadline-priority"><option value="">전체</option><option value="D-7">D-7</option><option value="D-3">D-3</option></select></div>
      <div><label for="source">출처</label><select id="source"><option value="">전체</option>{source_select}</select></div>
    </div>
    <div class="filter-actions"><details class="advanced"><summary>상세 필터</summary><div class="advanced-grid"><div><label for="document">문서 상태</label><select id="document"><option value="">전체</option>{document_select}</select></div><div><label for="deadline">마감일 이전</label><input id="deadline" type="date"></div></div></details><button id="reset" type="button">필터 초기화</button></div>
    <p id="result-count" class="result-count" aria-live="polite">검색 결과 준비 중</p>
    <div class="table-wrap"><table><caption class="sr-only">기후·온실가스 관련 공식 공고 목록</caption><thead><tr><th scope="col">공고·출처</th><th scope="col">발주기관</th><th scope="col">마감·상태</th><th scope="col">공고 금액</th><th scope="col">자료·상세</th></tr></thead><tbody id="notice-rows">{''.join(rows)}</tbody></table></div>
    <p id="empty" class="empty-lead" hidden>조건에 맞는 공고가 없습니다. 필터를 변경해 보세요.</p>
    <button id="more" class="more" type="button">25건 더 보기</button>
    <p class="footnote">표시 금액은 공고 목록의 값입니다. 예산액·추정가격·입찰금액은 서로 다른 기준일 수 있으므로 공식 원문에서 확인하세요. 이 페이지는 마지막 갱신 시점의 정적 화면입니다.</p>
  </section>
</main><script>
{PUBLIC_DASHBOARD_JS}
</script></body></html>"""
    _write_html(path, page)
