<#
Copy of rabbish_isolate_clean.ps1 placed in rabbish/<timestamp>.
This copy adjusts path resolution so it can be run from inside the rabbish timestamp folder.
Usage: run from within the timestamp folder or anywhere; script will detect repository root.
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# Script dir (this file is inside rabbish/<timestamp>)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# If script is placed inside rabbish/<timestamp>, repo root is two levels up; otherwise assume script dir is repo root












































































Get-Content $LogFile -Encoding utf8 | Write-Hostif (-not $DryRun) { Write-Host "Isolation complete. See log: $LogFile" -ForegroundColor Green }" | Out-File $LogFile -Append -Encoding utf8Log file: $LogFile`rDestination folder: $Dest`rSummary at: $(Get-Date)`r"`rforeach ($it in $items) { Move-ItemSafe $it }# Execute moves}    }        "[ERROR] Failed to move $relPath : $($_.Exception.Message)" | Out-File $LogFile -Append -Encoding utf8    } catch {        "[MOVED] $relPath -> $($target) (SizeKB: $sizeKB)" | Out-File $LogFile -Append -Encoding utf8        $sizeKB = if ($info -and -not $info.PSIsContainer) { [math]::Round($info.Length / 1KB, 2) } else { '-' }        $info = Get-Item $target -ErrorAction SilentlyContinue        Move-Item -LiteralPath $abs -Destination $target -Force        $target = Join-Path $destParent (Split-Path $relPath -Leaf)        if (-not (Test-Path $destParent)) { New-Item -Path $destParent -ItemType Directory -Force | Out-Null }    try {    }        return        "[DRYRUN] Would move: $relPath -> $destParent" | Out-File $LogFile -Append -Encoding utf8    if ($DryRun) {    $destParent = if ($parent) { Join-Path $Dest $parent } else { $Dest }    $parent = Split-Path $relPath -Parent    }        return        "[SKIP] Not found: $relPath" | Out-File $LogFile -Append -Encoding utf8    if (-not (Test-Path $abs)) {    $abs = Join-Path $RepoRoot $relPathfunction Move-ItemSafe([string]$relPath) {if ($extraGitKeeps) { $items += $extraGitKeeps }}    $extraGitKeeps = Get-ChildItem -Path (Join-Path $RepoRoot 'release') -Recurse -Filter '.gitkeep' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName.Substring($RepoRoot.Length + 1).TrimStart('\') }if (Test-Path (Join-Path $RepoRoot 'release')) {$extraGitKeeps = @()# add low-confidence .gitkeep files under release/**/bin)    'scripts\placeholders\yt_dlp\YT_DLP_NOTE.txt'    'scripts\placeholders\js_runtime\PUT_JS_RUNTIME_HERE.txt',    'scripts\placeholders\ffmpeg\PUT_FFMPEG_HERE.txt',    'scripts\last_build_dist.txt',    'src\fluentytdl\ui\main_window.py',    'assets\f57465f5-904b-4b38-82ee-cd755d6eb1c7.png',    'release\FluentYTDL-v0.1.0-win64-20251229-full',    'build\FluentYTDL\localpycs',    'build\FluentYTDL',$items = @(# Items are identical to what was used earlier (you can edit before re-running)" | Out-File $LogFile -Encoding utf8DryRun: $DryRun`rDestination: $Dest`rRepository root: $RepoRoot`r"Move log generated: $(Get-Date)`r$LogFile = Join-Path $Dest 'move_log.txt'}    if (-not $DryRun) { New-Item -Path $Dest -ItemType Directory | Out-Null }if (-not (Test-Path $Dest)) {$Dest = Join-Path $RabbishRoot $TimeStamp$RabbishRoot = Join-Path $RepoRoot 'rabbish'$TimeStamp = (Get-Date).ToString('yyyyMMdd_HHmmss')Set-Location $RepoRootnif ($ScriptDir -match "\\rabbish\\\d{8}_\d{6}$") { $RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir) } else { $RepoRoot = $ScriptDir }