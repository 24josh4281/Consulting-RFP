import unittest
import tempfile
from pathlib import Path

from rfp_tracker.keyword_matcher import score_text
from rfp_tracker.models import Notice
from rfp_tracker.storage import connect, list_notices, update_notice_review, upsert_notice


KEYWORDS = {
    "min_relevance_score": 2,
    "keyword_groups": {
        "ghg": ["온실가스", "scope 3"],
        "ets": ["배출권거래제"],
        "reporting": ["cdp"],
    },
    "tender_terms": ["입찰", "공고", "용역"],
}


class KeywordMatcherTests(unittest.TestCase):
    def test_scores_climate_tender_notice(self):
        result = score_text("2026년 CDP 대응 및 Scope 3 온실가스 산정 컨설팅 용역 입찰", KEYWORDS)
        self.assertGreaterEqual(result.score, 4)
        self.assertIn("온실가스", result.keywords)

    def test_low_score_for_unrelated_cleaning_bid(self):
        result = score_text("본사 사옥 청소 용역 업체 선정 공고", KEYWORDS)
        self.assertLess(result.score, 4)


class StorageReviewTests(unittest.TestCase):
    def test_review_status_can_be_updated(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "tracker.db"
            connection = connect(db_path)
            upsert_notice(
                connection,
                Notice(
                    source_id="sample",
                    source_name="Sample",
                    external_id="notice-1",
                    title="온실가스 검증 용역 입찰",
                    url="https://example.com/notice-1",
                    relevance_score=6,
                    matched_keywords=["온실가스", "검증", "용역"],
                ),
            )

            rows = list_notices(connection)
            self.assertEqual(rows[0]["review_status"], "new")

            updated = update_notice_review(connection, rows[0]["id"], "interesting", "제안 검토")
            self.assertTrue(updated)
            rows = list_notices(connection)
            self.assertEqual(rows[0]["review_status"], "interesting")
            self.assertEqual(rows[0]["review_note"], "제안 검토")
            connection.close()


if __name__ == "__main__":
    unittest.main()
