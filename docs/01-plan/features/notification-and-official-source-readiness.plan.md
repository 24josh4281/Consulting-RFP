# Notification and Official Source Readiness Planning Document

> **Summary**: Add traceable email alerts and expand the tracker from a single 나라장터 connector to the highest-priority official climate-procurement sources.
>
> **Project**: Climate RFP Tracker
> **Version**: 0.2.0-draft
> **Author**: Codex
> **Date**: 2026-09-18
> **Status**: Approved for implementation by the requested continuation

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | Relevant tenders can be missed when staff manually search multiple portals, and repeated emails can obscure what is genuinely new. |
| **Solution** | Add a local SMTP notification module with delivery history, daily and weekly summaries, and a curated official-source catalog. |
| **Function/UX Effect** | The consultant can receive only newly detected opportunities, a daily 17:00 Korea-time briefing, and a weekly review without rechecking every portal. |
| **Core Value** | Each email keeps the notice URL, source, deadline, score, and collected RFP/task-document links traceable to the original source. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | Reduce missed climate/GHG/ETS consulting opportunities while retaining evidence and avoiding duplicate alerts. |
| **WHO** | ESG and climate consulting practitioners reviewing Korean public and approved public corporate procurement notices. |
| **RISK** | Missing API/SMTP credentials, source-page structure changes, and sending historical notices as if they were new. |
| **SUCCESS** | A configured SMTP account can send one deduplicated new-notice email, a daily briefing, and a weekly summary; unconfigured delivery never leaks credentials or silently marks messages sent. |
| **SCOPE** | Keyword noise control, briefing generation, notification state/delivery log, schedule scripts, and P0 source catalog integration. |

---

## 1. Overview

### 1.1 Purpose

Provide a practical local service that watches qualified opportunities and sends actionable emails after the next polling run, with a daily review at 17:00 Asia/Seoul and a weekly Friday 18:00 summary.

### 1.2 Background

The current MVP stores collected notices and document links locally, but it requires manual report checking. The supplied source catalog identifies official P0 inputs that should lead rollout: 나라장터, 나라장터 발주계획/사전규격, GIR, and the environment-ministry board. The supplied GitHub research supports direct official API integration and raw/provenance preservation, not blind code copying.

### 1.3 Related Documents

- Existing MVP plan: `docs/01-plan/features/rfp-climate-tracker.plan.md`
- Existing MVP design: `docs/02-design/features/rfp-climate-tracker.design.md`
- Source reference supplied by user: `C:/Users/24jos/Downloads/source_catalog.csv`
- Reuse reference supplied by user: `C:/Users/24jos/Downloads/10_GITHUB_RESEARCH.md`

---

## 2. Scope

### 2.1 In Scope

- [x] Exclude configured high-noise procurement terms before storage.
- [x] Generate a daily briefing with new, urgent, reviewed, and missing-document indicators.
- [x] Store notification baseline and delivery outcomes to prevent duplicate emails.
- [x] Provide generic SMTP delivery, test mode, and safe readiness reporting.
- [x] Provide Windows schedule-install scripts for 30-minute polling, 17:00 daily, and Friday 18:00 weekly runs.
- [x] Expand the 나라장터 용역 source filter to environment, climate, GHG, ETS, LCA, carbon-footprint, and environmental-impact-assessment terms.
- [x] Add GIR and the environment-ministry official boards as catalogued source candidates.

### 2.2 Out of Scope

- Bypassing login, CAPTCHA, robots restrictions, or private supplier portals.
- Sending email without the user’s SMTP credentials or a configured sender address.
- Treating keyword relevance as a legal bidding-eligibility decision.
- Bulk downloading or OCR of private RFP files.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | Filter notices matching configured exclusion terms before they enter normal results. | High | Complete |
| FR-02 | Create HTML and Markdown daily briefing files from local notices and document links. | High | Complete |
| FR-03 | Send deduplicated immediate, daily, and weekly emails through standard SMTP when explicitly requested. | High | Complete, SMTP credential pending |
| FR-04 | Record each attempted/successful delivery and keep a start-time baseline so old notices are not presented as newly detected. | High | Complete |
| FR-05 | Make an unconfigured SMTP account visible through a readiness command without exposing password values. | High | Complete |
| FR-06 | Add P0 official source candidates from the supplied catalog and disclose each source’s connection status. | High | Complete |
| FR-07 | Supply Windows scheduler scripts for 30-minute polling, daily 17:00, and weekly Friday 18:00 runs. | Medium | Complete, activation gated |
| FR-08 | Filter official 나라장터 service bids for environment, climate, GHG, ETS, LCA, carbon footprint, and environmental impact assessment. | High | Complete, service key pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Reliability | Delivery is recorded only after SMTP accepts the message. | SQLite delivery-log tests with a fake sender. |
| Security | Passwords remain in ignored `.env`; reports never print secret values. | Code inspection and readiness tests. |
| Traceability | Email records preserve the notice/source IDs and message purpose. | SQLite query and generated email preview. |
| Maintainability | Uses Python standard library and JSON configuration only. | Compile and unit-test run on Windows. |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [x] All listed functional requirements are implemented.
- [x] Unit tests cover exclusion, notification baseline, delivery de-duplication, and briefing content.
- [x] A dry-run produces email-ready content without sending external mail.
- [x] Documentation explains the one-time SMTP and scheduler setup.

### 4.2 Quality Criteria

- [x] Existing tests remain passing.
- [x] Unconfigured SMTP returns a specific readiness result rather than a false success.
- [x] A daily run cannot send the same daily key to the same recipient twice.

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| SMTP provider requirements vary | High | High | Use standard STARTTLS/SSL configuration and keep provider-specific values in `.env`. |
| 나라장터 service key is absent | High | High | Preserve a readiness gate and allow public official-board testing independently. |
| Historical notices trigger a flood after first setup | High | Medium | Require/automatically establish a notification baseline before immediate delivery. |
| Source pages change or expose only JavaScript content | Medium | Medium | Keep sources disabled until a live preview passes; report source-specific failures. |
| Corporate/private collection violates policy | High | Medium | Keep private sources disabled and require terms/permission review. |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `rfp_tracker/storage.py` | SQLite schema | Add notification state and delivery-log tables plus query helpers. |
| `rfp_tracker/cli.py` | CLI | Add briefing, notification, and readiness commands. |
| `rfp_tracker/keyword_matcher.py` / `fetchers.py` | Collection rules | Honor exclusion terms before relevance scoring/storage. |
| `configs/*.json`, `.env.example` | Configuration | Add official source candidates and SMTP/notification settings. |
| `scripts/*.ps1` | Operations | Add report and schedule-capable alert-cycle scripts. |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| SQLite notices | Create/update | `sync_command` → `upsert_notice` | Must preserve existing notice IDs and review data. |
| SQLite notices | Read | `render`, `export-csv`, `rfp-documents`, `list`, `stats` | New notification tables must not change existing reads. |
| Source config | Read | `sync_command` → `enabled_sources` → `build_fetcher` | Unsupported catalog candidates remain disabled. |
| Runner script | Run | `run_tracker.ps1`, `run_live_g2b_check.ps1` | Added outputs must preserve current parameters/defaults. |

### 6.3 Verification

- [ ] Existing report and review commands work against migrated SQLite databases.
- [ ] New delivery keys are unique per recipient/purpose.
- [ ] Live source URLs are tested only with limited public requests.

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple Python modules and local SQLite | Current local operational MVP | ☒ |
| **Dynamic** | Hosted app and user authentication | Later multi-user service | ☐ |
| **Enterprise** | Microservices and multi-tenant control | Future large-scale rollout | ☐ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Email transport | Provider SDK / SMTP | Python standard-library SMTP | Works with the user’s provider without a new vendor account. |
| Delivery state | File / SQLite | SQLite | One durable local record protects against duplicate mail. |
| Scheduler | Cloud runner / Windows Task Scheduler | Windows scripts with install command | Matches the current Windows-local workflow and keeps data local. |
| Source rollout | Mass crawling / official-first | Official-first | Prioritizes provenance, access control, and stable operation. |
| Testing | Live mail / fake sender | Fake sender plus dry-run | Does not send external email during validation. |

### 7.3 Clean Architecture Approach

`briefing.py` prepares business content, `notifications.py` owns delivery policy, `storage.py` persists state, and PowerShell only orchestrates commands. The collector does not depend on SMTP.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] Python standard-library-first modules
- [x] Windows-compatible PowerShell scripts
- [x] `.env.example` without live secrets
- [x] `unittest` test suite

### 8.2 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `SMTP_HOST` | Outbound mail host | Local only | ☒ |
| `SMTP_PORT` | Provider port | Local only | ☒ |
| `SMTP_USERNAME` | SMTP authentication name | Local only | ☒ |
| `SMTP_PASSWORD` | SMTP app password/token | Local only | ☒ |
| `SMTP_FROM` | Visible sender address | Local only | ☒ |

---

## 9. Next Steps

1. [x] Write the pragmatic design document.
2. [x] Implement and test the alert cycle without actual credentials.
3. [ ] Add the user’s chosen SMTP credential values locally and send a single test message.
4. [ ] Register the scheduler only after the test message succeeds.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-18 | Initial plan from the supplied source and GitHub research | Codex |
