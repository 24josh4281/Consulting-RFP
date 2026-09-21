---
template: design
version: 1.3
---

# G2B RFP Priority Review and Pages Design Document

> **Summary**: 공식 G2B 첨부 복원, 내부 입찰 적합성 검토, Tier 1 우선 검토, 비밀 없는 GitHub Pages 스냅샷 설계.
>
> **Project**: Consulting-RFP
> **Version**: Local working tree
> **Author**: Codex
> **Date**: 2026-09-21
> **Status**: In progress
> **Planning Doc**: `docs/01-plan/features/g2b-rfp-priority-review-and-pages.plan.md`

### Pipeline References (if applicable)

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | SQLite schema in section 3 | N/A |
| Phase 2 | Existing Python conventions | N/A |
| Phase 3 | Static workbench view | N/A |
| Phase 4 | Local CLI, no hosted API | N/A |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 실제 원문 근거를 넓히고, 공개 현황과 내부 영업판단을 안전하게 분리한다. |
| **WHO** | 이너젠 입찰 검토 담당자와 공개 공고 링크를 보는 브라우저 사용자이다. |
| **RISK** | 파일 접근 제한과 internal bid-fit 정보의 공개 노출이다. |
| **SUCCESS** | 공식 첨부 복원, Tier 1 우선 화면, editable review worksheet, sanitized Pages 배포가 검증된다. |
| **SCOPE** | raw attachment backfill, fit-review, priority view, Excel, Pages, QA이다. |

---

## 1. Overview

### 1.1 Design Goals

- G2B attachment URL을 existing raw JSON의 명시적 file URL/name 쌍에서만 복원한다.
- 자동·사람 검토 데이터가 raw notices/attachments를 바꾸지 않게 한다.
- Tier 1은 “입찰 확정”이 아니라 “공식 원문 우선 검토”로만 표시한다.
- public site는 allowlist payload를 통해 internal fit fields가 원천적으로 렌더러에 전달되지 않게 한다.

### 1.2 Design Principles

- Public source fact before interpretation.
- Separate source record, derived document insight, and human bid-fit judgement.
- Direct public access only.
- One writer per review record; upsert is idempotent.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | Excel-only manual review | New authenticated web service | SQLite review table + static local/public views |
| **New Files** | 1 | 10+ | 4-6 |
| **Modified Files** | 2 | 8+ | 6-8 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | manual drift | hosting/auth scope growth | public/internal separation must be tested |
| **Recommendation** | short-lived workaround | future product phase | **Selected** |

**Selected**: Option C. It adds a persistent local review workflow and an accessible public snapshot without treating a static site as an authenticated review system.

### 2.1 Component Diagram

    existing G2B raw_json
            |
            v
    extract_g2b_spec_attachments -> attachments -> document extractor -> document_insights
            |                                               |
            v                                               v
    bid_fit_reviews <--------------------- local workbench payload -> HTML + Excel
                                                               |
                                                               v
                                                     public allowlist payload
                                                               |
                                                               v
                                                       site/index.html -> Pages

### 2.2 Data Flow

    raw G2B API JSON
      -> explicit URL/name attachment parser
      -> idempotent attachment insert
      -> direct-public HWPX cache/parse only
      -> source-backed document insight
      -> priority_status derived from tier/source/document/review state
      -> internal payload includes fit review
      -> public projection strips fit/review/private fields

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| G2B backfill | `notices.raw_json`, attachments | recover attachment links with no extra API query |
| Fit review repository | SQLite notices | preserve human bid decisions separately |
| Priority view | normalized payload | explain why a record appears first |
| Excel builder | internal JSON payload, artifact tool | editable assessment grid |
| Pages workflow | generated `site/` | serve a static public snapshot |

---

## 3. Data Model

### 3.1 Entity Definition

`bid_fit_reviews` fields:

    id, notice_id, consulting_fit, qualification_requirements,
    proposed_team, bid_decision, key_risks, decision_note,
    updated_at

`consulting_fit` values: `not_reviewed`, `high`, `medium`, `low`.

`bid_decision` values: `pending`, `bid`, `conditional`, `no_bid`.

### 3.2 Entity Relationships

    Notice 1 ---- N Attachment
       |
       +---- N DocumentInsight
       |
       +---- 0..1 BidFitReview

### 3.3 Database Schema

```sql
CREATE TABLE bid_fit_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  notice_id INTEGER NOT NULL UNIQUE,
  consulting_fit TEXT NOT NULL DEFAULT 'not_reviewed',
  qualification_requirements TEXT NOT NULL DEFAULT '',
  proposed_team TEXT NOT NULL DEFAULT '',
  bid_decision TEXT NOT NULL DEFAULT 'pending',
  key_risks TEXT NOT NULL DEFAULT '',
  decision_note TEXT NOT NULL DEFAULT '',
  updated_at TEXT,
  FOREIGN KEY(notice_id) REFERENCES notices(id) ON DELETE CASCADE
);
```

No source column is changed. A removal of an attachment only affects raw sync lifecycle; fit review remains bound to the notice.

---

## 4. API Specification

### 4.1 Local CLI Interface

| Command | Description | Side Effect |
|--------|-------------|-------------|
| `backfill-g2b-attachments` | Recover stored official G2B attachment links | adds source attachment rows only |
| `fit-review set` | Save one human bid-fit decision | upserts one derived review row |
| `fit-review list` | Display stored review values | read-only |
| `render-workbench --public` | Write sanitized Pages snapshot | static HTML only |

### 4.2 Detailed Specification

`fit-review set` validates allowed enum values before calling parameterized SQLite upsert. Empty text fields remain blank, not inferred.

`public` projection removes `review_note`, `reviewed_at`, all `fit_review` fields, `tier_reason`, and all cache/error paths. It also excludes `sample_esg_tenders` notices.

---

## 5. UI/UX Design

### 5.1 Screen Layout

    Internal workbench
      KPI cards
      Tier 1 official priority review table
      full notice filters/table
      per-notice source/documents + bid-fit summary

    Public Pages snapshot
      source coverage note
      official source-only filtered public table
      original notice/document links and source-backed summaries

### 5.2 User Flow

    Local: open workbench -> open Tier 1 priority -> read source document -> record fit review in Excel/CLI -> regenerate outputs

    Public: open Pages URL -> filter official notices -> open official source links

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| priority panel | `render.py` | official Tier 1 ordering and status explanation |
| fit summary | `render.py` | local-only human decision display |
| fit worksheet | workbook builder | editable review fields and dropdowns |
| public projection | `documents.py` | privacy allowlist and sample exclusion |
| Pages workflow | `.github/workflows/pages.yml` | build/deploy static `site` artifact |

### 5.4 Page UI Checklist

#### Internal Workbench

- [ ] Priority panel: official Tier 1 only, source document status, deadline, review status, `우선 보기` action
- [ ] Full-table filter: priority/official filter in addition to existing filters
- [ ] Detail: current fit/review status, qualification, team, bid decision, key risk, note
- [ ] Detail: official source/RFP links and source-backed document summary

#### Public Pages

- [ ] Notice list: official sources only, no sample records
- [ ] Links: official notice and publicly collected attachments
- [ ] Notice detail: public document summary and amount basis only
- [ ] Exclusion: no internal review note, bid decision, team, qualification, or credentials

---

## 6. Error Handling

| Code | Message | Cause | Handling |
|------|---------|-------|----------|
| `raw_json_invalid` | G2B raw source cannot be parsed | legacy/corrupt record | skip and report count; preserve raw record |
| `no_g2b_attachment` | no explicit attachment URL exists | source did not provide spec documents | retain missing-document state |
| `fit_review_invalid` | invalid enum value | CLI input error | fail before database mutation |
| `pages_deploy_failed` | Pages workflow failed | GitHub Actions/repository setting | retain local artifact and report workflow URL/log |

---

## 7. Security Considerations

- [x] All fit-review SQL is parameterized.
- [x] Public payload is a whitelist, not an internal payload with individual fields hidden in CSS.
- [x] `.env`, data DB, outputs, reports, local notification configs remain ignored.
- [x] Pages uses GitHub Actions token; no local GitHub token is retrieved or stored.
- [x] Public document downloader only follows already collected public URLs.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1 | G2B attachment parser, backfill, fit-review upsert, public sanitizer | Python unittest | Do |
| L2 | internal/public HTML structure and privacy fields | Python unittest / static assertion | Do |
| L3 | workbook inspection, validation, formula scan, render | artifact tool | Check |
| L4 | Git push / Pages workflow artifact | Git and GitHub HTTP/Actions | Check |

### 8.2 L1 Test Scenarios

| # | Target | Test Description | Expected Result |
|---|--------|-----------------|-----------------|
| 1 | attachment parser | raw JSON has named HWPX URL with extension-less path | attachment retains label and `hwpx` type |
| 2 | backfill | repeated invocation | one source attachment row per unique URL |
| 3 | stale gap | real attachment exists after backfill | blank missing state does not remain primary |
| 4 | fit review | upsert values | source notice stays unchanged |
| 5 | priority | official Tier 1 vs sample | official appears in priority list, sample excluded |
| 6 | public payload | internal fields set | public projection has none of them |

### 8.3 L2 Test Scenarios

| # | Page | Action | Expected Result |
|---|------|--------|----------------|
| 1 | Internal workbench | render priority panel | Tier 1 official information present |
| 2 | Public snapshot | render with `--public` | no internal fields or sample domains in HTML |

### 8.4 L3 Scenario

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|------------------|
| 1 | Analyst worksheet | Dashboard -> 입찰적합성검토 -> add review | typed source fields preserved and dropdowns exist |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:------------:|---------------------|
| Notice | 3 | official Tier 1, sample Tier 1, Tier 2 |
| Attachment | 2 | G2B HWPX URL, raw file name |
| BidFitReview | 1 | all enumerated choices and narrative fields |

---

## 9. Clean Architecture

| Layer | Responsibility | Location |
|-------|---------------|----------|
| Presentation | local HTML, public HTML, Excel | `render.py`, builder, `site/` |
| Application | CLI workflow | `cli.py`, Pages workflow |
| Domain | attachment mapping, priority, sanitization | `fetchers.py`, `documents.py` |
| Infrastructure | SQLite and direct public files | `storage.py`, existing downloader |

`render.py` receives a normalized payload. It does not create review decisions or make network calls. The Pages workflow receives only `site/`.

---

## 10. Coding Convention Reference

| Target | Rule | Example |
|--------|------|---------|
| Python function | snake_case | `backfill_g2b_attachments` |
| SQLite table | snake_case plural | `bid_fit_reviews` |
| User decisions | explicit enum | `conditional`, not inferred text |
| Public fields | whitelist projection | `build_public_workbench_payload` |
| Deployment | standard GitHub Actions | `.github/workflows/pages.yml` |

---

## 11. Implementation Guide

### 11.1 File Structure

    rfp_tracker/
      fetchers.py
      storage.py
      documents.py
      render.py
      cli.py
    scripts/
      build_rfp_workbench_workbook.mjs
    .github/workflows/
      pages.yml
    site/
      index.html (generated public snapshot)
    tests/
      test_document_insights.py

### 11.2 Implementation Order

1. [ ] G2B named attachment extraction/backfill and tests
2. [ ] bid fit review storage, CLI, payload and tests
3. [ ] priority panel and internal/public render tests
4. [ ] Excel review sheet, validation and visual QA
5. [ ] public site generation, Pages workflow, Git review/push

### 11.3 Session Guide

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| G2B documents | `module-1` | named attachment recovery and HWPX extraction | 2-3 |
| Internal review | `module-2` | fit-review storage, CLI, payload, Excel | 3-4 |
| Priority/public site | `module-3` | priority panel, sanitizer, Pages pipeline | 3-4 |
| QA/deploy | `module-4` | source, workbook, Git, Pages verification | 2-3 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | Complete |
| Session 2 | Do | modules 1-2 | Current |
| Session 3 | Do + Check | modules 3-4 | Current |
| Session 4 | Report | 전체 | Current |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-21 | Pragmatic local/public design selected | Codex |
