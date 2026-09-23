# Innergen source expansion — Design Document

> Project: Consulting-RFP | Date: 2026-09-23 | Status: Approved | Plan: [source expansion](../../01-plan/features/innergen-source-expansion.plan.md)

## Context Anchor

| Key | Value |
|---|---|
| WHY | Client funding calls are fragmented outside G2B. |
| WHO | Innergen consultants and client companies. |
| RISK | Stale deadlines, duplicate syndication, source copyright, new API credential, KICoX TLS issue. |
| SUCCESS | Conservative parsers and tests; only verified notices in operational/public output. |
| SCOPE | KEITI/KICoX boards and Bizinfo API connector; no application submission or document downloads. |

## 1. Overview

Separate reading/normalization from existing G2B and source-neutral storage. Applicant calls always use `category=grant_application`; they never become Tier 1 bids.

## 2. Architecture Options

| Option | Change | Trade-off |
|---|---|---|
| A | Put all parsing in `fetchers.py` | Small diff, brittle and coupled. |
| B | Separate subsystems, schema migration | Clean but overbuilt. |
| C (selected) | Source-specific readers + existing `Notice`/Tier 2 | Clear boundaries without migration. |

Flow: official list/API → exact climate applicant filter → date/status evidence → `Notice` → SQLite → existing Tier 2 display/digest. Disabled sources cannot affect production output.

## 3. Data Model

No migration. `(source_id, external_id)` remains the identity. `raw` stores only provenance, application start/status and retrieval timestamp. Bizinfo's original description is neither used for classification nor copied to public output; selection is title-led. Financed amount is not guessed from a programme's total budget.

## 4. API Specification

Bizinfo official endpoint: `GET https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do` with `crtfcKey`, `dataType=json`, bounded `searchCnt`, `pageUnit` and `pageIndex`. Parse `jsonArray.item` with documented alternate field names (`seq`/`pblancId`, `reqstDt`/`reqstBeginEndDe`). Require a separate `BIZINFO_API_KEY`; the data.go.kr G2B key is not reused. No request when key is missing or source disabled.

KEITI/KICoX use official public GET list/detail only. KEITI listing `bcIdx`; KICoX `PB_...` identifier. Do not follow JS-only attachment download handlers. KICoX stays off while Python TLS cannot negotiate a secure connection.

## 5. UI/UX

Reuse the current dashboard's `지원금 신청`, Tier 2 and application deadline rendering. No new UI control. Grant rows must link to the original official call and never claim `접수 중` without an evidenced deadline. No public Bizinfo output in this cycle.

### Page checklist

- [x] Existing grant-type filter remains functional (public payload regression test).
- [x] Source name, original title/link, application deadline and Tier 2 badge render for a verified fixture.
- [x] Unknown/closed grants are not highlighted as active (including KICoX `마감`).

## 6. Error Handling

Source failures produce a partial sync status and source ID/type-only warning, not a leaked URL with key. Malformed JSON or missing ID fails closed. A page layout change yields no guessed notice.

## 7. Security

Only hardcoded HTTPS official hosts. Fixed query parameters; never log credentials, return raw API payload to public output, or disable TLS verification. Do not fetch private pages or download files. Publication requires separate source rights check.

## 8. Test Plan

| Level | Scenario | Expected |
|---|---|---|
| L1 | KEITI list/detail fixture | Correct ID/title and conservative deadline. |
| L1 | KICoX list/detail fixture | Closed status and exact application window. |
| L1 | Bizinfo JSON sample | Alternate fields, key-safe request, applicant filter. |
| L1 | Tiering | Funding/CBAM grant Tier 2, event/supplier bid excluded. |
| L2 | Public dashboard test | Existing grant badge/filter and no raw description. |
| L3 | Temporary DB sync | No duplicate same-source ID, closed not active. |

## 9. Structure

`rfp_tracker/grant_fetchers.py` handles public boards; `rfp_tracker/bizinfo_fetcher.py` handles API; `fetchers.py` dispatches. Config and tests get bounded additions.

## 10. Conventions

Standard library, explicit dates and units, immutable source title, source URL audit trail. No blanket keyword inclusion from buyer name or broad `환경` alone.

## 11. Implementation Guide

1. Parsers and tests.
2. Factory, Tier 2 gate, example configuration.
3. Limited KEITI live dry run and full test suite.
4. Update catalog; review generated/public files before optional push.

### 11.3 Session Guide

| Module | Scope |
|---|---|
| module-1 | Board/API parsers and fixtures. |
| module-2 | Integration, tiering, configuration. |
| module-3 | Local verification, catalog and safe rollout. |
