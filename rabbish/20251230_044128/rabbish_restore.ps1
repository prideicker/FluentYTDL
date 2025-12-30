param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$Root = 'D:\YouTube\FluentYTDL\rabbish\20251230_044128'
$BuildDir = Join-Path $Root 'build_FluentYTDL'
$Target = 'D:\YouTube\build\FluentYTDL'

if (-not (Test-Path $BuildDir)) {
    Write-Host "Nothing to restore: $BuildDir" -ForegroundColor Yellow
    exit 0
}

if ($DryRun) {
    Write-Host "DRYRUN: Would move:`n  $BuildDir`n-> $Target" -ForegroundColor Cyan
    exit 0
}

try {
    # Ensure parent exists
    $parent = Split-Path $Target -Parent
    if (-not (Test-Path $parent)) { New-Item -Path $parent -ItemType Directory | Out-Null }
    Move-Item -LiteralPath $BuildDir -Destination $Target -Force -ErrorAction Stop
    $log = Join-Path $Root 'restore_build_log.txt'
    "Restored $BuildDir -> $Target on $(Get-Date)" | Out-File $log -Encoding utf8 -Append
    Write-Host "Restored to: $Target" -ForegroundColor Green
    Write-Host "Log written to: $log" -ForegroundColor Green
} catch {
    Write-Host "Error restoring: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}