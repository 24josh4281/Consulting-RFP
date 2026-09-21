# 이너젠 적합성 Tier 분류 및 뉴스레터 개선 분석 보고서

> **Analysis Type**: Design/implementation gap analysis and operational safety verification
>
> **Project**: Climate/GHG/ETS RFP Tracker
> **Version**: 현재 로컬 작업본
> **Analyst**: Codex
> **Date**: 2026-09-21
> **Design Doc**: [innergen-tiering-and-newsletter.design.md](../02-design/features/innergen-tiering-and-newsletter.design.md)

### Pipeline References (for verification)

| Phase | Document | Verification Target |
|-------|----------|---------------------|
| Phase 1 | [Tier plan](../01-plan/features/innergen-tiering-and-newsletter.plan.md) | SQLite terminology and preservation rules |
| Phase 2 | Existing Python conventions | Standard-library-only, snake_case, unittest |
| Phase 4 | [CLI design](../02-design/features/innergen-tiering-and-newsletter.design.md#4-api-specification) | `sync`, `tier`, `tier-audit` contract |
| Phase 8 | This report | Architecture, data safety, operational verification |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 기후 키워드 전체가 아니라 이너젠 컨설팅 기회 중심으로 검토 우선순위를 정한다. |
| **WHO** | 이너젠의 입찰·컨설팅 담당자와 고객사 추천 담당자다. |
| **RISK** | 제목만으로 잘못 분류할 수 있으므로 근거와 수동 보정을 제공한다. |
| **SUCCESS** | Tier 1 즉시 알림, Tier별 뉴스레터, 수동 Tier 보존, 기존 원문·발송 이력 보존. |
| **SCOPE** | Rule module, SQLite migration, CLI, report views, email template, tests, existing-data audit. |

---

## Strategic Alignment Check

### PRD Alignment

별도 PRD는 없으며, 사용자가 제시한 세 Tier 정의가 제품 요구사항의 기준이다.

| PRD Element | Expected | Implementation Status |
|-------------|----------|:---------------------:|
| Core Problem (WHY) | 직접 컨설팅과 참고 공고를 즉시 분리 | ✅ Addressed |
| Target User (WHO) | 이너젠 입찰/컨설팅 운영자 | ✅ Addressed |
| Value Proposition | Tier 1 우선 알림과 읽기 쉬운 뉴스레터 | ✅ Delivered |

### Success Criteria Status

| # | Criteria (from Plan) | Status | Evidence |
|---|----------------------|:------:|----------|
| SC-1 | Tier 1/2/3 예시 분류 | ✅ | `TieringTests.test_innergen_tiers_follow_business_scope_and_exclusion_priority` |
| SC-2 | 수동 Tier가 후속 수집에서 보존 | ✅ | `TieringTests.test_manual_tier_is_preserved_when_source_notice_is_refreshed` |
| SC-3 | 즉시 알림은 Tier 1만 | ✅ | `NotificationTests.test_immediate_only_sends_tier_1_and_digest_is_bordered_newsletter` |
| SC-4 | 일일/주간 뉴스레터에 세 Tier와 테두리 표 | ✅ | 같은 뉴스레터 렌더링 테스트 |
| SC-5 | 실제 DB 기존 공고 재분류/리포트 재생성 | ✅ | `tier-audit --apply`: 49건 적용, reports 4종 재생성 |
| SC-6 | 컴파일 및 테스트 | ✅ | `py_compile`, unittest 44/44 passed |

**Success Rate**: 6/6 criteria met

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | `review_status`와 `business_tier`를 분리 | ✅ | 없음 |
| [Design] | 순수 `tiering.py` + SQLite 메타데이터 | ✅ | 없음 |
| [Design] | 수동 Tier는 자동 sync/audit가 덮어쓰지 않음 | ✅ | 없음 |
| [Design] | 실제 SMTP 대신 fake sender/dry-run으로 검증 | ✅ | 없음 |
| [Check] | 수집 키워드가 IT 공고를 Tier 2로 올린 문제를 확인 | ✅ | 제목·카테고리 중심 판단으로 보정 |

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

이너젠의 업무 기준이 실제 공고 목록·알림 대상·HTML 메일에 일관되게 적용되고, 기존 원문과 운영 기록을 손상시키지 않는지 확인한다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/innergen-tiering-and-newsletter.design.md`
- **Implementation Path**: `rfp_tracker/tiering.py`, `models.py`, `storage.py`, `cli.py`, `notifications.py`, `briefing.py`, `render.py`, `documents.py`
- **Analysis Date**: 2026-09-21

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API / CLI Contracts

| Design | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| `sync` assigns automatic Tier | `cli.sync_command` calls `assess_innergen_tier` before upsert | ✅ Match | 모든 수집 출처에 적용 |
| `tier-audit --apply` | `cli.tier_audit_command` | ✅ Match | 수동 Tier는 보존 |
| `tier --id --tier --reason` | `cli.tier_command` | ✅ Match | 허용 Tier와 사유를 검증 |
| Tier 1 immediate only | `list_unnotified_notices(... business_tiers=(tier_1,))` | ✅ Match | 기존 review 상태 제외 규칙도 유지 |
| Tier 1/2/3 digest | `notifications._newsletter_html` | ✅ Match | daily/weekly에 세 구역 출력 |

### 2.2 Data Model

| Field | Design Type | Impl Type | Status |
|-------|-------------|-----------|--------|
| `business_tier` | text enum | SQLite `TEXT NOT NULL` | ✅ |
| `tier_reason` | text | SQLite `TEXT NOT NULL` | ✅ |
| `tier_source` | `automatic` / `manual` | SQLite `TEXT NOT NULL` | ✅ |
| `tiered_at` | datetime text | SQLite `TEXT` | ✅ |
| Raw source / review / deliveries | unchanged | existing columns/tables preserved | ✅ |

### 2.3 Component Structure

| Design Component | Implementation File | Status |
|------------------|---------------------|--------|
| Pure Tier rule | `rfp_tracker/tiering.py` | ✅ Match |
| Notice Tier metadata | `rfp_tracker/models.py` | ✅ Match |
| Migration + persistence | `rfp_tracker/storage.py` | ✅ Match |
| CLI override/audit | `rfp_tracker/cli.py` | ✅ Match |
| Newsletter presentation | `rfp_tracker/notifications.py` | ✅ Match |
| Dashboard/RFP/CSV/briefing views | `render.py`, `documents.py`, `briefing.py` | ✅ Match |

### 2.4 Functional Depth Analysis

| File | Depth Score | Placeholder Indicators | Missing Design Elements |
|------|:----------:|----------------------|------------------------|
| `tiering.py` | 100 | 없음 | 없음 |
| `storage.py` | 100 | 없음 | 없음 |
| `cli.py` | 100 | 없음 | 없음 |
| `notifications.py` | 100 | 없음 | 없음 |
| report views | 100 | 없음 | 없음 |

**Shallow File Count**: 0 / 8 files

### 2.5 Page UI Checklist Verification

| Page | Design Elements | Implemented | Missing | Rate |
|------|:--------------:|:-----------:|:-------:|:----:|
| Email newsletter | masthead, summary, 3 Tier sections, tables, links, guidance | 7 | 0 | 100% |
| Dashboard | Tier badge and reason | 2 | 0 | 100% |
| RFP index/CSV | Tier and reason fields | 2 | 0 | 100% |

**Functional Match Rate**: 100%

### 2.6 API Contract Verification

이 기능은 HTTP API가 아니라 로컬 CLI 계약이다. `python -m rfp_tracker --help`로 `tier`, `tier-audit` 명령 노출을 확인했고, unit tests가 입력·저장·알림 선택을 검증한다.

| # | Contract | CLI | Storage | Result |
|---|----------|:---:|:-------:|:------:|
| 1 | automatic Tier | ✅ | ✅ | PASS |
| 2 | manual Tier preservation | ✅ | ✅ | PASS |
| 3 | immediate Tier 1 filter | ✅ | ✅ | PASS |
| 4 | daily/weekly Tier newsletter | ✅ | ✅ | PASS |

**Contract Match Rate**: 4/4 = 100%

### 2.7 Runtime Verification Results

#### L1: Python unit and CLI tests

| # | Test | Expected | Actual | Pass |
|---|------|----------|--------|:----:|
| 1 | `unittest discover -s tests -v` | all tests pass | 44 / 44 passed | ✅ |
| 2 | `py_compile` | modified modules compile | no errors | ✅ |
| 3 | CLI help | Tier commands exposed | `tier`, `tier-audit` shown | ✅ |

**L1 Score**: 3/3 = 100%

#### L2: Render / email action checks

| # | Target | Action | Expected Result | Pass |
|---|--------|--------|-----------------|:----:|
| 1 | immediate email | fake sender with Tier 1/2/3 data | Tier 1 only | ✅ |
| 2 | daily newsletter | fake sender | masthead, all Tier sections, `border:1px solid #D1D5DB` | ✅ |
| 3 | reports | regenerate dashboard/RFP/briefing/CSV | Tier and reason fields visible | ✅ |

**L2 Score**: 3/3 = 100%

#### L3: Operational data-flow checks

| # | Scenario | Steps | Result | Pass |
|---|----------|:-----:|--------|:----:|
| 1 | existing data backfill | dry-run → `--apply` | 49 metadata updates; raw/review/attachment/delivery preserved | ✅ |
| 2 | classification calibration | inspect proposed Tier 1/2 items | broad matcher false positives moved to Tier 3 | ✅ |
| 3 | delivery safety | actual immediate dry-run | 0 planned / 0 sent | ✅ |
| 4 | weekly layout safety | actual weekly dry-run | 1 planned / 0 sent | ✅ |

**L3 Score**: 4/4 = 100%

**Runtime Match Rate**: 100%

### 2.8 Match Rate Summary

```text
Structural Match Rate:  100%
Functional Match Rate:  100%
Contract Match Rate:    100%
Runtime Match Rate:     100%
Overall Match Rate:     100%

Match: 24 items | Shallow: 0 | Not implemented: 0
```

---

## 3. Code Quality Analysis

### 3.1 Complexity Analysis

| File | Function | Complexity | Status | Recommendation |
|------|----------|------------|--------|----------------|
| `tiering.py` | `assess_innergen_tier` | moderate, ordered rules | ✅ Good | Keep rules explicit and add examples with user feedback |
| `notifications.py` | `_newsletter_html` | moderate, template composition | ✅ Good | Keep HTML email style table-based |
| `storage.py` | `upsert_notice` | moderate, preserves manual Tier | ✅ Good | Preserve integration tests when schema evolves |

### 3.2 Code Smells

| Type | File | Location | Description | Severity |
|------|------|----------|-------------|----------|
| Calibration finding | `tiering.py` | initial audit | broad matched keywords elevated unrelated IT notices | ✅ Resolved by title/category-only sync path |
| Duplicate signal display | `tiering.py` | signal aggregation | `환경영향평가` appeared twice in rationale | ✅ Resolved by de-duplication helper |
| - | - | - | No unresolved code smell found in feature scope | - |

### 3.3 Security Issues

| Severity | File | Issue | Recommendation |
|----------|------|-------|----------------|
| Info | `notifications.py` | HTML receives source title/URL values | `html.escape` is applied before output; keep this path for future fields |
| Info | all | SMTP/API secrets | no secret output or storage was added |
| - | - | no critical issue found | - |

---

## 4. Performance Analysis (if applicable)

Tier evaluation is a small in-memory title check per notice. The operational audit completed 49 notices in roughly one second; no performance bottleneck is indicated at the current scale.

---

## 5. Test Coverage

### 5.1 Coverage Status

| Area | Current | Target | Status |
|------|---------|--------|--------|
| Tier rule examples | 9 representative titles | core Tier 1/2/3/false-positive cases | ✅ |
| Manual override | 1 persistence regression | preserve against refresh | ✅ |
| Notification selection/render | immediate + daily fake sender | no real SMTP | ✅ |
| Existing tracker regression | 44 total unittest cases | all pass | ✅ |

### 5.2 Uncovered Areas

- A real Daum client visual rendering check was intentionally not run to avoid sending a test email to the operational recipient.
- Future feedback should add real anonymized titles that were manually moved between Tiers.

---

## 6. Clean Architecture Compliance

### 6.1 Layer Dependency Verification

| Layer | Expected Dependencies | Actual Dependencies | Status |
|-------|----------------------|---------------------|--------|
| Presentation | application/domain/storage | CLI, reports, email template | ✅ |
| Application | domain/infrastructure | sync and notification dispatch | ✅ |
| Domain | no SQLite/SMTP/CLI | `tiering.py` uses standard library only | ✅ |
| Infrastructure | model data only | `storage.py` persists Notice metadata | ✅ |

### 6.2 Dependency Violations

No violations found in feature scope.

### 6.3 Layer Assignment Verification

| Component | Designed Layer | Actual Location | Status |
|-----------|---------------|-----------------|--------|
| Tier assessment | Domain | `rfp_tracker/tiering.py` | ✅ |
| Tier persistence | Infrastructure | `rfp_tracker/storage.py` | ✅ |
| Sync/audit/override | Application/Presentation | `rfp_tracker/cli.py` | ✅ |
| Newsletter | Presentation | `rfp_tracker/notifications.py` | ✅ |

### 6.4 Architecture Score

```text
Architecture Compliance: 100%
Correct layer placement: 4/4 feature components
Dependency violations: 0
```

---

## 7. Convention Compliance

### 7.1 Naming Convention Check

| Category | Convention | Files Checked | Compliance | Violations |
|----------|------------|:-------------:|:----------:|------------|
| Constants | `UPPER_SNAKE_CASE` | 1 | 100% | - |
| Functions | `snake_case` | 8 | 100% | - |
| Types | `PascalCase` | 2 | 100% | - |
| Stored Tier values | lowercase underscore | 4 | 100% | - |

### 7.2 Folder Structure Check

| Expected Path | Exists | Contents Correct | Notes |
|---------------|:------:|:----------------:|-------|
| `rfp_tracker/tiering.py` | ✅ | ✅ | pure domain rule |
| `docs/01-plan/features/` | ✅ | ✅ | plan |
| `docs/02-design/features/` | ✅ | ✅ | design |
| `docs/03-analysis/` | ✅ | ✅ | this analysis |
| `docs/05-qa/` | ✅ | ✅ | QA report |

### 7.3 Import Order Check

- [x] Standard library imports first
- [x] Local package imports second
- [x] No extra third-party package added

### 7.4 Environment Variable Check

| Variable | Actual | Status |
|----------|--------|--------|
| `DATA_GO_KR_SERVICE_KEY` | untouched | ✅ |
| `SMTP_*` | untouched | ✅ |
| Tier feature variable | none required | ✅ |

### 7.5 Convention Score

```text
Convention Compliance: 100%
```

---

## 8. Overall Score

```text
Overall Score: 100/100 for this feature scope
Design match: 100 | Data safety: 100 | Tests: 100 | Security: 100
```

---

## 9. Recommended Actions

### 9.1 Immediate (within 24 hours)

| Priority | Item | File | Assignee |
|----------|------|------|----------|
| High | Tier 1 5건의 원문/RFP를 사람이 확인 | dashboard/RFP index | 이너젠 담당자 |
| Medium | 다음 17:00 메일의 실제 받은편지함 레이아웃을 확인 | Daum mailbox | 이너젠 담당자 |

### 9.2 Short-term (within 1 week)

| Priority | Item | File | Expected Impact |
|----------|------|------|-----------------|
| Medium | 수동 Tier 변경 사례를 축적 | SQLite / `tier` CLI | 규칙 정확도 향상 |
| Medium | Tier 2 고객사 추천 여부를 review note로 기록 | dashboard | 추천 파이프라인 관리 |

### 9.3 Long-term (backlog)

| Item | File | Notes |
|------|------|-------|
| RFP 본문 요약 보조 | source-specific document adapters | 공개 접근 가능한 첨부만 대상으로 함 |
| Tier feedback dashboard filter | HTML dashboard | Tier별 버튼/집계 추가 가능 |

---

## 10. Design Document Updates Needed

- [x] 초기 설계의 “수집 키워드 보조” 가정은 실제 검증 결과에 따라 제목·카테고리 중심의 보수적 판단으로 구현했다.
- [ ] 사내 수동 보정 사례가 충분해지면 이너젠 고유 용어집을 별도 설정 파일로 분리한다.

---

## 11. Next Steps

- [x] Tier metadata 및 newsletters 구현
- [x] regression/operational QA
- [x] completion report 작성
- [ ] 다음 수신 메일의 실제 화면 확인 후 필요 시 색상/열 폭만 미세 조정

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-21 | Tier/newletter implementation analysis | Codex |
