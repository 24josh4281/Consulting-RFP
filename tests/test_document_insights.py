from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
import zipfile

from rfp_tracker.documents import (
    backfill_g2b_attachments,
    build_public_workbench_payload,
    build_workbench_payload,
    extract_amount_evidence,
    extract_document_insights,
    extract_hwpx_paragraphs,
    summarize_hwpx_task,
)
from rfp_tracker.fetchers import extract_g2b_spec_attachments
from rfp_tracker.models import Attachment, Notice
from rfp_tracker.render import render_workbench_dashboard
from rfp_tracker.storage import (
    connect,
    list_document_insights,
    list_notices,
    upsert_bid_fit_review,
    upsert_document_insight,
    upsert_notice,
)


class DocumentInsightTests(unittest.TestCase):
    def test_g2b_named_attachment_uses_filename_when_download_url_has_no_extension(self):
        attachments = extract_g2b_spec_attachments(
            {
                "ntceSpecDocUrl1": "https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?fileSeq=7",
                "ntceSpecFileNm1": "제안요청서_최종.hwpx",
            }
        )

        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].label, "제안요청서_최종.hwpx")
        self.assertEqual(attachments[0].file_type, "hwpx")

    def test_g2b_raw_backfill_is_idempotent_and_hides_stale_blank_gap(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = connect(Path(tmp_dir) / "tracker.db")
            upsert_notice(
                connection,
                Notice(
                    source_id="g2b_service_bids",
                    source_name="나라장터",
                    external_id="g2b-1",
                    title="온실가스 Scope 3 산정 고도화 컨설팅",
                    url="https://www.g2b.go.kr/pn/example-notice",
                    business_tier="tier_1",
                    raw={
                        "ntceSpecDocUrl1": "https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?fileSeq=1",
                        "ntceSpecFileNm1": "제안요청서.hwpx",
                    },
                ),
            )
            notice = list_notices(connection)[0]
            upsert_document_insight(
                connection,
                notice_id=int(notice["id"]),
                attachment_id=None,
                document_url="",
                document_label="",
                source_url=str(notice["url"]),
                extraction_status="missing_document_url",
            )

            first = backfill_g2b_attachments(connection)
            second = backfill_g2b_attachments(connection)
            attachments = connection.execute(
                "SELECT label, file_type FROM attachments WHERE notice_id = ?",
                (notice["id"],),
            ).fetchall()
            payload = build_workbench_payload(connection)

            self.assertEqual(first["added"], 1)
            self.assertEqual(second["added"], 0)
            self.assertEqual(len(attachments), 1)
            self.assertEqual(attachments[0]["label"], "제안요청서.hwpx")
            self.assertEqual(attachments[0]["file_type"], "hwpx")
            self.assertEqual(payload["notices"][0]["document_status"], "not_attempted")
            self.assertNotIn(
                "missing_document_url",
                [item["extraction_status"] for item in payload["notices"][0]["insights"]],
            )
            connection.close()

    def test_fit_review_and_public_projection_keep_source_and_internal_data_separate(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            connection = connect(root / "tracker.db")
            official = Notice(
                source_id="official_board",
                source_name="Official Board",
                external_id="official-1",
                title="온실가스 Scope 3 산정 컨설팅",
                url="https://official.example/notice-1",
                budget="120000000",
                business_tier="tier_1",
                review_status="interesting",
                review_note="INTERNAL-REVIEW-NOTE",
                attachments=[
                    Attachment(
                        label="제안요청서.hwpx",
                        url="https://official.example/rfp-1.hwpx",
                        file_type="hwpx",
                    )
                ],
            )
            sample = Notice(
                source_id="sample_esg_tenders",
                source_name="Sample",
                external_id="sample-1",
                title="샘플 온실가스 컨설팅",
                url="https://example.com/sample-1",
                business_tier="tier_1",
            )
            upsert_notice(connection, official)
            upsert_notice(connection, sample)
            official_row = next(row for row in list_notices(connection) if row["external_id"] == "official-1")
            attachment = connection.execute(
                "SELECT id, url FROM attachments WHERE notice_id = ?",
                (official_row["id"],),
            ).fetchone()
            before = dict(official_row)
            upsert_document_insight(
                connection,
                notice_id=int(official_row["id"]),
                attachment_id=int(attachment["id"]),
                document_url=str(attachment["url"]),
                document_label="제안요청서.hwpx",
                source_url=str(official_row["url"]),
                extraction_status="extracted",
                task_summary="Scope 3 산정 범위와 제출요건을 확인한다.",
                amount_value_krw=120_000_000,
                amount_text="120,000,000원",
                amount_basis="예산액",
            )
            self.assertTrue(
                upsert_bid_fit_review(
                    connection,
                    notice_id=int(official_row["id"]),
                    consulting_fit="high",
                    qualification_requirements="온실가스 산정 실적",
                    proposed_team="PM 1명, GHG 전문가 2명",
                    bid_decision="conditional",
                    key_risks="내부-위험",
                    decision_note="INTERNAL-BID-NOTE",
                )
            )
            after = next(row for row in list_notices(connection) if row["external_id"] == "official-1")
            internal = build_workbench_payload(connection)
            public = build_public_workbench_payload(connection)
            internal_path = root / "internal.html"
            public_path = root / "public.html"
            render_workbench_dashboard(internal, internal_path)
            render_workbench_dashboard(public, public_path, public=True)
            internal_rendered = internal_path.read_text(encoding="utf-8")
            rendered = public_path.read_text(encoding="utf-8")

            self.assertEqual(after["title"], before["title"])
            self.assertEqual(after["raw_json"], before["raw_json"])
            internal_official = next(item for item in internal["notices"] if item["external_id"] == "official-1")
            self.assertEqual(internal_official["fit_review"]["consulting_fit"], "high")
            self.assertEqual(internal_official["priority_status"], "official_tier_1")
            self.assertEqual(len(public["notices"]), 1)
            self.assertNotIn("source_id", public["notices"][0])
            self.assertNotIn("fit_review", public["notices"][0])
            self.assertNotIn("review_note", public["notices"][0])
            self.assertIn("Tier 1 우선 검토", internal_rendered)
            self.assertIn("INTERNAL-BID-NOTE", internal_rendered)
            self.assertNotIn("INTERNAL-REVIEW-NOTE", rendered)
            self.assertNotIn("INTERNAL-BID-NOTE", rendered)
            self.assertNotIn("내부-위험", rendered)
            self.assertNotIn("example.com", rendered)
            connection.close()
    def test_hwpx_parser_reads_paragraphs_and_amount_basis(self):
        payload = BytesIO()
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hp:section xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            '<hp:p><hp:run><hp:t>사업범위</hp:t></hp:run></hp:p>'
            '<hp:p><hp:run><hp:t>배출량 산정과 검증 기능을 개선한다.</hp:t></hp:run></hp:p>'
            '<hp:p><hp:run><hp:t>예 산 액:500,000,000원(부가가치세 포함)</hp:t></hp:run></hp:p>'
            '</hp:section>'
        )
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("Contents/section0.xml", xml)

        paragraphs = extract_hwpx_paragraphs(payload.getvalue())
        amount = extract_amount_evidence(paragraphs)

        self.assertIn("배출량 산정", paragraphs[1])
        self.assertEqual(amount["amount_basis"], "예산액")
        self.assertEqual(amount["amount_value_krw"], 500_000_000)
        self.assertEqual(amount["amount_text"], "500,000,000원")

    def test_known_gir_task_summary_is_concise_and_source_based(self):
        summary = summarize_hwpx_task(
            ["사업범위", "배출량 산정과 배출권 거래 기능을 개선한다."],
            "2026년 목표관리제·배출권거래제 통합정보시스템 기능개선",
        )
        self.assertIn("NGMS", summary)
        self.assertIn("배출량 산정", summary)
        self.assertLessEqual(len(summary), 220)

    def test_sample_attachment_is_recorded_without_network_download(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = connect(Path(tmp_dir) / "tracker.db")
            upsert_notice(
                connection,
                Notice(
                    source_id="sample_esg_tenders",
                    source_name="Sample",
                    external_id="sample-1",
                    title="온실가스 산정 컨설팅",
                    url="https://example.com/notices/sample-1",
                    attachments=[
                        Attachment(
                            label="제안요청서",
                            url="https://example.com/files/sample.hwpx",
                            file_type="hwpx",
                        )
                    ],
                ),
            )

            outcomes = extract_document_insights(
                connection,
                cache_dir=Path(tmp_dir) / "cache",
            )
            insights = list_document_insights(connection)

            self.assertEqual(outcomes[0]["extraction_status"], "sample_source")
            self.assertEqual(insights[0]["extraction_status"], "sample_source")
            self.assertFalse((Path(tmp_dir) / "cache").exists())
            connection.close()

    def test_insight_upsert_preserves_notice_and_attachment_source_records(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = connect(Path(tmp_dir) / "tracker.db")
            upsert_notice(
                connection,
                Notice(
                    source_id="official",
                    source_name="Official",
                    external_id="notice-1",
                    title="배출권거래제 과업",
                    url="https://official.example/notice",
                    budget="500000000",
                    attachments=[
                        Attachment(
                            label="제안요청서",
                            url="https://official.example/rfp.hwpx",
                            file_type="hwpx",
                        )
                    ],
                ),
            )
            before = list_notices(connection)[0]
            attachment = connection.execute("SELECT id FROM attachments").fetchone()

            upsert_document_insight(
                connection,
                notice_id=int(before["id"]),
                attachment_id=int(attachment["id"]),
                document_url="https://official.example/rfp.hwpx",
                document_label="제안요청서",
                source_url="https://official.example/notice",
                extraction_status="extracted",
                task_summary="공개 원문 요약",
                amount_value_krw=500_000_000,
                amount_text="500,000,000원",
                amount_basis="예산액",
                evidence_excerpt="예산액: 500,000,000원",
            )

            after = list_notices(connection)[0]
            insight = list_document_insights(connection)[0]
            self.assertEqual(after["title"], before["title"])
            self.assertEqual(after["budget"], before["budget"])
            self.assertEqual(after["attachments_json"], before["attachments_json"])
            self.assertEqual(insight["task_summary"], "공개 원문 요약")
            connection.close()

    def test_workbench_payload_and_html_keep_one_notice_row(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            connection = connect(root / "tracker.db")
            upsert_notice(
                connection,
                Notice(
                    source_id="official",
                    source_name="Official",
                    external_id="notice-1",
                    title="온실가스 Scope 3 산정 컨설팅",
                    url="https://official.example/notice",
                    business_tier="tier_1",
                    tier_reason="Scope 3 산정 컨설팅",
                    attachments=[
                        Attachment(
                            label="제안요청서",
                            url="https://official.example/rfp.hwpx",
                            file_type="hwpx",
                        ),
                        Attachment(
                            label="입찰공고문",
                            url="https://official.example/notice.hwpx",
                            file_type="hwpx",
                        ),
                    ],
                ),
            )
            notice_id = int(list_notices(connection)[0]["id"])
            for attachment in connection.execute("SELECT id, url, label FROM attachments").fetchall():
                upsert_document_insight(
                    connection,
                    notice_id=notice_id,
                    attachment_id=int(attachment["id"]),
                    document_url=str(attachment["url"]),
                    document_label=str(attachment["label"]),
                    source_url="https://official.example/notice",
                    extraction_status="extracted",
                    task_summary="Scope 3 산정 범위와 제출요건을 확인한다.",
                    amount_value_krw=80_000_000,
                    amount_text="80,000,000원",
                    amount_basis="예산액",
                    evidence_excerpt="예산액: 80,000,000원",
                )

            payload = build_workbench_payload(connection)
            out_path = root / "workbench.html"
            render_workbench_dashboard(payload, out_path)
            rendered = out_path.read_text(encoding="utf-8")

            self.assertEqual(len(payload["notices"]), 1)
            self.assertEqual(payload["summary"]["extracted_documents"], 2)
            self.assertIn("data-tier=", rendered)
            self.assertIn("Scope 3 산정 범위", rendered)
            connection.close()


if __name__ == "__main__":
    unittest.main()
