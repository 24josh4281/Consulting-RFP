---
template: analysis
version: 1.3
---

# G2B RFP Priority Review and Pages Analysis Report

> **Analysis Type**: implementation gap, data-flow, privacy review
>
> **Project**: Consulting-RFP
> **Analyst**: Codex
> **Date**: 2026-09-21
> **Design Doc**: [design](../02-design/features/g2b-rfp-priority-review-and-pages.design.md)

## Context Anchor

| Key | Result |
|---|---|
| WHY | Expand source-backed RFP review while keeping bid judgement private. |
| WHO | Innergen bid reviewers and public dashboard viewers. |
| RISK | Unsupported public files and disclosure of internal review data. |
| SUCCESS | Public links are recovered; official Tier 1 is separated; review data remains local-only. |
| SCOPE | G2B attachment backfill, document evidence, priority/fit UX, workbook, Pages snapshot. |

## Strategic Alignment Check

| Criterion | Status | Evidence |
|---|:---:|---|
| Named G2B URL/file-name pairs are recovered without API recall. | ✅ | `extract_g2b_spec_attachments`, `backfill_g2b_attachments`; 37 notices / 139 links added. |
| Direct public HWPX extraction is source-backed. | ✅ | 47 HWPX processed: 43 extracted, 4 safely retained as failures. |
| Official Tier 1 is separated from sample data. | ✅ | Derived `priority_status`; current dashboard has 2 official Tier 1 records and excludes 3 samples. |
| Fit review does not overwrite source facts. | ✅ | Separate `bid_fit_reviews` table and preservation test. |
| Public site contains only public facts. | ✅ | Whitelist projection and static assertion exclude internal field names, credentials, and sample domain. |
| Pages URL is live. | ⚠️ | Workflow pushed, but `Configure Pages` failed because the repository's Pages feature is not yet enabled. |

## Design vs Implementation

| Design component | Implementation | Status |
|---|---|:---:|
| G2B named attachment parser | `rfp_tracker/fetchers.py` | ✅ |
| Idempotent source-link backfill | `documents.py`, `storage.py` | ✅ |
| Separate human fit review | `bid_fit_reviews`, `fit-review` CLI | ✅ |
| Internal Tier 1 priority screen | `render.py` | ✅ |
| Bordered editable Excel review grid | `build_rfp_workbench_workbook.mjs` | ✅ |
| Public allowlist projection | `build_public_workbench_payload` | ✅ |
| Pages deployment | `.github/workflows/pages.yml` | ⚠️ activation prerequisite remains |

## Data-Flow and Security Check

```
G2B raw JSON -> named attachment facts -> public HWPX evidence -> internal workbench/Excel
                                                  |
human bid-fit record --------------------------------> internal workbench only
public allowlist -------------------------------------> site/index.html
```

- All review writes use parameterized SQL and validate controlled values before the upsert.
- The public renderer receives no `source_id`, Tier, review status/note, fit record, cache path, or downloader error text.
- `site/index.html` was scanned for private field names, credential markers, and `example.com`; none were present.
- `.env`, data, document cache, outputs, reports, and node modules were excluded from Git staging.

## Runtime Verification

| Check | Actual result | Status |
|---|---|:---:|
| Unit/regression tests | 65 / 65 passed | ✅ |
| Full compile check | `compileall` passed | ✅ |
| G2B actual backfill | 44 processed; 37 with explicit files; 139 added | ✅ |
| Public direct HWPX | 47 processed; 43 extracted; no protected-source bypass | ✅ |
| Workbook formula scan | 0 formula errors | ✅ |
| Workbook visual review | Borders, yellow editable columns, dropdowns confirmed | ✅ |
| Git push | `22b55b9` pushed to `main` | ✅ |
| Pages deploy | `Configure Pages` failed; Pages endpoint still 404 | ⚠️ |

## Remaining Gaps and Recommended Action

1. The four HWPX failures are retained as source links: three returned a non-HWPX response and one exceeded the 16 MB safety cap. Do not infer their content; review the official links manually or add a separately approved parser/limit policy.
2. A repository owner must sign in to GitHub and set **Settings → Pages → Build and deployment → Source → GitHub Actions**. Then rerun the existing workflow; no code change is needed.
3. The public dashboard is a reviewed static snapshot. Refresh it after a local collection cycle, then commit and push `site/index.html`.
