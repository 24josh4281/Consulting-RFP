import unittest
import os
import tempfile
from pathlib import Path

from rfp_tracker.companies import Company, generate_homepage_sources, normalize_url
from rfp_tracker.config import load_dotenv, set_source_enabled
from rfp_tracker.documents import classify_document, list_document_rows
from rfp_tracker.keyword_matcher import score_text
from rfp_tracker.models import Attachment, Notice
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


class CompanyUtilityTests(unittest.TestCase):
    def test_normalize_homepage_url(self):
        self.assertEqual(normalize_url("www.example.com"), "https://www.example.com")
        self.assertEqual(normalize_url("https://example.com"), "https://example.com")

    def test_generate_homepage_sources_is_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out = Path(tmp_dir) / "sources.json"
            generate_homepage_sources(
                [
                    Company(name="Example Corp", ticker="000001", homepage="https://example.com"),
                    Company(name="No Homepage", ticker="000002", homepage=""),
                ],
                out,
            )
            text = out.read_text(encoding="utf-8")
            self.assertIn('"enabled": false', text)
            self.assertIn("Example Corp", text)
            self.assertNotIn("No Homepage", text)


class ConfigUtilityTests(unittest.TestCase):
    def test_load_dotenv_sets_missing_values_without_override(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text("RFP_TRACKER_TEST_KEY=from_file\n", encoding="utf-8")
            original = os.environ.pop("RFP_TRACKER_TEST_KEY", None)
            try:
                loaded = load_dotenv(env_path)
                self.assertEqual(loaded, 1)
                self.assertEqual(os.environ["RFP_TRACKER_TEST_KEY"], "from_file")

                env_path.write_text("RFP_TRACKER_TEST_KEY=changed\n", encoding="utf-8")
                loaded = load_dotenv(env_path)
                self.assertEqual(loaded, 0)
                self.assertEqual(os.environ["RFP_TRACKER_TEST_KEY"], "from_file")
            finally:
                if original is None:
                    os.environ.pop("RFP_TRACKER_TEST_KEY", None)
                else:
                    os.environ["RFP_TRACKER_TEST_KEY"] = original

    def test_set_source_enabled_updates_matching_source_only(self):
        config = {
            "sources": [
                {"id": "sample", "enabled": True},
                {"id": "g2b_service_bids", "enabled": False},
            ]
        }
        updated = set_source_enabled(config, "g2b_service_bids", True)
        self.assertTrue(updated)
        self.assertTrue(config["sources"][1]["enabled"])
        self.assertTrue(config["sources"][0]["enabled"])
        self.assertFalse(set_source_enabled(config, "missing", True))


class DocumentIndexTests(unittest.TestCase):
    def test_classifies_common_rfp_documents(self):
        self.assertEqual(classify_document("RFP.pdf", "https://example.com/rfp.pdf"), "rfp")
        self.assertEqual(classify_document("task order", "https://example.com/task-order.hwp"), "scope")
        self.assertEqual(classify_document("submission forms", "https://example.com/forms.zip"), "forms")

    def test_document_rows_include_missing_document_gap(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "tracker.db"
            connection = connect(db_path)
            upsert_notice(
                connection,
                Notice(
                    source_id="sample",
                    source_name="Sample",
                    external_id="notice-with-doc",
                    title="Climate RFP notice",
                    url="https://example.com/notice-with-doc",
                    relevance_score=6,
                    matched_keywords=["climate", "rfp"],
                    attachments=[
                        Attachment(
                            label="RFP PDF",
                            url="https://example.com/files/climate-rfp.pdf",
                            file_type="pdf",
                        )
                    ],
                ),
            )
            upsert_notice(
                connection,
                Notice(
                    source_id="sample",
                    source_name="Sample",
                    external_id="notice-without-doc",
                    title="Climate scope notice",
                    url="https://example.com/notice-without-doc",
                    relevance_score=5,
                    matched_keywords=["climate"],
                ),
            )

            rows = list_document_rows(connection)
            kinds = [row["document_kind"] for row in rows]
            self.assertIn("rfp", kinds)
            self.assertIn("missing", kinds)

            rfp_rows = list_document_rows(connection, kind="rfp")
            self.assertEqual(len(rfp_rows), 1)
            self.assertEqual(rfp_rows[0]["document_url"], "https://example.com/files/climate-rfp.pdf")
            connection.close()


if __name__ == "__main__":
    unittest.main()
