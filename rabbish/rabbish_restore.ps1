<#
rabbish_restore.ps1
Restore files moved into this timestamp folder back to the repository root.
Usage:
  - Dry run to see actions: powershell -NoProfile -ExecutionPolicy Bypass -File .\rabbish_restore.ps1 -DryRun
  - To actually restore: powershell -NoProfile -ExecutionPolicy Bypass -File .\rabbish_restore.ps1
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# This script is expected to live inside rabbish/<timestamp>
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RabbishTimestampFolder = $ScriptDir

# Repo root is two levels up from the timestamp folder
$RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

Write-Host "Restore: source=$RabbishTimestampFolder  repo=$RepoRoot  DryRun=$DryRun" -ForegroundColor Cyan

# Safety: do not allow restoring into an unexpected repo root that doesn't look like a project
if (-not (Test-Path (Join-Path $RepoRoot 'main.py'))) {
    Write-Host "Warning: target repo root does not contain main.py. Aborting." -ForegroundColor Red
    exit 1
}

$LogFile = Join-Path $RabbishTimestampFolder 'restore_log.txt'
"Restore log generated: $(Get-Date)`r
Source: $RabbishTimestampFolder`r
Repository root: $RepoRoot`r
DryRun: $DryRun`r
" | Out-File $LogFile -Encoding utf8

# Collect items to restore (all top-level entries in the timestamp folder except the log and scripts)
$entries = Get-ChildItem -Path $RabbishTimestampFolder -Force | Where-Object { $_.Name -notin @('move_log.txt','restore_log.txt','rabbish_restore.ps1','rabbish_isolate_clean.ps1') }

function Restore-ItemSafe([System.IO.FileSystemInfo]$item) {
    $rel = $item.FullName.Substring($RabbishTimestampFolder.Length + 1)
    $dest = Join-Path $RepoRoot $rel

    if ($DryRun) {
        "[DRYRUN] Would move: $rel -> $dest" | Out-File $LogFile -Append -Encoding utf8
        return
    }

    try {
        $parent = Split-Path $dest -Parent
        if (-not (Test-Path $parent)) { New-Item -Path $parent -ItemType Directory -Force | Out-Null }
        Move-Item -LiteralPath $item.FullName -Destination $dest -Force
        "[RESTORED] $rel -> $dest" | Out-File $LogFile -Append -Encoding utf8
    } catch {
        "[ERROR] Failed to restore $rel : $($_.Exception.Message)" | Out-File $LogFile -Append -Encoding utf8
    }
}

foreach ($e in $entries) {
    Restore-ItemSafe $e
}

"`r
Summary at: $(Get-Date)`r
Source folder: $RabbishTimestampFolder`r
Log file: $LogFile`r
" | Out-File $LogFile -Append -Encoding utf8

if (-not $DryRun) { Write-Host "Restore complete. See log: $LogFile" -ForegroundColor Green }
Get-Content $LogFile -Encoding utf8 | Write-Host
