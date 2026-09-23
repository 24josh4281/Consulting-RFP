# Official Grant Notice Intake Planning Document

> **Summary**: Add official corporate grant calls to the existing climate RFP tracker.
>
> **Project**: Consulting-RFP | **Date**: 2026-09-23 | **Status**: Implemented and locally verified

## Executive Summary

| Perspective | Content |
|-------------|---------|
| Problem | G2B equipment tenders are procurement by recipients, not applications for support; genuine grant calls are missed. |
| Solution | Read bounded, public official grant boards from KOSMES, KECO and KEA, retaining source URLs and deadline evidence. |
| Function/UX Effect | Tier 2 shows customer-application calls separately from bidding opportunities, with honest closed/unknown status. |
| Core Value | Innergen can recommend real support opportunities to clients without misrepresenting equipment tenders as grants. |

## Context Anchor

| Key | Value |
|-----|-------|
| WHY | Grant calls are absent from the G2B-heavy pipeline. |
| WHO | Innergen consultants and client companies considering GHG/ETS equipment support. |
| RISK | False-open status, supplier-procurement false positives, site structure changes. |
| SUCCESS | Official source URLs, correct deadline/status, Tier 2 grant labeling, passing tests. |
| SCOPE | Public HTML boards only; no login, form submission, or grant application automation. |

## 1. Overview

The existing `sync`/SQLite/public-dashboard/email pipeline already handles notices and Tier 2, but no grant-specific source is enabled. This cycle adds official intake with minimum changes to current behavior.

## 2. Scope

### In scope

- [x] Public KOSMES corporate carbon-equipment grant board.
- [x] KECO ETS carbon-equipment grant calls from its public notice board.
- [x] KEA ETS reduction-equipment and carbon-equipment auction notice boards.
- [x] Exact original links, application deadline and explicit source-type label.
- [x] Scheduled sync integration, tests, and public-safe dashboard projection.

### Out of scope

- Application/login automation; scraping authenticated e-Naradoum pages.
- General environmental grants without a climate/GHG/ETS equipment connection.
- Claiming every government grant is covered or a funding award is guaranteed.

## 3. Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | Only capture official, public, applicant-facing support notices. | High |
| FR-02 | Capture stable ID, published/closing date, source/detail URL, public attachments when direct URLs exist. | High |
| FR-03 | Never call an undated grant open; respect explicit closed status. | High |
| FR-04 | Show a grant-application type independently of business Tier. | High |
| FR-05 | Keep Tier 1 immediate mail behavior; Tier 2 remains in daily/weekly active digests. | Medium |

## 4. Success Criteria

- [x] Parser tests for each board and application date formatting pass.
- [x] Non-grant board items and supplier equipment purchases are excluded from Tier 2 grant intake.
- [x] One bounded live dry run against official public pages succeeds without credentials or document downloads.
- [x] Existing suite passes and existing sample/secret exclusions remain intact.

## 5. Risks and Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| HTML layout changes | Missing notices | Fail visibly per source and test against observed HTML shape. |
| Date unknown or explicit closure | False-open customer recommendation | Treat unknown grant deadline and source-closed status as inactive. |
| Public exposure | Client confusion or private data leak | Publish only source facts through existing public projection; review generated diff. |

## 6. Impact Analysis

| Resource | Current consumers | Change |
|----------|-------------------|--------|
| `build_fetcher` and source configs | `sync`, `doctor`, scheduled tracker | Add one source type with bounded adapters. |
| `notices.category` and raw JSON | SQLite, workbench, email | Store grant evidence without schema migration. |
| `is_notice_active` | Dashboard, briefing, notifications | Grant-specific conservative rule. |
| Public payload/rendering | GitHub Pages snapshot | Add a type badge/filter and source-appropriate wording. |

## 7. Architecture Considerations

Use the existing Python standard-library fetch/config/storage pipeline. No new dependency or server. Scope is a small dynamic data-source extension, not a new app framework.

## 8. Convention Prerequisites

Preserve `.env` and local config secrecy, Windows-compatible commands, and original source content. The new source URLs require no API key.

## 9. Next Steps

1. Implement dedicated source parsers and tests using captured public-page shapes.
2. Verify on a temporary database before touching the operational database.
3. Back up operational DB, add sources, render and inspect locally.
4. Publish only if public-deployment approval is confirmed.
