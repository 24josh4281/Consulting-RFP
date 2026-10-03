import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from rfp_tracker.briefing import is_notice_active
from rfp_tracker.documents import build_public_workbench_payload, build_workbench_payload
from rfp_tracker.render import render_workbench_dashboard
from rfp_tracker.storage import connect, list_notices, upsert_notice
from rfp_tracker.fetchers import G2BBidApiFetcher
from rfp_tracker.models import Notice


class G2BPrebidTests(unittest.TestCase):
    def test_published_prebid_notice_is_kept_until_deadline(self):
        now = datetime(2026, 10, 1, 16, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        notice = Notice(
            source_id="g2b_service_bids",
            source_name="나라장터",
            external_id="R26BK01752198-000",
            title="아산화질소 온실가스 저감 및 자원화 기술개발사업 기획 연구",
            url="https://www.g2b.go.kr/",
            deadline_at="2026-10-13 10:00:00",
            raw={"bidBeginDt": "2026-10-08 10:00:00"},
        )
        self.assertTrue(G2BBidApiFetcher._is_currently_open(notice, now))
        self.assertFalse(G2BBidApiFetcher._is_currently_open(notice, now + timedelta(days=12)))

    def test_bid_window_status_counts_and_new_discovery(self):
        start = datetime(2026, 10, 8, 10, tzinfo=ZoneInfo("Asia/Seoul"))
        deadline = datetime(2026, 10, 13, 10, tzinfo=start.tzinfo)
        cases = (
            (start - timedelta(seconds=1), False, True, True, "입찰 시작 전"),
            (start, True, False, True, "입찰 접수 중"),
            (deadline + timedelta(seconds=1), False, False, False, "입찰 종료·확인"),
        )
        for now, active, upcoming, discoverable, label in cases:
            with self.subTest(now=now), tempfile.TemporaryDirectory() as directory:
                connection = connect(Path(directory) / "tracker.db")
                notice = Notice(
                    source_id="g2b_service_bids", source_name="나라장터",
                    external_id="R26BK01752198-000",
                    title="아산화질소 온실가스 저감 및 자원화 기술개발사업 기획 연구",
                    url="https://www.g2b.go.kr/", deadline_at="2026-10-13 10:00:00",
                    business_tier="tier_1", relevance_score=7,
                    raw={"bidBeginDt": "2026-10-08 10:00:00"},
                )
                upsert_notice(connection, notice)
                connection.execute("UPDATE notices SET first_seen_at = ?", (now.isoformat(),))
                connection.commit()
                self.assertEqual(is_notice_active(list_notices(connection)[0], now), active)
                self.assertEqual(G2BBidApiFetcher._is_currently_open(notice, now), discoverable)
                with patch("rfp_tracker.documents.seoul_now", return_value=now):
                    public = build_public_workbench_payload(connection)
                    internal = build_workbench_payload(connection)
                for payload in (public, internal):
                    self.assertEqual(len(payload["notices"]), 1)
                    item = payload["notices"][0]
                    self.assertEqual(item["is_active"], active)
                    self.assertEqual(item["is_upcoming"], upcoming)
                    self.assertEqual(payload["summary"]["active_tier_1"], int(active))
                self.assertEqual(public["notices"][0]["is_new_tier_1"], discoverable)
                output = Path(directory) / "public.html"
                render_workbench_dashboard(public, output, public=True)
                rendered = output.read_text(encoding="utf-8")
                self.assertIn(label, rendered)
                new_section = rendered.split('<section id="new-tier1"', 1)[1].split('</section>', 1)[0]
                self.assertEqual(notice.title in new_section, discoverable)
                self.assertIn('value="open" selected>접수 중·시작 전', rendered)
                connection.close()

    def test_missing_invalid_start_and_non_g2b_keep_previous_behavior(self):
        now = datetime(2026, 10, 8, 10, tzinfo=ZoneInfo("Asia/Seoul"))
        row = {"source_id": "g2b_service_bids", "category": "", "deadline_at": "2026-10-13 10:00:00"}
        for raw in ("{}", "invalid", "[]", json.dumps({"bidBeginDt": "unknown"})):
            with self.subTest(raw=raw):
                self.assertTrue(is_notice_active(dict(row, raw_json=raw), now))
        self.assertTrue(is_notice_active(dict(row, source_id="official_board", raw_json=json.dumps({"bidBeginDt": "2026-10-09 10:00:00"})), now))
        self.assertFalse(is_notice_active(dict(row, deadline_at="2026-10-08 09:59:59", raw_json="{}"), now))


if __name__ == "__main__":
    unittest.main()
