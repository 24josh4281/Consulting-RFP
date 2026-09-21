# RFP Workbench and Document Extraction Planning Document

> **Summary**: 모든 추적 공고, 문서 확인 상태, 과업 요약, 금액 근거를 한 화면과 한 개의 Excel 파일에서 검토할 수 있게 한다.
>
> **Project**: Consulting-RFP
> **Version**: Local working tree
> **Author**: Codex
> **Date**: 2026-09-21
> **Status**: Complete

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 49건의 후보 공고가 있으나 Tier, 원문 문서, 금액의 근거를 한 번에 비교하기 어렵다. |
| **Solution** | 원문 공고와 별도로 문서 추출 결과를 저장하고, HTML 작업대와 Excel 검토 파일로 보여 준다. |
| **Function/UX Effect** | 사용자는 Tier, 상태, 출처, 문서 확인 여부와 마감일로 전체 공고를 필터링하고 해당 원문을 바로 열 수 있다. |
| **Core Value** | 자동 요약과 원문 사실을 분리하므로, 확인되지 않은 과업 또는 금액이 확정 정보처럼 보이지 않는다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 많은 후보 공고를 안전하고 빠르게 일일 검토하기 위해서이다. |
| **WHO** | 기후변화, 온실가스, 배출권거래제, Scope 1·2·3 컨설팅 기회를 검토하는 이너젠 담당자이다. |
| **RISK** | 포털이 첨부 URL을 주지 않거나, 문서 금액이 예산·추정가격·계약금액 중 무엇인지 불명확할 수 있다. |
| **SUCCESS** | 모든 공고가 하나의 대시보드와 Excel 파일에 표시되고, 문서 확인 상태와 금액 기준이 구분된다. |
| **SCOPE** | 별도 추출결과 저장소, 공개 HWPX 추출, 정적 작업대, Excel 파일, 자동 검증이다. |

---

## 1. Overview

### 1.1 Purpose

기존 공고, 첨부, Tier, 검토 상태, 발송 기록을 보존한 채 공고별 문서 접근성, 간단 과업 요약, 금액 근거를 연결한다.

### 1.2 Background

현재 데이터베이스에는 49건의 공고가 있다. 이 중 온실가스종합정보센터(GIR) 공고의 HWPX 첨부 6건만 공개 URL로 직접 읽을 수 있다. example.com 링크 4건은 샘플이므로 실제 RFP 근거로 사용하지 않는다. 나라장터 목록 API는 대부분 첨부 URL을 제공하지 않아 원문 파일첨부 확인이 필요하다.

### 1.3 Related Documents

- Existing Tier design: docs/02-design/features/innergen-tiering-and-newsletter.design.md
- Existing RFP link analysis: docs/03-analysis/rfp-document-index.analysis.md
- Operations guide: docs/OPERATIONS.md

---

## 2. Scope

### 2.1 In Scope

- [ ] 원문 notices와 attachments를 바꾸지 않는 document_insights 저장소를 추가한다.
- [ ] 직접 공개된 문서 URL만 다운로드하여 읽는다.
- [ ] 과업 요약, 금액, 금액 기준, 문장 근거, 추출 상태를 기록한다.
- [ ] Tier, 검토상태, 출처, 문서상태, 마감일 필터가 있는 HTML 작업대를 만든다.
- [ ] 원문 공고와 RFP/과업지시서 링크를 공고 상세에 함께 제공한다.
- [ ] Dashboard, 공고목록, 문서요약, 출처·이용안내 시트가 있는 Excel 파일을 만든다.
- [ ] 금액과 날짜가 명확할 때만 Excel의 숫자/날짜 타입으로 저장한다.
- [ ] 테스트, 데이터 보존 검사, Excel 렌더 검증을 실행한다.

### 2.2 Out of Scope

- 나라장터 로그인, CAPTCHA, 권한 제한, 보호된 다운로드의 우회.
- 샘플 링크를 실제 공고 또는 실제 문서로 판정.
- 원문 과업지시서, 원본 공고 금액, Tier, 검토상태, 발송 기록의 임의 변경.
- 이번 기능 검증 중 메일 발송.
- 별도 승인 없는 Git commit 또는 push.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 모든 저장 공고를 Tier, 검토상태, 출처, 문서상태, 마감일로 필터할 수 있다. | High | Complete |
| FR-02 | 원문 공고와 수집된 RFP/과업지시서 링크를 같은 공고에서 확인할 수 있다. | High | Complete |
| FR-03 | 추출 결과는 URL, 문서명, 상태, 요약, 금액 원문, 금액 기준, 근거 문장, 추출시각을 가진다. | High | Complete |
| FR-04 | 공개 GIR HWPX 문서를 직접 읽고 요약·금액 근거를 저장한다. | High | Complete |
| FR-05 | 샘플, 누락, 지원하지 않는 형식, 다운로드 실패를 명시적으로 구분한다. | High | Complete |
| FR-06 | 필터·정렬 가능한 단일 Excel 검토 파일을 생성한다. | High | Complete |
| FR-07 | 예산, 추정가격, 기초금액, 투찰금액, 계약금액이 서로 다를 수 있음을 안내한다. | Medium | Complete |
| FR-08 | 추출, 대시보드 생성, Excel 생성 명령을 반복 실행할 수 있다. | Medium | Complete |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Accuracy | 요약/금액은 저장된 공개 원문 문장 또는 공고 목록 값에 근거한다. | 단위 테스트와 수동 원문 점검 |
| Traceability | 모든 추출값에 문서 URL, 문서명, 근거 문장, 시각을 남긴다. | SQLite/Excel 검토 |
| Safety | extraction은 notices, attachments, review/Tier, notification rows를 수정하지 않는다. | 전후 행 수와 회귀 테스트 |
| Usability | 경계가 있는 표, 짧은 한국어 라벨, 고정 헤더와 필터를 제공한다. | HTML/Excel 렌더 점검 |
| Maintainability | 문서읽기, 저장소, 화면, Excel 생성을 분리한다. | 코드 구조와 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [x] 현재 49건 모두 작업대와 Excel에서 확인 가능하다.
- [x] 공개 GIR HWPX 문서는 원문을 수정하지 않고 처리된다.
- [x] 샘플/미수집/제한 문서는 검증되지 않은 상태로 표시된다.
- [x] 각 행에 원문 공고와 연결 문서 링크가 있다.
- [x] 출력용 Excel 파일 1개가 전용 outputs 폴더에 생성된다.
- [x] 테스트와 Excel 오류 검사가 통과한다.
- [x] 남은 접근 제한이 문서와 화면에 설명된다.

### 4.2 Quality Criteria

- [x] 비밀키, SMTP 비밀번호, 서비스키가 출력물이나 로그에 없다.
- [x] 이메일을 보내지 않는다.
- [x] 금액 원문과 금액 기준을 숫자 값과 함께 보존한다.
- [x] 모든 Excel 시트를 정상 배율로 렌더해 가독성을 확인한다.

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 나라장터 목록 API가 첨부 URL을 주지 않는다. | High | High | 원문 공고 링크와 파일첨부 수동 확인 상태를 표시한다. |
| 한 문서에 서로 다른 성격의 금액이 여러 개 있다. | High | Medium | 근거 문장과 금액 기준을 함께 저장하고 계약금액으로 임의 표기하지 않는다. |
| 공개 다운로드 주소가 바뀌거나 일시 실패한다. | Medium | Medium | 오류 상태와 원문 URL을 남겨 재시도할 수 있게 한다. |
| 샘플 데이터가 실제 RFP처럼 보인다. | High | Medium | sample_source 상태로 분리하고 검증 건수에서 제외한다. |
| 대량 표가 읽기 어렵다. | Medium | Low | KPI, 필터, 고정 헤더, 간결한 상세 패널을 적용한다. |
| 새 스키마가 알림을 방해한다. | High | Low | 별도 테이블을 사용하고 기존 기능 회귀 테스트를 실행한다. |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| rfp_tracker/storage.py | SQLite schema/repository | document_insights 테이블과 읽기·쓰기 함수를 추가한다. |
| rfp_tracker/documents.py | Extraction service | 공개 URL 판정, HWPX 본문 추출, 요약·금액 근거 분석을 추가한다. |
| rfp_tracker/render.py | HTML renderer | 기존 목록형 대시보드를 확장 작업대로 개선한다. |
| rfp_tracker/cli.py | CLI | 추출, 작업대, Excel 입력 JSON 명령을 추가한다. |
| scripts/build_rfp_workbench_workbook.mjs | Artifact builder | 입력 JSON에서 xlsx를 생성한다. |
| tests | Automated QA | 문서 상태, 금액 파싱, 데이터 보존, 화면 출력 테스트를 추가한다. |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| notices | READ | list_notices, dashboard, CSV, briefing, notifications | insight join이 공고를 중복시키지 않는지 확인 |
| attachments | READ/UPDATE | sync upsert, documents, notifications, reports | extraction이 첨부를 삭제/갱신하지 않는지 확인 |
| Tier and review | READ/UPDATE | tier/review CLI, notifications, briefing | 변경 의도 없음 |
| notification deliveries | READ/WRITE | notification cycle | 변경 의도 없음, send 명령 미실행 |
| render command | READ | CLI render_dashboard | 기존 명령 호환성 유지 |

### 6.3 Verification

- [x] 추출 전후 공고·첨부 수를 비교한다.
- [x] 새 정보가 별도 테이블에만 저장되는지 확인한다.
- [x] render, render-documents, briefing, notification status를 회귀 점검한다.
- [x] 비밀값이나 이메일 전송 부작용이 없는지 확인한다.

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|----------------|:--------:|
| **Starter** | Python, SQLite, 정적 HTML, 명령행 | 현재 로컬 운영 도구 | ☑ |
| **Dynamic** | 다중 사용자 웹 서비스 | 향후 포털 | ☐ |
| **Enterprise** | 마이크로서비스 | 대규모 상용 서비스 | ☐ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Storage | notice 컬럼 추가 / 별도 추출 테이블 | 별도 테이블 | 원문 의미와 자동 추출을 분리한다. |
| Document parsing | 브라우저 자동화 / 공개 다운로드 분석 | 공개 다운로드 분석 | 안전한 공개 문서만 다루고 제한을 우회하지 않는다. |
| Dashboard | 서버 프레임워크 / 정적 HTML | 정적 HTML | 현재 로컬 사용 흐름에서 바로 열 수 있다. |
| Workbook | Python writer / artifact tool | artifact tool | 타입 검증과 렌더 검증을 함께 할 수 있다. |
| Testing | 수동만 / Python+artifact checks | Python+artifact checks | Windows에서 반복 가능한 검증을 제공한다. |

### 7.3 Clean Architecture Approach

Selected Level: Starter

    rfp_tracker/
      documents.py
      storage.py
      render.py
      cli.py
    scripts/
      build_rfp_workbench_workbook.mjs
    tests/
      test_document_insights.py

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] rfp_tracker Python package
- [x] tests Python unittest folder
- [x] configs JSON folder
- [x] .env ignored and 비밀값 비출력
- [x] README Windows 명령 안내

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|----------|
| Naming | snake_case Python | document_insight는 파생 정보에만 사용 | High |
| Source provenance | notice/attachment URL 있음 | 모든 요약에 URL과 근거 문장 필수 | High |
| Error handling | CLI 오류 출력 | 상태와 비밀 없는 오류 문구 저장 | High |
| Excel layout | 별도 템플릿 없음 | 간결한 대시보드, 타입, 필터, 출처 시트 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| 없음 | 이미 수집된 공개 URL만 사용한다. | Local | ☐ |

### 8.4 Pipeline Integration

| Phase | Status | Document Location | Command |
|-------|:------:|-------------------|---------|
| Phase 1 | N/A | 이 문서와 설계의 SQLite schema | N/A |
| Phase 2 | N/A | 기존 Python convention | N/A |

---

## 9. Next Steps

1. [x] 현재 공고, 첨부, 문서 접근 상태 점검
2. [x] 설계 문서 작성
3. [x] insight storage와 공개 HWPX 추출 구현
4. [x] 작업대와 Excel 생성 구현
5. [x] 테스트와 보고서 작성

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-21 | Initial implementation plan | Codex |
