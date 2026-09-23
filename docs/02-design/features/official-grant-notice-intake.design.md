# Official Grant Notice Intake Design Document

> **Project**: Consulting-RFP | **Date**: 2026-09-23 | **Status**: Implemented and locally verified
> **Planning Doc**: [official-grant-notice-intake.plan.md](../../01-plan/features/official-grant-notice-intake.plan.md)

## Context Anchor

| Key | Value |
|-----|-------|
| WHY | Grant calls are absent from the G2B-heavy pipeline. |
| WHO | Innergen consultants and client companies considering GHG/ETS equipment support. |
| RISK | False-open status, supplier-procurement false positives, site structure changes. |
| SUCCESS | Official source URLs, correct deadline/status, Tier 2 grant labeling, passing tests. |
| SCOPE | Public HTML boards only; no login, form submission, or grant application automation. |

## 1. Overview

Keep source parsing isolated from the existing G2B fetcher, reuse `Notice` and SQLite upsert, and derive public notice type from `category`.

## 2. Architecture Options

| Option | Approach | Trade-off |
|--------|----------|-----------|
| A | One broad regex scraper in `fetchers.py` | Few files, brittle board-specific behavior. |
| B | Separate fetcher, schema migration, status service | More explicit, unnecessarily large for this pipeline. |
| C (selected) | Separate bounded grant fetcher using existing notice model | Clear source-specific rules with minimal migration risk. |

Data flow: official public list → specific public detail → verified application deadline/status → `Notice(category=grant_application)` → existing upsert → Tier 2 → public dashboard and daily digest.

## 3. Data Model

No schema change. `source_id` + board ID is the stable key. `deadline_at` is the official application deadline; `raw_json` stores board status, application start, source type and retrieval provenance. If no deadline is extractable, the record is not considered open.

## 4. API Specification

No new API. GET public HTML only; no key, authentication, or POST to grant sites. KOSMES detail uses public GET parameters even though its website UI normally posts a form.

## 5. UI/UX Design

- [x] Type badge: `지원금 신청` or `입찰·구매` independently of Tier.
- [x] Type filter: all / customer grant / bid-purchase.
- [x] Grant row wording: `운영기관`, `신청 마감`, `공고·첨부`; no bid-budget inference.
- [x] Unknown grant deadline never displays `접수 중`.
- [x] Existing Tier, urgency and document filters still work.

## 6. Error Handling

One source failure is surfaced in sync logs; no synthetic notices are written. Bound listing pages/details and add delay between detail requests. Missing date is an inactive, review-needed record rather than an active opportunity.

## 7. Security Considerations

Only HTTPS allowlisted official hosts, public pages and direct public attachments. No private account pages, file downloads, or secrets in static output. Escape rendered HTML.

## 8. Test Plan

| Level | Scenario | Expected |
|-------|----------|----------|
| L1 parser | KOSMES list/status/date | Correct stable IDs; closed status inactive. |
| L1 parser | KECO search + detail and KEA list/detail | Only grant calls, reliable deadline extraction. |
| L1 domain | Procurement with “지원사업” phrase | Not mislabeled as a grant. |
| L2 render | Mixed grant/bid payload | Type labels/filter and deadline wording present. |
| L3 workflow | Temporary DB live sync and render | No secrets, duplicates, or false-open grants. |

## 9. Structure

`rfp_tracker/grant_fetchers.py` owns source-specific parsing. Existing `fetchers.py` factory, `tiering.py`, `briefing.py`, `documents.py`, `render.py`, `public_ui.py`, configs and tests get narrow updates.

## 10. Conventions

Standard library only. Full URLs and official titles preserved. No unsupported financial amount or award-rate assumptions.

## 11. Implementation Guide

1. Parser and grant-specific validation.
2. Factory/config/sync classification.
3. Conservative status and public rendering.
4. Unit tests, live temporary DB, backup and operational sync.

### Session Guide

| Module | Scope |
|--------|-------|
| module-1 | Source parsing + source config + tests |
| module-2 | Status, classification, dashboard + tests |
| module-3 | Live verification and safe rollout |
