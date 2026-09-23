# Innergen source expansion — Planning Document

> Project: Consulting-RFP | Date: 2026-09-23 | Status: Approved for bounded implementation

## Executive Summary

| Perspective | Content |
|---|---|
| Problem | G2B is not the application channel for many client-facing carbon grants and loans. |
| Solution | Add KEITI and KICoX public boards plus the officially documented Bizinfo grant API. |
| Function/UX Effect | Relevant customer applications can enter the existing Tier 2 dashboard and digest, separate from Tier 1 procurement. |
| Core Value | Innergen can spot funding for clients without presenting a supplier tender as a grant or a closed call as active. |

## Context Anchor

| Key | Value |
|---|---|
| WHY | Client funding calls are fragmented outside G2B. |
| WHO | Innergen consultants and client companies. |
| RISK | Stale deadlines, duplicate syndication, source copyright, new API credential, KICoX TLS issue. |
| SUCCESS | Conservative parsers and tests; only verified notices in operational/public output. |
| SCOPE | KEITI/KICoX boards and Bizinfo API connector; no application submission or document downloads. |

## 1. Overview

KEITI has published a 2026 greenhouse-gas reduction equipment financing call. KICoX has a 2026 carbon-neutrality transition loan call. Bizinfo publishes climate-equipment, international-abatement, and CBAM support calls. These are primarily **applicant-facing Tier 2** sources, not Innergen procurement bids. MSIT/IRIS are broad R&D feeds and SME24 overlaps Bizinfo; defer those until the first three sources can be measured for noise and overlap.

Official references: [KEITI call](https://www.keiti.re.kr/site/keiti/ex/board/View.do?bcIdx=39923&cbIdx=277), [KICoX call](https://www.kicox.or.kr/netzerofin/pbanc/pbancList.do), [Bizinfo API specification](https://bizinfo.go.kr/apiDetail.do?id=bizinfoApi).

## 2. Scope

### In scope

- [x] Bounded public HTML parsing for KEITI and KICoX; stable source IDs and original links.
- [x] Bizinfo API parser using its **separate** `BIZINFO_API_KEY`, disabled until issued.
- [x] Title-led climate/ETS/CBAM/customer-support filter; Tier 2 applicant classification.
- [x] Deadline and explicit closed-status rules; unknown deadline is never active.
- [x] Fixture tests, local limited verification, source catalog and deployment safeguards.

### Out of scope

- Applying for a grant, logging in, bypassing TLS/access controls, downloading documents.
- Full reproduction of source content or attachments on GitHub Pages.
- Automatic deduplication of merely similar calls across agencies without a shared official ID.
- Claiming real-time completeness or activation of an unverified API.

## 3. Requirements

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-01 | Only applicant-facing climate/GHG/ETS/CBAM funding or consulting-support calls enter this channel. | High | Implemented with conservative title gate |
| FR-02 | Preserve original title, stable ID, source URL, publication date, supported deadline and status evidence. | High | Implemented; unavailable fields remain empty |
| FR-03 | No positive deadline/status evidence means not active. | High | Implemented and tested |
| FR-04 | Missing keys and source failures remain visible, without preventing G2B collection or leaking credentials. | High | Implemented and tested |
| FR-05 | Keep new sources disabled until connectivity, authority and publication terms are checked. | High | KEITI ON after limited live check; KICoX/Bizinfo OFF |

## 4. Success Criteria

- Parser tests distinguish a grant from an event, supplier bid, unrelated R&D, and financing announcement.
- A 2026 closed KICoX call stays inactive even if a future date is present elsewhere in the page.
- Existing tests pass; KEITI bounded live dry run is recorded; KICoX/Bizinfo limitations are explicit.
- Public output contains no API key, private memo, copied description or document body.

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| False open | Client acts on expired call | Medium | Require deadline; honor source closed status. |
| Copyright/public reuse | Unlicensed publication | Medium | Connector off by default; publish no Bizinfo content until terms/permission are settled. |
| Cross-source duplicates | Duplicate digest items | Medium | Keep distinct provenance; do not enable syndication until duplicate behavior is reviewed. |
| KICoX TLS failure in Python | Missed collection | High locally | Parser and fixture test only; remain disabled, no TLS downgrade. |

## 6. Impact Analysis

| Resource | Current consumers | Change |
|---|---|---|
| Source config/factory | `sync`, `sources` | New disabled sources and fetcher route. |
| `grant_fetchers.py` | Existing four grant boards | Additional site parsers; existing adapters unchanged. |
| Tiering | DB, dashboard, briefing/email | Grant-only support expansion; procurement classification unchanged. |
| Public projection | GitHub Pages | No new publication of restricted source content in this cycle. |

## 7. Architecture Considerations

User selected pragmatic option C: isolated site/API parsers feeding the existing `Notice` model, SQLite and Tier 2 workflow. Python standard library; no schema migration or new frontend framework. Secrets stay in ignored `.env`.

## 8. Convention Prerequisites

Use HTTPS, bounded pages/details, source host allowlists and type-only error logging. Add `BIZINFO_API_KEY=` to the example environment only; never commit a real key. Preserve operational DB and current notification settings.

## 9. Next Steps

Design → parser/test implementation → limited source checks → security/public diff review → push code only if safe.
