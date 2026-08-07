param(
  [int]$Days = 14,
  [string]$Config = "configs\sources.example.json",
  [string]$Database = "data\rfp_tracker.db",
  [string]$Dashboard = "reports\dashboard.html",
  [string]$Csv = "reports\notices.csv",
  [string]$DocumentsHtml = "reports\rfp_documents.html",
  [string]$DocumentsCsv = "reports\rfp_documents.csv"
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

Invoke-Checked { python -m rfp_tracker sync --config $Config --db $Database --days $Days } "sync"
Invoke-Checked { python -m rfp_tracker render --db $Database --out $Dashboard } "render"
Invoke-Checked { python -m rfp_tracker export-csv --db $Database --out $Csv } "export-csv"
Invoke-Checked { python -m rfp_tracker render-documents --db $Database --html $DocumentsHtml --csv $DocumentsCsv } "render-documents"
Invoke-Checked { python -m rfp_tracker stats --db $Database } "stats"
