"""Re-extract grant amounts in an existing generated public HTML snapshot.

Useful when the private operational SQLite database is unavailable. Other rows,
collection dates, summaries and listing API amounts are preserved byte-for-byte.
Normal operational runs should use extract-documents then render-workbench.
"""
from __future__ import annotations

import argparse
import html
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rfp_tracker.documents import _download_public_hwpx, extract_hwpx_paragraphs, extract_amount_evidence
from rfp_tracker.render import _workbench_document_details


def refresh(snapshot: Path, cache: Path) -> int:
    text = snapshot.read_text(encoding="utf-8")
    notice_ids = re.findall(r'<tr id="notice-(\d+)"[^>]*data-notice-type="grant_application"', text)
    refreshed = 0
    for notice_id in notice_ids:
        pattern = re.compile(r'(<tr id="detail-' + notice_id + r'"[^>]*>)(.*?)(</tr>)', re.S)
        match = pattern.search(text)
        if not match:
            raise ValueError(f"Missing detail row: {notice_id}")
        body = match.group(2)
        insights = []
        for card in re.findall(r'<article class="document-card">.*?</article>', body, re.S):
            link = re.search(r'<a href="([^"]+)"[^>]*>(.*?)</a>', card, re.S)
            if not link:
                raise ValueError(f"Missing document link: {notice_id}")
            url, label = html.unescape(link.group(1)), html.unescape(link.group(2))
            summary = re.search(r'<p><strong>과업 요약:</strong> (.*?)</p>', card, re.S)
            amount = {"amount_value_krw": None, "amount_text": "", "amount_basis": "", "evidence_excerpt": ""}
            if label.lower().endswith(".hwpx"):
                # Download failures abort rather than publishing unverified evidence.
                path = _download_public_hwpx(url, cache, int(notice_id), None)
                amount = extract_amount_evidence(extract_hwpx_paragraphs(path.read_bytes()), notice_type="grant_application")
            insight = dict(amount, document_label=label, document_url=url,
                           extraction_status="extracted", task_summary=html.unescape(summary.group(1)) if summary else "")
            insights.append(insight)
            replacement = _workbench_document_details({"insights": [insight]}).strip()
            replacement = "\n".join(line.rstrip() for line in replacement.splitlines())
            body = body.replace(card, replacement, 1)
        if not insights:
            continue
        amount_texts = {i["amount_text"] for i in insights if i["amount_text"]}
        display = html.escape(next(iter(amount_texts))) if len(amount_texts) == 1 else "공고문 확인"
        body = re.sub(r'<p class="amount">.*?</p>',
                      '<p class="amount"><strong>문서 지원규모:</strong> ' + display + '</p>', body, flags=re.S)
        text = text[:match.start(2)] + body + text[match.end(2):]
        refreshed += 1
        print(f"notice-{notice_id}: {display}")
    snapshot.write_text(text, encoding="utf-8")
    return refreshed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("site/index.html"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/document_cache"))
    args = parser.parse_args()
    print(f"refreshed={refresh(args.snapshot, args.cache_dir)}")
