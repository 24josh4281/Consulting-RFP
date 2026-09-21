# 이너젠 적합성 Tier 분류 및 뉴스레터 개선 계획

> **Summary**: 수집 공고를 이너젠의 실제 컨설팅 적합도에 따라 Tier 1~3으로 분리하고, 즉시 알림과 일일·주간 메일을 읽기 쉬운 전문 브리핑으로 전환한다.
>
> **Project**: Climate/GHG/ETS RFP Tracker
> **Version**: 현재 로컬 작업본
> **Author**: Codex
> **Date**: 2026-09-21
> **Status**: Complete

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 점수만으로는 이너젠이 직접 제안할 컨설팅, 고객사에 추천할 설비 사업, 단순 참고 공고가 섞여 메일의 판단 속도와 가독성이 떨어진다. |
| **Solution** | 공고 원문과 검토 상태를 보존한 채 `business_tier`를 별도로 저장하고, 명시된 사업 범위 규칙으로 자동 분류하며 사람이 언제든 보정할 수 있게 한다. |
| **Function/UX Effect** | Tier 1은 즉시 알림의 대상이 되고, 일일·주간 메일은 Tier별 테두리 표와 우선순위 요약을 갖춘 뉴스레터가 된다. |
| **Core Value** | 첫 화면과 메일에서 “이너젠이 지금 검토할 공고”와 “고객사 추천/참고 공고”를 즉시 구분할 수 있다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 기후 관련 키워드가 있는 공고 전체가 아니라, 이너젠의 컨설팅 기회 중심으로 운영하기 위해서다. |
| **WHO** | 이너젠의 입찰·컨설팅 담당자와 고객사 추천 업무 담당자다. |
| **RISK** | 공고 제목만으로 업무 성격을 완벽하게 알 수 없어 자동 Tier가 틀릴 수 있다. |
| **SUCCESS** | Tier 1만 즉시 통지하고, Tier별 근거·수동 보정·테두리 있는 뉴스레터를 제공하며 기존 원문/발송 기록을 보존한다. |
| **SCOPE** | 분류 규칙 → SQLite 메타데이터 → CLI 보정/일괄 분류 → 대시보드·RFP 인덱스·뉴스레터 → 테스트/실데이터 검증. |

---

## 1. Overview

### 1.1 Purpose

이너젠에 맞는 컨설팅 기회를 Tier 1로 먼저 보여 주고, 고객사 추천 가능 사업(Tier 2)과 단순 참고 공고(Tier 3)를 분리한다. 이 분류는 입찰 자격이나 수주 가능성을 확정하지 않으며, 원문 RFP/과업지시서 검토를 대체하지 않는다.

### 1.2 Background

현재 추적기는 기후·온실가스·배출권 키워드를 넓게 수집한다. 이는 놓침을 줄이는 데 유용하지만 순수 과학, 행사, 투자, 시설·설비 사업까지 같은 흐름으로 보이므로 실제 제안 검토에 불필요한 부담을 준다.

### 1.3 Related Documents

- 기존 나라장터 정밀화 계획: [g2b-title-precision-and-rfp-access.plan.md](g2b-title-precision-and-rfp-access.plan.md)
- 기존 나라장터 정밀화 설계: [g2b-title-precision-and-rfp-access.design.md](../../02-design/features/g2b-title-precision-and-rfp-access.design.md)
- 소스 상태: [SOURCE_CATALOG_STATUS.md](../../SOURCE_CATALOG_STATUS.md)

---

## 2. Scope

### 2.1 In Scope

- [x] Tier 1: 기후변화 산업, 온실가스 외부사업, ETS, Scope 1·2·3 산정 고도화, 산업계 시나리오 분석, 관련 컨설팅·연구 과제를 자동 식별한다.
- [x] Tier 2: 기후·온실가스·배출권 관련 설비·시설·플랫폼·환경개선 사업을 고객사 추천 후보로 분리한다.
- [x] Tier 3: 행사·영상·투자·캠페인·교육·순수 과학 등 직접 컨설팅과 거리가 있는 공고를 참고군으로 분리한다.
- [x] 자동 분류 근거, 자동/수동 분류 출처, 분류 시각을 SQLite에 저장한다.
- [x] Tier 1 즉시 알림과 Tier 1/2/3 분리형 일일·주간 HTML 뉴스레터를 구현한다.
- [x] 대시보드, RFP 문서 인덱스, CSV, 브리핑에 Tier를 표시한다.
- [x] 기존 저장 공고를 삭제하지 않고 일괄 분류하는 안전한 명령을 제공한다.

### 2.2 Out of Scope

- 원문 RFP를 읽어 입찰 적합성·수주 가능성·가격을 자동 확정하지 않는다.
- 로그인, CAPTCHA, 접근 제한을 우회하거나 보호된 파일을 수집하지 않는다.
- 실제 SMTP 발송으로 디자인을 시험하지 않는다. 단위 테스트의 가짜 발송기와 dry-run만 사용한다.
- 사용자 승인 없이 Git 커밋·푸시하지 않는다.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 각 공고에 `tier_1`, `tier_2`, `tier_3`, `unclassified` 중 하나와 분류 근거를 저장한다. | High | Complete |
| FR-02 | 수집 시 자동 분류하고, 기존 공고는 별도 감사 명령으로 안전하게 채운다. | High | Complete |
| FR-03 | 사람이 공고 ID별 Tier와 근거를 수동 변경할 수 있으며, 후속 자동 수집은 수동 결정을 덮어쓰지 않는다. | High | Complete |
| FR-04 | 즉시 알림은 Tier 1만 발송한다. | High | Complete |
| FR-05 | 일일·주간 메일은 Tier 1, Tier 2, Tier 3을 각각 분리하여 보여 준다. | High | Complete |
| FR-06 | HTML 메일은 헤더, 요약 카드, 명확한 Tier 라벨, 테두리 있는 표/카드, 원문·문서 링크를 가진다. | High | Complete |
| FR-07 | 대시보드·문서 인덱스·CSV·브리핑에서 Tier와 근거를 확인할 수 있다. | Medium | Complete |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Data safety | 원문 JSON, 첨부, 검토 상태, 발송 기록은 변경·삭제하지 않는다. | 마이그레이션/일괄 분류 전후 레코드 및 테스트 확인 |
| Explainability | 자동 분류 결과마다 사람이 읽을 수 있는 한국어 근거를 남긴다. | Tier 단위 테스트 및 실제 DB 표본 확인 |
| Reliability | 수동 Tier는 후속 sync에서 보존된다. | SQLite upsert 테스트 |
| Email compatibility | 테두리는 인라인 CSS와 표 속성으로 표현한다. | HTML 문자열 단위 테스트 및 dry-run 미리보기 |
| Security | HTML에 공고 제목·URL을 출력할 때 이스케이프한다. | 기존 escape 경로 유지 및 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [x] 지정한 예시군이 Tier 1/2/3으로 기대대로 분류된다.
- [x] 수동으로 조정한 Tier가 다음 수집에서 보존된다.
- [x] 즉시 알림 후보가 Tier 1로 제한된다.
- [x] 일일·주간 이메일 미리보기에 세 Tier와 테두리 있는 표가 보인다.
- [x] 실제 DB의 기존 공고가 원문 보존 상태로 재분류되고 보고서가 다시 생성된다.
- [x] 전체 Python 테스트와 컴파일 검사가 통과한다.

### 4.2 Quality Criteria

- [x] 기존 `needs_review`, `not_relevant`, `closed` 알림 제외 규칙을 유지한다.
- [x] SMTP 실제 전송을 새로 만들거나 중복 전송하지 않는다.
- [x] 대시보드/CSV/문서 인덱스의 기존 열과 링크가 유지된다.

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 제목이 짧거나 모호해 Tier가 부정확함 | Medium | High | Tier 근거를 표시하고 `tier` CLI로 수동 보정하며 자동 수집은 수동 보정을 보존한다. |
| “연구”가 순수 과학과 정책/산업 컨설팅에 모두 등장함 | Medium | Medium | 기후·GHG·ETS·산업 시나리오 신호와 함께 있을 때만 Tier 1 연구로 본다. |
| 투자/행사 제목에 탄소중립 키워드가 있어 Tier 1로 오인됨 | High | Medium | 행사·영상·투자·펀드·교육 신호는 Tier 3 우선 규칙으로 둔다. |
| 새 뉴스레터 CSS가 메일 클라이언트마다 다르게 보임 | Medium | Medium | 표 기반 레이아웃과 인라인 테두리 스타일을 사용한다. |
| 자동 재분류가 사용자 판단을 덮어씀 | High | Low | `tier_source=manual`을 저장하고 자동 upsert/audit에서 제외한다. |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `notices` | SQLite schema | Tier, 근거, 출처, 시각 열을 추가한다. |
| `Notice` | Python data model | Tier 메타데이터를 저장한다. |
| `rfp_tracker.tiering` | Domain rule module | 이너젠 사업 범위용 순수 분류 규칙을 둔다. |
| `storage.py` | Persistence/query | 자동/수동 Tier 보존, 일괄 갱신, Tier별 즉시알림 필터를 지원한다. |
| `notifications.py` | Email presentation | Tier별 대상과 뉴스레터 렌더링을 전환한다. |
| `briefing.py`, `render.py`, `documents.py`, `cli.py` | Reports/CLI | Tier를 표시하고 보정·감사 명령을 제공한다. |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `notices` | CREATE/UPDATE | `cli.sync_command → storage.upsert_notice` | Tier 자동 부여와 수동 보존을 검증한다. |
| `notices` | READ | `storage.list_notices → briefing/render/export` | 새 열이 없어도 기존 보고서가 깨지지 않게 한다. |
| `notices` | READ | `list_notices_since`, `list_unnotified_notices → notifications.dispatch_notifications` | 즉시 알림의 Tier 1 제한을 검증한다. |
| `notices` | UPDATE | `review`, `g2b-title-audit` | 기존 검토 상태와 새 Tier를 독립적으로 유지한다. |
| `notification_deliveries` | CREATE/READ | `dispatch_notifications` | 중복 방지 키·발송 이력은 변경하지 않는다. |
| `attachments` | READ | 문서 인덱스·메일 | 첨부 수와 원문 링크는 그대로 보여 준다. |

### 6.3 Verification

- [ ] 모든 기존 SQL 조회가 추가 열과 호환되는지 확인한다.
- [ ] 수동 Tier, review_status, raw_json, notification_deliveries 보존을 테스트한다.
- [ ] 실제 데이터베이스 일괄 분류 후 공고 수와 발송 이력이 유지되는지 확인한다.

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 Python 패키지·SQLite·HTML 리포트 | 현 RFP 추적기 | ☑ |
| **Dynamic** | 웹 앱·BaaS 통합 | 향후 다중 사용자 포털 | ☐ |
| **Enterprise** | 마이크로서비스·엄격한 계층 | 대규모 상용 플랫폼 | ☐ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 분류 위치 | fetcher별 규칙 / sync 공통 규칙 / 외부 AI | sync 공통 순수 규칙 | 모든 출처에 일관되게 적용하고 테스트하기 쉽다. |
| 저장 방식 | review_status 재활용 / 별도 Tier 열 | 별도 Tier 열 | 수집 적합성·사람 검토 상태·사업 적합성을 혼동하지 않는다. |
| 수동 보정 | 메모만 기록 / 별도 CLI + 출처 | CLI + `tier_source` | 다음 자동 수집에서 의사결정이 보존된다. |
| 메일 구조 | 기존 단일 표 / CSS 카드만 / 표 기반 뉴스레터 | 표 기반 뉴스레터 | Daum 등 메일 클라이언트에서 안정적으로 보인다. |
| Testing | 수동 SMTP 테스트 / unittest 가짜 발송기 | unittest 가짜 발송기 | 실제 수신자에게 테스트 메일을 보내지 않는다. |

### 7.3 Clean Architecture Approach

```text
Selected Level: Starter (existing Python package)

rfp_tracker/
├── tiering.py          # 이너젠 사업 적합성 규칙 (순수 함수)
├── models.py           # Notice Tier 메타데이터
├── storage.py          # SQLite 보존/조회
├── notifications.py    # 대상 선택 + 뉴스레터 표현
└── cli.py              # sync / tier / tier-audit
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] Python 표준 라이브러리 중심의 낮은 의존성 구조
- [x] `tests/test_keyword_matcher.py`의 `unittest` 기반 회귀 테스트
- [x] Windows PowerShell 실행 스크립트
- [x] `.env` 비밀값은 Git 추적 제외

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|----------|
| Naming | Exists | Tier 값은 `tier_1`, `tier_2`, `tier_3`, `unclassified`로 고정 | High |
| Folder structure | Exists | 순수 업무 규칙은 `rfp_tracker/tiering.py`에 둔다 | High |
| Error handling | Exists | 알 수 없는 수동 Tier는 CLI에서 거부한다 | High |
| Email HTML | Partial | 외부 값은 escape, 표 셀에 테두리 스타일을 명시한다 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `DATA_GO_KR_SERVICE_KEY` | 나라장터 목록 수집 | Local runtime | ☐ (existing) |
| `SMTP_*` | 알림·브리핑 전송 | Local runtime | ☐ (existing) |
| 신규 환경 변수 | 없음 | N/A | ☐ |

### 8.4 Pipeline Integration

| Phase | Status | Document Location | Command |
|-------|:------:|-------------------|---------|
| Schema | Feature-local | This plan / SQLite migration | N/A |
| Convention | Existing | Python package/tests | N/A |

---

## 9. Next Steps

1. [x] Tier 기준과 알림 운영 원칙을 확정한다.
2. [x] 설계 문서를 작성하고, 실용적 분리형 옵션을 적용한다.
3. [x] 규칙·마이그레이션·뉴스레터를 구현한다.
4. [x] 단위 테스트·dry-run·실데이터 재분류를 검증한다.
5. [x] 완료 보고서를 작성한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-21 | Initial plan based on the user's Tier definitions | Codex |
