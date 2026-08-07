# Live Readiness Workflow Analysis

> Date: 2026-08-07  
> Feature: API key and live-source readiness workflow  
> Status: Implemented and validated

## 1. Current Situation

The tracker can run locally with sample data, but real 나라장터 collection requires `DATA_GO_KR_SERVICE_KEY`. Before this update, the user had to manually edit JSON and remember whether the key was present.

That is risky for a non-developer workflow because:

- a shared example config could be accidentally edited;
- a live source could be enabled without the required key;
- PowerShell native command failures may not stop scripts automatically.

## 2. Implemented Approach

| Item | Implementation |
|------|----------------|
| `.env` support | `python -m rfp_tracker ...` now loads project `.env` automatically without printing secrets |
| Local source config | `source-toggle` creates `configs/sources.local.json` instead of changing the shared example |
| Readiness check | `doctor` checks enabled sources and required API-key environment variables |
| Safe live script | `scripts/run_live_g2b_check.ps1` stops if `doctor --strict` fails |
| PowerShell failure handling | `run_tracker.ps1` and `run_live_g2b_check.ps1` now check `$LASTEXITCODE` after native commands |

## 3. Validation

Commands executed:

```powershell
python -m py_compile rfp_tracker\config.py rfp_tracker\cli.py rfp_tracker\api_keys.py rfp_tracker\fetchers.py
python -m unittest discover -s tests
python -m rfp_tracker source-toggle --source-id g2b_service_bids --enable --out configs\sources.local.json
python -m rfp_tracker doctor --config configs\sources.local.json
python -m rfp_tracker doctor --config configs\sources.local.json --strict
powershell -ExecutionPolicy Bypass -File .\scripts\run_live_g2b_check.ps1 -Days 3
powershell -ExecutionPolicy Bypass -File .\scripts\run_tracker.ps1 -Days 30
```

Results:

| Check | Result |
|-------|--------|
| Python compile | PASS |
| Unit tests | PASS: 9 tests |
| Source toggle | PASS: local config generated, example config preserved |
| Doctor non-strict | PASS: missing key reported without exposing secret values |
| Doctor strict | PASS: exits non-zero when key is missing |
| Live script without key | PASS: stops before live sync |
| Normal sample run | PASS: dashboard, notices CSV, RFP document reports generated |

## 4. Important Finding

PowerShell's `$ErrorActionPreference = "Stop"` does not reliably stop a script when a native command such as `python` exits with a non-zero code. The scripts now explicitly check `$LASTEXITCODE` after each command.

## 5. Remaining Risk

Live 나라장터 collection still cannot run until the user provides `DATA_GO_KR_SERVICE_KEY` through `.env` or a PowerShell environment variable.

## 6. Next Step

After the key is added:

```powershell
python -m rfp_tracker api-keys
powershell -ExecutionPolicy Bypass -File .\scripts\run_live_g2b_check.ps1 -Days 3
```
