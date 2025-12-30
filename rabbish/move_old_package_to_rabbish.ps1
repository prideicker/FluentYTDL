param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$RepoRoot = 'D:\YouTube\FluentYTDL'
$RabbishRoot = Join-Path $RepoRoot 'rabbish'
$TimeStamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$Dest = Join-Path $RabbishRoot $TimeStamp

$items = @(
    'scripts\package_menu.ps1',
    'scripts\package_zip.ps1',
    'scripts\package_zip.py',
    'scripts\package.ps1',
    'scripts\package.cmd'
)

if ($DryRun) {
    Write-Host "DRYRUN: Target dest: $Dest" -ForegroundColor Cyan
    foreach ($rel in $items) {
        $src = Join-Path $RepoRoot $rel
        Write-Host "DRYRUN: $src -> $($Dest) : Exists=$(Test-Path $src)" -ForegroundColor Cyan
    }
    exit 0
}

if (-not (Test-Path $Dest)) { New-Item -Path $Dest -ItemType Directory | Out-Null }
$log = Join-Path $Dest 'move_log.txt'

foreach ($rel in $items) {
    $src = Join-Path $RepoRoot $rel
    if (Test-Path $src) {
        $dst = Join-Path $Dest ([IO.Path]::GetFileName($rel))
        try {
            Move-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop
            "[MOVED] $src -> $dst" | Out-File $log -Encoding utf8 -Append
            Write-Host "Moved: $src -> $dst" -ForegroundColor Green
        } catch {
            "[ERROR] $src : $($_.Exception.Message)" | Out-File $log -Encoding utf8 -Append
            Write-Host ('Error moving {0}: {1}' -f $src, $_.Exception.Message) -ForegroundColor Red
        }
    } else {
        "[SKIP] Not found: $src" | Out-File $log -Encoding utf8 -Append
        Write-Host "Skip (not found): $src" -ForegroundColor Yellow
    }
}

# Create restore script
$restorePath = Join-Path $Dest 'rabbish_restore.ps1'
$restoreScriptTemplate = @'
param([switch]$DryRun)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$items = @(
"package_menu.ps1",
"package_zip.ps1",
"package_zip.py",
"package.ps1",
"package.cmd"
)
if ($DryRun) {
    Write-Host "DRYRUN: Restore list:" -ForegroundColor Cyan
    foreach ($f in $items) { Write-Host (("DRYRUN: {0} -> {1} : Exists={2}") -f (Join-Path $ScriptDir $f), (Join-Path "{DEST}" ("scripts\\" + $f)), (Test-Path (Join-Path $ScriptDir $f))) }
    exit 0
}
foreach ($f in $items) {
    $src = Join-Path $ScriptDir $f
    $dst = Join-Path "{DEST}" ("scripts\\" + $f)
    if (Test-Path $src) {
        $parent = Split-Path $dst -Parent
        if (-not (Test-Path $parent)) { New-Item -Path $parent -ItemType Directory | Out-Null }
        Move-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop
        (("Restored: {0} -> {1} on {2}") -f $src, $dst, (Get-Date)) | Out-File (Join-Path $ScriptDir 'restore_log.txt') -Encoding utf8 -Append
        Write-Host (("Restored: {0} -> {1}") -f $src, $dst) -ForegroundColor Green
    } else {
        Write-Host (("Nothing to restore at: {0}") -f $src) -ForegroundColor Yellow
    }
}
'@

$restoreScript = $restoreScriptTemplate -replace '{DEST}', $RepoRoot
$restoreScript | Out-File -FilePath $restorePath -Encoding utf8
"Move completed on $(Get-Date)" | Out-File $log -Encoding utf8 -Append
"Restore script created: $restorePath" | Out-File $log -Encoding utf8 -Append
Write-Host "Move finished. Log: $log" -ForegroundColor Green
Write-Host "Restore script: $restorePath" -ForegroundColor Green
