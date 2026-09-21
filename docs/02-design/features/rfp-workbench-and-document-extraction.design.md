# RFP Workbench and Document Extraction Design Document

> **Summary**: 원문을 보존하면서 전체 공고와 공개 문서 요약을 HTML/Excel에서 검토하는 작업대 설계.
>
> **Project**: Consulting-RFP
> **Version**: Local working tree
> **Author**: Codex
> **Date**: 2026-09-21
> **Status**: Complete
> **Planning Doc**: docs/01-plan/features/rfp-workbench-and-document-extraction.plan.md

### Pipeline References (if applicable)

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | SQLite schema in section 3 | N/A |
| Phase 2 | Existing Python conventions | N/A |
| Phase 3 | Static HTML workbench | N/A |
| Phase 4 | Local CLI, no web API | N/A |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 후보 공고를 일일 업무에서 안전하고 빠르게 검토한다. |
| **WHO** | 이너젠의 기후·GHG·ETS 컨설팅 기회 검토 담당자이다. |
| **RISK** | 접근 제한과 금액 용어 혼동으로 미확인 정보가 사실처럼 보일 수 있다. |
| **SUCCESS** | 전 공고를 필터링하고 공개 원문 근거를 확인할 수 있다. |
| **SCOPE** | insight 저장, HWPX 추출, HTML, Excel, QA이다. |

---

## 1. Overview

### 1.1 Design Goals

- 원문 notices와 attachments를 extraction이 수정하지 않게 한다.
- 공개 원문을 읽은 결과와 샘플/누락/실패 상태를 구분한다.
- 모든 금액을 단순 입찰금액으로 표시하지 않고 그 기준을 붙인다.
- 서버를 새로 만들지 않고 기존 명령행과 정적 리포트 흐름을 유지한다.

### 1.2 Design Principles

- Source fact before interpretation.
- 공고는 한 행으로 유지하고, 복수 문서/요약은 공고 상세에 묶는다.
- 직접 공개된 URL만 처리한다.
- 자동 추출과 사람의 Tier/검토 판단을 분리한다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | notice 컬럼에 요약 추가 | 새 웹/API 계층 | 별도 insight 테이블 + 정적 작업대 |
| **New Files** | 1-2 | 8+ | 3-5 |
| **Modified Files** | 2-3 | 8+ | 4-6 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 원문/파생값 혼재 | 과도한 범위 | 원문 보존과 실용성 균형 |
| **Recommendation** | 단기 목록 개선 | 미래 다중사용자 제품 | **Selected** |

**Selected**: Option C. 별도 파생정보 저장소와 정적 HTML/Excel 출력으로 원문 보존, 반복 실행, 간단한 운영을 모두 만족한다.

### 2.1 Component Diagram

    Public official attachment URL
                 |
                 v
    documents.py: download, HWPX parse, evidence extraction
                 |
                 v
    document_insights SQLite table
                 ^
                 |
    notices and attachments source records
          |                       |
          v                       v
    render.py HTML             artifact-tool XLSX builder

### 2.2 Data Flow

    Notice sync
      -> raw notices and attachments
      -> public-document eligibility
      -> public file cache
      -> HWPX text extraction
      -> summary, amount, evidence, status
      -> document_insights
      -> workbench HTML and Excel

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|------------|---------|
| Extractor | attachments, standard ZIP/XML, public HTTP | 공개 HWPX를 안전하게 읽는다. |
| Repository | SQLite notices/attachments | 파생 결과를 별도 저장한다. |
| Workbench | grouped repository query | 공고 한 행 단위로 렌더한다. |
| Excel builder | JSON hand-off, bundled artifact tool | 검토 가능한 xlsx를 만든다. |

---

## 3. Data Model

### 3.1 Entity Definition

DocumentInsight fields:

    id, notice_id, attachment_id, document_url, document_label,
    source_url, extraction_status, task_summary, amount_value_krw,
    amount_text, amount_basis, evidence_excerpt, extracted_at,
    error_message, cache_path

### 3.2 Entity Relationships

    Notice 1 to N Attachment
      |
      +---- 1 to N DocumentInsight

One unique notice/document URL pair has one latest derived record. A refreshed attachment URL may receive a new insight while the source notice stays unchanged.

### 3.3 Database Schema

    document_insights
      primary key id
      foreign key notice_id -> notices
      foreign key attachment_id -> attachments
      unique notice_id plus document_url

The record holds source wording and parsed numeric KRW separately. A null numeric amount means no unambiguous value was extracted.

---

## 4. API Specification

### 4.1 Local CLI Interface

| Command | Description | Side Effect |
|--------|-------------|-------------|
| extract-documents | 직접 공개된 첨부 URL을 처리하여 insight를 갱신한다. | 공개 파일 cache와 파생 DB 행만 생성 |
| render-workbench | 전체 HTML 작업대를 만든다. | HTML report 생성 |
| export-workbench-json | Excel 입력용 비밀 없는 데이터를 만든다. | JSON hand-off 생성 |
| build_rfp_workbench_workbook.mjs | JSON으로 Excel 파일을 만든다. | xlsx와 preview 생성 |

### 4.2 Detailed Specification

| Field | Meaning |
|-------|---------|
| extracted | 공개 파일을 읽고 과업 또는 금액 근거를 찾았다. |
| processed_no_evidence | 파일은 읽었지만 신뢰할 요약/금액 근거가 없다. |
| sample_source | 예시 또는 placeholder URL이다. |
| missing_document_url | 공고는 있으나 첨부 URL을 수집하지 못했다. |
| unsupported_file_type | 현 버전에서 안전하게 읽지 않는 형식이다. |
| download_failed | 공개 URL이 유효 파일을 반환하지 않았다. |
| parse_failed | 다운로드 파일의 문서 구조가 읽히지 않았다. |

---

## 5. UI/UX Design

### 5.1 Screen Layout

    Climate Procurement Workbench
    total, Tier 1, Tier 2, Tier 3, public document verified

    search | Tier | review state | source | document status | deadline

    notice table
    Tier | review | title and official link | deadline | listed amount | document state
      expandable detail:
        Tier reason, keywords, document links, task summary,
        amount basis/text, evidence excerpt, limitation

### 5.2 User Flow

    Open HTML or Excel
      -> filter Tier 1 and active deadline
      -> inspect task summary and amount basis
      -> open original notice or public document
      -> use existing review/tier command for human decision

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| KPI cards | render.py | 전체 및 문서 상태 요약 |
| Filter bar | render.py inline JavaScript | 화면에서만 필터 |
| Notice table | render.py | 공고 한 행 및 공식 링크 |
| Detail panel | render.py | 문서, 요약, 금액 근거, 제한 표시 |
| Dashboard sheet | workbook builder | Tier/문서상태 요약 |
| Notices sheet | workbook builder | 모든 공고의 필터 가능한 테이블 |
| Document Summary | workbook builder | 문서별 요약·근거 테이블 |

### 5.4 Page UI Checklist

#### Local Workbench Dashboard

- [ ] 검색: 공고명, 기관, 출처, 키워드, 문서명
- [ ] 필터: Tier 1, Tier 2, Tier 3, 전체
- [ ] 필터: review status, source, document extraction status
- [ ] 필터: open/closed and deadline
- [ ] KPI: total, each Tier, public document verified
- [ ] Table: official URL, method, listed amount, deadline
- [ ] Details: summary, amount basis, evidence, document link, limitation

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | Message | Cause | Handling |
|------|---------|-------|----------|
| sample_source | Sample or placeholder document | example/sample config | 증거로 사용하지 않는다. |
| missing_document_url | Attachment URL not collected | list API limitation | 원문 공고 링크를 제공한다. |
| unsupported_file_type | Document type not parsed | unsupported file | 링크와 상태를 보존한다. |
| download_failed | Public document unavailable | HTTP or timeout | 상태/오류를 저장하고 재시도 가능하게 한다. |
| parse_failed | Document not parseable | HWPX ZIP/XML error | 요약을 만들지 않는다. |

### 6.2 Error Response Format

    extraction_status: download_failed
    error_message: HTTP 404 from public attachment URL

---

## 7. Security Considerations

- [x] Data.go key, SMTP 정보, 비밀번호를 insight/HTML/Excel에 저장하지 않는다.
- [x] attachments에 이미 있는 공개 URL만 사용한다.
- [x] HTML에 넣는 원문은 모두 escape한다.
- [x] extraction이나 report command에서 메일을 보내지 않는다.
- [x] review, Tier, notification delivery state를 수정하지 않는다.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1 | schema, URL eligibility, HWPX, amount, grouped data | Python unittest | Do |
| L2 | HTML 구조, filter data attributes, escaping | Python unittest | Do |
| L3 | workbook inspect, formula scan, render | artifact tool | Check |

### 8.2 L1 Test Scenarios

| # | Target | Test Description | Expected Result |
|---|--------|-----------------|-----------------|
| 1 | Insight upsert | 같은 notice/URL 재실행 | 하나의 최신 insight 행 |
| 2 | Eligibility | example.com URL | sample_source, download 없음 |
| 3 | HWPX parser | XML fragment read | 정규화된 한국어 텍스트 |
| 4 | Amount parser | 단위/라벨 포함 금액 | 기준과 함께 저장 |
| 5 | Grouped query | 문서 여러 건 | notice 중복 없음 |
| 6 | Regression | existing suite | 기존 테스트 통과 |

### 8.3 L2 Test Scenarios

| # | Page | Action | Expected Result |
|---|------|--------|-----------------|
| 1 | Workbench | report open | filter, KPI, table 존재 |
| 2 | Workbench | filter event | data attributes로 결과 좁힘 |
| 3 | Workbench | details | 원문 URL과 파생값 구분 |

### 8.4 L3 Scenario

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|------------------|
| 1 | Analyst review | Dashboard -> Notices filter -> Document Summary | 번호/금액/헤더가 잘리고 formula error가 없다. |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:------------:|---------------------|
| Notice | 3 | 각 Tier 하나씩 |
| Attachment | 2 | 공개 HWPX와 sample/missing |
| DocumentInsight | 2 | extracted plus unavailable |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| Presentation | HTML/Excel views | render.py, builder |
| Application | CLI orchestration | cli.py |
| Domain | extraction and status rules | documents.py |
| Infrastructure | SQLite and public HTTP/cache | storage.py, documents.py |

### 9.2 Dependency Rules

    CLI -> document/query service -> SQLite or public source
    CLI -> renderer/builder input -> HTML or XLSX

Renderer는 정규화된 데이터만 받고 public download나 DB update를 하지 않는다.

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|------------|---------------|
| CLI | documents, storage, renderer | direct SQL strings |
| Renderer | labels, normalized rows | downloader |
| Documents | storage helper | HTML renderer |
| Storage | stdlib/models | notification sender |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| DocumentInsight helpers | Domain/infrastructure | documents.py, storage.py |
| render_workbench_dashboard | Presentation | render.py |
| CLI | Application | cli.py |
| Excel builder | Presentation | scripts/build_rfp_workbench_workbook.mjs |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| Target | Rule | Example |
|--------|------|---------|
| Python function | snake_case | extract_document_insight |
| SQLite table | snake_case plural | document_insights |
| status | lower snake_case | processed_no_evidence |
| output folder | date plus purpose | 20260921-rfp-workbench |

### 10.2 Import Order

1. Python standard library
2. Package-local modules
3. Bundled dependency only when necessary

### 10.3 Environment Variables

| Prefix | Purpose | Scope | Example |
|--------|---------|-------|---------|
| None new | Public source URLs only | Local | N/A |

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| Source-derived fields | source text/evidence and parsed values separate |
| Error handling | explicit status, no silent blank |
| Amount | text, basis, numeric KRW separate |
| Workbook | typed fields, frozen headers, boundaries, source guide |

---

## 11. Implementation Guide

### 11.1 File Structure

    rfp_tracker/
      documents.py
      storage.py
      render.py
      cli.py
    scripts/
      build_rfp_workbench_workbook.mjs
    tests/
      test_document_insights.py

### 11.2 Implementation Order

1. [x] SQLite insight schema/query
2. [x] public HWPX extraction and evidence
3. [x] CLI and JSON hand-off
4. [x] workbench HTML
5. [x] workbook output and verification
6. [x] regression tests and report

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| Insight storage | module-1 | schema and grouped query | 1-2 |
| Public extraction | module-2 | HWPX parser and evidence | 2-3 |
| Workbench view | module-3 | HTML, CLI, JSON | 1-2 |
| Excel/QA | module-4 | workbook and visual checks | 2-3 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | module-1,module-2 | 4-5 |
| Session 2 | Do | module-3,module-4 | 3-5 |
| Session 3 | Check + Report | whole feature | 2-3 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-21 | Pragmatic workbench design selected | Codex |
