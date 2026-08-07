# RFP Document Index Analysis

> Date: 2026-08-07  
> Feature: RFP/task-document review index  
> Status: Implemented and validated on sample/local DB

## 1. Current Situation

The tracker already stored notices and attachment links in SQLite, but consultants still had to open each notice row to confirm whether the RFP, task statement, bid notice, submission form, pricing sheet, or contract document was available.

This created two operational gaps:

1. RFP-related files were not grouped by business purpose.
2. Notices without collected document links were not clearly visible as follow-up items.

## 2. Implemented Approach

The new document index reads the existing `notices` and `attachments` tables and creates one checklist row per document link.

No notice data or source data is overwritten. The feature only adds reporting logic.

Document categories:

| Category | Meaning |
|----------|---------|
| `rfp` | RFP / proposal request |
| `scope` | Task statement / 과업지시서 / Scope of Work |
| `notice` | Bid notice / 공고문 |
| `forms` | Submission forms / 서식 / 양식 |
| `pricing` | Pricing sheet / 산출내역서 / 견적 |
| `contract` | Contract / agreement / terms |
| `missing` | Notice exists, but no document link has been collected |
| `other` | Document link exists but type is not confidently classified |

## 3. Files Added or Updated

| File | Purpose |
|------|---------|
| `rfp_tracker/documents.py` | Classifies document links and generates HTML/CSV document reports |
| `rfp_tracker/cli.py` | Adds `rfp-documents` and `render-documents` commands |
| `scripts/run_tracker.ps1` | Generates document reports during the normal daily run |
| `tests/test_keyword_matcher.py` | Adds document classification and document-row tests |
| `README.md` | Adds document-index usage |
| `docs/OPERATIONS.md` | Adds operating guide for RFP document review |

## 4. Runtime Validation

Commands executed:

```powershell
python -m py_compile rfp_tracker\documents.py rfp_tracker\cli.py rfp_tracker\storage.py rfp_tracker\render.py
python -m unittest discover -s tests
python -m rfp_tracker sync --config configs\sources.example.json --db data\rfp_documents_test.db --days 30
python -m rfp_tracker render-documents --db data\rfp_documents_test.db --html reports\rfp_documents.html --csv reports\rfp_documents.csv
python -m rfp_tracker rfp-documents --db data\rfp_documents_test.db --limit 10
powershell -ExecutionPolicy Bypass -File .\scripts\run_tracker.ps1 -Days 30
```

Results:

| Check | Result |
|-------|--------|
| Python compile | PASS |
| Unit tests | PASS: 7 tests |
| Sample sync | PASS: 3 relevant sample notices |
| Sample document report | PASS: 4 document rows |
| Main local run | PASS: 5 notices, 6 document-check rows |

## 5. Business Meaning

The consultant can now review documents in two layers:

1. `reports/dashboard.html`: Which bid notices are relevant?
2. `reports/rfp_documents.html`: Which RFP/task documents are attached, and which notices still need document follow-up?

This makes the workflow closer to a real RFP operations board: notice discovery, RFP document review, status tracking, and Excel export are now connected.

## 6. Remaining Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Some portals hide documents behind login or JavaScript | Document row may show as `missing` | Add source-specific adapter after permission review |
| Current live G2B source is disabled without `DATA_GO_KR_SERVICE_KEY` | Real 나라장터 notices are not yet collected | Set API key and enable the source |
| Document type classification is keyword-based | Some files may be classified as `other` | Add terms as new source patterns are observed |
| Bulk file download is not implemented | HTML/CSV link review is available, but local file archive is not | Implement only after legal/storage approval |

## 7. Recommendation

Next best step:

1. Add `DATA_GO_KR_SERVICE_KEY` as an environment variable.
2. Enable the 나라장터 source in `configs/sources.example.json`.
3. Run a short live test with `--days 3`.
4. Review `reports/rfp_documents.html`.
5. Use `missing` rows to decide which source-specific parsers should be built first.
