"""Read public grant boards into an in-memory DB without touching operational data.

Usage: python -X utf8 scripts/verify_official_grants.py --days 365
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rfp_tracker.briefing import is_notice_active  # noqa: E402
from rfp_tracker.config import read_json  # noqa: E402
from rfp_tracker.documents import build_public_workbench_payload  # noqa: E402
from rfp_tracker.fetchers import build_fetcher  # noqa: E402
from rfp_tracker.render import render_workbench_dashboard  # noqa: E402
from rfp_tracker.storage import connect, list_notices, upsert_notice  # noqa: E402
from rfp_tracker.tiering import TIER_2, assess_innergen_tier  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="공식 지원사업 공개 공고만 안전하게 시험 조회")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--render", type=Path, help="선택: 공개 형태의 로컬 HTML 미리보기 생성")
    args = parser.parse_args()
    config = read_json(ROOT / "configs" / "sources.example.json")
    keywords = read_json(ROOT / "configs" / "keywords.json")
    db = connect(":memory:")
    try:
        for source in config["sources"]:
            if source.get("type") != "official_grant_board":
                continue
            notices = build_fetcher(source, keywords, config["global"], ROOT).fetch(args.days)
            print(f"{source['id']}: {len(notices)}건")
            for notice in notices:
                assessment = assess_innergen_tier(notice.title, category=notice.category)
                notice.business_tier = assessment.tier
                notice.tier_reason = assessment.reason
                if notice.business_tier != TIER_2:
                    raise ValueError(f"지원사업 후보가 Tier 2가 아닙니다: {notice.title}")
                upsert_notice(db, notice)
                state = "신청 가능" if is_notice_active({
                    "category": notice.category,
                    "deadline_at": notice.deadline_at,
                    "raw_json": json.dumps(notice.raw, ensure_ascii=False),
                }) else "마감·확인 필요"
                print(f"  {state} | {notice.deadline_at or '기한 미수집'} | {notice.title}")
        rows = list_notices(db)
        active = sum(1 for row in rows if is_notice_active(row))
        print(f"합계 {len(rows)}건 / 신청 가능 {active}건")
        if args.render:
            payload = build_public_workbench_payload(db)
            args.render.parent.mkdir(parents=True, exist_ok=True)
            render_workbench_dashboard(payload, args.render, public=True)
            print(f"미리보기: {args.render}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
