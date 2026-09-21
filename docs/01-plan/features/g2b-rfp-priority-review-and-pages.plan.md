---
template: plan
version: 1.3
---

# G2B RFP Priority Review and Pages Planning Document

> **Summary**: 나라장터 공식 첨부 링크를 복원하고, Tier 1 우선 검토와 내부 입찰 적합성 검토표를 제공하며, 민감 정보를 제외한 읽기 전용 공개 대시보드를 배포한다.
>
> **Project**: Consulting-RFP
> **Version**: Local working tree
> **Author**: Codex
> **Date**: 2026-09-21
> **Status**: In progress

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 나라장터 44건 중 다수는 원본 API 응답에 첨부 URL이 있어도 추적 DB의 첨부 목록으로 연결되지 않아 RFP·과업지시서 확인 범위가 작다. Tier 1에는 샘플도 섞여 있어 실제 우선 검토 대상이 불분명하다. |
| **Solution** | 원본 API의 `ntceSpecDocUrlN/ntceSpecFileNmN` 필드를 안전하게 backfill하고, 별도 적합성 검토 저장소와 Tier 1 우선 검토 뷰를 추가한다. 공개 Pages는 민감한 내부 판단을 제거한 정적 스냅샷으로 만든다. |
| **Function/UX Effect** | 담당자는 공식 RFP 링크와 원문 요약을 더 많이 확인하고, Excel에서 입찰 적합성·자격·투입인력·bid/no-bid 의견을 기록할 수 있다. 어느 컴퓨터에서도 공개 링크로 공공 공고 스냅샷을 열 수 있다. |
| **Core Value** | 공공 원문과 내부 영업 판단을 분리하여 정보 접근성을 높이면서도 이너젠의 검토 메모와 인력계획을 공개하지 않는다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 실제 입찰 기회를 원문 근거로 빠르게 선별하고, 내부 bid/no-bid 판단을 안전하게 관리한다. |
| **WHO** | 이너젠의 기후·GHG·ETS 입찰 검토 담당자와 공개 공고 현황을 확인하는 브라우저 사용자이다. |
| **RISK** | 나라장터 첨부는 파일 형식·공개 접근성마다 다르고, 내부 자격·인력·입찰 의견을 공개하면 영업정보가 노출될 수 있다. |
| **SUCCESS** | 원본 API에 이미 있는 공개 첨부 URL을 모두 연결하고, 실제 공식 Tier 1을 우선 표시하며, 내부 적합성 검토표와 공개 Pages를 분리해 검증한다. |
| **SCOPE** | G2B attachment backfill, public HWPX extraction, priority view, bid-fit storage/Excel, sanitized Pages build, Git push and Pages workflow이다. |

---

## 1. Overview

### 1.1 Purpose

누락으로 보이던 나라장터 RFP·과업지시서 링크를 기존 수집 원본에서 복원하고, 이너젠의 실제 입찰 검토 흐름을 한 화면·한 Excel 검토표로 강화한다. 동시에 공공 정보만 담은 URL을 GitHub Pages로 제공한다.

### 1.2 Background

현 DB에는 나라장터 44건, GIR 2건, 샘플 3건이 있다. 나라장터 원본 JSON을 점검한 결과 37개 공고에 `ntceSpecDocUrlN`과 `ntceSpecFileNmN`이 있으며, 직접 공개 HWPX URL은 응답 200 및 HWPX ZIP 시그니처를 확인했다. Tier 1 5건 중 실제 공식 소스는 GIR 2건이고 샘플 3건은 실제 기회로 우선 처리하면 안 된다.

### 1.3 Related Documents

- Existing workbench: `docs/04-report/features/rfp-workbench-and-document-extraction.report.md`
- Existing source readiness: `docs/04-report/features/g2b-title-precision-and-rfp-access.report.md`
- Operating guide: `docs/OPERATIONS.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] G2B raw JSON의 `ntceSpecDocUrlN/ntceSpecFileNmN`을 `attachments`에 중복 없이 backfill한다.
- [ ] 직접 공개 HWPX를 기존 evidence-first 추출기로 처리한다.
- [ ] Tier 1 공식 소스를 샘플·미확인 레코드와 분리한 우선 검토 패널과 필터를 제공한다.
- [ ] 원본 공고와 별도인 `bid_fit_reviews`에 적합성·자격·투입인력·입찰 의견·위험·메모를 저장한다.
- [ ] 내부 HTML 상세와 Excel `입찰적합성검토` 시트에 저장된 검토값을 표시한다.
- [ ] 공공 원문 정보만 포함한 `site/index.html`을 만든다.
- [ ] GitHub Pages Actions workflow, 테스트, 문서, 검증된 Git push를 수행한다.

### 2.2 Out of Scope

- 나라장터 로그인·CAPTCHA·권한 제한 다운로드 우회.
- RFP에서 확인되지 않은 금액·자격·범위의 추측.
- 공개 Pages에 내부 review note, 적합성, 예상 투입인력, bid/no-bid 의견, 비밀키를 포함.
- 메일 발송 또는 SMTP 설정 변경.
- 공고 원문·원본 금액·Tier 분류를 적합성 검토 입력으로 덮어쓰기.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | G2B raw JSON의 공개 첨부 URL과 파일명을 attachment로 복원한다. | High | Pending |
| FR-02 | 첨부가 생긴 공고의 낡은 `missing_document_url` 파생 상태를 정확히 해소한다. | High | Pending |
| FR-03 | Tier 1 공식 공고를 원문 확인 여부·마감·검토상태와 함께 우선 표시한다. | High | Pending |
| FR-04 | 샘플/placeholder는 실제 우선 기회와 분리 표시한다. | High | Pending |
| FR-05 | 공고별 입찰 적합성·필요 자격·예상 투입인력·입찰 의견·위험/메모를 원문과 분리해 저장한다. | High | Pending |
| FR-06 | Excel에 편집 가능한 입찰적합성검토 시트와 목록 필터를 제공한다. | High | Pending |
| FR-07 | 공개 사이트는 내부 판단을 제거하고 공개 공고·공식 링크·원문 근거만 표시한다. | High | Pending |
| FR-08 | GitHub Pages workflow를 커밋·푸시하고 외부 URL을 검증한다. | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Traceability | 첨부 URL은 G2B raw JSON의 file name/URL 쌍에서만 생성한다. | unit test, sample DB backfill check |
| Safety | fit review는 별도 table이며 notices/attachments를 바꾸지 않는다. | source row preservation test |
| Confidentiality | 공개 payload/site에서 internal review fields와 credential names/value가 없다. | payload/HTML security assertions |
| Usability | Tier 1 우선 검토와 Excel review fields가 명확하게 분리된다. | HTML structure, workbook render |
| Deployability | Pages workflow가 생성되고 public repo push 후 deployment URL을 확인한다. | Git/GitHub Actions and HTTP check |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] G2B raw attachment backfill tests and actual DB backfill pass.
- [ ] Public direct HWPX is processed without accessing protected sources.
- [ ] 공식 Tier 1 우선 검토 목록과 샘플 분리가 화면에서 확인된다.
- [ ] 적합성 검토표는 Excel에서 입력 가능하고 local payload에 보존된다.
- [ ] public site does not include `review_note`, qualification, team, decision, risk, or credentials.
- [ ] all regression tests pass and generated workbook has no formula errors.
- [ ] reviewed source/docs/site files are committed and pushed to `main`.

### 4.2 Quality Criteria

- [ ] 모든 신규 SQL은 parameterized query를 사용한다.
- [ ] 기존 49 notice rows와 source attachments가 보존된다.
- [ ] 공개 Pages는 API key/SMTP/DB에 의존하지 않는 정적 파일이다.
- [ ] GitHub Pages failure 시 원인과 next action을 명확히 남긴다.

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| G2B 링크가 파일 형식·접근정책에 따라 다르다. | High | Medium | 파일명 기준 형식 분류, direct-public HWPX만 추출, 나머지는 링크·상태 보존 |
| 내부 검토 정보가 public site에 노출된다. | High | Medium | public payload whitelist 방식과 automated assertion |
| public Pages가 자동으로 활성화되지 않는다. | Medium | Medium | standard Pages Actions workflow; deployment API/HTTP 결과를 확인 |
| 기존 작업트리가 이미 변경되어 있다. | High | Medium | data/.env/outputs/node_modules 제외, diff 검토 후 관련 source/docs만 stage |
| Tier 1 자동 분류가 실입찰 적합성을 보장하지 않는다. | High | High | ‘우선 검토’로만 표기하고 bid/no-bid은 사람 입력 필드로 유지 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `rfp_tracker/fetchers.py` | Source adapter | G2B explicit attachment URL/file-name extraction |
| `rfp_tracker/storage.py` | SQLite schema/repository | bid fit review table and safe queries |
| `rfp_tracker/documents.py` | Domain/payload | backfill, stale-gap handling, priority and public payload projection |
| `rfp_tracker/render.py` | Presentation | Tier 1 priority panel, fit summary, public rendering option |
| `rfp_tracker/cli.py` | Application | backfill, fit-review, public render commands |
| `scripts/build_rfp_workbench_workbook.mjs` | Workbook | editable fit-review worksheet |
| `.github/workflows/pages.yml`, `site/index.html` | Deployment | sanitized public snapshot deployment |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| notices | READ/UPDATE | sync, tiering, review, briefing, notifications, workbench | Must preserve raw source and existing review semantics |
| attachments | CREATE/READ | fetchers, sync, document extraction, workbench | Backfill must be idempotent |
| document_insights | CREATE/READ | extraction, render, Excel | stale blank gap row must not outrank a real attachment |
| review status | READ/UPDATE | CLI, briefing, notifications | fit review must not replace it |
| workbook payload | READ | Excel builder | add fit fields without altering typed date/amount behavior |
| reports/site | WRITE | workbench renderer/Pages | public projection must exclude private fields |

### 6.3 Verification

- [ ] Existing source consumers remain compatible.
- [ ] Fit reviews do not change raw notice or attachment values.
- [ ] Public dashboard output is sanitized.
- [ ] Git staging does not include `.env`, data DB, reports, outputs, or node_modules.

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|----------------|:--------:|
| **Starter** | Python, SQLite, static HTML, CLI | Current local operational workflow | ☑ |
| **Dynamic** | Multi-user server-side review app | Future authenticated team workflow | ☐ |
| **Enterprise** | Microservices, dedicated access control | High-scale commercial platform | ☐ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| G2B attachment recovery | re-call API / raw JSON backfill / browser automation | raw JSON backfill | avoids extra API load and uses collected official data |
| Bid-fit data | notice columns / separate table | separate table | raw source facts and human judgement remain separate |
| Tier 1 screen | new web app / static priority panel | static priority panel | matches current local workflow and preserves simple deployment |
| Public link | local file / sanitized Pages snapshot | sanitized Pages snapshot | accessible from any browser without exposing internal review data |
| Deployment | manual Pages settings / GitHub Actions Pages | GitHub Actions Pages | uses repository-scoped automatic token, no local secret extraction |

### 7.3 Clean Architecture Approach

Selected Level: Starter

    G2B raw JSON -> fetchers/documents -> attachments/document_insights
                                            |
    human fit review -> bid_fit_reviews ----+-> internal payload -> HTML/Excel
                                            |
                                            +-> public payload whitelist -> site/index.html -> Pages

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] Python package and `unittest` test folder
- [x] SQLite raw-source / derived-data separation
- [x] `.env`, data DB, reports, local configs are ignored
- [x] static HTML output is escaped and direct-public URLs only

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|----------|
| Naming | snake_case Python/status values | `bid_fit_reviews`, `priority_status` | High |
| Public payload | no formal whitelist yet | explicit allowed public fields | High |
| Error handling | explicit document state | Pages/deploy failure stays visible | High |
| Excel input | existing typed tables | editable review fields and dropdowns | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| None | GitHub Actions uses `GITHUB_TOKEN`; local document work uses existing source URL only. | CI | ☐ |

### 8.4 Pipeline Integration

| Phase | Status | Document Location | Command |
|-------|:------:|-------------------|---------|
| Phase 1 | N/A | this plan/design schema | N/A |
| Phase 2 | N/A | existing Python conventions | N/A |

---

## 9. Next Steps

1. [x] Inspect current source payload, workbook, remote, and public Pages state.
2. [ ] Write design and implement small tested modules.
3. [ ] Run source backfill and public-document extraction.
4. [ ] Generate local and public artifacts, validate, commit, push, and verify deployment.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-21 | Initial implementation plan | Codex |
