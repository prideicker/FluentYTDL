param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$Repo = 'D:\YouTube\FluentYTDL'
$now = (Get-Date).ToString('yyyyMMdd_HHmmss')
$archiveName = "archived_helpers2_$now"
$archiveDir = Join-Path $Repo "rabbish\$archiveName"

$candidates = @(
    'count_script_references.ps1',
    'temp_parse_scripts.ps1',
    'remove_config_history_auto.ps1',
    'remove_config_from_history.ps1',
    'force_cleanup_dist.ps1',
    'fetch_tools.ps1'
)

if ($DryRun) {
    Write-Host "DRYRUN: Would create archive dir: $archiveDir" -ForegroundColor Cyan
    foreach ($f in $candidates) {
        $src = Join-Path $Repo "scripts\$f"
        Write-Host "DRYRUN: $src -> $archiveDir : Exists=$(Test-Path $src)" -ForegroundColor Cyan
    }
    exit 0
}

# Create archive dir
if (-not (Test-Path $archiveDir)) { New-Item -Path $archiveDir -ItemType Directory | Out-Null }

# Move candidates
foreach ($f in $candidates) {
    $src = Join-Path $Repo "scripts\$f"
    if (Test-Path $src) {
        try {
            Move-Item -LiteralPath $src -Destination $archiveDir -Force -ErrorAction Stop
            Write-Host "Moved: $src -> $archiveDir" -ForegroundColor Green
        } catch {
            Write-Host ('Error moving {0}: {1}' -f $src, $_.Exception.Message) -ForegroundColor Red
        }
    } else {
        Write-Host "Not found (skipped): $src" -ForegroundColor Yellow
    }
}

# Create zip and remove temp folder
$zipPath = Join-Path $Repo "rabbish\$archiveName.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $archiveDir '*') -DestinationPath $zipPath -Force
Remove-Item -LiteralPath $archiveDir -Recurse -Force

# Update move log
$log = Join-Path $Repo 'rabbish\move_log.txt'
"[ARCHIVE] Created $zipPath on $(Get-Date)" | Out-File $log -Encoding utf8 -Append
(Get-ChildItem -Path (Join-Path $Repo 'rabbish') -Filter '*.zip' | Select-Object -ExpandProperty FullName) | Out-File $log -Encoding utf8 -Append

Write-Host "Archive created: $zipPath" -ForegroundColor Green

# Commit zip
try {
    git -C $Repo add $zipPath
    git -C $Repo commit -m "Archive additional helper scripts into rabbish/$archiveName.zip" | Out-Null
    Write-Host "Committed archive to git." -ForegroundColor Green
} catch {
    Write-Host "No git commit performed (maybe nothing to commit): $($_.Exception.Message)" -ForegroundColor Yellow
}
