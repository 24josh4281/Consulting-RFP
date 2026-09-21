# 이너젠 적합성 Tier 분류 및 뉴스레터 개선 설계

> **Summary**: 공고의 수집 적합성과 별도로 이너젠 사업 적합 Tier를 저장하고, Tier 1 중심의 알림·뉴스레터를 제공한다.
>
> **Project**: Climate/GHG/ETS RFP Tracker
> **Version**: 현재 로컬 작업본
> **Author**: Codex
> **Date**: 2026-09-21
> **Status**: Implemented — QA PASS
> **Planning Doc**: [innergen-tiering-and-newsletter.plan.md](../../01-plan/features/innergen-tiering-and-newsletter.plan.md)

### Pipeline References (if applicable)

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | SQLite migration in this design | N/A |
| Phase 2 | Existing Python conventions/tests | N/A |
| Phase 3 | Email HTML layout | N/A |
| Phase 4 | CLI interface | N/A |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 기후 키워드 전체가 아닌 이너젠 컨설팅 기회 중심으로 검토 우선순위를 정한다. |
| **WHO** | 이너젠의 입찰·컨설팅 담당자와 고객사 추천 담당자다. |
| **RISK** | 제목만으로 잘못 분류할 수 있으므로 근거와 수동 보정을 제공한다. |
| **SUCCESS** | Tier 1 즉시 알림, Tier별 뉴스레터, 수동 Tier 보존, 기존 원문·발송 이력 보존. |
| **SCOPE** | Rule module, SQLite migration, CLI, report views, email template, tests, existing-data audit. |

---

## 1. Overview

### 1.1 Design Goals

- 수집 관련성(`relevance_score`), 검토 상태(`review_status`), 이너젠 사업 적합성(`business_tier`)을 독립시킨다.
- 특정 출처가 아닌 모든 수집 공고에 같은 Tier 기준을 적용한다.
- 자동 분류는 설명 가능하고, 사용자의 수동 결정은 안정적으로 보존한다.
- Daum 같은 일반 메일 클라이언트에서도 읽히도록 표 기반 HTML을 사용한다.

### 1.2 Design Principles

- 원문 보존: 공고 원문, 첨부, 검토/발송 기록은 삭제하거나 바꾸지 않는다.
- 사람 우선: 자동 Tier는 검토 보조이며, 수동 보정이 우선한다.
- 보수적 알림: 즉시 알림은 Tier 1만 보낸다.
- 설명 가능성: 각 Tier에 한국어 근거를 남긴다.

---

## 2. Architecture Options (v1.7.0)

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | `review_status`에 Tier 문자열을 섞음 | 별도 service/repository 계층과 정책 파일 전면 분리 | 별도 순수 규칙 모듈 + SQLite 메타데이터 + 기존 CLI/메일 재사용 |
| **New Files** | 0 | 4+ | 3 문서/모듈 |
| **Modified Files** | 3 | 8+ | 7~8 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | High (기존 상태 혼동) | Low (범위 과다) | Low (기존 흐름 보존) |
| **Recommendation** | 비추천 | 향후 상용 멀티테넌트 전환 시 | **선택** |

**Selected**: **Option C — Pragmatic Balance**. 사용자가 정의한 운영 규칙을 빠르게 적용하되, `tiering.py`에 규칙을 고립해 향후 이너젠의 피드백으로 안전하게 조정한다. 사용자의 “이렇게 나눠서 해줘” 요청을 이 범위의 구현 승인으로 반영한다.

### 2.1 Component Diagram

```text
공개 출처 수집
       │ Notice
       ▼
sync_command ──► assess_innergen_tier() ──► storage.upsert_notice()
                                                    │
               ┌────────────────────────────────────┼───────────────────────────────────┐
               ▼                                    ▼                                   ▼
        immediate (Tier 1)            daily/weekly (Tier 1/2/3)          dashboard / RFP index / CSV
```

### 2.2 Data Flow

```text
공고 제목·카테고리·매칭 키워드
    → Tier 3 제외 신호 우선 확인
    → Tier 1 컨설팅/정책·GHG·ETS 신호 확인
    → Tier 2 설비·시설·환경개선 신호 확인
    → Tier + 한국어 근거 + automatic 저장
    → 수동 보정 시 manual 저장 및 자동 덮어쓰기 방지
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|------------|---------|
| `tiering.py` | Python standard library | 순수 업무 규칙 평가 |
| `storage.py` | `Notice`, sqlite3 | Tier 마이그레이션·보존·조회 |
| `cli.py` | tiering, storage | sync 자동평가·수동 보정·audit |
| `notifications.py` | briefing view, storage | Tier별 대상과 HTML 뉴스레터 |
| reports | storage/briefing | Tier 및 근거 표시 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
@dataclass(slots=True)
class TierAssessment:
    tier: str                 # tier_1 | tier_2 | tier_3 | unclassified
    reason: str               # 사람이 읽는 한국어 근거
    matched_signals: list[str]

@dataclass(slots=True)
class Notice:
    # existing collection and review fields ...
    business_tier: str = "unclassified"
    tier_reason: str = ""
    tier_source: str = "automatic"  # automatic | manual
    tiered_at: str = ""
```

### 3.2 Entity Relationships

```text
notices (1) ── (N) attachments
   │
   └── business_tier / tier_reason / tier_source / tiered_at

notification_deliveries → notices.id (existing, unchanged)
```

### 3.3 Database Schema (if applicable)

```sql
ALTER TABLE notices ADD COLUMN business_tier TEXT NOT NULL DEFAULT 'unclassified';
ALTER TABLE notices ADD COLUMN tier_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE notices ADD COLUMN tier_source TEXT NOT NULL DEFAULT 'automatic';
ALTER TABLE notices ADD COLUMN tiered_at TEXT;
CREATE INDEX IF NOT EXISTS idx_notices_business_tier
ON notices(business_tier, review_status, relevance_score);
```

`connect()`에서 열 존재 여부를 확인하는 마이그레이션을 수행한다. 기존 행은 `unclassified`로 시작하며, `tier-audit --apply`가 자동 Tier만 채운다. `tier_source=manual` 행은 audit/sync가 바꾸지 않는다.

---

## 4. API Specification

이 프로젝트는 로컬 CLI가 운영 인터페이스다.

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| CLI | `sync` | 수집 시 자동 Tier를 평가한다. | Local workspace |
| CLI | `tier-audit --apply` | 기존 공고를 삭제 없이 자동 Tier로 채운다. | Local workspace |
| CLI | `tier --id N --tier tier_1 --reason ...` | 사람이 Tier와 근거를 보정한다. | Local workspace |
| CLI | `notifications dispatch` | Tier별 이메일을 preview/send 한다. | SMTP configuration |

### 4.2 Detailed Specification

#### `tier --id <id> --tier <tier> --reason <text>`

**Request (CLI):**

```text
python -m rfp_tracker tier --db data\rfp_tracker_official.db --id 4 --tier tier_1 --reason "ETS 시스템 고도화 컨설팅 기회"
```

**Response:**

```text
[done] Notice 4 classified as tier_1 (manual)
```

**Error Responses:**

- `2`: 허용하지 않는 Tier 값 또는 빈 수동 근거
- `1`: 존재하지 않는 공고 ID

---

## 5. UI/UX Design (if applicable)

### 5.1 Screen Layout

```text
┌─ INNERGEN CLIMATE INTELLIGENCE ───────────────────┐
│ 기후·탄소 입찰 브리핑 / 기준시각 / 수집 범위       │
├─────────┬─────────┬─────────┐
│ Tier 1  │ Tier 2  │ Tier 3  │    ← 요약 카드
├───────────────────────────────────────────────────┤
│ Tier 1 — 이너젠 직접 컨설팅 검토 (테두리 표)       │
├───────────────────────────────────────────────────┤
│ Tier 2 — 고객사 추천 가능 사업 (테두리 표)         │
├───────────────────────────────────────────────────┤
│ Tier 3 — 참고 / 직접 컨설팅 비적합 (테두리 표)     │
└───────────────────────────────────────────────────┘
```

### 5.2 User Flow

```text
즉시 수집 → Tier 1이면 즉시 알림 → 담당자 원문/RFP 확인
일일·주간 → Tier 1 우선 검토 → Tier 2 고객사 추천 → Tier 3 참고/제외
잘못된 Tier → CLI 수동 보정 → 이후 자동 수집에서 보존
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| Tier badge | `render.py`, `documents.py` | 공고의 적합성 레이블 표시 |
| Newsletter masthead | `notifications.py` | 메일 정체성과 기준 시각 표시 |
| KPI summary table | `notifications.py` | Tier별 건수와 행동 우선순위 표시 |
| Tier section table | `notifications.py` | 공고·마감·근거·RFP·원문을 테두리 표로 표시 |

### 5.4 Page UI Checklist (v2.1.0)

#### 이메일 뉴스레터

- [x] Masthead: `INNERGEN CLIMATE INTELLIGENCE` 및 브리핑 종류
- [x] Summary: 전체와 Tier 1/2/3 건수
- [x] Tier 1 표: 제목, 출처/발주처, 마감, 분류 근거, 문서, 원문
- [x] Tier 2 표: 고객사 추천 안내와 동일 열
- [x] Tier 3 표: 참고·직접 컨설팅 비적합 안내와 동일 열
- [x] 각 표와 카드에 실제 테두리 스타일
- [x] 원문 및 수집 문서 URL
- [x] 사람이 원문/RFP를 확인해야 한다는 면책·검토 안내

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | Message | Cause | Handling |
|------|---------|-------|----------|
| 1 | Notice id not found | 없는 공고 ID | ID를 확인하도록 안내 |
| 2 | Unknown tier | 허용되지 않는 Tier | `tier_1`, `tier_2`, `tier_3`, `unclassified` 중 선택하도록 안내 |
| 2 | Manual reason required | 수동 조정 근거 없음 | 검토 가능한 짧은 근거를 요구 |
| N/A | Empty Tier section | 해당 기간 공고 없음 | 뉴스레터에 빈 상태 문구 표시 |

### 6.2 Error Response Format

```text
[error] Unknown tier: tier_one. Allowed: tier_1, tier_2, tier_3, unclassified
```

---

## 7. Security Considerations

- [x] 공고 제목, 발주처, URL은 HTML escape한다.
- [x] SMTP 비밀번호·API 키는 뉴스레터, CLI 출력, 보고서에 포함하지 않는다.
- [x] 외부 URL은 수집된 원문 또는 공개 첨부 URL만 사용한다.
- [x] 수동 보정은 로컬 작업공간 명령으로만 수행한다.
- [x] 실제 SMTP 전송은 기존 `--send` 명시 호출에서만 수행한다.

---

## 8. Test Plan (v2.3.0)

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1: Rule tests | Tier 분류 우선순위·수동 보존 | Python `unittest` | Do |
| L1: Storage tests | SQLite migration/upsert/audit | Python `unittest` | Do |
| L2: Email render tests | Tier 섹션, 테두리, HTML escape | Python `unittest` | Do |
| L3: Operational dry run | 실제 DB audit/report/preview | CLI (no `--send`) | Check |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Method | Test Description | Expected Status | Expected Response |
|---|----------|--------|-----------------|:--------------:|-------------------|
| 1 | `tiering.assess` | function | Scope 3 산정 컨설팅 | 0 | `tier_1` |
| 2 | `tiering.assess` | function | 대기배출 플랫폼·설비 지원 | 0 | `tier_2` |
| 3 | `tiering.assess` | function | 탄소중립 펀드 투자유치/행사 | 0 | `tier_3` |
| 4 | `storage.upsert` | function | manual Tier 후 재수집 | 0 | manual 값 보존 |
| 5 | `notifications.dispatch` | function | immediate 후보에 Tier 2 혼합 | 0 | Tier 1만 가짜 발송 |

### 8.3 L2: UI Action Test Scenarios

| # | Page | Action | Expected Result | Data Verification |
|---|------|--------|----------------|-------------------|
| 1 | Newsletter | Tier 1/2/3 혼합 payload 생성 | 세 제목/라벨과 테두리 표가 존재 | 각 공고의 근거와 원문 링크가 출력 |
| 2 | Dashboard | HTML 생성 | Tier badge/근거 열이 존재 | SQLite Tier와 일치 |
| 3 | Document index | HTML/CSV 생성 | Tier/근거 열이 존재 | 원문/RFP 링크 유지 |

### 8.4 L3: E2E Scenario Test Scenarios

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|------------------|
| 1 | 기존 데이터 보강 | `tier-audit` dry-run → `--apply` → reports | 공고 수/원문/발송 이력 보존, Tier 건수 출력 |
| 2 | 메일 안전성 | test DB + fake sender | 실제 SMTP 호출 없이 대상과 HTML을 검증 |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:------------:|---------------------|
| Notice | 5 | Tier 1/2/3 제목, source, score, URL, first_seen_at |
| Notice (manual) | 1 | `tier_source=manual`, 수동 근거 |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| Presentation | CLI·HTML·email output | `cli.py`, `render.py`, `documents.py`, `notifications.py` |
| Application | sync orchestration and notification dispatch | `cli.py`, `notifications.py` |
| Domain | Tier definitions and rules | `tiering.py`, `models.py` |
| Infrastructure | SQLite and SMTP | `storage.py`, existing SMTP code |

### 9.2 Dependency Rules

```text
Presentation ──► Application ──► Domain
      │                    │
      └────────────────────┴──► Infrastructure

tiering.py is pure: it must not import sqlite3, SMTP, or CLI modules.
```

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|------------|---------------|
| `tiering.py` | dataclasses, typing, re | storage/notifications/CLI |
| `storage.py` | models | notifications/CLI |
| `notifications.py` | briefing view, storage | CLI |
| `cli.py` | all feature modules | N/A |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| Tier assessment | Domain | `rfp_tracker/tiering.py` |
| Notice metadata | Domain | `rfp_tracker/models.py` |
| Tier persistence | Infrastructure | `rfp_tracker/storage.py` |
| Sync/audit/override | Application/Presentation | `rfp_tracker/cli.py` |
| Newsletter | Presentation | `rfp_tracker/notifications.py` |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| Target | Rule | Example |
|--------|------|---------|
| Constants | `UPPER_SNAKE_CASE` | `TIER_1`, `VALID_BUSINESS_TIERS` |
| Functions | `snake_case` | `assess_innergen_tier()` |
| Data class | `PascalCase` | `TierAssessment` |
| Stored enum | lowercase underscore | `tier_1`, `unclassified` |

### 10.2 Import Order

1. Python standard library
2. Local package imports
3. No added third-party dependencies

### 10.3 Environment Variables

| Prefix | Purpose | Scope | Example |
|--------|---------|-------|---------|
| `DATA_GO_KR_` | 나라장터 수집 | Local runtime | `DATA_GO_KR_SERVICE_KEY` |
| `SMTP_` | 이메일 전송 | Local runtime | `SMTP_HOST` |

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| Classification reasons | 한국어 한 문장 + 매칭 신호 |
| Manual values | `tier_source=manual`로 명시 |
| HTML mail | `<table role="presentation">` + 인라인 border |
| Tests | `unittest` temp SQLite + fake sender |

---

## 11. Implementation Guide

### 11.1 File Structure

```text
rfp_tracker/
├── tiering.py                         # new
├── models.py                          # modified
├── storage.py                         # modified
├── cli.py                             # modified
├── notifications.py                   # modified
├── briefing.py / render.py / documents.py  # modified
└── tests/test_keyword_matcher.py      # extended
```

### 11.2 Implementation Order

1. [x] Tier constants/rules and `Notice` metadata를 추가한다.
2. [x] SQLite migration/upsert/manual override/audit를 구현한다.
3. [x] sync에 자동 분류를 연결하고, report views에 표시한다.
4. [x] immediate Tier 1 필터와 newsletter HTML을 구현한다.
5. [x] 단위 테스트, dry-run, 실제 데이터 audit/report를 수행한다.

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| Domain + storage | `module-1` | Tier 규칙, DB 마이그레이션, 수동 보정 | 1 |
| Reporting + email | `module-2` | dashboard/RFP/CSV/뉴스레터 | 1 |
| QA + operational audit | `module-3` | tests, dry-run, existing DB classification | 1 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `module-1` | 1 |
| Session 2 | Do | `module-2` | 1 |
| Session 3 | Check + Report | `module-3` | 1 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-21 | Selected pragmatic Tier + newsletter design | Codex |
