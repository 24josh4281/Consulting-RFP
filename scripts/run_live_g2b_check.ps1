param(
  [int]$Days = 3,
  [string]$BaseConfig = "configs\sources.example.json",
  [string]$Config = "configs\sources.local.json",
  [string]$Database = "data\rfp_tracker_live.db",
  [string]$Dashboard = "reports\dashboard_live.html",
  [string]$Csv = "reports\notices_live.csv",
  [string]$DocumentsHtml = "reports\rfp_documents_live.html",
  [string]$DocumentsCsv = "reports\rfp_documents_live.csv"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

function Invoke-Checked {
  param(
    [scriptblock]$Command,
    [string]$Name
  )

  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE"
  }
}

if (-not (Test-Path -LiteralPath $Config)) {
  Invoke-Checked { python -m rfp_tracker source-toggle --config $BaseConfig --out $Config --source-id g2b_service_bids --enable } "source-toggle"
}

Invoke-Checked { python -m rfp_tracker doctor --config $Config --strict } "doctor"

Invoke-Checked { powershell -ExecutionPolicy Bypass -File .\scripts\run_tracker.ps1 `
  -Days $Days `
  -Config $Config `
  -Database $Database `
  -Dashboard $Dashboard `
  -Csv $Csv `
  -DocumentsHtml $DocumentsHtml `
  -DocumentsCsv $DocumentsCsv } "run_tracker"
