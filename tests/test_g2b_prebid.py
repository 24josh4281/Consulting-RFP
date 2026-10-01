import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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


if __name__ == "__main__":
    unittest.main()
