<#
rabbish_isolate.ps1
Safer replacement that moves confirmed redundant items into a timestamped subfolder under `rabbish/`.
Usage: run from repository root (where project files like main.py exist):
    powershell -NoProfile -ExecutionPolicy Bypass -File .\rabbish_isolate.ps1
This script MOVES files (no deletion). A log will be created at the destination.
#>

































































Get-Content $LogFile -Encoding utf8 | Write-Host
nif (-not $DryRun) { Write-Host "Isolation complete. See log: $LogFile" -ForegroundColor Green }" | Out-File $LogFile -Append -Encoding utf8Log file: $LogFile`rDestination folder: $Dest`rSummary at: $(Get-Date)`r
n"`rforeach ($it in $items) { Move-ItemSafe $it }
n# Execute moves}    }        "[ERROR] Failed to move $relPath : $($_.Exception.Message)" | Out-File $LogFile -Append -Encoding utf8    } catch {        "[MOVED] $relPath -> $($target) (SizeKB: $sizeKB)" | Out-File $LogFile -Append -Encoding utf8        $sizeKB = if ($info -and -not $info.PSIsContainer) { [math]::Round($info.Length / 1KB, 2) } else { '-' }        $info = Get-Item $target -ErrorAction SilentlyContinue        Move-Item -LiteralPath $abs -Destination $target -Force        $target = Join-Path $destParent (Split-Path $relPath -Leaf)        if (-not (Test-Path $destParent)) { New-Item -Path $destParent -ItemType Directory -Force | Out-Null }
n    try {    }        return        "[DRYRUN] Would move: $relPath -> $destParent" | Out-File $LogFile -Append -Encoding utf8
n    if ($DryRun) {    $destParent = if ($parent) { Join-Path $Dest $parent } else { $Dest }
n    $parent = Split-Path $relPath -Parent    }        return        "[SKIP] Not found: $relPath" | Out-File $LogFile -Append -Encoding utf8    if (-not (Test-Path $abs)) {    $abs = Join-Path $RepoRoot $relPath
nfunction Move-ItemSafe([string]$relPath) {if ($extraGitKeeps) { $items += $extraGitKeeps }}    $extraGitKeeps = Get-ChildItem -Path (Join-Path $RepoRoot 'release') -Recurse -Filter '.gitkeep' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName.Substring($RepoRoot.Length + 1).TrimStart('\') }
n# add low-confidence .gitkeep files under release/**/bin
n$extraGitKeeps = @()
nif (Test-Path (Join-Path $RepoRoot 'release')) {)    'scripts\placeholders\yt_dlp\YT_DLP_NOTE.txt'    'scripts\placeholders\js_runtime\PUT_JS_RUNTIME_HERE.txt',    'scripts\placeholders\ffmpeg\PUT_FFMPEG_HERE.txt',    'scripts\last_build_dist.txt',    'src\fluentytdl\ui\main_window.py',    'assets\f57465f5-904b-4b38-82ee-cd755d6eb1c7.png',    'release\FluentYTDL-v0.1.0-win64-20251229-full',    'build\FluentYTDL\localpycs',    'build\FluentYTDL',
n$items = @(" | Out-File $LogFile -Encoding utf8DryRun: $DryRun`rDestination: $Dest`rRepository root: $RepoRoot`r"Move log generated: $(Get-Date)`r
n$LogFile = Join-Path $Dest 'move_log.txt'}    if (-not $DryRun) { New-Item -Path $Dest -ItemType Directory | Out-Null }
nif (-not (Test-Path $Dest)) {$Dest = Join-Path $RabbishRoot $TimeStamp$RabbishRoot = Join-Path $RepoRoot 'rabbish'
n$TimeStamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
n# Repo root = script directory
n$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
nSet-Location $RepoRoot
n$ErrorActionPreference = 'Stop')    [switch]$DryRunnparam(