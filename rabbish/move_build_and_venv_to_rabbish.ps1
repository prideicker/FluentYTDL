param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$RepoRoot = 'D:\YouTube\FluentYTDL'
$RabbishRoot = Join-Path $RepoRoot 'rabbish'
$TimeStamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$Dest = Join-Path $RabbishRoot $TimeStamp

$entries = @(
    @{Name='build_FluentYTDL'; Source = Join-Path $RepoRoot 'build\FluentYTDL'; Dest = Join-Path $Dest 'build_FluentYTDL'; Restore = 'D:\\YouTube\\FluentYTDL\\build\\FluentYTDL' },
    @{Name='venv'; Source = Join-Path $RepoRoot '.venv'; Dest = Join-Path $Dest '.venv'; Restore = 'D:\\YouTube\\FluentYTDL\\.venv' }
)

if ($DryRun) {
    Write-Host "DRYRUN: Would create folder: $Dest" -ForegroundColor Cyan
    foreach ($e in $entries) {
        Write-Host "DRYRUN: $($e.Source) -> $($e.Dest) : Exists=$(Test-Path $e.Source)" -ForegroundColor Cyan
    }
    exit 0
}

# Create dest
if (-not (Test-Path $Dest)) { New-Item -Path $Dest -ItemType Directory | Out-Null }
$LogFile = Join-Path $Dest 'move_log.txt'

foreach ($e in $entries) {
    if (Test-Path $e.Source) {
        try {
            Move-Item -LiteralPath $e.Source -Destination $e.Dest -Force -ErrorAction Stop
            "[MOVED] $($e.Source) -> $($e.Dest)" | Out-File $LogFile -Encoding utf8 -Append
            Write-Host "Moved: $($e.Source) -> $($e.Dest)" -ForegroundColor Green
        } catch {
            "[ERROR] Failed moving $($e.Source): $($_.Exception.Message)" | Out-File $LogFile -Encoding utf8 -Append
            Write-Host "Error moving $($e.Source): $($_.Exception.Message)" -ForegroundColor Red
        }
    } else {
        "[SKIP] Not found: $($e.Source)" | Out-File $LogFile -Encoding utf8 -Append
        Write-Host "Skip (not found): $($e.Source)" -ForegroundColor Yellow
    }
}

# Create restore script in the timestamp folder
$restorePath = Join-Path $Dest 'rabbish_restore.ps1'
$restoreScriptTemplate = @'
param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$Root = '__DEST__'

$items = @(
    @{Src = Join-Path $Root 'build_FluentYTDL'; Target = 'D:\\YouTube\\FluentYTDL\\build\\FluentYTDL'},
    @{Src = Join-Path $Root '.venv'; Target = 'D:\\YouTube\\FluentYTDL\\.venv'}
)

if ($DryRun) {
    Write-Host "DRYRUN: Would restore the following:" -ForegroundColor Cyan
    foreach ($i in $items) { Write-Host "DRYRUN: $($i.Src) -> $($i.Target) : Exists=$(Test-Path $($i.Src))" }
    exit 0
}

foreach ($i in $items) {
    if (Test-Path $i.Src) {
        $parent = Split-Path $i.Target -Parent
        if (-not (Test-Path $parent)) { New-Item -Path $parent -ItemType Directory | Out-Null }
        Move-Item -LiteralPath $i.Src -Destination $i.Target -Force -ErrorAction Stop
        "Restored: $($i.Src) -> $($i.Target) on $(Get-Date)" | Out-File (Join-Path $Root 'restore_log.txt') -Encoding utf8 -Append
        Write-Host "Restored: $($i.Src) -> $($i.Target)" -ForegroundColor Green
    } else {
        Write-Host "Nothing to restore at: $($i.Src)" -ForegroundColor Yellow
    }
}
'@

$restoreScript = $restoreScriptTemplate -replace '__DEST__', $Dest
$restoreScript | Out-File -FilePath $restorePath -Encoding utf8
"Move completed on $(Get-Date)" | Out-File $LogFile -Encoding utf8 -Append
"Restore script created: $restorePath" | Out-File $LogFile -Encoding utf8 -Append

Write-Host "Move finished. Log: $LogFile" -ForegroundColor Green
Write-Host "Restore script: $restorePath" -ForegroundColor Green
