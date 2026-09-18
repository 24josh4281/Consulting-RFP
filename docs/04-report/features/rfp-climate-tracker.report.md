# RFP Climate Tracker Completion Report

> **Status**: Complete for local MVP
>
> **Project**: Climate RFP Tracker
> **Version**: 0.1.0
> **Author**: Codex
> **Completion Date**: 2026-08-07
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | RFP Climate Tracker |
| Start Date | 2026-08-07 |
| End Date | 2026-08-07 |
| Duration | 1 working session |

### 1.2 Results Summary

| Metric | Result |
|--------|--------|
| Completion Rate | 95% for local MVP scope |
| Implemented Items | 11 / 11 MVP items |
| Runtime Validation | PASS |
| Unit Tests | PASS: 3 tests |
| Sample Notices Collected | 3 relevant notices |
| Output Files | SQLite DB, HTML dashboard, CSV export |

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | ESG/기후 컨설팅 입찰 공고를 여러 사이트에서 반복 검색해야 하고, RFP·과업지시서·첨부 후보 연결이 누락되기 쉬웠다. |
| **Solution** | 출처 설정, 나라장터 API 연동 준비, 공개 HTML 수집, 키워드 점수화, SQLite 저장, HTML/CSV 출력, 검토 상태 관리를 갖춘 로컬 MVP를 구현했다. |
| **Function/UX Effect** | 샘플 기준 관련 공고 3건을 추출하고, 대시보드에서 점수·출처·첨부 후보·검토 상태·메모를 한 화면에서 확인할 수 있게 했다. |
| **Core Value** | 컨설턴트가 매일 입찰 사이트를 수동 확인하는 시간을 줄이고, 관심 공고를 `interesting`, `submitted`, `closed` 등으로 추적할 수 있게 했다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | 샘플 공고에서 관련 공고만 추출 | Met | `sync`: 후보 3건 |
| SC-2 | SQLite DB 저장 | Met | `data/rfp_tracker_script_test.db` 생성 |
| SC-3 | HTML 대시보드 생성 | Met | `reports/dashboard.html` 생성 |
| SC-4 | CSV 생성 | Met | `reports/notices.csv` 생성 |
| SC-5 | 나라장터 API키 안전 처리 | Met | 환경변수 없으면 skip, 코드에 키 저장 없음 |
| SC-6 | 공고별 검토 상태 관리 | Met | `review`, `list`, `stats` 명령 검증 |
| SC-7 | Windows 운영 실행 스크립트 | Met | `scripts/run_tracker.ps1` 실행 성공 |
| SC-8 | 기본 테스트 통과 | Met | `python -m unittest discover -s tests`: 3 tests OK |

**Success Rate**: 8/8 criteria met (100% within local MVP scope)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 로컬 MVP부터 구축 | Yes | API키/로그인 없이도 샘플 기반 실행 검증 완료 |
| [Plan] | 민간 사이트는 기본 비활성화 | Yes | 약관/권한 리스크를 피하면서 어댑터 구조 확보 |
| [Design] | Python 표준 라이브러리 중심 | Yes | 별도 패키지 설치 없이 Windows에서 실행 |
| [Design] | SQLite + HTML/CSV 출력 | Yes | 컨설턴트가 브라우저/Excel로 바로 검토 가능 |
| [Check] | 공고 lifecycle/status 필요 | Yes | `review_status`, `review_note`, `reviewed_at` 추가 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | `docs/01-plan/features/rfp-climate-tracker.plan.md` | Finalized |
| Design | `docs/02-design/features/rfp-climate-tracker.design.md` | Finalized |
| Check | `docs/03-analysis/rfp-climate-tracker.analysis.md` | Complete |
| Operations | `docs/OPERATIONS.md` | Complete |
| Report | Current document | Complete |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 출처 설정 파일 관리 | Complete | `configs/sources.example.json` |
| FR-02 | 나라장터 OpenAPI 연동 준비 | Complete | 서비스키 필요 시 환경변수 사용 |
| FR-03 | 공개 HTML 링크/첨부 후보 추출 | Complete | `generic_html`, `sample_html` |
| FR-04 | ESG/기후/GHG/ETS 키워드 점수화 | Complete | `configs/keywords.json` |
| FR-05 | SQLite 저장 및 중복 방지 | Complete | `(source_id, external_id)` unique |
| FR-06 | HTML/CSV 출력 | Complete | `reports/dashboard.html`, `reports/notices.csv` |
| FR-07 | 공고 검토 상태/메모 관리 | Complete | `list`, `review`, `stats` |
| FR-08 | 운영 스크립트 | Complete | `scripts/run_tracker.ps1` |
| FR-09 | API 키 인벤토리와 대기업 포털 확장 준비 | Complete | `configs/api_keys.example.json`, `portal-discover` |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| Safety | No hardcoded API key | Environment variable only | Met |
| Maintainability | Add source by config/adapter | Implemented | Met |
| Usability | PowerShell-friendly commands | Implemented | Met |
| Data QA | Matched keywords and score stored | Implemented | Met |
| Traceability | Raw API/notice data preserved | `raw_json` field | Met |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| Source config | `configs/sources.example.json` | Complete |
| Keyword config | `configs/keywords.json` | Complete |
| Python package | `rfp_tracker/` | Complete |
| Tests | `tests/test_keyword_matcher.py` | Complete |
| Operations guide | `docs/OPERATIONS.md` | Complete |
| API/portal expansion guide | `docs/API_KEYS_AND_COMPANY_PORTALS.md` | Complete |
| Dashboard | `reports/dashboard.html` | Complete |
| CSV | `reports/notices.csv` | Complete |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| Live 나라장터 API validation | Requires user service key | High | 30-60 minutes after key setup |
| Priority private-site adapters | Requires target site list and policy check | High | 0.5-1 day per site |
| Attachment download/OCR/PDF extraction | Needs legal/operational approval and file handling design | Medium | 1-2 days |
| Automatic notification | Email/Slack connector not installed/configured | Medium | 0.5-1 day |

### 4.2 Cancelled/On Hold Items

| Item | Reason | Alternative |
|------|--------|-------------|
| Login-based crawling | Risky without explicit account/permission workflow | Keep disabled; use public/API sources first |
| Bulk attachment download | Could violate site terms or create storage risk | Store attachment candidate links first |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| MVP Match Rate | 90% | 95% | +5% after operational enhancement |
| Unit Tests | Passing | 3/3 passing | +1 review workflow test |
| Sample Relevant Notices | >= 3 | 3 | Met |
| Output Generation | HTML + CSV | Both generated | Met |
| Critical Safety Issues | 0 | 0 | Met |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| Unrelated tender noise | Required at least one ESG/climate/GHG/ETS domain keyword | Cleaning-only tender excluded |
| Attachment links as notices | File-extension links attach to previous relevant notice | RFP/task-order links connected |
| No review lifecycle | Added review status/note fields and CLI commands | Candidate management possible |
| Windows DB file lock in test | Closed SQLite connection in test | Tests pass |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well

- Starting with sample data made it possible to validate logic without API keys.
- Keeping private sites disabled by default reduced legal/operational risk.
- SQLite was enough for traceable MVP data handling without installing a database server.

### 6.2 What Needs Improvement

- The first MVP did not include review lifecycle fields; these were added after Check.
- Live API validation still depends on the user’s 공공데이터포털 service key.
- Private procurement sites need individual adapter design rather than generic scraping assumptions.

### 6.3 What to Try Next

- Add a `sources.production.json` once actual target sites are selected.
- Add attachment metadata extraction for PDF/HWP only after policy confirmation.
- Add email/Slack alerts only after the user chooses the channel and authorizes the connector.

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | MVP scope clear | Add target-source priority matrix |
| Design | Adapter-based | Add per-source compliance checklist |
| Do | Local CLI | Add source-specific tests as adapters grow |
| Check | Sample runtime validation | Add live API validation once key is available |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] Set `DATA_GO_KR_SERVICE_KEY`
- [ ] Enable `g2b_service_bids`
- [ ] Run `powershell -ExecutionPolicy Bypass -File .\scripts\run_tracker.ps1 -Days 3`
- [ ] Review `reports/dashboard.html`
- [ ] Mark promising notices as `interesting`

### 8.2 Next PDCA Cycle

| Item | Priority | Expected Start |
|------|----------|----------------|
| Live 나라장터 API validation | High | After service key setup |
| Top 5 private-source adapter design | High | After target site selection |
| Notification workflow | Medium | After stable sources |

---

## 9. Changelog

### v0.1.0 (2026-08-07)

**Added:**

- Source config and keyword config
- G2B API fetcher structure
- Generic/sample HTML fetcher
- SQLite storage
- HTML dashboard
- CSV export
- Review status/note workflow
- Operations script and guide
- Unit tests

**Fixed:**

- Domain-keyword requirement to reduce unrelated tender noise
- Attachment candidate linking
- Windows SQLite test connection lock

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.3 | 2026-09-18 | Added official GIR detail/RFP links, source catalog, briefing, email readiness, and scheduler scripts | Codex |
| 1.2 | 2026-08-07 | Added `.env` auto-loading, live readiness checks, and safe PowerShell failure handling | Codex |
| 1.1 | 2026-08-07 | Added RFP/document index reports and CLI commands | Codex |
| 1.0 | 2026-08-07 | Completion report created | Codex |

## Post-MVP Update: Official Source, RFP Link, and Email Readiness

### What changed

- Added an official-board adapter for the public 온실가스종합정보센터(GIR) bid board. It follows only public detail pages and records public RFP/notice attachment links.
- Added exclusion terms to prevent obvious non-consulting noise (for example cleaning, security, food service, and unrelated facilities work) from entering the candidate queue.
- Added consultant-facing HTML/Markdown briefing files for urgent deadlines, new notices, document gaps, and similar notices.
- Added SMTP-ready immediate/daily/weekly notification commands with a durable SQLite delivery log and first-run baseline.
- Added PowerShell scripts that support 30-minute polling, daily 17:00 KST, and Friday 18:00 KST scheduling after a successful SMTP test.
- Added source-catalog and operations documentation based on the supplied reference files. No third-party repository code was copied.

### Validation result

| Check | Result |
|---|---|
| Python compile | PASS |
| Unit tests | PASS: 17 tests |
| Official GIR limited live check | PASS: 2 public climate/ETS notices |
| GIR public document links | PASS: 6 RFP/notice/reason links |
| Document report | PASS: 5 notices, 10 document rows including samples |
| Notification first-run baseline | PASS: no historical mail is sent as new |
| Actual SMTP email | Not run: credentials intentionally absent |

### Remaining limitation

The tracker does not claim live coverage of every Korean corporate procurement portal. Public official sources are active or catalogued first; private portals remain disabled until their access terms, public listing structure, and operational permission are individually verified. Actual external email still requires local SMTP credentials and a deliberate test send.

## Post-MVP Update: Live Readiness Workflow

### What changed

- Added automatic `.env` loading for CLI commands.
- Added `doctor` command to check whether enabled live sources have required API-key environment variables.
- Added `source-toggle` command to create local source configs without overwriting `configs/sources.example.json`.
- Added `scripts/run_live_g2b_check.ps1` for safe short 나라장터 live tests.
- Updated PowerShell scripts to stop on failed native commands by checking `$LASTEXITCODE`.

### Validation result

| Check | Result |
|-------|--------|
| Python compile | PASS |
| Unit tests | PASS: 9 tests |
| `source-toggle` | PASS |
| `doctor --strict` without key | PASS: blocks live run |
| `run_live_g2b_check.ps1` without key | PASS: stops before live sync |
| Normal sample run | PASS |

### Remaining limitation

Actual 나라장터 live collection still requires the user to add `DATA_GO_KR_SERVICE_KEY` to `.env` or the PowerShell environment.

## Post-MVP Update: RFP Document Index

### What changed

- Added document classification for RFP, task statement, bid notice, submission form, pricing, contract, other, and missing document links.
- Added `reports/rfp_documents.html` for browser-based RFP document review.
- Added `reports/rfp_documents.csv` for Excel-based document checklists.
- Added `rfp-documents` and `render-documents` CLI commands.
- Updated the daily PowerShell runner to generate document reports automatically.

### Validation result

| Check | Result |
|-------|--------|
| Python compile | PASS |
| Unit tests | PASS: 7 tests |
| Sample document report | PASS: 4 document rows |
| Main local run | PASS: 5 notices, 6 document-check rows |

### Remaining limitation

The feature indexes document links that have already been collected. Actual live 나라장터/RFP document coverage still requires `DATA_GO_KR_SERVICE_KEY`, enabled live source configuration, and source-specific parsing for portals that hide files behind login, JavaScript, or detail pages.
