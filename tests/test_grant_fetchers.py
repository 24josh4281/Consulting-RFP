import argparse
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from rfp_tracker.briefing import build_briefing, is_notice_active
from rfp_tracker.cli import sync_command
from rfp_tracker.documents import build_public_workbench_payload
from rfp_tracker.grant_fetchers import (
    OfficialGrantFetcher,
    application_period,
    is_customer_grant_title,
    is_customer_portfolio_grant,
    public_attachments,
    parse_keco_rows,
    parse_kea_rows,
    parse_keiti_rows,
    parse_kicox_rows,
    parse_kosmes_rows,
)
from rfp_tracker.bizinfo_fetcher import (
    BizinfoGrantApiFetcher,
    bizinfo_application_window,
    parse_bizinfo_items,
)
from rfp_tracker.models import Notice
from rfp_tracker.render import render_workbench_dashboard
from rfp_tracker.storage import connect, list_notices, upsert_notice
from rfp_tracker.tiering import TIER_2, TIER_3, assess_innergen_tier


class OfficialGrantParsingTests(unittest.TestCase):
    def test_kosmes_application_window_and_closed_status(self):
        page = '''<table><tr onClick="javascript:goDetail(48)" style="cursor:pointer;">
        <td>8</td><td>2026년 중소기업 탄소중립 설비투자 지원(공급망 트랙) 참여기업 모집 공고</td>
        <td>2026년 2차</td><td>2026-04-13 09:00 ~ 2026-05-06 16:00</td>
        <td><span>접수마감</span></td></tr></table>'''
        rows = parse_kosmes_rows(page, "https://esg.kosmes.or.kr/esgplatform/bsnPuan/bsnPuanList.do")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_id"], "48")
        self.assertEqual(rows[0]["deadline_at"], "2026-05-06 16:00")
        self.assertEqual(rows[0]["start_at"], "2026-04-13 09:00")
        self.assertIn("bsnPuanId=48", rows[0]["url"])
        self.assertEqual(rows[0]["source_status"], "접수마감")

    def test_keco_table_filters_non_grant_and_preserves_published_date(self):
        page = '''<table><tr><td>20</td><td class="tit_new">
        <a href="javascript:;" onclick="location.href='./view.do?article_seq=99711&amp;cpage=1'">
        2026년도 배출권거래제 할당대상업체 탄소중립설비 지원사업 2차 공고</a></td>
        <td>담당자</td><td>첨부</td><td>2026-05-22</td></tr>
        <tr><td>19</td><td><a onclick="location.href='./view.do?article_seq=123'">일반 행사 공고</a></td>
        <td>담당자</td><td></td><td>2026-05-22</td></tr></table>'''
        rows = parse_keco_rows(page, "https://www.keco.or.kr/web/lay1/bbs/S1T17C108/A/18/list.do")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_id"], "99711")
        self.assertEqual(rows[0]["published_at"], "2026-05-22")
        self.assertTrue(rows[0]["url"].startswith("https://www.keco.or.kr/"))

    def test_kea_card_and_auction_board_variants(self):
        card = '''<a href="/etsg/sg/notice/view.do?seq=1" class="board_list_item notice">
        <span class="board_title">2026년 배출권거래제 감축설비 지원사업 공고</span>
        <div class="board_col board_col_date">2025.12.30</div></a>'''
        auction = '''<tr><td>4</td><td><a href="/etsa/ia/notice/view.do?seq=6">
        2026년도 탄소중립 설비투자 프로젝트 경매사업 공고(2차)</a></td>
        <td>관리자</td><td>2026.04.16</td></tr>'''
        self.assertEqual(parse_kea_rows(card, "https://min24.energy.or.kr/etsg/sg/notice/list.do")[0]["published_at"], "2025-12-30")
        self.assertEqual(parse_kea_rows(auction, "https://min24.energy.or.kr/etsa/ia/notice/list.do")[0]["external_id"], "6")

    def test_application_period_handles_korean_weekday_and_hour(self):
        start, end = application_period("신청기간 : 2026.04.16.(목). ~ 2026.5.15.(금). 16시까지")
        self.assertEqual(start, "2026-04-16 00:00")
        self.assertEqual(end, "2026-05-15 16:00")
        start, end = application_period("접수기간 2026. 5.22.(금) 13:00 ~ 2026. 6.23.(화) 16:00")
        self.assertEqual(start, "2026-05-22 13:00")
        self.assertEqual(end, "2026-06-23 16:00")
        self.assertEqual(application_period("공고일 2026.5.22. 신청방법: e나라도움"), ("", ""))

    def test_grant_title_gate_ignores_performers_and_procurement(self):
        self.assertTrue(is_customer_grant_title("2026년 배출권거래제 감축설비 지원사업 공고"))
        self.assertFalse(is_customer_grant_title("탄소중립 설비투자 지원사업 수행사 모집"))
        self.assertFalse(is_customer_grant_title("탄소중립 설비투자 지원사업 공기압축기 구매입찰"))
        self.assertFalse(is_customer_grant_title("탄소중립 설비투자 지원사업 공기압축기 구매입찰 공고"))
        self.assertEqual(
            assess_innergen_tier("2026년 배출권거래제 감축설비 지원사업 공고", category="grant_application").tier,
            TIER_2,
        )
        self.assertEqual(
            assess_innergen_tier("2026년 배출권거래제 감축설비 지원사업 공고", category="g2b_bid_api").tier,
            TIER_3,
        )

    def test_public_attachment_links_stay_on_official_host(self):
        detail = ('<a href="/download.do?file=1">공고문.pdf</a>'
                  '<a href="https://example.net/download.do?file=2">외부자료.pdf</a>')
        links = public_attachments(detail, "https://www.keco.or.kr/view.do?article_seq=1", "keco")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].file_type, "pdf")
        self.assertIn("www.keco.or.kr/download.do", links[0].url)

    def test_keiti_portfolio_call_and_kicox_closed_status(self):
        keiti = '''<li><div class="cate"><a href="/site/keiti/ex/board/View.do?cbIdx=277&amp;bcIdx=39923"
        onclick="doBbsContentFView('39923');return false;">
        <span class="date">2026-03-04</span>
        <span class="subject">2026년도 제2차 미래환경산업육성융자(온실가스배출저감설비자금) 지원사업 공고</span>
        </a></div></li>'''
        rows = parse_keiti_rows(keiti, "https://www.keiti.re.kr/site/keiti/ex/board/List.do?cbIdx=277")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_id"], "39923")
        self.assertIn("bcIdx=39923", rows[0]["url"])

        kicox = '''<tr><td class="num">9</td><td class="sbj"><a href="#"
        onclick="fn_view('PB_00000000000000079');"><span>마감</span>
        2026년 탄소중립 전환 선도프로젝트 융자지원 사업 공고</a></td>
        <td>공단관리자</td><td>2026-02-25</td></tr>'''
        rows = parse_kicox_rows(kicox, "https://www.kicox.or.kr/netzerofin/pbanc/pbancList.do")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_status"], "마감")
        self.assertIn("seq=PB_00000000000000079", rows[0]["url"])
        self.assertEqual(
            application_period("접수기간 : 2026-02-25 09:00 ~ 2026-04-10 18:00"),
            ("2026-02-25 09:00", "2026-04-10 18:00"),
        )

    def test_climate_grant_gate_excludes_event_and_pure_r_and_d(self):
        self.assertTrue(is_customer_portfolio_grant("2026년 2차 EU CBAM 대응 기업지원 컨설팅 공고"))
        self.assertTrue(is_customer_portfolio_grant("2026년 3차 온실가스 국제감축사업 투자지원사업 모집 공고"))
        self.assertFalse(is_customer_portfolio_grant("2026년 기후공시 대응 세미나 개최 공고"))
        self.assertFalse(is_customer_portfolio_grant("2026년 온실가스 기술개발 투자지원사업 공고"))
        self.assertEqual(
            assess_innergen_tier("2026년 2차 EU CBAM 대응 기업지원 컨설팅 공고", category="grant_application").tier,
            TIER_2,
        )
        self.assertEqual(
            assess_innergen_tier("2026년 온실가스 기술개발 설비지원사업 공고", category="grant_application").tier,
            TIER_3,
        )

    def test_bizinfo_documented_fields_are_parsed_without_description_republication(self):
        current = datetime(2026, 9, 23, 10, tzinfo=ZoneInfo("Asia/Seoul"))
        sample = {"jsonArray": {"item": [
            {"pblancId": "PBLN_1", "pblancNm": "2026년 EU CBAM 대응 기업지원 컨설팅 공고",
             "pblancUrl": "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_1",
             "creatPnttm": "2026-09-22 10:00:00", "reqstBeginEndDe": "20260922 ~ 20261001",
             "excInsttNm": "한국환경공단", "bsnsSumryCn": "복제하면 안 되는 원문"},
            {"seq": "PBLN_2", "title": "기후 행사 세미나 공고", "link": "https://www.bizinfo.go.kr/other",
             "reqstDt": "20260922 ~ 20261001"},
            {"seq": "PBLN_3", "title": "온실가스 설비지원사업 공고", "link": "https://evil.example/other",
             "reqstDt": "20260922 ~ 20261001"},
        ]}}
        source = {"id": "bizinfo_climate_grants", "name": "기업마당"}
        notices = parse_bizinfo_items(sample, source, 3, current)
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].deadline_at, "2026-10-01")
        self.assertEqual(notices[0].buyer, "한국환경공단")
        self.assertNotIn("복제하면", str(notices[0]))
        self.assertEqual(bizinfo_application_window("상시 모집"), ("", ""))
        self.assertEqual(bizinfo_application_window("20261001 ~ 20260922"), ("", ""))

    def test_bizinfo_key_is_required_and_endpoint_is_allowlisted(self):
        source = {"id": "bizinfo_climate_grants", "name": "기업마당", "endpoint": "https://evil.example/api"}
        with self.assertRaises(ValueError):
            BizinfoGrantApiFetcher(source, {}, {}, Path.cwd())
        source["endpoint"] = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"
        with patch.dict("os.environ", {"BIZINFO_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "전용 API 키"):
                BizinfoGrantApiFetcher(source, {}, {}, Path.cwd()).fetch(3)
        with patch.dict("os.environ", {"BIZINFO_API_KEY": "test-secret"}), \
                patch("rfp_tracker.bizinfo_fetcher.fetch_text", side_effect=OSError("url?crtfcKey=test-secret")):
            with self.assertRaises(RuntimeError) as failure:
                BizinfoGrantApiFetcher(source, {}, {}, Path.cwd()).fetch(3)
        self.assertNotIn("test-secret", str(failure.exception))

    def test_keiti_rejects_detail_links_outside_official_host(self):
        page = '''<a href="https://evil.example/View.do?bcIdx=39923">
        <span class="date">2026-09-23</span>
        <span class="subject">2026년 온실가스 저감설비 융자지원사업 공고</span></a>'''
        source = {
            "id": "keiti_ghg_financing_grants", "name": "한국환경산업기술원", "board": "keiti",
            "url": "https://www.keiti.re.kr/site/keiti/ex/board/List.do?cbIdx=277",
            "max_pages": 1,
        }
        with patch("rfp_tracker.grant_fetchers.fetch_text", return_value=page) as fetch:
            notices = OfficialGrantFetcher(source, {}, {}, Path.cwd()).fetch(3)
        self.assertEqual(notices, [])
        self.assertEqual(fetch.call_count, 1)


class GrantDashboardTests(unittest.TestCase):
    def test_unknown_or_explicitly_closed_grant_is_never_open(self):
        current = datetime(2026, 9, 23, 10, tzinfo=ZoneInfo("Asia/Seoul"))
        self.assertFalse(is_notice_active({"category": "grant_application", "deadline_at": "", "raw_json": "{}"}, current))
        self.assertFalse(is_notice_active({
            "category": "grant_application", "deadline_at": "2026-10-01 16:00",
            "raw_json": '{"application_status":"접수마감"}',
        }, current))
        self.assertFalse(is_notice_active({
            "category": "grant_application", "deadline_at": "2026-10-01 16:00",
            "raw_json": '{"application_status":"마감"}',
        }, current))
        self.assertFalse(is_notice_active({
            "category": "grant_application", "deadline_at": "2026-10-01 16:00",
            "raw_json": '{"application_start_at":"2026-09-24 09:00"}',
        }, current))
        self.assertTrue(is_notice_active({
            "category": "grant_application", "deadline_at": "2026-10-01 16:00", "raw_json": "{}",
        }, current))

    def test_public_payload_and_page_distinguish_grant_from_bid(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = connect(Path(tmp) / "test.db")
            grant = Notice(
                source_id="kosmes_carbon_grants", source_name="중진공 지원사업", external_id="48",
                title="2026년 중소기업 탄소중립 설비투자 지원사업 공고",
                url="https://esg.kosmes.or.kr/esgplatform/bsnPuan/bsnPuanView.do?bsnPuanId=48",
                deadline_at="2026-10-01 16:00", buyer="중소벤처기업진흥공단",
                category="grant_application", business_tier=TIER_2, relevance_score=8,
                raw={"application_status": "접수중"},
            )
            upsert_notice(db, grant)
            row = list_notices(db)[0]
            self.assertEqual(row["category"], "grant_application")
            payload = build_public_workbench_payload(db)
            self.assertEqual(payload["notices"][0]["notice_type"], "grant_application")
            self.assertNotIn("raw", payload["notices"][0])
            page = Path(tmp) / "index.html"
            render_workbench_dashboard(payload, page, public=True)
            html_text = page.read_text(encoding="utf-8")
            self.assertIn('id="notice-type"', html_text)
            self.assertIn('data-notice-type="grant_application"', html_text)
            self.assertIn("지원금 신청", html_text)
            self.assertIn("운영기관", html_text)
            self.assertNotIn("application_status", html_text)
            db.close()

    def test_briefing_respects_explicitly_closed_grant_even_with_future_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = connect(Path(tmp) / "test.db")
            upsert_notice(db, Notice(
                source_id="keco_ets_equipment_grants", source_name="한국환경공단", external_id="test-closed",
                title="2026년 배출권거래제 탄소중립설비 지원사업 공고",
                url="https://www.keco.or.kr/example", deadline_at="2026-10-01 16:00",
                category="grant_application", business_tier=TIER_2, relevance_score=8,
                raw={"application_status": "접수마감"},
            ))
            briefing = build_briefing(db, now=datetime(2026, 9, 23, 10, tzinfo=ZoneInfo("Asia/Seoul")))
            self.assertEqual(briefing["summary"]["tier_2"], 0)
            self.assertEqual(briefing["summary"]["eligible_notices"], 0)
            db.close()


class GrantSyncTests(unittest.TestCase):
    def test_grant_board_failure_does_not_stop_other_sources(self):
        db = connect(":memory:")
        config = {"global": {}, "sources": [
            {"id": "broken_grant", "type": "official_grant_board", "enabled": True},
            {"id": "other_board", "type": "generic_html", "enabled": True},
        ]}
        called: list[str] = []

        def fetcher_for(source, *_args):
            def fetch(*, days):
                called.append(source["id"])
                if source["id"] == "broken_grant":
                    raise OSError("board unavailable")
                return []
            return SimpleNamespace(fetch=fetch)

        args = argparse.Namespace(config="unused", keywords="unused", db=":memory:", days=3, source_type=None)
        with patch("rfp_tracker.cli.read_json", side_effect=[config, {}]), \
                patch("rfp_tracker.cli.build_fetcher", side_effect=fetcher_for), \
                patch("rfp_tracker.cli.connect", return_value=db):
            self.assertEqual(sync_command(args), 0)
        self.assertEqual(called, ["broken_grant", "other_board"])
        status, message = db.execute("select status,message from sync_runs order by id desc limit 1").fetchone()
        self.assertEqual(status, "partial")
        self.assertIn("broken_grant", message)
        db.close()

    def test_bizinfo_failure_does_not_stop_other_sources(self):
        db = connect(":memory:")
        config = {"global": {}, "sources": [
            {"id": "bizinfo_climate_grants", "type": "bizinfo_grant_api", "enabled": True},
            {"id": "other_board", "type": "generic_html", "enabled": True},
        ]}
        called: list[str] = []

        def fetcher_for(source, *_args):
            def fetch(*, days):
                called.append(source["id"])
                if source["type"] == "bizinfo_grant_api":
                    raise RuntimeError("key-safe failure")
                return []
            return SimpleNamespace(fetch=fetch)

        args = argparse.Namespace(config="unused", keywords="unused", db=":memory:", days=3, source_type=None)
        with patch("rfp_tracker.cli.read_json", side_effect=[config, {}]), \
                patch("rfp_tracker.cli.build_fetcher", side_effect=fetcher_for), \
                patch("rfp_tracker.cli.connect", return_value=db):
            self.assertEqual(sync_command(args), 0)
        self.assertEqual(called, ["bizinfo_climate_grants", "other_board"])
        status, message = db.execute("select status,message from sync_runs order by id desc limit 1").fetchone()
        self.assertEqual(status, "partial")
        self.assertIn("bizinfo_climate_grants", message)
        db.close()


if __name__ == "__main__":
    unittest.main()
