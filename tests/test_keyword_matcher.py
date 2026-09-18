import json
import unittest
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from rfp_tracker.briefing import briefing_markdown, build_briefing
from rfp_tracker.companies import Company, generate_homepage_sources, normalize_url
from rfp_tracker.config import load_dotenv, read_json, set_source_enabled
from rfp_tracker.documents import classify_document, list_document_rows
from rfp_tracker.fetchers import build_fetcher
from rfp_tracker.keyword_matcher import extension_from_url, is_excluded, is_relevant, score_text
from rfp_tracker.models import Attachment, Notice
from rfp_tracker.notifications import dispatch_notifications
from rfp_tracker.storage import connect, list_notices, update_notice_review, upsert_notice


KEYWORDS = {
    "min_relevance_score": 2,
    "keyword_groups": {
        "ghg": ["온실가스", "scope 3"],
        "ets": ["배출권거래제"],
        "reporting": ["cdp"],
    },
    "tender_terms": ["입찰", "공고", "용역"],
    "exclude_terms": ["청소", "경비"],
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_KEYWORDS = read_json(PROJECT_ROOT / "configs" / "keywords.json")


class KeywordMatcherTests(unittest.TestCase):
    def test_scores_climate_tender_notice(self):
        result = score_text("2026년 CDP 대응 및 Scope 3 온실가스 산정 컨설팅 용역 입찰", KEYWORDS)
        self.assertGreaterEqual(result.score, 4)
        self.assertIn("온실가스", result.keywords)

    def test_low_score_for_unrelated_cleaning_bid(self):
        result = score_text("본사 사옥 청소 용역 업체 선정 공고", KEYWORDS)
        self.assertLess(result.score, 4)

    def test_excluded_term_overrides_other_relevance_signals(self):
        text = "온실가스 배출량 관리 시스템 청소 용역 입찰"
        self.assertTrue(is_excluded(text, KEYWORDS))
        self.assertFalse(is_relevant(text, KEYWORDS))

    def test_environmental_consulting_terms_are_relevant_in_project_filter(self):
        text = "환경영향평가 및 탄소발자국 LCA 컨설팅 용역 입찰"
        result = score_text(text, PROJECT_KEYWORDS)
        self.assertTrue(is_relevant(text, PROJECT_KEYWORDS))
        self.assertIn("환경영향평가", result.keywords)
        self.assertIn("탄소발자국", result.keywords)

    def test_environmental_cleaning_and_waste_collection_stay_excluded(self):
        self.assertFalse(is_relevant("환경미화 및 청소 용역 입찰", PROJECT_KEYWORDS))
        self.assertFalse(is_relevant("사업장 폐기물 수집운반 처리 용역 입찰", PROJECT_KEYWORDS))

    def test_environmental_impact_assessment_is_not_blocked_by_waste_context(self):
        self.assertTrue(is_relevant("폐기물 처리시설 환경영향평가 용역 입찰", PROJECT_KEYWORDS))


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

    def test_g2b_environment_source_and_daily_1700_config_are_ready(self):
        sources = read_json(PROJECT_ROOT / "configs" / "sources.example.json")
        g2b = next(source for source in sources["sources"] if source["id"] == "g2b_service_bids")
        notification_config = read_json(PROJECT_ROOT / "configs" / "notifications.example.json")
        self.assertEqual(g2b["priority"], "P0")
        self.assertEqual(g2b["max_pages"], 5)
        self.assertEqual(
            g2b["endpoint"],
            "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc",
        )
        self.assertEqual(g2b["service_key_param"], "serviceKey")
        self.assertIn("https://www.g2b.go.kr/", g2b["portal_url"])
        self.assertEqual(notification_config["daily_send_at"], "17:00")


class G2BFetcherTests(unittest.TestCase):
    def test_g2b_fetch_uses_current_service_key_parameter(self):
        source = {
            "id": "g2b_service_bids",
            "name": "G2B environmental services",
            "type": "g2b_bid_api",
            "endpoint": "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc",
            "service_key_env": "TEST_G2B_SERVICE_KEY",
            "max_pages": 1,
            "default_params": {"inqryDiv": "1", "type": "json", "numOfRows": "100"},
        }
        payload = json.dumps({"response": {"body": {"items": {"item": []}}}})
        fetcher = build_fetcher(source, PROJECT_KEYWORDS, {}, Path("."))

        with patch.dict(os.environ, {"TEST_G2B_SERVICE_KEY": "test-key"}, clear=False), patch(
            "rfp_tracker.fetchers.fetch_text", return_value=payload
        ) as fetch_text:
            self.assertEqual(fetcher.fetch(days=3), [])

        request_url = fetch_text.call_args.args[0]
        self.assertIn("serviceKey=test-key", request_url)
        self.assertNotIn("ServiceKey=", request_url)

    def test_g2b_environmental_service_notice_passes_project_filter(self):
        source = {
            "id": "g2b_service_bids",
            "name": "G2B environmental services",
            "type": "g2b_bid_api",
            "endpoint": "https://example.com/g2b",
        }
        payload = {
            "response": {
                "body": {
                    "items": {
                        "item": [
                            {
                            "bidNtceNo": "R26BK00000001",
                            "bidNtceOrd": "000",
                            "bidNtceNm": "온실가스 감축 및 환경영향평가 컨설팅 용역 입찰",
                            "bidNtceDt": "202609180900",
                            "bidClseDt": "202609251000",
                            "dminsttNm": "테스트 기관",
                            "bidNtceDtlUrl": "https://www.g2b.go.kr/example",
                            }
                        ]
                    }
                }
            }
        }
        fetcher = build_fetcher(source, PROJECT_KEYWORDS, {}, Path("."))
        notices = fetcher._parse_payload(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(len(notices), 1)
        self.assertIn("환경영향평가", notices[0].matched_keywords)

    def test_g2b_api_error_payload_is_reported_without_creating_notice(self):
        source = {
            "id": "g2b_service_bids",
            "name": "G2B environmental services",
            "type": "g2b_bid_api",
            "endpoint": "https://example.com/g2b",
        }
        payload = {
            "OpenAPI_ServiceResponse": {
                "cmmMsgHeader": {"errMsg": "SERVICE_KEY_IS_NULL", "returnReasonCode": "20"}
            }
        }
        fetcher = build_fetcher(source, PROJECT_KEYWORDS, {}, Path("."))

        with patch("builtins.print") as printed:
            notices = fetcher._parse_payload(json.dumps(payload))

        self.assertEqual(notices, [])
        self.assertIn("SERVICE_KEY_IS_NULL", printed.call_args.args[0])


class DocumentIndexTests(unittest.TestCase):
    def test_extracts_file_type_from_official_board_label_with_size(self):
        self.assertEqual(extension_from_url("제안요청서.hwpx\n (5,044,108 Byte)"), "hwpx")

    def test_refreshes_tokenized_official_attachment_without_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = connect(Path(tmp_dir) / "tracker.db")
            original = Notice(
                source_id="official-board",
                source_name="Official board",
                external_id="tokenized-attachment",
                title="온실가스 검증 용역 입찰",
                url="https://example.com/notice",
                relevance_score=6,
                matched_keywords=["온실가스", "검증"],
                attachments=[
                    Attachment(
                        label="제안요청서.hwpx (10 Byte)",
                        url="https://example.com/download?encFileId=old&fileSeq=2",
                        file_type="",
                    )
                ],
            )
            refreshed = Notice(
                source_id=original.source_id,
                source_name=original.source_name,
                external_id=original.external_id,
                title=original.title,
                url=original.url,
                relevance_score=original.relevance_score,
                matched_keywords=original.matched_keywords,
                attachments=[
                    Attachment(
                        label="제안요청서.hwpx (10 Byte)",
                        url="https://example.com/download?encFileId=new&fileSeq=2",
                        file_type="hwpx",
                    )
                ],
            )
            upsert_notice(connection, original)
            upsert_notice(connection, refreshed)

            rows = list_document_rows(connection)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["file_type"], "hwpx")
            self.assertIn("encFileId=new", str(rows[0]["document_url"]))
            connection.close()

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


class BriefingTests(unittest.TestCase):
    def test_briefing_highlights_urgent_and_missing_documents(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "tracker.db"
            connection = connect(db_path)
            upsert_notice(
                connection,
                Notice(
                    source_id="sample",
                    source_name="Sample",
                    external_id="urgent-no-doc",
                    title="온실가스 배출권거래제 컨설팅 입찰",
                    url="https://example.com/urgent",
                    deadline_at="20260920",
                    relevance_score=7,
                    matched_keywords=["온실가스", "배출권거래제"],
                ),
            )
            upsert_notice(
                connection,
                Notice(
                    source_id="sample",
                    source_name="Sample",
                    external_id="with-rfp",
                    title="기후리스크 분석 RFP",
                    url="https://example.com/rfp",
                    relevance_score=6,
                    matched_keywords=["기후", "분석"],
                    attachments=[Attachment(label="제안요청서", url="https://example.com/rfp.pdf", file_type="pdf")],
                ),
            )
            now = datetime(2026, 9, 18, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
            briefing = build_briefing(connection, due_days=7, min_score=3, now=now)
            self.assertEqual(briefing["summary"]["urgent"], 1)
            self.assertEqual(briefing["summary"]["missing_documents"], 1)
            self.assertIn("문서 확인 필요", briefing_markdown(briefing))
            connection.close()


class OfficialBoardFetcherTests(unittest.TestCase):
    def test_detail_page_adds_public_rfp_link_and_metadata(self):
        source = {
            "id": "official-board",
            "name": "Official board",
            "type": "official_board_html",
            "url": "https://board.example.com/list",
            "detail_url_contains": "/home/board/read.do",
            "detail_title_prefix": "[입찰]",
            "max_detail_pages": 1,
            "detail_delay_seconds": 0,
        }
        listing_html = '<a href="/home/board/read.do?boardId=1">[입찰] 온실가스 검증 용역</a>'
        detail_html = """
        <p>등록일 2026-09-18</p><p>등록자 기획총괄팀</p>
        <p>전자입찰로 진행합니다.</p>
        <a href="/files/download?file=1">제안요청서.hwpx</a>
        """

        def fake_fetch(url, timeout, user_agent):
            return listing_html if url == source["url"] else detail_html

        with patch("rfp_tracker.fetchers.fetch_text", side_effect=fake_fetch):
            fetcher = build_fetcher(source, KEYWORDS, {"request_timeout_seconds": 5}, Path("."))
            notices = fetcher.fetch(days=3)

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].published_at, "2026-09-18")
        self.assertEqual(notices[0].procurement_method, "전자입찰")
        self.assertEqual(len(notices[0].attachments), 1)
        self.assertEqual(notices[0].attachments[0].file_type, "hwpx")


class NotificationTests(unittest.TestCase):
    def test_daily_email_uses_configured_1700_label(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = connect(Path(tmp_dir) / "tracker.db")
            baseline = datetime(2026, 9, 18, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
            dispatch_notifications(connection, recipients=["alerts@example.com"], mode="immediate", now=baseline)
            upsert_notice(
                connection,
                Notice(
                    source_id="sample",
                    source_name="Sample",
                    external_id="daily-1700",
                    title="환경영향평가 컨설팅 용역 입찰",
                    url="https://example.com/daily",
                    relevance_score=6,
                    matched_keywords=["환경영향평가"],
                ),
            )
            later = (baseline + timedelta(minutes=1)).isoformat(timespec="seconds")
            connection.execute("UPDATE notices SET first_seen_at = ?, last_seen_at = ?", (later, later))
            connection.commit()

            captured: list[str] = []
            result = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="daily",
                daily_send_at="17:00",
                send=True,
                sender=lambda _recipient, payload: captured.append(payload.text),
                now=baseline + timedelta(hours=7),
            )
            self.assertEqual(result[0].sent, 1)
            self.assertIn("17:00", captured[0])
            connection.close()

    def test_immediate_alert_uses_baseline_and_prevents_duplicate_delivery(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "tracker.db"
            connection = connect(db_path)
            now = datetime(2026, 9, 18, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
            sent: list[str] = []

            first = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="immediate",
                min_score=3,
                send=True,
                sender=lambda _recipient, payload: sent.append(payload.subject),
                now=now,
            )
            self.assertTrue(first[0].baseline_initialized)
            self.assertEqual(sent, [])

            upsert_notice(
                connection,
                Notice(
                    source_id="sample",
                    source_name="Sample",
                    external_id="new-after-baseline",
                    title="온실가스 검증 용역 입찰",
                    url="https://example.com/new",
                    relevance_score=6,
                    matched_keywords=["온실가스", "검증"],
                ),
            )
            later = (now + timedelta(minutes=1)).isoformat(timespec="seconds")
            connection.execute("UPDATE notices SET first_seen_at = ?, last_seen_at = ?", (later, later))
            connection.commit()

            second = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="immediate",
                min_score=3,
                send=True,
                sender=lambda _recipient, payload: sent.append(payload.subject),
                now=now + timedelta(minutes=2),
            )
            self.assertEqual(second[0].sent, 1)
            self.assertEqual(len(sent), 1)

            third = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="immediate",
                min_score=3,
                send=True,
                sender=lambda _recipient, payload: sent.append(payload.subject),
                now=now + timedelta(minutes=3),
            )
            self.assertEqual(third[0].sent, 0)
            self.assertEqual(len(sent), 1)
            connection.close()

    def test_failed_immediate_email_stays_retryable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "tracker.db"
            connection = connect(db_path)
            now = datetime(2026, 9, 18, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
            dispatch_notifications(connection, recipients=["alerts@example.com"], mode="immediate", now=now)
            upsert_notice(
                connection,
                Notice(
                    source_id="sample",
                    source_name="Sample",
                    external_id="retryable",
                    title="배출권거래제 검토 용역 입찰",
                    url="https://example.com/retry",
                    relevance_score=6,
                    matched_keywords=["배출권거래제"],
                ),
            )
            later = (now + timedelta(minutes=1)).isoformat(timespec="seconds")
            connection.execute("UPDATE notices SET first_seen_at = ?, last_seen_at = ?", (later, later))
            connection.commit()

            failed = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="immediate",
                send=True,
                sender=lambda _recipient, _payload: (_ for _ in ()).throw(RuntimeError("smtp unavailable")),
                now=now + timedelta(minutes=2),
            )
            self.assertEqual(failed[0].failed, 1)

            sent: list[str] = []
            retried = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="immediate",
                send=True,
                sender=lambda _recipient, payload: sent.append(payload.subject),
                now=now + timedelta(minutes=3),
            )
            self.assertEqual(retried[0].sent, 1)
            self.assertEqual(len(sent), 1)
            connection.close()

    def test_historical_backfill_is_not_sent_as_new(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "tracker.db"
            connection = connect(db_path)
            baseline = datetime(2026, 9, 18, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
            dispatch_notifications(connection, recipients=["alerts@example.com"], mode="immediate", now=baseline)
            upsert_notice(
                connection,
                Notice(
                    source_id="official-board",
                    source_name="Official board",
                    external_id="old-backfill",
                    title="온실가스 배출권거래제 통합정보시스템 용역",
                    url="https://example.com/old",
                    published_at="2026-07-23",
                    relevance_score=7,
                    matched_keywords=["온실가스", "배출권거래제"],
                ),
            )
            later = (baseline + timedelta(minutes=1)).isoformat(timespec="seconds")
            connection.execute("UPDATE notices SET first_seen_at = ?, last_seen_at = ?", (later, later))
            connection.commit()

            sent: list[str] = []
            result = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="immediate",
                send=True,
                sender=lambda _recipient, payload: sent.append(payload.subject),
                now=baseline + timedelta(minutes=2),
            )
            self.assertEqual(result[0].sent, 0)
            self.assertEqual(result[0].planned, 0)
            self.assertEqual(sent, [])
            connection.close()


if __name__ == "__main__":
    unittest.main()
