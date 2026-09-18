# G2B Environmental Coverage and 17:00 Briefing Planning Document

> **Summary**: Expand the official 나라장터 service-tender filter to environmental and climate consulting signals, and move the daily briefing to 17:00 Korea time.
>
> **Project**: Climate RFP Tracker
> **Version**: 0.2.1-draft
> **Author**: Codex
> **Date**: 2026-09-18
> **Status**: Approved by the requested continuation

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | The existing 나라장터 source primarily described climate/GHG/ETS, so environmental-impact, LCA, and resource-circulation consulting notices could be missed. |
| **Solution** | Use the official service-tender OpenAPI with a transparent expanded keyword profile and a bounded five-page polling limit. |
| **Function/UX Effect** | The daily email is prepared at 17:00 KST, while Friday's weekly review remains at 18:00 KST. |
| **Core Value** | More relevant public opportunities are found without using login bypasses or losing provenance to the official notice/API. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | Capture practical environment and climate consulting opportunities from 나라장터 before manual searches miss them. |
| **WHO** | Korean ESG, climate, GHG, ETS, and environmental consulting teams. |
| **RISK** | Broad environment terms can add facilities or waste-hauling noise; API volume is limited by the user's service key. |
| **SUCCESS** | Environmental consulting notices score as relevant, cleaning/hauling noise stays excluded, and the daily schedule displays 17:00 KST. |
| **SCOPE** | Keyword profile, G2B source configuration, notification defaults, schedules, documentation, and tests. |

---

## 1. Overview

### 1.1 Purpose

Make the 나라장터 service-bid connector useful for environment, climate, GHG, ETS, carbon-footprint, LCA, energy-efficiency, and environmental-impact-assessment consulting work.

### 1.2 Background

The official 나라장터 bid API supports separate business operations for goods, services, construction, and foreign procurement. This iteration targets **services**, which is the most relevant category for consulting. It does not claim coverage of every public procurement category or portal.

### 1.3 Related Documents

- Existing notification plan: `docs/01-plan/features/notification-and-official-source-readiness.plan.md`
- Existing notification design: `docs/02-design/features/notification-and-official-source-readiness.design.md`
- Official API reference: `https://www.data.go.kr/data/15129394/openapi.do`

## 2. Scope

### 2.1 In Scope

- [x] Add environmental consulting keyword signals and targeted exclusion terms.
- [x] Mark the 나라장터 service source as official P0 and add a G2B portal reference URL.
- [x] Bound each API poll to five pages to stay within a conservative development traffic profile.
- [x] Set daily notification configuration and Windows scheduler default to 17:00 KST.
- [x] Preserve Friday weekly briefing at 18:00 KST.

### 2.2 Out of Scope

- Using a G2B account, CAPTCHA bypass, or private supplier features.
- Activating goods/construction source operations without a separate live API validation.
- Sending email before SMTP credentials and a test message are configured.

## 3. Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | Environmental impact assessment, LCA, carbon footprint, resource circulation, renewable energy, and climate adaptation terms are evaluated. | High | Complete |
| FR-02 | Cleaning, environmental beautification, waste collection/haulage, and similar noise stay excluded. | High | Complete |
| FR-03 | 나라장터 service source is official P0, HTTPS, and limited to five 100-row pages per polling run. | High | Complete, service key pending |
| FR-04 | Daily briefing setting and Windows task default are 17:00 Asia/Seoul. | High | Complete |
| FR-05 | Weekly Friday briefing stays 18:00 Asia/Seoul. | Medium | Complete |

## 4. Success Criteria

- [x] Unit tests prove included and excluded environmental examples.
- [x] Configuration test proves P0 G2B profile and 17:00 daily setting.
- [x] Existing test suite and PowerShell parsing pass.
- [ ] Live G2B API run succeeds after the user adds `DATA_GO_KR_SERVICE_KEY`.

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Broad `환경` signal creates false positives | Medium | Medium | Keep a transparent exclusion list and human review status. |
| API key/traffic issue | High | High | No call without a configured key; cap at five pages and retain 30-minute polling. |
| Service-only scope misses construction implementation bids | Medium | Medium | Add a separately validated construction adapter in a later PDCA cycle. |
| Daily time is misunderstood as instant notification | Low | Medium | Keep 30-minute new-notice polling separate from the 17:00 digest. |

## 6. Impact Analysis

| Resource | Consumers | Change |
|----------|-----------|--------|
| `configs/keywords.json` | All fetchers | Expanded inclusion/exclusion profile. |
| `configs/sources*.json` | `sync_command`, scheduler | Official G2B metadata, HTTPS endpoint, bounded page count. |
| notification configuration | CLI, PowerShell, Codex heartbeat | Daily time changes from 18:00 to 17:00. |

## 7. Architecture Considerations

**Selected: Pragmatic starter approach.** No new service or dependency is introduced. The existing official API fetcher gathers service notices; the existing local scorer applies the expanded profile; SQLite retains raw data and review status; schedules only orchestrate those safe pieces.

## 8. Convention Prerequisites

- Python standard library and `unittest` remain the implementation baseline.
- API/SMTP secrets remain in ignored `.env` only.
- G2B public URL and API endpoint are configuration values, not hardcoded in business logic.

## 9. Next Steps

1. Add `DATA_GO_KR_SERVICE_KEY` locally and run a three-day G2B validation.
2. Review the first environmental candidate batch and add only evidence-based noise exclusions.
3. Decide whether a separately validated G2B construction source is needed.
