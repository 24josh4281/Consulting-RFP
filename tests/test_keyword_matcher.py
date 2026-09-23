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
from rfp_tracker.keyword_matcher import assess_g2b_title, extension_from_url, is_excluded, is_relevant, score_text
from rfp_tracker.models import Attachment, Notice
from rfp_tracker.notifications import dispatch_notifications, read_notification_config
from rfp_tracker.storage import connect, list_notices, update_notice_review, update_notice_tier, upsert_notice
from rfp_tracker.tiering import TIER_1, TIER_2, TIER_3, assess_innergen_tier


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


class TieringTests(unittest.TestCase):
    def test_innergen_tiers_follow_business_scope_and_exclusion_priority(self):
        cases = [
            ("Scope 3 온실가스 산정 고도화 컨설팅 용역", TIER_1),
            ("ETS 배출권 제도 분석 컨설팅", TIER_1),
            ("배출권거래제 통합정보시스템 기능개선 연구 용역", TIER_3),
            ("기후변화 산업 전환 시나리오 분석 연구", TIER_1),
            ("아산화질소 온실가스 저감 및 자원화 기술개발사업 기획 연구", TIER_1),
            ("비이산화탄소 온실가스 저감·관리 기술개발사업 사전기획 연구", TIER_1),
            ("Verra 외부사업 감축실적 방법론 개발 컨설팅", TIER_1),
            ("ITMO 국제감축사업 온실가스 감축량 평가 용역", TIER_1),
            ("CBAM 및 CSRD Scope 1~3 공시 대응 컨설팅", TIER_1),
            ("RE100 PPA 조달 계획 및 재무적 영향 분석", TIER_1),
            ("K-RE100 재생에너지 PPA 조달 중개 및 민감도 진단", TIER_1),
            ("PAS 2060 탄소중립 인증 계획 수립", TIER_1),
            ("온실가스 감축실적 Credit 발급 지원", TIER_1),
            ("온실가스 저감 설비 설치 지원사업", TIER_2),
            ("탄소중립 설비투자 지원사업_인버터 공기압축기", TIER_3),
            ("환경설비 도입 보조금 지원사업", TIER_2),
            ("친환경 설비 도입 금리 지원사업", TIER_2),
            ("온실가스 감축설비 저금리 융자 지원사업", TIER_2),
            ("스마트 불법대기배출 통합 플랫폼 개발", TIER_3),
            ("파주교하 상록아파트 외벽 환경 개선공사", TIER_3),
            ("기후위기 대응 아동복지시설 지원사업", TIER_3),
            ("수질복원센터 하수찌꺼기 운반 및 처리용역", TIER_3),
            ("탄소중립펀드 투자유치 운영 용역", TIER_3),
            ("기후위기 대응 홍보 영상 제작", TIER_3),
            ("탄소 소재 기초과학 실험 연구", TIER_3),
            ("CDPR 정밀 제어 알고리즘 개발", TIER_3),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(assess_innergen_tier(title).tier, expected)

    def test_manual_tier_is_preserved_when_source_notice_is_refreshed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = connect(Path(tmp_dir) / "tracker.db")
            original = Notice(
                source_id="sample",
                source_name="Sample",
                external_id="manual-tier",
                title="온실가스 산정 컨설팅 용역",
                url="https://example.com/original",
                relevance_score=7,
                business_tier=TIER_1,
                tier_reason="자동 분류",
            )
            upsert_notice(connection, original)
            notice_id = int(list_notices(connection)[0]["id"])
            self.assertTrue(update_notice_tier(connection, notice_id, TIER_3, "사내 판단으로 이번에는 제외"))

            refreshed = Notice(
                source_id="sample",
                source_name="Sample",
                external_id="manual-tier",
                title="온실가스 산정 컨설팅 용역 (정정)",
                url="https://example.com/refreshed",
                relevance_score=8,
                business_tier=TIER_1,
                tier_reason="자동 재분류",
            )
            upsert_notice(connection, refreshed)
            row = list_notices(connection)[0]
            self.assertEqual(row["business_tier"], TIER_3)
            self.assertEqual(row["tier_source"], "manual")
            self.assertEqual(row["tier_reason"], "사내 판단으로 이번에는 제외")
            self.assertEqual(row["title"], "온실가스 산정 컨설팅 용역 (정정)")
            connection.close()

    def test_tier_two_requires_a_customer_application_not_a_supplier_purchase(self):
        self.assertEqual(
            assess_innergen_tier(
                "2026년 탄소중립 설비투자 지원사업_인버터 공기압축기",
                buyer="주식회사 구산테크",
                procurement_method="일반경쟁",
            ).tier,
            TIER_3,
        )
        self.assertEqual(
            assess_innergen_tier("환경설비 도입 보조금 지원사업 참여기업 모집").tier,
            TIER_2,
        )


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

    def test_latin_abbreviation_does_not_match_as_a_partial_word(self):
        result = score_text("CDPR 정밀 제어 알고리즘 개발", PROJECT_KEYWORDS)
        self.assertNotIn("cdp", [keyword.lower() for keyword in result.keywords])

    def test_g2b_title_policy_keeps_ambiguous_environment_notice_for_review(self):
        assessment = assess_g2b_title("친환경 교통체계 구축사업 관련 연수 대행 용역", PROJECT_KEYWORDS)
        self.assertEqual(assessment.tier, "needs_review")

    def test_g2b_title_policy_requires_domain_signal_in_the_title(self):
        assessment = assess_g2b_title("정보보안 및 개인정보보호 관리체계 강화 컨설팅 및 인증 용역", PROJECT_KEYWORDS)
        self.assertEqual(assessment.tier, "ignore")

    def test_g2b_title_policy_accepts_specific_environment_research(self):
        assessment = assess_g2b_title("스마트 불법대기배출 통합 플랫폼 개발", PROJECT_KEYWORDS)
        self.assertEqual(assessment.tier, "strong")
        self.assertIn("대기배출", assessment.strong_keywords)

    def test_g2b_intake_only_accepts_innergen_scope(self):
        from rfp_tracker.keyword_matcher import is_climate_related_title

        self.assertTrue(is_climate_related_title("RE100 PPA 조달 전략 수립", PROJECT_KEYWORDS))
        self.assertTrue(is_climate_related_title("탄소중립 설비투자 지원사업", PROJECT_KEYWORDS))
        self.assertFalse(is_climate_related_title("친환경 교통체계 구축사업 관련 연수", PROJECT_KEYWORDS))
        self.assertFalse(is_climate_related_title("생활환경 개선공사", PROJECT_KEYWORDS))


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

    def test_needs_review_notice_is_stored_but_omitted_from_alerts_and_briefing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "tracker.db"
            connection = connect(db_path)
            now = datetime(2026, 9, 18, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
            dispatch_notifications(connection, recipients=["alerts@example.com"], mode="immediate", now=now)
            upsert_notice(
                connection,
                Notice(
                    source_id="g2b_service_bids",
                    source_name="G2B",
                    external_id="ambiguous-title",
                    title="친환경 교통체계 연수 대행 용역",
                    url="https://example.com/notice",
                    relevance_score=5,
                    matched_keywords=["친환경", "용역"],
                    review_status="needs_review",
                    review_note="사람 검토 필요",
                ),
            )
            first_seen = (now + timedelta(minutes=1)).isoformat(timespec="seconds")
            connection.execute("UPDATE notices SET first_seen_at = ?, last_seen_at = ?", (first_seen, first_seen))
            connection.commit()

            sent: list[str] = []
            alert = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="immediate",
                send=True,
                sender=lambda _recipient, payload: sent.append(payload.subject),
                now=now + timedelta(minutes=2),
            )
            briefing = build_briefing(connection, now=now + timedelta(minutes=2))
            rows = list_notices(connection)

            self.assertEqual(rows[0]["review_status"], "needs_review")
            self.assertEqual(alert[0].planned, 0)
            self.assertEqual(sent, [])
            self.assertEqual(briefing["summary"]["total_notices"], 0)
            self.assertEqual(briefing["summary"]["eligible_notices"], 0)
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

    def test_g2b_environment_source_and_twice_daily_config_are_ready(self):
        sources = read_json(PROJECT_ROOT / "configs" / "sources.example.json")
        g2b = next(source for source in sources["sources"] if source["id"] == "g2b_service_bids")
        notification_config = read_json(PROJECT_ROOT / "configs" / "notifications.example.json")
        self.assertEqual(g2b["priority"], "P0")
        self.assertEqual(g2b["max_pages"], 5)
        self.assertEqual(
            g2b["endpoint"],
            "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch",
        )
        self.assertEqual(g2b["service_key_param"], "serviceKey")
        self.assertIn("https://www.g2b.go.kr/", g2b["portal_url"])
        self.assertEqual(notification_config["daily_send_times"], ["10:00", "17:00"])

    def test_legacy_single_daily_time_remains_supported(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "notifications.json"
            config_path.write_text(
                json.dumps({"recipients": ["alerts@example.com"], "daily_send_at": "17:00"}),
                encoding="utf-8",
            )
            config = read_notification_config(config_path)
            self.assertEqual(config["daily_send_times"], ["17:00"])


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

    def test_g2b_uses_title_only_and_drops_unrelated_environment_notices(self):
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
                                "bidNtceNo": "R26BK00000002",
                                "bidNtceNm": "정보보안 및 개인정보보호 관리체계 강화 컨설팅 및 인증 용역",
                                "dminsttNm": "한국원자력환경공단",
                            },
                            {
                                "bidNtceNo": "R26BK00000003",
                                "bidNtceNm": "친환경 교통체계 구축사업 관련 연수 대행 용역",
                                "dminsttNm": "테스트 기관",
                            },
                        ]
                    }
                }
            }
        }
        fetcher = build_fetcher(source, PROJECT_KEYWORDS, {}, Path("."))
        notices = fetcher._parse_payload(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(notices, [])

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

    def test_g2b_missing_document_explains_how_to_check_public_attachment_section(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = connect(Path(tmp_dir) / "tracker.db")
            upsert_notice(
                connection,
                Notice(
                    source_id="g2b_service_bids",
                    source_name="나라장터",
                    external_id="g2b-no-attachment-url",
                    title="온실가스 검증 용역",
                    url="https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=test",
                    relevance_score=6,
                    matched_keywords=["온실가스", "검증"],
                ),
            )
            rows = list_document_rows(connection)
            self.assertEqual(rows[0]["document_kind"], "missing")
            self.assertIn("파일첨부", str(rows[0]["document_access_hint"]))
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
                    business_tier=TIER_1,
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
                    business_tier=TIER_1,
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
        published_date = datetime.now().strftime("%Y-%m-%d")
        detail_html = f"""
        <p>등록일 {published_date}</p><p>등록자 기획총괄팀</p>
        <p>전자입찰로 진행합니다.</p>
        <a href="/files/download?file=1">제안요청서.hwpx</a>
        """

        def fake_fetch(url, timeout, user_agent):
            return listing_html if url == source["url"] else detail_html

        with patch("rfp_tracker.fetchers.fetch_text", side_effect=fake_fetch):
            fetcher = build_fetcher(source, KEYWORDS, {"request_timeout_seconds": 5}, Path("."))
            notices = fetcher.fetch(days=3)

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].published_at, published_date)
        self.assertEqual(notices[0].procurement_method, "전자입찰")
        self.assertEqual(len(notices[0].attachments), 1)
        self.assertEqual(notices[0].attachments[0].file_type, "hwpx")


class NotificationTests(unittest.TestCase):
    def test_daily_email_sends_each_configured_slot_once(self):
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
            morning = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="daily",
                daily_slot="10:00",
                send=True,
                sender=lambda _recipient, payload: captured.append(payload.text),
                now=baseline,
            )
            evening = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="daily",
                daily_slot="17:00",
                send=True,
                sender=lambda _recipient, payload: captured.append(payload.text),
                now=baseline + timedelta(hours=7),
            )
            duplicate_evening = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="daily",
                daily_slot="17:00",
                send=True,
                sender=lambda _recipient, payload: captured.append(payload.text),
                now=baseline + timedelta(hours=7, minutes=5),
            )
            self.assertEqual(morning[0].sent, 1)
            self.assertEqual(evening[0].sent, 1)
            self.assertEqual(duplicate_evening[0].skipped, 1)
            self.assertEqual(len(captured), 2)
            self.assertIn("10:00", captured[0])
            self.assertIn("17:00", captured[1])
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
                    business_tier=TIER_1,
                    tier_reason="온실가스 검증 컨설팅",
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

    def test_immediate_only_sends_tier_1_and_digest_is_bordered_newsletter(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = connect(Path(tmp_dir) / "tracker.db")
            now = datetime(2026, 9, 18, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
            dispatch_notifications(connection, recipients=["alerts@example.com"], mode="immediate", now=now)
            notices = [
                Notice(
                    source_id="sample",
                    source_name="Sample",
                    external_id="tier-1",
                    title="Scope 3 산정 고도화 컨설팅",
                    url="https://example.com/tier-1",
                    relevance_score=8,
                    business_tier=TIER_1,
                    tier_reason="Scope 3 산정 컨설팅",
                ),
                Notice(
                    source_id="sample",
                    source_name="Sample",
                    external_id="tier-2",
                    title="온실가스 저감 설비 설치 지원",
                    url="https://example.com/tier-2",
                    relevance_score=6,
                    business_tier=TIER_2,
                    tier_reason="온실가스 설비 지원",
                ),
                Notice(
                    source_id="sample",
                    source_name="Sample",
                    external_id="tier-3",
                    title="탄소중립 포럼 영상 제작",
                    url="https://example.com/tier-3",
                    relevance_score=5,
                    business_tier=TIER_3,
                    tier_reason="행사·영상 사업",
                ),
                Notice(
                    source_id="sample_esg_tenders",
                    source_name="Sample only",
                    external_id="example-tier-1",
                    title="샘플 배출권거래제 컨설팅",
                    url="https://example.com/sample-tier-1",
                    relevance_score=7,
                    business_tier=TIER_1,
                ),
            ]
            for notice in notices:
                upsert_notice(connection, notice)
            later = (now + timedelta(minutes=1)).isoformat(timespec="seconds")
            connection.execute("UPDATE notices SET first_seen_at = ?, last_seen_at = ?", (later, later))
            connection.commit()

            immediate_payloads = []
            immediate = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="immediate",
                send=True,
                sender=lambda _recipient, payload: immediate_payloads.append(payload),
                now=now + timedelta(minutes=2),
            )
            self.assertEqual(immediate[0].sent, 1)
            self.assertEqual(len(immediate_payloads), 1)
            self.assertIn("Scope 3 산정 고도화 컨설팅", immediate_payloads[0].html)
            self.assertNotIn("온실가스 저감 설비 설치 지원", immediate_payloads[0].html)
            self.assertNotIn("샘플 배출권거래제 컨설팅", immediate_payloads[0].html)

            digest_payloads = []
            daily = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="daily",
                daily_slot="10:00",
                send=True,
                sender=lambda _recipient, payload: digest_payloads.append(payload),
                now=now + timedelta(minutes=3),
            )
            self.assertEqual(daily[0].sent, 1)
            newsletter = digest_payloads[0].html
            self.assertIn("INNERGEN CLIMATE INTELLIGENCE", newsletter)
            self.assertIn("오늘 신규 추가", newsletter)
            self.assertIn("Tier 1 · 이너젠 직접 컨설팅 검토", newsletter)
            self.assertIn("Tier 2 · 고객사 설비·금융지원 추천", newsletter)
            self.assertNotIn("Tier 3 · 참고 / 직접 컨설팅 비적합", newsletter)
            self.assertIn("border:1px solid #D1D5DB", newsletter)
            self.assertIn("온실가스 저감 설비 설치 지원", newsletter)
            self.assertNotIn("탄소중립 포럼 영상 제작", newsletter)
            self.assertNotIn("샘플 배출권거래제 컨설팅", newsletter)
            self.assertIn("오늘 신규 추가 · Tier 1", newsletter)
            self.assertIn("https://24josh4281.github.io/Consulting-RFP/", newsletter)
            weekly_payloads = []
            weekly = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="weekly",
                send=True,
                sender=lambda _recipient, payload: weekly_payloads.append(payload),
                now=now + timedelta(minutes=4),
            )
            self.assertEqual(weekly[0].sent, 1)
            self.assertIn("온실가스 저감 설비 설치 지원", weekly_payloads[0].html)
            self.assertNotIn("탄소중립 포럼 영상 제작", weekly_payloads[0].html)
            self.assertNotIn("Tier 3", weekly_payloads[0].text)
            connection.close()

    def test_daily_digest_features_new_tier_one_and_keeps_all_active_tier_one_two(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = connect(Path(tmp_dir) / "tracker.db")
            current = datetime(2026, 9, 23, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
            dispatch_notifications(connection, recipients=["alerts@example.com"], mode="immediate", now=current - timedelta(days=1))
            cases = [
                ("new-tier-1", "신규 Scope 3 산정 용역", TIER_1, current),
                ("new-tier-2", "신규 온실가스 설비 지원", TIER_2, current),
                ("new-tier-3", "신규 탄소중립 행사 용역", TIER_3, current),
                ("old-tier-1", "진행 중 배출권거래제 연구", TIER_1, current - timedelta(days=2)),
                ("old-tier-2", "진행 중 온실가스 설비 지원", TIER_2, current - timedelta(days=2)),
                ("old-tier-3", "오래된 기후 영상 제작", TIER_3, current - timedelta(days=2)),
            ]
            for external_id, title, tier, first_seen in cases:
                upsert_notice(
                    connection,
                    Notice(
                        source_id="sample",
                        source_name="Sample",
                        external_id=external_id,
                        title=title,
                        url=f"https://example.com/{external_id}",
                        relevance_score=6,
                        business_tier=tier,
                        tier_reason="검토용 분류",
                    ),
                )
                connection.execute(
                    "UPDATE notices SET first_seen_at = ? WHERE external_id = ?",
                    (first_seen.isoformat(timespec="seconds"), external_id),
                )
            connection.commit()

            captured = []
            result = dispatch_notifications(
                connection,
                recipients=["alerts@example.com"],
                mode="daily",
                daily_slot="10:00",
                send=True,
                sender=lambda _recipient, payload: captured.append(payload),
                now=current,
            )
            self.assertEqual(result[0].sent, 1)
            self.assertEqual(len(captured), 1)
            for _external_id, title, _tier, _first_seen in (cases[0], cases[1], cases[3], cases[4]):
                self.assertEqual(captured[0].html.count(title), 1)
            self.assertNotIn(cases[2][1], captured[0].html)
            self.assertNotIn(cases[5][1], captured[0].html)
            self.assertIn("오늘 신규 추가 · Tier 1", captured[0].text)
            self.assertIn("[오늘 신규 추가 · Tier 1] 1건", captured[0].text)
            self.assertIn("현재 접수 중 Tier 1", captured[0].text)
            self.assertIn("현재 접수 중 Tier 2", captured[0].text)
            self.assertIn("https://24josh4281.github.io/Consulting-RFP/", captured[0].text)
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
                    business_tier=TIER_1,
                    tier_reason="배출권거래제 검토 컨설팅",
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
