# RFP Climate Tracker Design Document

> **Summary**: 공공/민간 입찰 공고를 출처별로 수집하고 ESG·기후 관련성 점수로 관리하는 로컬 MVP 설계
>
> **Project**: Climate RFP Tracker
> **Version**: 0.1.0
> **Author**: Codex
> **Date**: 2026-08-07
> **Status**: Draft
> **Planning Doc**: `docs/01-plan/features/rfp-climate-tracker.plan.md`

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

### 1.1 Design Goals

- 비개발자도 실행 가능한 로컬 자동화
- 출처를 JSON 설정으로 쉽게 추가
- 원문 숫자나 공고 내용을 임의 수정하지 않고 보존
- API키/로그인 정보는 코드에 저장하지 않음

### 1.2 Design Principles

- 작은 단위로 수집하고 검증한다.
- 먼저 후보를 모으고, 사람이 최종 판단한다.
- 민간 사이트는 약관 확인 전 대량 수집하지 않는다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 단일 스크립트 | 웹앱+DB+스케줄러 | CLI+SQLite+정적 HTML |
| **New Files** | 2~3 | 30+ | 15 내외 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 확장 어려움 | 과한 초기 투자 | 균형 |
| **Recommendation** | 단기 실험 | 상용화 이후 | **선택** |

**Selected**: Option C — 기능은 충분히 나누되 서버/회원/배포는 아직 만들지 않는다.

### 2.1 Component Diagram

```text
configs/sources.json
        |
        v
  Source Fetchers  ---> Keyword Matcher ---> SQLite Storage
   |       |                  |                    |
   |       |                  v                    v
 G2B    Generic HTML      score/keywords      CSV / HTML Dashboard
 API
```

### 2.2 Data Flow

```text
출처 설정 읽기 → 출처별 수집 → 키워드 점수화 → 중복 제거 저장 → HTML/CSV 리포트 생성
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| CLI | config, fetchers, storage, render | 사용자 실행 명령 |
| Fetchers | keyword matcher, models | 출처별 공고 후보 생성 |
| Storage | sqlite3 | 중복 제거 및 이력 저장 |
| Render | sqlite rows | 검토용 HTML 생성 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
Notice(
  source_id: str,
  source_name: str,
  external_id: str,
  title: str,
  url: str,
  published_at: str,
  deadline_at: str,
  buyer: str,
  budget: str,
  procurement_method: str,
  relevance_score: int,
  matched_keywords: list[str],
  attachments: list[Attachment],
  raw: dict
)
```

### 3.2 Entity Relationships

```text
Notice 1 ─── N Attachment
SyncRun 1 ── N Notice candidates during run
```

### 3.3 Database Schema

- `notices`: 공고 목록, 관련성 점수, 원본 JSON
- `attachments`: 공고별 첨부 후보 링크
- `sync_runs`: 수집 실행 이력

---

## 4. API Specification

### 4.1 CLI Commands

| Command | Description |
|---------|-------------|
| `python -m rfp_tracker sources` | 설정된 출처 목록 확인 |
| `python -m rfp_tracker sync` | 공고 후보 수집 및 DB 저장 |
| `python -m rfp_tracker render` | HTML 대시보드 생성 |
| `python -m rfp_tracker export-csv` | CSV 파일 생성 |

### 4.2 External API

나라장터는 공식 `ad/BidPublicInfoService` 용역 오퍼레이션을 사용하도록 준비한다. 현재 목록 주소는 `https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc`이며, 서비스키는 `serviceKey` 파라미터로 전달하되 값은 `DATA_GO_KR_SERVICE_KEY` 환경변수에서만 읽는다.

---

## 5. UI/UX Design

### 5.1 Screen Layout

```text
Climate RFP Tracker
검색창
┌────┬──────────────┬──────┬────────┬──────┬──────────┬──────┐
│점수│공고명         │출처  │기관    │마감  │매칭키워드│첨부  │
└────┴──────────────┴──────┴────────┴──────┴──────────┴──────┘
```

### 5.2 User Flow

```text
sync 실행 → render 실행 → dashboard.html 열기 → 후보 검토 → CSV로 제안 검토표 작성
```

### 5.3 Page UI Checklist

#### Dashboard

- [x] 검색 입력창
- [x] 관련성 점수
- [x] 공고명 링크
- [x] 출처명
- [x] 수요/발주기관
- [x] 마감/개찰일 후보
- [x] 매칭 키워드
- [x] 첨부 후보 링크

---

## 6. Error Handling

| Code/Case | Cause | Handling |
|-----------|-------|----------|
| Missing API key | `DATA_GO_KR_SERVICE_KEY` 없음 | 나라장터 수집 skip, 메시지 출력 |
| Invalid JSON | API 응답 오류/권한 문제 | 경고 출력 후 해당 호출 제외 |
| Network error | 사이트 차단/타임아웃 | 실행 실패 메시지 표시 |
| Unsupported source type | 설정 오류 | 명확한 오류 메시지 |

---

## 7. Security Considerations

- API키는 환경변수로만 사용
- 로그인 자동화 없음
- 첨부파일 대량 다운로드 없음
- 원문 공고 데이터는 `raw_json`으로 보존
- 민간 사이트는 기본 비활성화

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1 | 키워드 점수화 | unittest | Do |
| L1 | 샘플 HTML 수집 | CLI 실행 | Do |
| L2 | HTML 대시보드 생성 | 파일 생성 확인 | Check |
| L2 | CSV 생성 | 파일 생성 확인 | Check |

### 8.2 Test Scenarios

| # | Scenario | Expected |
|---|----------|----------|
| 1 | 샘플 HTML sync | 기후/GHG/ETS 관련 공고 후보 저장 |
| 2 | 청소 용역 샘플 포함 | 낮은 관련성으로 제외 |
| 3 | dashboard render | `reports/dashboard.html` 생성 |
| 4 | export-csv | `reports/notices.csv` 생성 |

---

## 9. Clean Architecture

| Layer | Responsibility | Location |
|-------|---------------|----------|
| Interface | CLI | `rfp_tracker/cli.py` |
| Application | 수집 흐름 조율 | `cli.py`, `fetchers.py` |
| Domain | Notice/Attachment 모델, 키워드 점수 | `models.py`, `keyword_matcher.py` |
| Infrastructure | SQLite, HTTP, HTML rendering | `storage.py`, `render.py`, `fetchers.py` |

---

## 10. Coding Convention Reference

| Target | Rule | Example |
|--------|------|---------|
| Functions | snake_case | `score_text()` |
| Files | snake_case.py | `keyword_matcher.py` |
| Config | JSON | `sources.example.json` |
| Outputs | local folders | `data/`, `reports/` |

---

## 11. Implementation Guide

### 11.1 File Structure

```text
rfp_tracker/
  cli.py
  config.py
  fetchers.py
  keyword_matcher.py
  models.py
  render.py
  storage.py
configs/
  keywords.json
  sources.example.json
samples/
  sample_notices.html
```

### 11.2 Implementation Order

1. [x] 데이터 모델 정의
2. [x] 키워드 점수화 구현
3. [x] HTML/API 수집기 구현
4. [x] SQLite 저장 구현
5. [x] HTML/CSV 출력 구현
6. [x] 테스트 및 샘플 실행

### 11.3 Session Guide

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| Source ingestion | `module-1` | 나라장터/API/HTML 수집 | 5 |
| Data QA | `module-2` | 키워드 점수, DB 중복 제거 | 4 |
| Review UI | `module-3` | HTML/CSV 산출물 | 3 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-07 | Initial MVP design | Codex |
