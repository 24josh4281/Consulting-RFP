# RFP Climate Tracker Check Report

> **Date**: 2026-08-07
> **Scope**: Local MVP validation with sample tender notices

## 1. Validation Summary

| Item | Result |
|------|--------|
| Unit tests | PASS: 3 tests |
| Sample sync | PASS: 3 relevant notices collected |
| Dashboard render | PASS: `reports/dashboard.html` generated |
| CSV export | PASS: `reports/notices.csv` generated |
| Attachment linking | PASS: 4 attachment candidates linked |
| Review workflow | PASS: notice status can be marked and summarized |
| Operations script | PASS: `scripts/run_tracker.ps1` executed successfully |

## 2. Evidence

### 2.1 Test Command

```powershell
python -m unittest discover -s tests
```

Result:

```text
Ran 3 tests
OK
```

### 2.2 Sync Command

```powershell
python -m rfp_tracker sync --config configs\sources.example.json --db data\rfp_tracker_mvp.db --days 30
```

Result:

```text
[sync] sample_esg_tenders: 후보 3건
[done] 수집 후보 3건, 신규 3건
```

### 2.3 Output Commands

```powershell
python -m rfp_tracker render --db data\rfp_tracker_mvp.db --out reports\dashboard.html
python -m rfp_tracker export-csv --db data\rfp_tracker_mvp.db --out reports\notices.csv
```

Result:

```text
dashboard.html: 3 notices
notices.csv: 3 notices
```

## 3. Data QA Findings

| Check | Finding | Action |
|-------|---------|--------|
| Unrelated tender noise | “청소 용역” initially risked matching if only tender terms were used | Required at least one ESG/climate/GHG/ETS domain keyword |
| Attachment linking | File links could become separate notices | File-extension links now attach to the previous relevant notice |
| API key safety | No key available in environment | G2B source remains disabled and skips if key is missing |

## 4. Remaining Gaps

| Gap | Severity | Recommendation |
|-----|----------|----------------|
| 나라장터 live API not tested | Medium | Set `DATA_GO_KR_SERVICE_KEY`, enable `g2b_service_bids`, test 3-day window |
| 민간 사이트별 상세 첨부 구조 unknown | High | Pick top 5 target sites and build adapters one by one |
| “실시간” scheduling not yet installed | Medium | Add Windows Task Scheduler script after source list stabilizes |
| Duplicate/changed notice lifecycle | Medium | Add status fields such as `new`, `reviewed`, `interesting`, `submitted`, `closed` |

## 5. Match Rate

Static implementation and sample runtime checks meet the MVP success criteria.

Estimated MVP match rate after operational enhancement: **95%**

## 6. Operational Enhancement Validation

Additional commands verified after the initial MVP check:

```powershell
python -m rfp_tracker list --db data\rfp_tracker_operational.db --limit 10
python -m rfp_tracker review --db data\rfp_tracker_operational.db --id 1 --status interesting --note "CDP/Scope 3 제안 검토 후보"
python -m rfp_tracker stats --db data\rfp_tracker_operational.db
powershell -ExecutionPolicy Bypass -File .\scripts\run_tracker.ps1 -Days 30 -Database data\rfp_tracker_script_test.db -Dashboard reports\dashboard.html -Csv reports\notices.csv
```

Results:

```text
list: 3 notices displayed
review: Notice 1 marked as interesting
stats: total=3, new=2, interesting=1
run_tracker.ps1: sync/render/export/stats completed
```
