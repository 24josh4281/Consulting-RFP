from __future__ import annotations

import html
import json
from pathlib import Path


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
        cards.append(
            f"""
            <tr>
              <td class="score">{row["relevance_score"]}</td>
              <td>{row["id"]}</td>
              <td><span class="status status-{html.escape(row["review_status"] or "new")}">{html.escape(row["review_status"] or "new")}</span></td>
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
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #e5e8e8; padding: 10px; vertical-align: top; }}
    th {{ text-align: left; background: #f8f9f9; position: sticky; top: 0; }}
    .score {{ font-weight: 700; color: #117864; }}
    .status {{ display: inline-block; padding: 3px 8px; border-radius: 999px; background: #ecf0f1; font-size: 12px; }}
    .status-interesting {{ background: #d5f5e3; color: #145a32; }}
    .status-not_relevant {{ background: #fadbd8; color: #922b21; }}
    .status-submitted {{ background: #d6eaf8; color: #1b4f72; }}
    .status-watch {{ background: #fcf3cf; color: #7d6608; }}
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
