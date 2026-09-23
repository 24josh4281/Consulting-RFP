from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .tiering import TIER_1, TIER_2, TIER_3, tier_short_label
from zoneinfo import ZoneInfo

from .storage import list_notices


SEOUL_TZ = ZoneInfo("Asia/Seoul")


def seoul_now() -> datetime:
    return datetime.now(SEOUL_TZ)


def parse_notice_datetime(value: object) -> datetime | None:
    """Accept common 나라장터/board timestamp shapes without changing raw values."""
    text = str(value or "").strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(SEOUL_TZ) if parsed.tzinfo else parsed.replace(tzinfo=SEOUL_TZ)
    except ValueError:
        pass

    digits = "".join(re.findall(r"\d", text))
    for pattern, length in (("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12), ("%Y%m%d", 8)):
        if len(digits) >= length:
            try:
                return datetime.strptime(digits[:length], pattern).replace(tzinfo=SEOUL_TZ)
            except ValueError:
                continue
    return None


def deadline_priority_label(days_remaining: int | None) -> str:
    """Highlight notices exactly seven or three calendar days before deadline."""
    return f"D-{days_remaining}" if days_remaining in {7, 3} else ""


def is_notice_active(row: Any, now: datetime | None = None) -> bool:
    """Return whether a stored notice is still accepting bids or has no known deadline."""
    current = now or seoul_now()
    deadline_text = str(row["deadline_at"] or "").strip()
    deadline = parse_notice_datetime(deadline_text)
    if deadline is None:
        return True
    digits = "".join(character for character in deadline_text if character.isdigit())
    # Date-only source values represent the whole KST calendar day, not midnight.
    if len(digits) <= 8:
        return deadline.date() >= current.date()
    return deadline >= current


def _json_list(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _keyword_set(value: object) -> set[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return set()
    return {str(item) for item in parsed} if isinstance(parsed, list) else set()


def notice_view(row: Any, now: datetime | None = None) -> dict[str, Any]:
    current = now or seoul_now()
    deadline = parse_notice_datetime(row["deadline_at"])
    days_remaining = (deadline.date() - current.date()).days if deadline else None
    attachments = _json_list(row["attachments_json"] if "attachments_json" in row.keys() else "[]")
    return {
        "id": int(row["id"]),
        "title": str(row["title"]),
        "url": str(row["url"] or ""),
        "source_name": str(row["source_name"]),
        "buyer": str(row["buyer"] or ""),
        "budget": str(row["budget"] or ""),
        "procurement_method": str(row["procurement_method"] or ""),
        "published_at": str(row["published_at"] or ""),
        "deadline_at": str(row["deadline_at"] or ""),
        "deadline": deadline,
        "days_remaining": days_remaining,
        "deadline_priority": deadline_priority_label(days_remaining),
        "relevance_score": int(row["relevance_score"]),
        "review_status": str(row["review_status"]),
        "business_tier": str(row["business_tier"] if "business_tier" in row.keys() else "unclassified"),
        "tier_reason": str(row["tier_reason"] if "tier_reason" in row.keys() else ""),
        "tier_source": str(row["tier_source"] if "tier_source" in row.keys() else "automatic"),
        "matched_keywords": sorted(_keyword_set(row["matched_keywords"])),
        "attachments": attachments,
        "document_count": len(attachments),
        "first_seen_at": str(row["first_seen_at"] or ""),
    }


def _deduplicate(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in items:
        if item["id"] not in seen:
            result.append(item)
            seen.add(item["id"])
    return result


def find_similar_pairs(items: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for index, left in enumerate(items):
        left_terms = set(left["matched_keywords"])
        if not left_terms:
            continue
        for right in items[index + 1 :]:
            common_terms = sorted(left_terms & set(right["matched_keywords"]))
            same_buyer = bool(left["buyer"] and left["buyer"] == right["buyer"])
            if len(common_terms) >= 2 or (same_buyer and common_terms):
                pairs.append(
                    {
                        "left": left,
                        "right": right,
                        "common_terms": common_terms,
                    }
                )
                if len(pairs) >= limit:
                    return pairs
    return pairs


def build_briefing(
    connection: Any,
    *,
    due_days: int = 7,
    min_score: int = 3,
    limit: int = 20,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or seoul_now()
    views = [notice_view(row, current) for row in list_notices(connection)]
    eligible = [
        item
        for item in views
        if item["relevance_score"] >= min_score
        and is_notice_active(item, current)
        and item["review_status"] not in {"not_relevant", "closed", "needs_review"}
    ]
    today_new = [
        item
        for item in eligible
        if (first_seen := parse_notice_datetime(item["first_seen_at"])) and first_seen.date() == current.date()
    ]
    urgent = [
        item
        for item in eligible
        if item["days_remaining"] is not None and 0 <= item["days_remaining"] <= due_days
    ]
    deadline_priority = [item for item in eligible if item["deadline_priority"]]
    missing_documents = [item for item in eligible if item["document_count"] == 0]
    watched = [item for item in eligible if item["review_status"] in {"watch", "interesting"}]
    high_score_missing = [item for item in missing_documents if item["relevance_score"] >= min_score + 2]
    tier_order = {TIER_1: 0, TIER_2: 1, TIER_3: 2}
    action_queue = sorted(
        _deduplicate(urgent + today_new + high_score_missing + watched),
        key=lambda item: (
            tier_order.get(item["business_tier"], 3),
            item["days_remaining"] is None,
            item["days_remaining"] if item["days_remaining"] is not None else 9999,
            -item["relevance_score"],
        ),
    )[:limit]
    return {
        "generated_at": current,
        "due_days": due_days,
        "min_score": min_score,
        "summary": {
            "total_notices": len(views),
            "eligible_notices": len(eligible),
            "new_today": len(today_new),
            "unreviewed": sum(1 for item in eligible if item["review_status"] == "new"),
            "urgent": len(urgent),
            "missing_documents": len(missing_documents),
            "watching": len(watched),
            "tier_1": sum(1 for item in eligible if item["business_tier"] == TIER_1),
            "tier_2": sum(1 for item in eligible if item["business_tier"] == TIER_2),
            "tier_3": sum(1 for item in eligible if item["business_tier"] == TIER_3),
        },
        "action_queue": action_queue,
        "new_today": today_new[:limit],
        "urgent": urgent[:limit],
        "deadline_priority": deadline_priority,
        "missing_documents": missing_documents[:limit],
        "similar_pairs": find_similar_pairs(eligible[: max(limit * 2, 20)]),
    }


def _display_deadline(item: dict[str, Any]) -> str:
    if not item["deadline_at"]:
        return "마감일 미수집"
    if item["days_remaining"] is None:
        return item["deadline_at"]
    if item["days_remaining"] < 0:
        return f"{item['deadline_at']} (마감 경과)"
    return f"{item['deadline_at']} (D-{item['days_remaining']})"


def _markdown_item(item: dict[str, Any]) -> str:
    title = item["title"].replace("|", "\\|")
    source = item["source_name"].replace("|", "\\|")
    deadline = _display_deadline(item).replace("|", "\\|")
    keywords = ", ".join(item["matched_keywords"]) or "-"
    link = f"[공고 열기]({item['url']})" if item["url"] else "링크 미수집"
    tier = tier_short_label(item["business_tier"])
    reason = item["tier_reason"].replace("|", "\\|") or "원문 확인 필요"
    return f"| {tier} | {title} | {source} | {deadline} | {item['relevance_score']} | {reason} | {keywords} | {link} |"


def briefing_markdown(briefing: dict[str, Any]) -> str:
    summary = briefing["summary"]
    generated_at = briefing["generated_at"].strftime("%Y-%m-%d %H:%M KST")
    lines = [
        "# 기후·GHG·ETS 입찰 브리핑",
        "",
        f"생성 시각: {generated_at}",
        "",
        "## 오늘의 요약",
        "",
        "| 전체 | 기준점수 이상 | Tier 1 | Tier 2 | Tier 3 | 오늘 수집 | D-{} 이내 | 문서 미수집 |".format(briefing["due_days"]),
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| {total_notices} | {eligible_notices} | {tier_1} | {tier_2} | {tier_3} | {new_today} | {urgent} | {missing_documents} |".format(**summary),
        "",
        "## 우선 확인 공고",
        "",
    ]
    if briefing["action_queue"]:
        lines.extend(
            [
                "| Tier | 공고 | 출처 | 마감 | 점수 | 분류 근거 | 키워드 | 원문 |",
                "|---|---|---|---|---:|---|---|---|",
                *[_markdown_item(item) for item in briefing["action_queue"]],
            ]
        )
    else:
        lines.append("현재 우선 확인 조건에 맞는 공고가 없습니다.")

    lines.extend(["", "## 문서 확인 필요", ""])
    if briefing["missing_documents"]:
        lines.extend(
            [
                "| Tier | 공고 | 출처 | 마감 | 점수 | 분류 근거 | 키워드 | 원문 |",
                "|---|---|---|---|---:|---|---|---|",
                *[_markdown_item(item) for item in briefing["missing_documents"]],
            ]
        )
    else:
        lines.append("문서 링크가 누락된 기준점수 이상 공고가 없습니다.")

    lines.extend(["", "## 유사 공고 신호", ""])
    if briefing["similar_pairs"]:
        for pair in briefing["similar_pairs"]:
            terms = ", ".join(pair["common_terms"])
            lines.append(f"- {pair['left']['title']} ↔ {pair['right']['title']} (공통: {terms})")
    else:
        lines.append("현재 수집 범위에서는 유사 공고 쌍이 충분하지 않습니다.")

    lines.extend(
        [
            "",
            "검토 전에는 원문 공고와 첨부 RFP/과업지시서를 확인하세요. 본 브리핑은 입찰 자격 또는 수주 가능성을 확정하지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)


def briefing_html(briefing: dict[str, Any]) -> str:
    summary = briefing["summary"]
    generated_at = briefing["generated_at"].strftime("%Y-%m-%d %H:%M KST")

    def item_rows(items: list[dict[str, Any]]) -> str:
        if not items:
            return '<tr><td colspan="8">해당 공고가 없습니다.</td></tr>'
        rows: list[str] = []
        for item in items:
            link = f'<a href="{html.escape(item["url"], quote=True)}" target="_blank" rel="noreferrer">원문</a>' if item["url"] else "미수집"
            rows.append(
                "<tr>"
                f"<td>{html.escape(item['title'])}</td>"
                f"<td>{html.escape(tier_short_label(item['business_tier']))}</td>"
                f"<td>{html.escape(item['source_name'])}</td>"
                f"<td>{html.escape(_display_deadline(item))}</td>"
                f"<td>{item['relevance_score']}</td>"
                f"<td>{html.escape(item['tier_reason'] or '원문 확인 필요')}</td>"
                f"<td>{html.escape(', '.join(item['matched_keywords']) or '-')}</td>"
                f"<td>{link}</td>"
                "</tr>"
            )
        return "\n".join(rows)

    similar = "".join(
        "<li>{} ↔ {} <span>(공통: {})</span></li>".format(
            html.escape(pair["left"]["title"]),
            html.escape(pair["right"]["title"]),
            html.escape(", ".join(pair["common_terms"])),
        )
        for pair in briefing["similar_pairs"]
    ) or "<li>현재 수집 범위에서는 유사 공고 쌍이 충분하지 않습니다.</li>"

    cards = "".join(
        f'<section class="card"><strong>{html.escape(label)}</strong><b>{value}</b></section>'
        for label, value in [
            ("전체 공고", summary["total_notices"]),
            ("기준점수 이상", summary["eligible_notices"]),
            ("Tier 1", summary["tier_1"]),
            ("Tier 2", summary["tier_2"]),
            ("Tier 3", summary["tier_3"]),
            ("오늘 수집", summary["new_today"]),
            (f"D-{briefing['due_days']} 이내", summary["urgent"]),
            ("문서 미수집", summary["missing_documents"]),
            ("관심/추적", summary["watching"]),
        ]
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>기후 RFP 브리핑</title>
<style>
body{{font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;max-width:1280px;margin:32px auto;padding:0 20px;color:#172025;background:#f5f8f6}}
h1{{margin-bottom:4px}} .muted{{color:#5a6b62}} .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:24px 0}}
.card{{background:#fff;border:1px solid #d8e2db;border-radius:10px;padding:16px}} .card strong{{display:block;color:#4b6255;font-size:13px}} .card b{{display:block;font-size:26px;margin-top:6px}}
section.panel{{background:#fff;border:1px solid #d8e2db;border-radius:10px;padding:18px;margin:18px 0;overflow:auto}} table{{width:100%;border-collapse:collapse;font-size:14px}} th,td{{text-align:left;padding:10px;border-bottom:1px solid #e5ece7;vertical-align:top}} th{{background:#edf5ef}} a{{color:#166534}} li{{margin:8px 0}} li span{{color:#5a6b62}}
</style>
</head>
<body>
<h1>기후·GHG·ETS 입찰 브리핑</h1>
<p class="muted">생성 시각: {generated_at}</p>
<div class="cards">{cards}</div>
<section class="panel"><h2>우선 확인 공고</h2><table><thead><tr><th>공고</th><th>Tier</th><th>출처</th><th>마감</th><th>점수</th><th>분류 근거</th><th>키워드</th><th>원문</th></tr></thead><tbody>{item_rows(briefing['action_queue'])}</tbody></table></section>
<section class="panel"><h2>문서 확인 필요</h2><table><thead><tr><th>공고</th><th>Tier</th><th>출처</th><th>마감</th><th>점수</th><th>분류 근거</th><th>키워드</th><th>원문</th></tr></thead><tbody>{item_rows(briefing['missing_documents'])}</tbody></table></section>
<section class="panel"><h2>유사 공고 신호</h2><ul>{similar}</ul></section>
<p class="muted">원문 공고와 첨부 RFP/과업지시서를 확인한 뒤 입찰 자격과 제안 가능성을 판단하세요.</p>
</body></html>"""


def render_briefing_html(briefing: dict[str, Any], out_path: str | Path) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(briefing_html(briefing), encoding="utf-8")


def write_briefing_markdown(briefing: dict[str, Any], out_path: str | Path) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(briefing_markdown(briefing), encoding="utf-8")
