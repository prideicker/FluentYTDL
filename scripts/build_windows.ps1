param(
  [ValidateSet('onedir','onefile')]
  [string]$Mode = 'onedir',

  [ValidateSet('full','shell')]
  [string]$Flavor = 'full'
)

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = $env:FLUENTYTDL_PYTHON
if ([string]::IsNullOrWhiteSpace($python)) {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py -3"
  } else {
    $python = "python"
  }
}

Write-Host "Building FluentYTDL ($Mode)..."

# Packaging flavor:
# - full: bundle tools from assets/bin into dist/_internal (ffmpeg/deno/yt-dlp)
# - shell: do NOT bundle tools; app will rely on user-provided paths / PATH.
if ($Flavor -eq 'shell') {
  $env:FLUENTYTDL_BUNDLE_TOOLS = '0'
} else {
  $env:FLUENTYTDL_BUNDLE_TOOLS = '1'
}

# Previously we auto-fetched bundled tools; with the new bin-only packaging
# behavior the build process expects tools to be managed separately. No auto
# fetch performed here to avoid noisy checks.

# Clean previous builds
# Attempt to stop common bundled-tool processes that may keep files locked,
# then retry removal with exponential backoff to avoid "file in use" errors.
function Stop-ToolProcesses {
  param([string[]]$ExeNames = @('yt-dlp.exe','ffmpeg.exe','deno.exe'))

  foreach ($exe in $ExeNames) {
    try {
      # suppress taskkill 'not found' messages by redirecting stderr to nul
      Start-Process -FilePath 'cmd.exe' -ArgumentList "/c taskkill /F /IM $exe 2>nul" -NoNewWindow -Wait -ErrorAction SilentlyContinue
    } catch {
      # ignore
    }
  }
}

function Remove-WithRetry {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [int]$Attempts = 4
  )

  for ($i = 0; $i -lt $Attempts; $i++) {
    if (-not (Test-Path $Path)) { return }
    try {
      Remove-Item $Path -Recurse -Force -ErrorAction Stop
      return
    } catch {
      Start-Sleep -Seconds ([math]::Max(1, 2 * ($i + 1)))
      Stop-ToolProcesses
    }
  }

  if (Test-Path $Path) {
    Write-Warning "Unable to remove path: $Path (may be in use). Continuing without clean removal."
  }
}

Stop-ToolProcesses
Remove-WithRetry -Path "$root\build"
Remove-WithRetry -Path "$root\dist"

$spec = Join-Path $root 'FluentYTDL.spec'

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
# Ensure PyInstaller can find the package in src
$srcPath = Join-Path $root 'src'
# Use a unique dist path for this build to avoid conflicts with an existing locked `dist` folder.
if ($Mode -eq 'onefile') {
  $pyDistPath = Join-Path $root 'dist'
  Invoke-Expression "$python -m PyInstaller --noconfirm --clean --onefile --name FluentYTDL --distpath `"$pyDistPath`" --paths `"$srcPath`" `"$root\main.py`""
} else {
  $pyDistPath = Join-Path $root ("dist\FluentYTDL_build_{0}" -f $timestamp)
  Invoke-Expression "$python -m PyInstaller `"$spec`" --noconfirm --clean --distpath `"$pyDistPath`""
}

# Expose the produced dist path for downstream packaging steps.
$env:FLUENTYTDL_BUILD_DIST = $pyDistPath
try {
  $outFile = Join-Path $root 'scripts\last_build_dist.txt'
  Set-Content -LiteralPath $outFile -Value $pyDistPath -Force -Encoding UTF8
} catch {
  Write-Warning "Failed to write last build dist file: $($_.Exception.Message)"
}

if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed (exit code=$LASTEXITCODE). Ensure PyInstaller is installed in the selected Python environment."
}

if ($Mode -eq 'onefile') {
  if (-not (Test-Path "$root\dist\FluentYTDL.exe")) {
    throw "Build did not produce expected output: $root\dist\FluentYTDL.exe"
  }
} else {
  if (-not (Test-Path $pyDistPath)) {
    throw "Build did not produce expected output folder: $pyDistPath"
  }
}

if ($Flavor -eq 'full' -and $Mode -eq 'onedir') {
  Write-Host "Bundling tools (Flavor=full)..."
  $binSrc = Join-Path $root 'assets\bin'
  $binDest = Join-Path $pyDistPath 'bin'

  if (Test-Path $binSrc) {
    if (-not (Test-Path $binDest)) {
      New-Item -ItemType Directory -Force -Path $binDest | Out-Null
    }
    Copy-Item -Path "$binSrc\*" -Destination $binDest -Recurse -Force
    Write-Host "Tools bundled to: $binDest"
  } else {
    Write-Warning "Source assets\bin not found. Skipping tool bundling."
  }
}

Write-Host "\nBuild output: $env:FLUENTYTDL_BUILD_DIST"