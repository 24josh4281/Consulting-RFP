param(
  [int]$Limit = 20,
  [string]$CompanyCsv = "data\krx_listed_companies.csv",
  [string]$PortalCsv = "reports\portal_candidates.csv",
  [string]$SourceConfig = "configs\company_homepages.generated.json",
  [int]$SourceLimit = 100
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

python -m rfp_tracker api-keys
python -m rfp_tracker companies-fetch-krx --out $CompanyCsv
python -m rfp_tracker company-sources --input $CompanyCsv --out $SourceConfig --limit $SourceLimit
python -m rfp_tracker portal-discover --input $CompanyCsv --out $PortalCsv --limit $Limit
