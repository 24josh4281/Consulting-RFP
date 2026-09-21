from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from unittest import mock
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "scripts" / "extract_climate_procurement_history.py"
SPEC = importlib.util.spec_from_file_location("climate_procurement_history", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ClimateProcurementHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.keyword_config = MODULE.read_json(ROOT_DIR / "configs" / "keywords.json")

    def test_month_windows_split_rolling_five_year_period_without_gaps(self) -> None:
        windows = MODULE.month_windows(date(2021, 9, 21), date(2026, 9, 21))
        self.assertEqual(len(windows), 61)
        self.assertEqual(windows[0].api_start, "202109210000")
        self.assertEqual(windows[0].api_end, "202109302359")
        self.assertEqual(windows[-1].api_start, "202609010000")
        self.assertEqual(windows[-1].api_end, "202609212359")
        for previous, current in zip(windows, windows[1:]):
            self.assertEqual(previous.end.date().fromordinal(previous.end.date().toordinal() + 1), current.start.date())

    def test_specific_ghg_title_is_core(self) -> None:
        result = MODULE.classify_title(
            "온실가스 배출권거래제 명세서 및 배출량산정계획서 컨설팅 용역",
            self.keyword_config,
        )
        self.assertEqual(result["relevance_status"], "핵심")
        self.assertIn("온실가스", result["categories"])
        self.assertIn("배출권거래제", result["categories"])

    def test_ambiguous_carbon_material_title_requires_review(self) -> None:
        result = MODULE.classify_title(
            "탄소 소재 시험분석 장비 유지보수",
            self.keyword_config,
        )
        self.assertEqual(result["relevance_status"], "검토필요")

    def test_latin_ets_requires_standalone_token(self) -> None:
        result = MODULE.classify_title("PETS 시스템 유지관리", self.keyword_config)
        self.assertEqual(result["categories"], [])
        result = MODULE.classify_title("K-ETS 대응 컨설팅", self.keyword_config)
        self.assertIn("배출권거래제", result["categories"])

    def test_cache_key_never_depends_on_service_key_value(self) -> None:
        params_a = {"serviceKey": "secret-a", "pageNo": "1", "bidNtceNm": "기후"}
        params_b = {"serviceKey": "secret-b", "pageNo": "1", "bidNtceNm": "기후"}
        self.assertEqual(
            MODULE.ApiCache.query_key(MODULE.BID_PUBLIC_ENDPOINT, params_a),
            MODULE.ApiCache.query_key(MODULE.BID_PUBLIC_ENDPOINT, params_b),
        )

    def test_normalize_items_accepts_single_or_list_response(self) -> None:
        self.assertEqual(MODULE.normalize_items({"items": {"item": {"id": 1}}}), [{"id": 1}])
        self.assertEqual(MODULE.normalize_items({"items": {"id": 1}}), [{"id": 1}])
        self.assertEqual(
            MODULE.normalize_items({"items": {"item": [{"id": 1}, {"id": 2}]}}),
            [{"id": 1}, {"id": 2}],
        )

    def test_amount_conversion_distinguishes_zero_from_missing(self) -> None:
        self.assertEqual(MODULE.int_or_blank("0"), 0)
        self.assertEqual(MODULE.int_or_blank("1,234"), 1234)
        self.assertEqual(MODULE.int_or_blank(""), "")
        self.assertEqual(MODULE.int_or_blank(None), "")

    def test_unregistered_service_key_error_is_parsed_without_secret(self) -> None:
        raw = (
            '{"OpenAPI_ServiceResponse":{"cmmMsgHeader":'
            '{"errMsg":"SERVICE_KEY_IS_NOT_REGISTERED_ERROR",'
            '"returnAuthMsg":"등록되지 않은 서비스키","returnReasonCode":"30"}}}'
        )
        code, message = MODULE.parse_error_payload(raw)
        self.assertEqual(code, "SERVICE_KEY_IS_NOT_REGISTERED_ERROR")
        self.assertEqual(message, "등록되지 않은 서비스키")

    def test_winner_list_parser_requires_exactly_eight_fields(self) -> None:
        parsed = MODULE.parse_caret_list(
            (
                "[1^주식회사 기후^123-45-67890^홍길동^1000000^88.125^7^202501021030],"
                " [2^탄소 주식회사^222-33-44444^김대표^900000^79.5^7^202501021030]"
            ),
            MODULE.BIDWINNER_LIST_FIELDS,
        )
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["parse_status"], "정상")
        self.assertEqual(parsed[0]["winner_company"], "주식회사 기후")
        self.assertEqual(parsed[1]["award_amount_krw"], "900000")
        self.assertEqual(
            parsed[0]["raw_entry"],
            "[1^주식회사 기후^123-45-67890^홍길동^1000000^88.125^7^202501021030]",
        )

        malformed = MODULE.parse_caret_list(
            "[1^업체^123^대표^1000^88.1^2]",
            MODULE.BIDWINNER_LIST_FIELDS,
        )
        self.assertIn("필드수불일치", malformed[0]["parse_status"])
        self.assertEqual(malformed[0]["winner_company"], "")

    def test_contract_list_parser_preserves_dash_as_missing(self) -> None:
        parsed = MODULE.parse_caret_list(
            "[1^C-1^계약명^계약기관^수요기관^수의계약^-^20250103]",
            MODULE.CONTRACT_LIST_FIELDS,
        )
        self.assertEqual(parsed[0]["parse_status"], "정상")
        self.assertEqual(parsed[0]["contract_amount_krw"], "")
        self.assertEqual(MODULE.int_or_blank(parsed[0]["contract_amount_krw"]), "")

    def test_technical_request_uses_technical_budget_fields_only(self) -> None:
        endpoint, operation = MODULE._request_endpoint("기술용역")
        self.assertEqual(endpoint, MODULE.PROCUREMENT_REQUEST_TECH_ENDPOINT)
        row = MODULE._request_output_row(
            request_no="REQ-1",
            service_type="기술용역",
            operation=operation,
            status="조회완료",
            item={
                "prcrmntReqNm": "기술 요청",
                "totSrvceBdgtAmt": "1,000",
                "thtmBdgtAmt": "400",
                "contrctAmt": "999999",
            },
        )
        self.assertEqual(row["total_service_budget_amount_krw"], 1000)
        self.assertEqual(row["current_budget_amount_krw"], 400)
        self.assertEqual(row["budget_amount_krw"], "")
        self.assertNotIn("contrctAmt", row)

    def test_general_request_uses_budget_and_representative_amount(self) -> None:
        _, operation = MODULE._request_endpoint("일반용역")
        row = MODULE._request_output_row(
            request_no="REQ-2",
            service_type="일반용역",
            operation=operation,
            status="조회완료",
            item={"bdgtAmt": "0", "rprsntAmt": "2,500", "contrctAmt": "999"},
        )
        self.assertEqual(row["budget_amount_krw"], 0)
        self.assertEqual(row["representative_amount_krw"], 2500)
        self.assertEqual(row["total_service_budget_amount_krw"], "")

    def test_multiple_awards_and_contracts_are_not_summed_into_notice(self) -> None:
        rows = [
            {
                "record_id": "N-000",
                "winner_count": "",
                "participant_count": "",
                "winner_company": "",
                "winner_business_no": "",
                "award_amount_krw": "",
                "award_rate_pct": "",
                "contract_count": "",
                "contract_amount_krw": "",
                "contract_date": "",
                "procurement_request_name": "",
                "procurement_request_budget_amount_krw": "",
                "procurement_request_representative_amount_krw": "",
                "procurement_request_total_service_budget_amount_krw": "",
                "procurement_request_current_budget_amount_krw": "",
                "procurement_request_order_agency": "",
                "procurement_request_input_date": "",
            }
        ]
        winners = [
            {"participant_count": 4, "winner_company": "A", "winner_business_no": "1", "award_amount_krw": 100, "award_rate_pct": 80.0},
            {"participant_count": 4, "winner_company": "B", "winner_business_no": "2", "award_amount_krw": 200, "award_rate_pct": 81.0},
        ]
        contracts = [
            {"contract_amount_krw": 100, "contract_date": "20250101"},
            {"contract_amount_krw": 200, "contract_date": "20250102"},
        ]
        outcome = MODULE.EnrichmentOutcome(
            awards=[],
            contracts=[],
            procurement_requests=[],
            summaries={
                "N-000": {
                    "contract_lookup_status": "조회완료—정확한 차수 일치",
                    "exact_match": True,
                    "winners": winners,
                    "winner_parse_issue": False,
                    "contracts": contracts,
                    "contract_parse_issue": False,
                    "requests": {},
                }
            },
            contract_complete=True,
            procurement_request_complete=True,
            contract_lookups=1,
            contract_live_requests=1,
            procurement_request_lookups=0,
            procurement_request_live_requests=0,
            warnings=[],
        )
        MODULE.apply_contract_enrichment(rows, outcome)
        self.assertEqual(rows[0]["winner_count"], 2)
        self.assertEqual(rows[0]["award_amount_krw"], "")
        self.assertEqual(rows[0]["winner_company"], "")
        self.assertIn("복수 2건", rows[0]["award_data_status"])
        self.assertEqual(rows[0]["contract_count"], 2)
        self.assertEqual(rows[0]["contract_amount_krw"], "")
        self.assertIn("합산", rows[0]["contract_data_status"])

    def test_contract_enrichment_joins_only_exact_notice_order(self) -> None:
        class FakeClient:
            live_requests = 0

            @staticmethod
            def is_cached(endpoint, params):
                return True

            @staticmethod
            def get(endpoint, params, **kwargs):
                if endpoint == MODULE.CONTRACT_PROCESS_ENDPOINT:
                    return MODULE.ApiResult(
                        True,
                        "00",
                        "정상",
                        {
                            "items": {
                                "item": [
                                    {
                                        "bidNtceNo": "N",
                                        "bidNtceOrd": "00",
                                        "prcrmntReqNo": "REQ-1",
                                        "bidwinrInfoList": "[1^기후기업^123^대표^1000^88.1^4^202501021000]",
                                        "cntrctInfoList": "[1^C-1^계약명^계약기관^수요기관^일반경쟁^900^20250103]",
                                    },
                                    {
                                        "bidNtceNo": "N",
                                        "bidNtceOrd": "002",
                                        "bidwinrInfoList": "[1^미연결기업^999^대표^500^77.0^2^202501021000]",
                                        "cntrctInfoList": "",
                                    },
                                ]
                            }
                        },
                        "{}",
                        cached=True,
                    )
                return MODULE.ApiResult(
                    True,
                    "00",
                    "정상",
                    {
                        "items": {
                            "item": {
                                "prcrmntReqNo": "REQ-1",
                                "prcrmntReqNm": "기후 요청",
                                "bdgtAmt": "1200",
                                "rprsntAmt": "1100",
                                "orderInsttNm": "조달기관",
                                "inptDt": "20241201",
                            }
                        }
                    },
                    "{}",
                    cached=True,
                )

        rows = []
        for order in ("000", "001"):
            rows.append(
                {
                    "record_id": f"N-{order}",
                    "bid_notice_no": "N",
                    "bid_notice_order": order,
                    "notice_year": 2025,
                    "relevance_status": "핵심",
                    "opening_date": "202501021000",
                    "notice_date": "2025-01-01",
                    "service_type": "일반용역",
                    "winner_count": "",
                    "participant_count": "",
                    "winner_company": "",
                    "winner_business_no": "",
                    "award_amount_krw": "",
                    "award_rate_pct": "",
                    "contract_count": "",
                    "contract_amount_krw": "",
                    "contract_date": "",
                    "procurement_request_name": "",
                    "procurement_request_budget_amount_krw": "",
                    "procurement_request_representative_amount_krw": "",
                    "procurement_request_total_service_budget_amount_krw": "",
                    "procurement_request_current_budget_amount_krw": "",
                    "procurement_request_order_agency": "",
                    "procurement_request_input_date": "",
                }
            )
        outcome = MODULE.collect_contract_enrichment(
            FakeClient(),
            rows,
            max_contract_live_requests=1,
            max_procurement_request_live_requests=1,
        )
        MODULE.apply_contract_enrichment(rows, outcome)
        self.assertEqual(len(outcome.awards), 2)
        linked_award = next(
            award for award in outcome.awards if award["exact_order_match_yn"] == "Y"
        )
        orphan_award = next(
            award for award in outcome.awards if award["exact_order_match_yn"] == "N"
        )
        self.assertEqual(linked_award["record_id"], "N-000")
        self.assertEqual(linked_award["bid_notice_order"], "00")
        self.assertEqual(orphan_award["record_id"], "")
        self.assertIn("감사추적용", orphan_award["link_status"])
        self.assertTrue(any("미연결" in warning for warning in outcome.warnings))
        self.assertEqual(rows[0]["winner_company"], "기후기업")
        self.assertEqual(rows[0]["award_amount_krw"], 1000)
        self.assertEqual(rows[0]["contract_amount_krw"], 900)
        self.assertEqual(rows[0]["procurement_request_no"], "REQ-1")
        self.assertEqual(rows[0]["procurement_request_budget_amount_krw"], 1200)
        self.assertIn("정확한 차수 응답 없음", rows[1]["award_data_status"])
        self.assertEqual(rows[1]["winner_count"], "")
        self.assertEqual(rows[1]["contract_count"], "")

    def test_contract_service_cap_includes_prior_probe_calls(self) -> None:
        class ProbeCountedClient:
            live_requests = 1
            live_requests_by_endpoint = {MODULE.CONTRACT_PROCESS_ENDPOINT: 1}

            @staticmethod
            def is_cached(endpoint, params):
                return False

            @staticmethod
            def get(endpoint, params, **kwargs):
                raise AssertionError("서비스별 상한 이후에는 신규 호출하면 안 됩니다.")

        rows = [
            {
                "record_id": "N-000",
                "bid_notice_no": "N",
                "bid_notice_order": "000",
                "notice_year": 2025,
                "relevance_status": "핵심",
                "opening_date": "202501021000",
                "notice_date": "2025-01-01",
                "service_type": "일반용역",
            }
        ]
        outcome = MODULE.collect_contract_enrichment(
            ProbeCountedClient(),
            rows,
            max_contract_live_requests=1,
            max_procurement_request_live_requests=1,
        )
        self.assertFalse(outcome.contract_complete)
        self.assertFalse(outcome.procurement_request_complete)
        self.assertEqual(outcome.contract_lookups, 0)
        self.assertIn(
            "재실행 필요",
            outcome.summaries["N-000"]["contract_lookup_status"],
        )

    def test_year_balanced_priority_starts_with_one_notice_per_year(self) -> None:
        rows = []
        for year in (2026, 2025, 2024):
            for suffix in ("A", "B"):
                rows.append(
                    {
                        "bid_notice_no": f"{year}-{suffix}",
                        "notice_year": year,
                        "relevance_status": "핵심",
                        "opening_date": f"{year}01010000",
                        "notice_date": f"{year}-01-01",
                    }
                )
        ordered = MODULE.prioritized_bid_notice_numbers(rows)
        self.assertEqual({value[:4] for value in ordered[:3]}, {"2026", "2025", "2024"})

    def test_retry_never_exceeds_endpoint_or_global_live_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = MODULE.ApiCache(Path(temp_dir) / "cache.db")
            client = MODULE.G2BClient(
                "secret",
                cache,
                delay_seconds=0,
                max_live_requests=10,
            )
            client._request = mock.Mock(
                return_value=MODULE.ApiResult(False, "23", "retry", {}, "")
            )
            with mock.patch.object(MODULE.time, "sleep", return_value=None):
                with self.assertRaises(MODULE.RequestBudgetExceeded):
                    client.get(
                        "https://example.test/endpoint",
                        {"pageNo": "1"},
                        use_cache=False,
                        live_request_budget=2,
                    )
            self.assertEqual(client.live_requests, 2)
            self.assertEqual(
                client.live_requests_by_endpoint["https://example.test/endpoint"], 2
            )
            self.assertEqual(client._request.call_count, 2)
            cache.close()

    def test_daily_hard_cap_persists_and_is_shared_by_request_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache.db"
            cache = MODULE.ApiCache(cache_path)
            client = MODULE.G2BClient(
                "secret",
                cache,
                delay_seconds=0,
                max_live_requests=10,
                daily_group_caps={MODULE.PROCUREMENT_REQUEST_SERVICE_GROUP: 1},
            )
            client._request = mock.Mock(
                return_value=MODULE.ApiResult(
                    True, "00", "정상", {"items": []}, "{}"
                )
            )
            client.get(
                MODULE.PROCUREMENT_REQUEST_ENDPOINT,
                {"prcrmntReqNo": "R1"},
                use_cache=False,
            )
            with self.assertRaises(MODULE.DailyRequestBudgetExceeded):
                client.get(
                    MODULE.PROCUREMENT_REQUEST_TECH_ENDPOINT,
                    {"prcrmntReqNo": "R2"},
                    use_cache=False,
                )
            self.assertEqual(client._request.call_count, 1)
            self.assertEqual(
                cache.daily_attempts(MODULE.PROCUREMENT_REQUEST_SERVICE_GROUP), 1
            )
            cache.close()

            reopened = MODULE.ApiCache(cache_path)
            self.assertEqual(
                reopened.daily_attempts(MODULE.PROCUREMENT_REQUEST_SERVICE_GROUP), 1
            )
            reopened.close()

    def test_contract_quota_error_stops_before_next_notice(self) -> None:
        class QuotaClient:
            live_requests = 0
            live_requests_by_endpoint = {}
            calls = 0

            @staticmethod
            def is_cached(endpoint, params):
                return False

            @classmethod
            def get(cls, endpoint, params, **kwargs):
                cls.calls += 1
                return MODULE.ApiResult(
                    False,
                    "22",
                    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR",
                    {},
                    "",
                )

        rows = [
            {
                "record_id": f"N{year}-000",
                "bid_notice_no": f"N{year}",
                "bid_notice_order": "000",
                "notice_year": year,
                "relevance_status": "핵심",
                "opening_date": f"{year}01010000",
                "notice_date": f"{year}-01-01",
                "service_type": "일반용역",
            }
            for year in (2025, 2024)
        ]
        outcome = MODULE.collect_contract_enrichment(
            QuotaClient(),
            rows,
            max_contract_live_requests=850,
            max_procurement_request_live_requests=850,
        )
        self.assertEqual(QuotaClient.calls, 1)
        self.assertFalse(outcome.contract_complete)
        self.assertFalse(outcome.procurement_request_complete)

    def test_request_quota_error_blocks_both_general_and_technical_operations(self) -> None:
        class RequestQuotaClient:
            live_requests = 0
            live_requests_by_endpoint = {}
            request_calls = 0

            @staticmethod
            def is_cached(endpoint, params):
                return True

            @classmethod
            def get(cls, endpoint, params, **kwargs):
                if endpoint == MODULE.CONTRACT_PROCESS_ENDPOINT:
                    bid_no = params["bidNtceNo"]
                    return MODULE.ApiResult(
                        True,
                        "00",
                        "정상",
                        {
                            "items": {
                                "item": {
                                    "bidNtceNo": bid_no,
                                    "bidNtceOrd": "000",
                                    "prcrmntReqNo": f"REQ-{bid_no}",
                                    "bidwinrInfoList": "",
                                    "cntrctInfoList": "",
                                }
                            }
                        },
                        "{}",
                        cached=True,
                    )
                cls.request_calls += 1
                return MODULE.ApiResult(
                    False,
                    "22",
                    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR",
                    {},
                    "",
                )

        rows = []
        for year, service_type in ((2026, "일반용역"), (2025, "기술용역")):
            rows.append(
                {
                    "record_id": f"N{year}-000",
                    "bid_notice_no": f"N{year}",
                    "bid_notice_order": "000",
                    "notice_year": year,
                    "relevance_status": "핵심",
                    "opening_date": f"{year}01010000",
                    "notice_date": f"{year}-01-01",
                    "service_type": service_type,
                }
            )
        outcome = MODULE.collect_contract_enrichment(
            RequestQuotaClient(),
            rows,
            max_contract_live_requests=850,
            max_procurement_request_live_requests=850,
        )
        self.assertEqual(RequestQuotaClient.request_calls, 1)
        self.assertTrue(outcome.contract_complete)
        self.assertFalse(outcome.procurement_request_complete)
        self.assertEqual(len(outcome.procurement_requests), 2)

    def test_cli_rejects_service_specific_limit_above_900_before_key_lookup(self) -> None:
        with mock.patch.object(MODULE, "load_dotenv"):
            result = MODULE.main(["--max-contract-lookups", "901"])
        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
