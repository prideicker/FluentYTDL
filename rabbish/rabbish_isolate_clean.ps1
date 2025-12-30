<#
rabbish_isolate_clean.ps1
Safer replacement that moves confirmed redundant items into a timestamped subfolder under `rabbish/`.
Usage: run from repository root (where project files like main.py exist):
    powershell -NoProfile -ExecutionPolicy Bypass -File .\rabbish_isolate_clean.ps1
This script MOVES files (no deletion). A log will be created at the destination.
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# Repo root = script directory
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$TimeStamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$RabbishRoot = Join-Path $RepoRoot 'rabbish'
$Dest = Join-Path $RabbishRoot $TimeStamp

if (-not (Test-Path $Dest)) {
    if (-not $DryRun) { New-Item -Path $Dest -ItemType Directory | Out-Null }
}

$LogFile = Join-Path $Dest 'move_log.txt'
"Move log generated: $(Get-Date)`r
Repository root: $RepoRoot`r
Destination: $Dest`r
DryRun: $DryRun`r
" | Out-File $LogFile -Encoding utf8

$items = @(
    'build\FluentYTDL',
    'build\FluentYTDL\localpycs',
    'release\FluentYTDL-v0.1.0-win64-20251229-full',
    'assets\f57465f5-904b-4b38-82ee-cd755d6eb1c7.png',
    'src\fluentytdl\ui\main_window.py',
    'scripts\last_build_dist.txt',
    'scripts\placeholders\ffmpeg\PUT_FFMPEG_HERE.txt',
    'scripts\placeholders\js_runtime\PUT_JS_RUNTIME_HERE.txt',
    'scripts\placeholders\yt_dlp\YT_DLP_NOTE.txt'
)

# add low-confidence .gitkeep files under release/**/bin
$extraGitKeeps = @()
if (Test-Path (Join-Path $RepoRoot 'release')) {
    $extraGitKeeps = Get-ChildItem -Path (Join-Path $RepoRoot 'release') -Recurse -Filter '.gitkeep' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName.Substring($RepoRoot.Length + 1).TrimStart('\') }
}
if ($extraGitKeeps) { $items += $extraGitKeeps }

function Move-ItemSafe([string]$relPath) {
    $abs = Join-Path $RepoRoot $relPath
    if (-not (Test-Path $abs)) {
        "[SKIP] Not found: $relPath" | Out-File $LogFile -Append -Encoding utf8
        return
    }

    $parent = Split-Path $relPath -Parent
    $destParent = if ($parent) { Join-Path $Dest $parent } else { $Dest }

    if ($DryRun) {
        "[DRYRUN] Would move: $relPath -> $destParent" | Out-File $LogFile -Append -Encoding utf8
        return
    }

    try {
        if (-not (Test-Path $destParent)) { New-Item -Path $destParent -ItemType Directory -Force | Out-Null }
        $target = Join-Path $destParent (Split-Path $relPath -Leaf)
        Move-Item -LiteralPath $abs -Destination $target -Force
        $info = Get-Item $target -ErrorAction SilentlyContinue
        $sizeKB = if ($info -and -not $info.PSIsContainer) { [math]::Round($info.Length / 1KB, 2) } else { '-' }
        "[MOVED] $relPath -> $($target) (SizeKB: $sizeKB)" | Out-File $LogFile -Append -Encoding utf8
    } catch {
        "[ERROR] Failed to move $relPath : $($_.Exception.Message)" | Out-File $LogFile -Append -Encoding utf8
    }
}

# Execute moves
foreach ($it in $items) { Move-ItemSafe $it }

"`r
Summary at: $(Get-Date)`r
Destination folder: $Dest`r
Log file: $LogFile`r
" | Out-File $LogFile -Append -Encoding utf8

if (-not $DryRun) { Write-Host "Isolation complete. See log: $LogFile" -ForegroundColor Green }
Get-Content $LogFile -Encoding utf8 | Write-Host
