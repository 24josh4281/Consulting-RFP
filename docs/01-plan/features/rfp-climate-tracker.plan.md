# RFP Climate Tracker Planning Document

> **Summary**: 한국 공공·민간 입찰 공고 중 기후, 온실가스, 배출권거래제, ESG 컨설팅 관련 공고를 추적·관리하는 로컬 MVP
>
> **Project**: Climate RFP Tracker
> **Version**: 0.1.0
> **Author**: Codex
> **Date**: 2026-08-07
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 나라장터와 민간 대기업 입찰 페이지가 흩어져 있어 ESG/기후 컨설팅 공고를 사람이 반복 검색해야 하며, RFP·과업지시서·서식 연결도 누락되기 쉽다. |
| **Solution** | 출처별 수집기를 두고 공고명/본문/첨부 링크를 기후·GHG·ETS 키워드로 필터링해 SQLite와 HTML 대시보드로 관리한다. |
| **Function/UX Effect** | 사용자는 하루 또는 주 단위로 새 공고 후보, 관련 키워드, 발주기관, 첨부 후보를 한 화면에서 확인하고 CSV로 검토할 수 있다. |
| **Core Value** | 반복 검색 시간을 줄이고, ESG 컨설팅 영업/제안 기회를 더 빠르게 발견하며, 공고 검토의 추적성을 높인다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 공고 탐색·RFP 확인·첨부 연결이 수작업이라 기회 누락과 QA 부담이 크다. |
| **WHO** | ESG/기후 컨설턴트, 제안서 담당자, 사업개발 담당자 |
| **RISK** | 사이트별 약관, 로그인, API키, 첨부 구조가 달라 무리한 “전체 자동수집”은 법무·운영 리스크가 있다. |
| **SUCCESS** | 샘플 공고에서 관련 공고만 추출하고, DB/CSV/HTML 대시보드를 생성하며, 나라장터 API키 연결 준비가 완료된다. |
| **SCOPE** | 1차: 로컬 MVP. 2차: 출처별 상세 어댑터. 3차: 알림/스케줄러/첨부 원문 분석. |

---

## 1. Overview

### 1.1 Purpose

기후·온실가스·배출권거래제·ESG 보고/검증 관련 컨설팅 입찰 공고를 자동으로 모아 검토 가능한 형태로 정리한다.

### 1.2 Background

나라장터는 공공데이터포털 OpenAPI로 접근하는 것이 안전하고, 민간 기업 입찰 사이트는 공개 HTML, 로그인 포털, JavaScript 페이지가 섞여 있다. 따라서 처음부터 모든 사이트를 무리하게 크롤링하기보다 “출처별 어댑터를 추가할 수 있는 구조”를 먼저 만든다.

### 1.3 Related Documents

- Design: `docs/02-design/features/rfp-climate-tracker.design.md`
- Keywords: `configs/keywords.json`
- Sources: `configs/sources.example.json`

---

## 2. Scope

### 2.1 In Scope

- [x] 나라장터 OpenAPI 연동 코드 구조
- [x] 공개 HTML 입찰 페이지 범용 파서
- [x] 기후/GHG/ETS/ESG 키워드 점수화
- [x] SQLite 저장
- [x] HTML 대시보드 생성
- [x] Excel 검토용 CSV 내보내기
- [x] 샘플 공고 실행 검증

### 2.2 Out of Scope

- 로그인 필요한 민간 포털 자동 접속
- 첨부파일 대량 다운로드
- 법률 검토 없이 민간 사이트 데이터 재배포
- API키를 코드에 직접 저장
- 실시간 푸시 알림/이메일/Slack 알림

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 출처 설정 파일에서 수집 대상을 관리한다. | High | Implemented |
| FR-02 | 나라장터 OpenAPI를 서비스키 기반으로 호출할 수 있다. | High | Implemented, key required |
| FR-03 | 공개 HTML 페이지에서 링크/문서 후보를 추출한다. | High | Implemented |
| FR-04 | ESG/기후/GHG/ETS 키워드로 관련성 점수를 계산한다. | High | Implemented |
| FR-05 | 공고와 첨부 후보를 SQLite에 저장한다. | High | Implemented |
| FR-06 | HTML 대시보드와 CSV를 생성한다. | Medium | Implemented |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Safety | API키는 환경변수로만 사용 | 코드/설정 검토 |
| Maintainability | 출처별 수집기를 독립적으로 추가 가능 | 파일 구조 검토 |
| Usability | 비개발자도 PowerShell 명령 3개로 실행 가능 | README 확인 |
| Data QA | 관련성 점수와 매칭 키워드를 함께 저장 | DB/CSV 확인 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [x] 샘플 공고 수집 실행
- [x] 관련 공고 후보가 SQLite에 저장
- [x] HTML 대시보드 생성
- [x] CSV 생성
- [x] 기본 테스트 통과

### 4.2 Quality Criteria

- [x] Python 표준 라이브러리만 사용
- [x] 기존 파일 수정/삭제 없음
- [x] API키 하드코딩 없음
- [x] 외부 대량 호출 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 민간 사이트 약관/권한 문제 | High | High | 공개 페이지만 기본 지원, 출처별 정책 확인 후 활성화 |
| 나라장터 API키/활용신청 필요 | Medium | High | 환경변수 방식으로 구현, 키 없으면 자동 skip |
| 첨부파일 구조가 사이트마다 다름 | Medium | High | 1차는 첨부 후보 링크 저장, 2차에서 상세 어댑터 추가 |
| 키워드 기반 필터의 누락/오탐 | Medium | Medium | 매칭 키워드/점수 저장, 컨설턴트가 키워드 조정 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| Workspace | New files only | 새 MVP 프로젝트 파일 생성 |
| SQLite DB | Local data | 수집 결과 저장 |
| HTML/CSV reports | Local outputs | 검토용 산출물 생성 |

### 6.2 Current Consumers

빈 워크스페이스에서 시작했으므로 기존 소비자는 없다.

### 6.3 Verification

- [x] 기존 파일과 충돌 없음
- [x] 샘플 데이터로 결과 확인
- [x] CSV/HTML 산출물 생성

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 스크립트/로컬 파일 | 개인 업무 자동화 MVP | ✅ |
| **Dynamic** | 웹앱/DB/알림/API 서버 | 팀 운영 SaaS |  |
| **Enterprise** | 권한/감사로그/대규모 수집 | 상용 플랫폼 |  |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Language | Python / Node | Python | ESG/Excel/PDF 업무 자동화와 궁합이 좋고 Windows 실행이 쉽다. |
| Storage | CSV / SQLite / Postgres | SQLite | 설치 없이 추적성과 중복 제거가 가능하다. |
| UI | CLI only / HTML / Web app | Static HTML | 브라우저에서 바로 검토 가능하고 운영 부담이 낮다. |
| Crawling | Aggressive scraping / Adapter-based | Adapter-based | 사이트별 권한·구조 차이를 안전하게 처리한다. |

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] 새 프로젝트라 기존 컨벤션 없음
- [x] 표준 라이브러리 중심 Python
- [x] 설정은 JSON
- [x] 출력은 `data/`, `reports/`

### 8.2 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `DATA_GO_KR_SERVICE_KEY` | 나라장터 OpenAPI 서비스키 | Local shell only | 사용자가 직접 설정 |

---

## 9. Next Steps

1. [ ] 나라장터 서비스키 발급 후 실제 API 테스트
2. [ ] 우선순위 민간 사이트 5~10개 선정
3. [ ] 사이트별 이용약관/robots/로그인 여부 확인
4. [ ] 출처별 상세 첨부파일 어댑터 추가
5. [ ] Windows 작업 스케줄러 또는 자동화 도구로 주기 실행

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-07 | Initial local MVP plan | Codex |

