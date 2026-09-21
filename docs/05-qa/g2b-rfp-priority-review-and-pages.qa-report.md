---
template: qa-report
version: 2.1.1
---

# QA Report: G2B RFP Priority Review and Pages

> **Date**: 2026-09-21
> **Verdict**: PASS WITH DEPLOYMENT PREREQUISITE
> **Pass Rate**: 65/65 automated tests; 1 external Pages prerequisite outstanding
> **Critical Issues**: 0

## 1. Test Summary

| Level | Type | Status | Result |
|---|---|:---:|---|
| L1 | Python unit/regression | ✅ | 65/65 passed |
| L2 | Payload and static HTML privacy assertion | ✅ | official-only output; no internal fields/sample-domain/credential markers |
| L3 | Workbook build/inspect/formula scan | ✅ | 5 sheets, 0 formula errors |
| L4 | Visual UX check | ✅ | table borders, yellow editable cells, fit/decision dropdowns confirmed |
| L5 | Actual source data flow | ✅ | 139 G2B links recovered; 43 public HWPX extractions |
| L6 | GitHub Pages deployment | ⚠️ | workflow pushed; repository Pages activation not enabled |

## 2. Failed Tests / Controlled Exceptions

| Item | Result | Handling |
|---|---|---|
| 3 public URLs labeled HWPX | non-ZIP response | marked `download_failed`; original links retained |
| 1 public HWPX | exceeded 16 MB limit | marked `download_failed`; no override or bypass attempted |
| Pages configure step | GitHub Pages 404 / workflow failure | owner must enable Pages once through GitHub settings |

## 3. Metrics

| Metric | Value |
|---|---|
| G2B notices examined | 44 |
| Notices with explicit attachment pairs | 37 |
| G2B attachment links recovered | 139 |
| Direct HWPX processed | 47 |
| Extracted public documents | 43 |
| Current official Tier 1 priority records | 2 |
| Public snapshot records | 46 |
| Public document links | 145 |

## 4. Recommendations

- Enable GitHub Pages with GitHub Actions, then rerun the already-pushed workflow.
- Treat extracted amount as its labeled source basis, not as a final bid/award/contract price.
- Use `fit-review set` for dashboard-persistent Go/No-Go notes; Excel remains a convenient editable review sheet.
- Keep the 16 MB cap and protected-access boundary unless a separately reviewed policy changes them.
