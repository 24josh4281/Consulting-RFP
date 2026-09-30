from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from rfp_tracker.keiti_bid_fetcher import KeitiBidFetcher, parse_keiti_bid_rows


BASE = "https://www.keiti.re.kr/site/keiti/ex/board/List.do?cbIdx=277"


def card(category: str, number: str, title: str, day: str = "2026-09-30") -> str:
    return (f'<a href="/site/keiti/ex/board/View.do?cbIdx=277&amp;bcIdx={number}">'
            f'<span class="cateName">{category}</span><span class="date">{day}</span>'
            f'<span class="subject">{title}</span></a>')


class KeitiBidTests(TestCase):
    def test_parser_keeps_only_new_bid_notice(self):
        listing = (card("입찰", "1", "온실가스 배출량 산정 용역 입찰공고")
                   + card("입찰", "2", "[기술평가결과] 온실가스 배출량 산정 용역")
                   + card("공지", "3", "탄소중립 설비 지원사업 공고"))
        rows = parse_keiti_bid_rows(listing)
        self.assertEqual([row["external_id"] for row in rows], ["1"])
        self.assertEqual(rows[0]["url"], "https://www.keiti.re.kr/site/keiti/ex/board/View.do?cbIdx=277&bcIdx=1")

    def test_skips_result_only_page_and_reads_next_page(self):
        source = {"id": "keiti_bid_notices", "name": "KEITI 입찰", "type": "keiti_bid_board",
                  "url": BASE, "max_pages": 2, "max_detail_pages": 8, "detail_delay_seconds": 0.1}
        keywords = {"min_relevance_score": 1, "keyword_groups": {"ghg": ["온실가스"]},
                    "exclude_terms": [], "work_terms": ["산정", "용역"]}
        listing_one = card("입찰", "2", "[기술평가결과] 온실가스 배출량 산정 용역")
        listing_two = card("입찰", "1", "온실가스 배출량 산정 용역 입찰공고")

        def response(url, *_args):
            if "pageIndex=1" in url:
                return listing_one
            if "pageIndex=2" in url:
                return listing_two
            return '<a href="/common/board/Download.do?fileNo=1">제안요청서.pdf</a>'

        with patch("rfp_tracker.keiti_bid_fetcher.fetch_text", side_effect=response), patch("rfp_tracker.keiti_bid_fetcher.time.sleep"):
            notices = KeitiBidFetcher(source, keywords, {}, Path(".")).fetch(days=2)
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].external_id, "1")
        self.assertEqual(notices[0].deadline_at, "")
        self.assertEqual(len(notices[0].attachments), 1)
