# Company Portal Expansion Check Report

> **Date**: 2026-08-07
> **Scope**: API key readiness, KRX public company universe, and safe public homepage portal discovery

## 1. Current Situation

The user requested a continuation of the Climate RFP Tracker with:

- Actual API key readiness
- Domestic companies with assets of KRW 2 trillion or more
- Company procurement/bidding portal discovery
- Execution, not just planning

## 2. Safety Boundary

The following actions were not performed automatically:

- API key issuance or login on behalf of the user
- Use of hidden credentials
- Login-based private procurement portal crawling
- Bulk crawling of all company portals
- Attachment download from private company portals

Reason: these require user-owned credentials, site-specific permissions, or legal/terms review.

## 3. Implemented

| Item | Result |
|------|--------|
| API key inventory | Added `configs/api_keys.example.json` |
| Environment example | Added `.env.example` |
| Key status command | Added `python -m rfp_tracker api-keys` |
| KRX company universe command | Added `python -m rfp_tracker companies-fetch-krx` |
| Homepage source generation | Added `python -m rfp_tracker company-sources` |
| Portal candidate discovery | Added `python -m rfp_tracker portal-discover` |
| Operations script | Added `scripts/run_company_portal_discovery.ps1` |
| Documentation | Added `docs/API_KEYS_AND_COMPANY_PORTALS.md` |

## 4. Execution Results

### 4.1 API Key Status

```text
DATA_GO_KR_SERVICE_KEY: MISSING
OPENDART_API_KEY: MISSING
```

Impact:

- 나라장터 live API cannot be executed yet.
- OpenDART-based asset filtering cannot be executed yet.

### 4.2 KRX Listed Company Universe

Command:

```powershell
python -m rfp_tracker companies-fetch-krx --out data\krx_listed_companies.csv
```

Result:

```text
KRX listed companies: 2802 rows
Companies with homepage: 2625 rows
```

### 4.3 Company Homepage Source Config

Command:

```powershell
python -m rfp_tracker company-sources --input data\krx_listed_companies.csv --out configs\company_homepages.generated.json --limit 100
```

Result:

```text
Generated disabled source config for first 100 companies with homepage.
```

### 4.4 Portal Discovery Limited Run

Command:

```powershell
python -m rfp_tracker portal-discover --input data\krx_listed_companies.csv --out reports\portal_candidates.csv --limit 20 --timeout 10
```

Result:

```text
candidate=17
failed=1
no_candidate=15
```

Note: Candidate count can exceed checked company count because one company may expose multiple procurement-like links.

## 5. Data QA Notes

| Finding | Interpretation |
|---------|----------------|
| KRX list includes listed companies, not only asset >= KRW 2T companies | Asset filtering still requires OpenDART or validated KIND financial data extraction |
| Generated company sources are disabled | Prevents accidental mass crawling |
| Portal discovery result is a candidate list | Human review and terms/permission check required |
| Some links match generic procurement terms like “조달” | These may be business-description pages, not procurement portals |

## 6. Remaining Gaps

| Gap | Severity | Required Input |
|-----|----------|----------------|
| Actual 나라장터 API execution | High | `DATA_GO_KR_SERVICE_KEY` |
| Actual asset >= KRW 2T filtering | High | `OPENDART_API_KEY` or official financial extract |
| All company portal crawling | High | Site-by-site permission/terms decision |
| Private procurement portal access | High | User-owned login/partner permissions |

## 7. Recommended Next Execution

After keys are available:

```powershell
$env:DATA_GO_KR_SERVICE_KEY="..."
$env:OPENDART_API_KEY="..."
python -m rfp_tracker api-keys
python -m rfp_tracker sync --config configs\sources.example.json --db data\rfp_tracker.db --days 3
```

For portal discovery scale-up:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_company_portal_discovery.ps1 -Limit 100
```

Do not use unlimited discovery until candidate quality and site permissions are reviewed.

