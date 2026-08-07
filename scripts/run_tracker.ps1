param(
  [int]$Days = 14,
  [string]$Config = "configs\sources.example.json",
  [string]$Database = "data\rfp_tracker.db",
  [string]$Dashboard = "reports\dashboard.html",
  [string]$Csv = "reports\notices.csv"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

python -m rfp_tracker sync --config $Config --db $Database --days $Days
python -m rfp_tracker render --db $Database --out $Dashboard
python -m rfp_tracker export-csv --db $Database --out $Csv
python -m rfp_tracker stats --db $Database
