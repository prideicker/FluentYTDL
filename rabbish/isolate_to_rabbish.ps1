<#
isolate_to_rabbish.ps1
Safely move confirmed redundant files/dirs into a timestamped subfolder under `rabbish/`.
This script only MOVES files (no deletion). It creates a log at the destination describing every move.
#>

$ErrorActionPreference = 'Stop'
n# ---------- Setup ----------
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

n$TimeStamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$RabbishRoot = Join-Path $RepoRoot 'rabbish'
$Dest = Join-Path $RabbishRoot $TimeStamp

nif (-not (Test-Path $Dest)) { New-Item -Path $Dest -ItemType Directory | Out-Null }

n$LogFile = Join-Path $Dest 'move_log.txt'
"Move log generated: $(Get-Date)`r
Repository root: $RepoRoot`r
Destination: $Dest`r
" | Out-File $LogFile -Encoding utf8

n# ---------- Items to move (relative to repo root) ----------
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

n# Add optional low-confidence matches (.gitkeep inside release/*/bin)
$extraGitKeeps = Get-ChildItem -Path (Join-Path $RepoRoot 'release') -Recurse -Filter '.gitkeep' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName.Substring($RepoRoot.Length + 1).TrimStart('\') }
if ($extraGitKeeps) { $items += $extraGitKeeps }

n# ---------- Function: safe move & log ----------
function Move-ItemSafe([string]$relPath) {
    $abs = Join-Path $RepoRoot $relPath
    if (-not (Test-Path $abs)) {
        "[SKIP] Not found: $relPath" | Out-File $LogFile -Append -Encoding utf8
        return
    }

n    try {
        $parent = Split-Path $relPath -Parent
        $destParent = if ($parent) { Join-Path $Dest $parent } else { $Dest }
        if (-not (Test-Path $destParent)) { New-Item -Path $destParent -ItemType Directory -Force | Out-Null }

n        $target = Join-Path $destParent (Split-Path $relPath -Leaf)
        Move-Item -LiteralPath $abs -Destination $target -Force

n        $info = Get-Item $target -ErrorAction SilentlyContinue
        $sizeKB = if ($info -and -not $info.PSIsContainer) { [math]::Round($info.Length / 1KB, 2) } else { '-' }
        "[MOVED] $relPath -> $($target) (SizeKB: $sizeKB)" | Out-File $LogFile -Append -Encoding utf8
    } catch {
        "[ERROR] Failed to move $relPath : $($_.Exception.Message)" | Out-File $LogFile -Append -Encoding utf8
    }
}

n# ---------- Execute moves ----------
foreach ($it in $items) {
    Move-ItemSafe $it
}

n# ---------- Summary ----------
"`r
Summary at: $(Get-Date)`r
Destination folder: $Dest`r
Log file: $LogFile`r
" | Out-File $LogFile -Append -Encoding utf8

nWrite-Host "Isolation complete. Moved items (see log): $LogFile" -ForegroundColor Green

n# Print log to console for quick review
Get-Content $LogFile -Encoding utf8 | Write-Host










































































n# Output log content to console for quick review
nGet-Content $LogFile -Encoding utf8 | Write-Host
nWrite-Host "Isolation complete. Moved items (see log): $LogFile" -ForegroundColor Green" | Out-File $LogFile -Append -Encoding utf8Log file: $LogFile`rDestination folder: $Dest`rSummary at: $(Get-Date)`r"`r# Summarize}    Move-ItemSafe $itforeach ($it in $items) {# Run moves}    }        "[ERROR] Failed to move $relPath : $($_.Exception.Message)" | Out-File $LogFile -Append -Encoding utf8    } catch {        "[MOVED] $relPath -> $(Resolve-Path $target) (SizeKB: $size)" | Out-File $LogFile -Append -Encoding utf8        $size = if ($info -and $info.PSIsContainer -eq $false) { [math]::Round($info.Length / 1KB, 2) } else { '-' }        $info = Get-Item $target -ErrorAction SilentlyContinue        Move-Item -LiteralPath $abs -Destination $target -Force        $target = Join-Path $destPath (Split-Path $relPath -Leaf)        # Use Move-Item to preserve name inside the destination folder (keep relative structure)        if (-not (Test-Path $destPath)) { New-Item -Path $destPath -ItemType Directory -Force | Out-Null }        # Ensure destination parent exists        if ($destPath -eq $null -or $destPath -eq '') { $destPath = $Dest }        $destPath = Join-Path $Dest (Split-Path $relPath -Parent)
n    try {    }        return        "[SKIP] Not found: $relPath" | Out-File $LogFile -Append -Encoding utf8    if (-not (Test-Path $abs)) {    $abs = Join-Path $RepoRoot $relPathfunction Move-ItemSafe([string]$relPath) {# Function to safely move one item and log itif ($extraGitKeeps) { $items += $extraGitKeeps }$extraGitKeeps = Get-ChildItem -Path (Join-Path $RepoRoot 'release') -Recurse -Filter '.gitkeep' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName.Substring($RepoRoot.Length + 1) }# Also collect any .gitkeep files under release/*/bin (low-confidence items))    'scripts\placeholders\yt_dlp\YT_DLP_NOTE.txt'    'scripts\placeholders\js_runtime\PUT_JS_RUNTIME_HERE.txt',    'scripts\placeholders\ffmpeg\PUT_FFMPEG_HERE.txt',    'scripts\last_build_dist.txt',    'src\fluentytdl\ui\main_window.py',    'assets\f57465f5-904b-4b38-82ee-cd755d6eb1c7.png',    'release\FluentYTDL-v0.1.0-win64-20251229-full',    'build\FluentYTDL\localpycs',    'build\FluentYTDL',$items = @(# List of explicit items to move (relative to repo root)" | Out-File $LogFile -Encoding utf8Destination: $Dest`rRepository root: $RepoRoot`r"Move log generated: $(Get-Date)`r$LogFile = Join-Path $Dest 'move_log.txt'
nif (-not (Test-Path $Dest)) { New-Item -Path $Dest -ItemType Directory | Out-Null }
n$Dest = Join-Path $RabbishRoot $TimeStamp$RabbishRoot = Join-Path $RepoRoot 'rabbish'$TimeStamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
nSet-Location $RepoRoot$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path# Repo root: assume script is placed under repo root and run theren