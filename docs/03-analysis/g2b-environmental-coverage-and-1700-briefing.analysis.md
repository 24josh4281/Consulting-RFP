# G2B Environmental Coverage and 17:00 Briefing Analysis

> **Status**: Checked
>
> **Date**: 2026-09-18
> **Related plan**: `docs/01-plan/features/g2b-environmental-coverage-and-1700-briefing.plan.md`
> **Related design**: `docs/02-design/features/g2b-environmental-coverage-and-1700-briefing.design.md`

## 1. Verification Summary

| Check | Result | Evidence |
|---|---|---|
| Official G2B route | Pass, authentication pending | The retired `BidPublicInfoService02` route returned error `12`; the current official route returned `SERVICE_KEY_IS_NULL` / error `20` when intentionally called without a key. |
| Current API contract | Pass | Configuration now uses `https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc` and the official `serviceKey` query parameter. |
| Actual G2B response shape | Pass by fixture | Parser handles the official `response.body.items.item` nesting. |
| Environmental relevance | Pass | Tests cover environmental impact assessment, carbon footprint/LCA consulting, and exclusion of cleaning/waste-haulage noise. |
| Daily schedule | Pass | Local notification status reports `17:00 KST`; Friday weekly briefing remains `18:00 KST`. |
| Code quality | Pass | 25 automated tests, Python compilation, and PowerShell parsing all passed. |
| End-to-end dry run | Safe pass | The collection cycle completed without sending mail; G2B correctly skipped because no real service key is configured. |

## 2. What Changed After the First Probe

The first no-key probe exposed a material issue: the previous `BidPublicInfoService02` URL returned the official `NO_OPENAPI_SERVICE_ERROR` response. The connector was corrected before activation rather than left in a misleading “ready” state.

The current public-data portal's embedded OpenAPI definition identifies the `ad/BidPublicInfoService` host and `getBidPblancListInfoServc` service operation. A no-key request now reaches the expected authentication gate. This confirms the route, but it does **not** prove authorised data access; that requires the user's own approved service key.

## 3. Operational Result

- The local 나라장터 service source is enabled and labelled P0 official.
- Each polling run is bounded to five 100-row pages (maximum 500 list rows) before local relevance filtering.
- `환경`, environmental impact assessment, LCA, carbon footprint, resource circulation, renewable energy, climate adaptation, GHG, ETS, and related consulting terms are scored transparently.
- Environmental beautification, cleaning, waste collection, haulage, and waste-processing-only notices are excluded unless a more specific environmental consulting phrase qualifies them.
- The Codex 30-minute heartbeat is active; it uses 17:00 KST for the daily digest condition and 18:00 KST on Friday for the weekly digest condition.

## 4. Unresolved Validation Boundaries

| Boundary | Why it remains open | Safe next validation |
|---|---|---|
| Live G2B records | `DATA_GO_KR_SERVICE_KEY` is not configured locally. | Add the approved key only to `.env`, then run a three-day collection check. |
| Email delivery | SMTP host, user, password, and sender are not configured. | Configure SMTP locally and send one explicit test message before enabling production sends. |
| Keyword precision | `환경` is intentionally broad. | Review the first candidate batch and add narrowly evidenced exclusions only. |
| Wider public coverage | Goods and construction have separate G2B operations. | Add separate adapters only after their current operations and business value are verified. |

## 5. Decision

This PDCA increment is ready for local activation, but not for claiming live 나라장터 ingestion or email delivery. Both are correctly held behind the user's API/SMTP credentials and a first authorised test.
