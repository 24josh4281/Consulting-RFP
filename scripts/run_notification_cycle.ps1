param(
  [ValidateSet("immediate", "daily", "weekly", "daily-weekly")]
  [string]$Mode = "immediate",
  [int]$Days = 3,
  [string]$Config = "configs\sources.local.json",
  [string]$NotificationConfig = "configs\notifications.local.json",
  [string]$Database = "data\rfp_tracker_official.db",
  [string]$Dashboard = "reports\dashboard_official.html",
  [string]$Csv = "reports\notices_official.csv",
  [string]$DocumentsHtml = "reports\rfp_documents_official.html",
  [string]$DocumentsCsv = "reports\rfp_documents_official.csv",
  [string]$BriefingHtml = "reports\briefing_official.html",
  [string]$BriefingMarkdown = "reports\briefing_official.md",
  [switch]$Send
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
  throw "Source config not found: $Config. Create a reviewed local source config before enabling scheduled collection."
}

if (-not (Test-Path -LiteralPath $NotificationConfig)) {
  throw "Notification config not found: $NotificationConfig. Run 'python -m rfp_tracker notifications setup --recipient your@email' first."
}

Invoke-Checked {
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_tracker.ps1 `
    -Days $Days `
    -Config $Config `
    -Database $Database `
    -Dashboard $Dashboard `
    -Csv $Csv `
    -DocumentsHtml $DocumentsHtml `
    -DocumentsCsv $DocumentsCsv `
    -BriefingHtml $BriefingHtml `
    -BriefingMarkdown $BriefingMarkdown
} "run_tracker"

function Invoke-NotificationDispatch {
  param([string]$DispatchMode)
  $commandArgs = @(
    "-m", "rfp_tracker", "notifications", "dispatch",
    "--mode", $DispatchMode,
    "--db", $Database,
    "--config", $NotificationConfig
  )
  if ($Send) {
    $commandArgs += "--send"
  }
  else {
    Write-Host "[note] Dry-run mode: email content will be prepared but not sent. Add -Send after one successful SMTP test."
  }
  Invoke-Checked { python @commandArgs } "notifications-$DispatchMode"
}

switch ($Mode) {
  "daily-weekly" {
    Invoke-NotificationDispatch -DispatchMode "daily"
    if ((Get-Date).DayOfWeek -eq [System.DayOfWeek]::Friday) {
      Invoke-NotificationDispatch -DispatchMode "weekly"
    }
  }
  default {
    Invoke-NotificationDispatch -DispatchMode $Mode
  }
}
