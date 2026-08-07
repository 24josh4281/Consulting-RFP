param(
  [Parameter(Mandatory = $true)]
  [string]$RepoUrl,

  [string]$RemoteName = "origin",

  [string]$Branch = "main",

  [switch]$ReplaceExistingRemote,

  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

function Run-Git {
  param([string[]]$GitArgs)

  if ($DryRun) {
    Write-Output ("DRY RUN: git " + ($GitArgs -join " "))
    return
  }

  & git @GitArgs
  if ($LASTEXITCODE -ne 0) {
    throw "git command failed: git $($GitArgs -join ' ')"
  }
}

if (-not (Test-Path -LiteralPath ".git")) {
  throw "This folder is not a git repository. Run this from the project root."
}

if ($RepoUrl -notmatch "^https://github\.com/.+/.+\.git$" -and $RepoUrl -notmatch "^git@github\.com:.+/.+\.git$") {
  throw "RepoUrl should look like https://github.com/OWNER/REPO.git or git@github.com:OWNER/REPO.git"
}

$currentBranch = (& git branch --show-current).Trim()
if ($currentBranch -ne $Branch) {
  throw "Current branch is '$currentBranch', but this script is configured for '$Branch'."
}

$status = (& git status --porcelain)
if ($status) {
  if ($DryRun) {
    Write-Output "DRY RUN WARNING: Working tree is not clean. Actual push would stop here."
  } else {
    throw "Working tree is not clean. Commit or stash changes before pushing to GitHub."
  }
}

$existingRemote = (& git remote) | Where-Object { $_ -eq $RemoteName }
if ($existingRemote) {
  if (-not $ReplaceExistingRemote) {
    $existingUrl = (& git remote get-url $RemoteName).Trim()
    throw "Remote '$RemoteName' already exists: $existingUrl. Re-run with -ReplaceExistingRemote to update it."
  }
  Run-Git @("remote", "set-url", $RemoteName, $RepoUrl)
} else {
  Run-Git @("remote", "add", $RemoteName, $RepoUrl)
}

Run-Git @("remote", "-v")
Run-Git @("push", "-u", $RemoteName, $Branch)

Write-Output "GitHub connection complete: $RepoUrl"
