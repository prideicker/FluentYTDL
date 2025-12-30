param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# Source build folder (external workspace build)
$Source = 'D:\YouTube\build\FluentYTDL'
if (-not (Test-Path $Source)) {
    Write-Host "Source not found: $Source" -ForegroundColor Yellow
    exit 0
}

# Destination in repo rabbish with timestamp
$RepoRabbish = 'D:\YouTube\FluentYTDL\rabbish'
$TimeStamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$DestRoot = Join-Path $RepoRabbish $TimeStamp
$Dest = Join-Path $DestRoot 'build_FluentYTDL'

if ($DryRun) {
    Write-Host "DRYRUN: Would move:`n  $Source`n-> $Dest" -ForegroundColor Cyan
    exit 0
}

# Ensure destination root exists
if (-not (Test-Path $DestRoot)) { New-Item -Path $DestRoot -ItemType Directory | Out-Null }

# Perform move
try {
    Move-Item -LiteralPath $Source -Destination $Dest -Force -ErrorAction Stop
    $log = Join-Path $DestRoot 'move_build_log.txt'
    "Moved $Source -> $Dest on $(Get-Date)" | Out-File $log -Encoding utf8 -Append
    Write-Host "Moved source to: $Dest" -ForegroundColor Green
    Write-Host "Log written to: $log" -ForegroundColor Green
} catch {
    Write-Host "Error moving: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}