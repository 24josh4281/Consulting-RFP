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
  [string]$DailySlot = "",
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
  python -m rfp_tracker reconcile-open-g2b `
    --db $Database `
    --config $Config `
    --best-effort `
    --quiet-if-done
} "reconcile-open-g2b"

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

Invoke-Checked {
  python -m rfp_tracker render-workbench `
    --db $Database `
    --out reports\rfp_workbench_official.html
} "render-workbench"

function Publish-PublicDashboard {
  $branch = (& git branch --show-current).Trim()
  if ($LASTEXITCODE -ne 0 -or $branch -ne "main") {
    throw "Public dashboard publishing requires the main branch."
  }
  $siteChanges = @(git status --porcelain -- site/index.html)
  if ($LASTEXITCODE -ne 0 -or $siteChanges.Count -gt 0) {
    throw "site/index.html has existing local changes; review them before scheduled publishing."
  }
  & git -c credential.interactive=never fetch --quiet origin main
  if ($LASTEXITCODE -ne 0) { throw "Could not check the remote main branch." }
  $localHead = (& git rev-parse HEAD).Trim()
  $remoteHead = (& git rev-parse origin/main).Trim()
  if ($localHead -ne $remoteHead) {
    throw "Local main and origin/main differ; review them before scheduled publishing."
  }

  Invoke-Checked {
    python -m rfp_tracker render-workbench `
      --db $Database `
      --out site\index.html `
      --public
  } "render-public-workbench"

  & git diff --quiet -- site/index.html
  if ($LASTEXITCODE -eq 0) { return }
  if ($LASTEXITCODE -ne 1) { throw "Could not compare the public dashboard." }
  & git add -- site/index.html
  if ($LASTEXITCODE -ne 0) { throw "Could not stage the public dashboard." }
  & git commit --only -m "chore: refresh public RFP dashboard" -- site/index.html
  if ($LASTEXITCODE -ne 0) { throw "Could not commit the public dashboard." }
  & git -c credential.interactive=never push origin main
  if ($LASTEXITCODE -ne 0) { throw "Could not publish the public dashboard." }
  Write-Host "[done] Public dashboard refreshed before email delivery."
}

if ($Send -and $Mode -in @("daily", "weekly", "daily-weekly")) {
  Publish-PublicDashboard
}

function Invoke-NotificationDispatch {
  param(
    [string]$DispatchMode,
    [string]$Slot = ""
  )
  $commandArgs = @(
    "-m", "rfp_tracker", "notifications", "dispatch",
    "--mode", $DispatchMode,
    "--db", $Database,
    "--config", $NotificationConfig
  )
  if ($DispatchMode -eq "daily") {
    if ([string]::IsNullOrWhiteSpace($Slot)) {
      throw "Daily mode needs -DailySlot (for example, 10:00 or 17:00)."
    }
    $commandArgs += @("--daily-slot", $Slot)
  }
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
    Invoke-NotificationDispatch -DispatchMode "daily" -Slot $DailySlot
    if ((Get-Date).DayOfWeek -eq [System.DayOfWeek]::Friday) {
      Invoke-NotificationDispatch -DispatchMode "weekly"
    }
  }
  default {
    Invoke-NotificationDispatch -DispatchMode $Mode -Slot $DailySlot
  }
}
