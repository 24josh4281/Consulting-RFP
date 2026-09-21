---
template: analysis
version: 1.3
---

# RFP Workbench and Document Extraction Analysis Report

> **Analysis Type**: Gap Analysis / Code Quality / Data Flow Review
>
> **Project**: Consulting-RFP
> **Version**: Local working tree
> **Analyst**: Codex
> **Date**: 2026-09-21
> **Design Doc**: [rfp-workbench-and-document-extraction.design.md](../02-design/features/rfp-workbench-and-document-extraction.design.md)

### Pipeline References (for verification)

| Phase | Document | Verification Target |
|-------|----------|---------------------|
| Plan | [Plan](../01-plan/features/rfp-workbench-and-document-extraction.plan.md) | Requirement and safety alignment |
| Design | [Design](../02-design/features/rfp-workbench-and-document-extraction.design.md) | Storage, extraction, presentation separation |
| Check | Current document | Functional, data, workbook validation |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 많은 기후·GHG·ETS 후보 공고를 빠르게 비교하되, 미확인 문서나 금액을 확정 사실처럼 보이지 않게 한다. |
| **WHO** | 이너젠의 기후·온실가스·배출권거래제 컨설팅 기회 검토 담당자이다. |
| **RISK** | 포털 첨부 URL 미수집, 제한된 원문 접근, 예산과 낙찰/계약 금액의 혼동이다. |
| **SUCCESS** | 모든 저장 공고가 한 작업대와 Excel에서 보이고, 원문 링크·문서 상태·근거·금액 기준이 분리된다. |
| **SCOPE** | 별도 insight 저장, 직접 공개 HWPX 추출, HTML 작업대, Excel, 자동 검증이다. |

---

## Strategic Alignment Check

### PRD Alignment

| PRD Element | Expected | Implementation Status |
|-------------|----------|:---------------------:|
| Core Problem (WHY) | 전체 후보의 빠르고 안전한 비교 | ✅ Addressed |
| Target User (WHO) | 비개발자 기후 컨설팅 담당자 | ✅ Addressed |
| Value Proposition | 원문 근거와 해석을 분리한 검토 흐름 | ✅ Delivered |

### Success Criteria Status

| # | Criteria (from Plan) | Status | Evidence |
|---|---------------------|:------:|----------|
| SC-1 | 49건 모두 작업대와 Excel에서 확인 | ✅ | HTML `notice-row` 49개, Excel 공고목록 시트 |
| SC-2 | 공개 GIR HWPX를 원문 변경 없이 처리 | ✅ | `document_insights` 6건 `extracted`; 보존 테스트 통과 |
| SC-3 | 샘플·누락·제한 상태를 분리 | ✅ | `sample_source` 4, `missing_document_url` 44 |
| SC-4 | 원문·문서 링크, 요약·금액 근거 제시 | ✅ | 공고 상세/문서요약 시트, 6개 공개 원문 근거 |
| SC-5 | Excel 1개 및 오류 없는 수식·렌더 | ✅ | 4개 시트, formula error 0, 4개 시트 렌더 점검 |
| SC-6 | 회귀·보안·부작용 점검 | ✅ | 62/62 테스트, SQLite integrity `ok`, 메일 미발송 |

**Success Rate**: 6/6 criteria met

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| Plan | 원문과 파생 요약을 별도 저장 | ✅ | 없음 |
| Design | 직접 공개 HWPX만 처리, 제한 우회 금지 | ✅ | 없음 |
| Design | 정적 HTML + 단일 Excel | ✅ | 없음 |

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

실제 현황 데이터와 공개 원문에서 작업대·Excel·요약·금액 근거가 일관되게 연결되는지, 기존 공고·첨부·Tier·알림 상태가 보존되는지 확인했다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/rfp-workbench-and-document-extraction.design.md`
- **Implementation Paths**: `rfp_tracker/documents.py`, `storage.py`, `render.py`, `cli.py`, `scripts/build_rfp_workbench_workbook.mjs`
- **Analysis Date**: 2026-09-21

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 Local Command Interface

| Design | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| `extract-documents` | `python -m rfp_tracker extract-documents` | ✅ Match | 공개 직접 URL만 처리 |
| `render-workbench` | `python -m rfp_tracker render-workbench` | ✅ Match | 필터형 정적 HTML 생성 |
| `export-workbench-json` | `python -m rfp_tracker export-workbench-json` | ✅ Match | Excel 입력용 비밀 없는 hand-off |
| Excel builder | `scripts/build_rfp_workbench_workbook.mjs` | ✅ Match | 4개 시트 xlsx 생성 |

### 2.2 Data Model

| Field group | Design | Implementation | Status |
|-------------|--------|----------------|--------|
| Source identity | notice, attachment, document URL/label | `document_insights`의 FK·URL·label | ✅ |
| Extraction state | extracted / unavailable / error | 명시적 snake_case 상태값 | ✅ |
| Derived facts | summary, amount text/value/basis, evidence | 별도 nullable 필드 | ✅ |
| Auditability | extracted time, cache path, error | `extracted_at`, `cache_path`, `error_message` | ✅ |

### 2.3 Component Structure

| Design Component | Implementation File | Status |
|------------------|---------------------|--------|
| Document extractor | `rfp_tracker/documents.py` | ✅ Match |
| Insight repository | `rfp_tracker/storage.py` | ✅ Match |
| Workbench renderer | `rfp_tracker/render.py` | ✅ Match |
| CLI orchestration | `rfp_tracker/cli.py` | ✅ Match |
| Workbook builder | `scripts/build_rfp_workbench_workbook.mjs` | ✅ Match |
| Regression tests | `tests/test_document_insights.py` | ✅ Match |

### 2.4 Functional Depth Analysis

| File | Depth Score | Placeholder Indicators | Missing Design Elements |
|------|:----------:|----------------------|------------------------|
| `documents.py` | 100 | 없음 | 없음 |
| `storage.py` | 100 | 없음 | 없음 |
| `render.py` | 95 | 없음 | 서버 저장형 필터는 의도적으로 범위 제외 |
| `cli.py` | 100 | 없음 | 없음 |
| workbook builder | 100 | 없음 | 없음 |

**Shallow File Count**: 0 / 5 files (0%)

### 2.5 Page UI Checklist Verification

| Page | Design Elements | Implemented | Missing | Rate |
|------|:--------------:|:-----------:|:-------:|:----:|
| Local Workbench Dashboard | 8 | 8 | 0 | 100% |
| Excel workbook | 4 sheets/guide | 4 | 0 | 100% |

**Functional Match Rate**: 100% for planned local functions. Browser automation was not required for this static local report.

### 2.6 Runtime Verification Results

| Level | Verification | Result | Pass |
|-------|--------------|--------|:----:|
| L1 | Python unit and regression suite | 62/62 passed | ✅ |
| L2 | CLI/database/output structure | 49 notice rows, 54 insight rows, integrity `ok` | ✅ |
| L3 | Excel artifact inspect/formula scan/render | 4 sheets rendered, formula error 0 | ✅ |

### 2.7 Match Rate Summary

```
Structural Match Rate: 100%
Functional Match Rate: 100%
Contract Match Rate:   N/A (local CLI; no HTTP API contract)
Runtime Match Rate:    100% for executed local checks
```

---

## 3. Code Quality Analysis

### 3.1 Complexity and Maintainability

| Area | Status | Rationale |
|------|--------|-----------|
| Source/derived separation | ✅ Good | `document_insights` never replaces original notice/attachment fields. |
| Parsing scope | ✅ Good | HWPX ZIP/XML uses the standard library and an explicit public-URL gate. |
| Amount semantics | ✅ Good | parsed KRW, source text, basis, and evidence are separate fields. |
| Output readability | ✅ Good | dashboard filters, bordered Excel tables, frozen headers, and source guide. |

### 3.2 Code Smells

| Type | File | Description | Severity |
|------|------|-------------|----------|
| Supported-format limit | `documents.py` | Current automatic reader supports direct public HWPX only. | 🟡 Product limitation |
| Wide workbook table | workbook builder | Full URL/evidence fields make the source sheets horizontally wide. | 🟢 Intentional traceability trade-off |

### 3.3 Security Issues

| Severity | Area | Issue | Result |
|----------|------|-------|--------|
| 🔴 Critical | Generated HTML/JSON/XLSX | Secret leakage | 없음: credential variable labels not found in generated HTML/JSON |
| 🟡 Warning | Protected sources | Improper access bypass | 없음: direct public URL gate, no login/CAPTCHA bypass |
| 🟢 Info | Notifications | Unintended email | 없음: this feature did not run a send command |

---

## 4. Performance Analysis

| Area | Observation | Status |
|------|-------------|--------|
| Current data scale | 49 notices, 54 document status rows | ✅ Immediate local output |
| Download scope | direct public HWPX only, bounded cache/file size | ✅ Limits network and storage risk |
| Dashboard filtering | client-side over 49 rows | ✅ Sufficient for current scale |

No response-time target applies because this is a local static workbench, not a hosted API.

---

## 5. Test Coverage

| Area | Current | Target | Status |
|------|---------|--------|--------|
| Full regression suite | 62/62 | All pass | ✅ |
| New document-insight tests | 5/5 | All pass | ✅ |
| Workbook formula errors | 0 | 0 | ✅ |
| Workbook visual sheet renders | 4/4 | All sheets | ✅ |
| Source-data integrity | SQLite `ok` | `ok` | ✅ |

The suite contains one intentional safety-validation message for an invalid contract lookup limit; the test itself passed and does not indicate a runtime failure.

---

## 6. Clean Architecture Compliance

| Layer | Expected Responsibility | Actual Location | Status |
|-------|-------------------------|-----------------|--------|
| Presentation | HTML/Excel output | `render.py`, workbook builder | ✅ |
| Application | CLI orchestration | `cli.py`, `run_tracker.ps1` | ✅ |
| Domain | extraction/status/evidence rules | `documents.py` | ✅ |
| Infrastructure | SQLite, public cache/download | `storage.py`, `documents.py` | ✅ |

No presentation module downloads documents or writes source rows. No extraction code renders HTML or sends email.

---

## 7. Convention Compliance

| Category | Result | Notes |
|----------|:------:|-------|
| Python naming | ✅ | snake_case functions/statuses |
| Source provenance | ✅ | URL, label, evidence, time stored |
| Error handling | ✅ | explicit status rather than silent blank values |
| Excel types | ✅ | dates/numeric KRW stored as typed values when unambiguous |
| Secrets | ✅ | no new environment variable and no generated-output leak |

---

## 8. Overall Score

```
Overall Score: 96/100
- Design/implementation match: 100
- Test and data verification: 100
- Safety/provenance: 100
- Source coverage: 84 (44 status rows still lack a captured attachment URL)
```

The score does not imply that 100% of underlying public documents are available; it separates feature quality from external source coverage.

---

## 9. Recommended Actions

### 9.1 Immediate

| Priority | Item | Expected Impact |
|----------|------|-----------------|
| High | Open the 44 `첨부 URL 미수집` official notice links and capture genuinely public RFP/task files where allowed. | Expands source-verified summaries |
| High | Manually review the GIR system-development project for fit before bidding. | Avoids treating a Tier/keyword match as a consulting fit |

### 9.2 Short-term

| Priority | Item | Expected Impact |
|----------|------|-----------------|
| Medium | Add a manually maintained document URL field for portal attachments. | Converts URL gaps to traceable source records |
| Medium | Add PDF/HWP parsing only after testing representative public files. | Extends coverage safely |

### 9.3 Long-term

| Item | Notes |
|------|-------|
| Hosted multi-user workbench | Consider only if review workflow outgrows the local static report. |
| Human feedback loop | Record bid/no-bid outcome to refine Tier rule precision. |

---

## 10. Design Document Updates Needed

No implementation deviation requires a design change. Future PDF/HWP parsing should receive its own scoped design update because source handling and test fixtures will change.

---

## 11. Next Steps

- [x] Validate current workbench and workbook
- [x] Document source coverage and amount semantics
- [ ] Capture more direct public attachment URLs through permitted official pages
- [ ] Use human review for bid/no-bid decisions

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-21 | Final implementation analysis | Codex |
