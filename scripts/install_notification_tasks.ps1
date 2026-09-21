param(
  [string]$TaskPrefix = "ClimateRfpTracker",
  [int]$PollMinutes = 30,
  [string]$Config = "configs\sources.local.json",
  [string]$NotificationConfig = "configs\notifications.local.json",
  [switch]$ReplaceExisting,
  [switch]$Send
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if ($PollMinutes -lt 5) {
  throw "PollMinutes must be 5 minutes or longer to respect source/API rate limits."
}
if (-not $Send) {
  throw "This installer creates real email tasks. First run a dry-run and a successful SMTP test, then rerun with -Send."
}

python -m rfp_tracker notifications status --db data\rfp_tracker_official.db --config $NotificationConfig --strict
if ($LASTEXITCODE -ne 0) {
  throw "Notification readiness check failed. Configure .env and the local recipient file before scheduling real email."
}

$CycleScript = Join-Path $PSScriptRoot "run_notification_cycle.ps1"
$PowerShellExe = Join-Path $PSHOME "powershell.exe"

function Test-TaskExists {
  param([string]$Name)
  & schtasks.exe /Query /TN $Name *> $null
  return $LASTEXITCODE -eq 0
}

function Register-AlertTask {
  param(
    [string]$Name,
    [string]$Mode,
    [string]$DailySlot = "",
    [string[]]$ScheduleArguments
  )

  if ((Test-TaskExists -Name $Name) -and -not $ReplaceExisting) {
    throw "Task already exists: $Name. Review it first, or rerun with -ReplaceExisting."
  }

  $DailySlotArgument = if ([string]::IsNullOrWhiteSpace($DailySlot)) { "" } else { " -DailySlot $DailySlot" }
  $Action = "`"$PowerShellExe`" -NoProfile -ExecutionPolicy Bypass -File `"$CycleScript`" -Mode $Mode$DailySlotArgument -Config `"$Config`" -NotificationConfig `"$NotificationConfig`" -Send"
  $arguments = @("/Create", "/TN", $Name, "/TR", $Action) + $ScheduleArguments
  if ($ReplaceExisting) {
    $arguments += "/F"
  }
  & schtasks.exe @arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to register scheduled task: $Name"
  }
  Write-Host "[done] Scheduled task: $Name"
}

Register-AlertTask -Name "$TaskPrefix-Immediate" -Mode "immediate" -ScheduleArguments @("/SC", "MINUTE", "/MO", "$PollMinutes")
Register-AlertTask -Name "$TaskPrefix-Daily1000" -Mode "daily" -DailySlot "10:00" -ScheduleArguments @("/SC", "DAILY", "/ST", "10:00")
Register-AlertTask -Name "$TaskPrefix-Daily1700" -Mode "daily" -DailySlot "17:00" -ScheduleArguments @("/SC", "DAILY", "/ST", "17:00")
Register-AlertTask -Name "$TaskPrefix-WeeklyFriday1800" -Mode "weekly" -ScheduleArguments @("/SC", "WEEKLY", "/D", "FRI", "/ST", "18:00")

Write-Host "[done] Real email schedules were registered. Check Task Scheduler history after the first run."
