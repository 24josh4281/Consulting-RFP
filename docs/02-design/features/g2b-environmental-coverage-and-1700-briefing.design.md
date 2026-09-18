# G2B Environmental Coverage and 17:00 Briefing Design Document

> **Summary**: A configuration-first expansion of the official 나라장터 service connector and the daily briefing schedule.
>
> **Project**: Climate RFP Tracker
> **Version**: 0.2.1-draft
> **Author**: Codex
> **Date**: 2026-09-18
> **Status**: Implemented
> **Planning Doc**: `docs/01-plan/features/g2b-environmental-coverage-and-1700-briefing.plan.md`

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | Find public environmental and climate consulting opportunities reliably. |
| **WHO** | ESG, climate, GHG, ETS, and environmental consultants. |
| **RISK** | Keyword noise and API call limits. |
| **SUCCESS** | Relevant environmental notices pass, operational noise is excluded, and daily briefing defaults to 17:00 KST. |
| **SCOPE** | Config, keywords, scheduler time, automated checks, and source documentation. |

## 1. Overview

### 1.1 Design Goals

- Preserve direct official API provenance rather than scrape the browser-gated G2B home page.
- Keep rules editable by consultants in JSON.
- Cap API pages conservatively while leaving a documented tuning point.

### 1.2 Design Principles

- Service notices first; construction/goods require a separately validated operation.
- Inclusion and exclusion are both explicit and testable.
- New-notice polling and the 17:00 digest are separate schedules.

## 2. Architecture Options

| Option | Approach | Trade-off | Decision |
|---|---|---|---|
| A | Add only broad `환경` keyword | Fast but noisy | Not selected |
| B | Add all G2B business types now | Wider coverage but unvalidated endpoints/traffic | Deferred |
| C | Service API + targeted environment profile + bounded pages | Useful coverage with manageable risk | **Selected** |

## 3. Data Flow

```text
G2B official service API (key required)
  → five-page maximum response window
  → keyword inclusion/exclusion scoring
  → SQLite raw notice + review status
  → 30-minute new-notice alert / 17:00 daily digest / Friday 18:00 weekly digest
```

## 4. Configuration Contract

| Setting | Value | Purpose |
|---|---|---|
| `g2b_service_bids.endpoint` | `https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc` | Official service-tender list access |
| `g2b_service_bids.service_key_param` | `serviceKey` | Current official API authentication parameter name |
| `g2b_service_bids.max_pages` | `5` | Max 500 records per sync with `numOfRows=100` |
| `keyword_groups.environment` | Environmental consulting signals | Inclusion scoring |
| `exclude_terms` | Cleaning/haulage noise | Overrides inclusion when clearly operational |
| `daily_send_at` | `17:00` | Daily KST briefing setting |
| `weekly_send_at` | `18:00` | Existing Friday weekly digest |

## 5. Error Handling and Security

- Missing `DATA_GO_KR_SERVICE_KEY` skips G2B safely; it never triggers a fake success.
- API requests use HTTPS and the configured user agent.
- SMTP remains independent from collection and remains blocked until local credentials exist.
- The user must review the original notice/RFP before any bid decision.

## 6. Test Plan

| Scenario | Expected result |
|---|---|
| `환경영향평가` + `탄소발자국` consulting notice | Included |
| `환경미화` / `폐기물 수집운반` tender | Excluded |
| Waste facility environmental impact assessment | Included, not blocked by generic waste wording |
| G2B fixture payload with environmental terms | Parsed as one relevant notice |
| Shared notification example config | Daily time is `17:00` |

## 7. Implementation Guide

1. Update keyword and source configuration.
2. Align notification defaults and Windows daily task to 17:00.
3. Update the active 30-minute heartbeat's time condition.
4. Run unit, compile, PowerShell, and dry-run checks.
