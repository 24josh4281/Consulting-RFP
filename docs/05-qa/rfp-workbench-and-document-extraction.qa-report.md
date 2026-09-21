---
template: qa-report
version: 2.1.1
---

# QA Report: RFP Workbench and Document Extraction

> **Date**: 2026-09-21
> **Verdict**: PASS
> **Pass Rate**: 100
> **Critical Issues**: 0
> **Feature**: RFP Workbench and Document Extraction

---

## 1. Test Summary

| Level | Type | Status | Pass Rate | Failed |
|-------|------|:------:|:---------:|:------:|
| L1 | Python unit/regression test | PASS | 62/62 (100%) | 0 |
| L2 | CLI, HTML, SQLite data check | PASS | 4/4 (100%) | 0 |
| L3 | Excel workbook inspect/formula/render | PASS | 4/4 sheets (100%) | 0 |
| L4 | UX Flow Test | PASS | Filterable HTML + filterable Excel tables reviewed | 0 |
| L5 | Data Flow Test | PASS | source rows preserved; SQLite integrity `ok` | 0 |

## 2. Failed Tests

None.

`test_cli_rejects_service_specific_limit_above_900_before_key_lookup` prints the expected invalid-limit error as part of a safety test; the test passed and did not make a live request.

## 3. Critical Issues

None.

## 4. Debug Analysis

- Current database: 49 notices, 10 source attachment rows, 54 derived document-status rows.
- Directly readable public GIR HWPX: 6 `extracted` rows.
- Uncollected attachment URL: 44 `missing_document_url` rows.
- Placeholder/sample link: 4 `sample_source` rows.
- `PRAGMA integrity_check`: `ok`.
- Extraction only adds/updates `document_insights`; regression tests verify that notice and attachment source rows are preserved.

## 5. Metrics

| Metric | Value |
|--------|-------|
| M11 QA Pass Rate | 100% for executed checks |
| M12 Test Coverage (L1) | 62 passing regression tests; 5 dedicated document-insight tests |
| M13 E2E Coverage | Local static workbench and 4 rendered workbook sheets; no hosted browser E2E required |
| M14 Runtime Error Count | 0 unexpected errors |
| M15 Data Flow Integrity | Pass: 49 HTML notice rows, 49 workbook notices, database integrity `ok` |

## 6. Recommendations

1. Treat current document summaries as verified only for the 6 direct public HWPX records.
2. Do not label the extracted 500,000,000 KRW as an awarded or final bid amount; it is an explicitly labelled VAT-included project budget/required budget.
3. Add public attachment URLs through permitted official pages before expanding automatic document parsing to PDF/HWP.

## 7. Chrome MCP Status

Chrome/browser automation was not used. This is a local static HTML/Excel deliverable; verification used Python tests, SQLite checks, artifact inspection, formula scanning, and rendered Excel sheet review instead.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-09-21 | Final QA report |
