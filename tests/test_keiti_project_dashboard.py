import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from rfp_tracker.documents import build_public_workbench_payload
from rfp_tracker.grant_fetchers import parse_keiti_rows
from rfp_tracker.models import Notice
from rfp_tracker.render import render_workbench_dashboard
from rfp_tracker.storage import connect, upsert_notice
from rfp_tracker.tiering import TIER_1, assess_innergen_tier


class KeitiProjectDashboardTests(unittest.TestCase):
    def test_project_call_is_tier_one(self):
        title = "2026년도 「해외 환경프로젝트 타당성조사 지원사업」 본타당성조사(다년도) 모집 공고"
        card = ('<a href="/site/keiti/ex/board/View.do?cbIdx=277&amp;bcIdx=41408">'
                '<span class="cateName">공지</span><span class="date">2026-09-29</span>'
                f'<span class="subject">{title}</span></a>')
        rows = parse_keiti_rows(card, "https://www.keiti.re.kr/site/keiti/ex/board/List.do?cbIdx=277")
        self.assertEqual([row["external_id"] for row in rows], ["41408"])
        self.assertEqual(assess_innergen_tier(title, category="grant_application").tier, TIER_1)
        self.assertEqual(
            assess_innergen_tier("해외 녹색프로젝트 예비타당성조사 지원사업 모집 공고", category="grant_application").tier,
            TIER_1,
        )

    def test_upcoming_project_is_prominent_without_open_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = connect(Path(tmp) / "test.db")
            try:
                upsert_notice(db, Notice(
                    source_id="keiti_ghg_financing_grants", source_name="KEITI", external_id="41408",
                    title="해외 환경프로젝트 타당성조사 지원사업 모집 공고",
                    url="https://www.keiti.re.kr/site/keiti/ex/board/View.do?cbIdx=277&bcIdx=41408",
                    published_at="2026-09-29", deadline_at="2026-10-16 16:00",
                    category="grant_application", business_tier=TIER_1, relevance_score=8,
                    raw={"application_start_at": "2026-10-01 00:00"},
                ))
                with patch("rfp_tracker.documents.seoul_now", return_value=datetime(2026, 9, 30, 12, tzinfo=ZoneInfo("Asia/Seoul"))):
                    payload = build_public_workbench_payload(db)
                self.assertTrue(payload["notices"][0]["is_upcoming"])
                self.assertFalse(payload["notices"][0]["is_active"])
                page = Path(tmp) / "site.html"
                render_workbench_dashboard(payload, page, public=True)
                text = page.read_text(encoding="utf-8")
                self.assertIn('id="upcoming-tier1"', text)
                self.assertIn('data-active="upcoming"', text)
            finally:
                db.close()
