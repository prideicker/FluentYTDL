# FluentYTDL Packaging Script V2
# Rebuilt for stability and correct directory structure.

param(
  [ValidateSet('onedir','onefile')]
  [string]$Mode = 'onedir',

  [ValidateSet('full','shell')]
  [string]$Flavor = 'full',

  [switch]$NoZip
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Set root to project root
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "FluentYTDL Packaging V2" -ForegroundColor Cyan
Write-Host "Mode: $Mode | Flavor: $Flavor" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# --- 1. Environment Setup ---

function Get-Python {
    $py = $env:FLUENTYTDL_PYTHON
    if (-not [string]::IsNullOrWhiteSpace($py)) { return $py }
    
    # Try finding a python with PyInstaller
    $candidates = @('python', 'py -3', 'py')
    foreach ($c in $candidates) {
        try {
            $test = Invoke-Expression "$c -c `"import PyInstaller; print('ok')`"" 2>$null
            if ($test -match 'ok') { return $c }
        } catch {}
    }
    throw "Could not find Python with PyInstaller installed. Please install it (pip install pyinstaller)."
}

function Get-Version {
    $path = Join-Path $root 'pyproject.toml'
    if (Test-Path $path) {
        foreach ($line in Get-Content $path) {
            if ($line -match '^version\s*=\s*"([^"]+)"') { return $Matches[1] }
        }
    }
    return "0.0.0"
}

$python = Get-Python
Write-Host "Using Python: $python" -ForegroundColor Gray

# Clean previous build artifacts to prevent mixing
Write-Host "Cleaning up old build/dist folders..." -ForegroundColor Gray
if (Test-Path "$root\build") { Remove-Item "$root\build" -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path "$root\dist") { Remove-Item "$root\dist" -Recurse -Force -ErrorAction SilentlyContinue }

# --- 2. Build Process (PyInstaller) ---

Write-Host "`n[1/3] Running PyInstaller..." -ForegroundColor Cyan

# Path to main script
$mainScript = Join-Path $root "main.py"
if (-not (Test-Path $mainScript)) { throw "main.py not found at $mainScript" }

# Base PyInstaller arguments
$pyArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--noconsole",
    "--name", "FluentYTDL",
    "--workpath", (Join-Path $root "build"),
    "--distpath", (Join-Path $root "dist"),
    "--icon", (Join-Path $root "assets\logo.png") # Add application icon
)

if ($Mode -eq 'onefile') {
    $pyArgs += "--onefile"
} else {
    $pyArgs += "--onedir"
    $pyArgs += "--contents-directory", "." # Keep folder structure clean
}

# Add source path to search path
$srcPath = Join-Path $root "src"
$pyArgs += "--paths", "`"$srcPath`""

# Execute Build
$buildCmd = "$python $pyArgs `"$mainScript`""
Write-Host "Executing: $buildCmd" -ForegroundColor Gray
Invoke-Expression $buildCmd

if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed with code $LASTEXITCODE" }

# --- 3. Post-Build: Bundle Tools ---

Write-Host "`n[2/3] Bundling External Tools..." -ForegroundColor Cyan

# Define Source of tools
$toolSource = Join-Path $root "assets\bin"
if (-not (Test-Path $toolSource)) {
    # Fallback to src location if root assets missing
    $toolSource = Join-Path $root "src\fluentytdl\assets\bin"
}

# Define where tools should go.
# We prepare a staging folder for the final Zip to ensure consistent structure.
$releaseDir = Join-Path $root "release"
if (-not (Test-Path $releaseDir)) { New-Item -ItemType Directory -Path $releaseDir | Out-Null }

# Prefer version from tag when running in CI (triggered on tag)
$version = Get-Version
if ($env:GITHUB_REF -and ($env:GITHUB_REF -match 'refs/tags/v(.+)')) {
    $version = $Matches[1]
    Write-Host "CI: Using version from tag: $version"
}
# deterministic date for builds (allow override via env)
$buildDate = if ($env:FLUENTYTDL_BUILD_DATE) { $env:FLUENTYTDL_BUILD_DATE } else { Get-Date -Format 'yyyyMMdd' }
$date = $buildDate
# determine arch robustly
if ($env:GITHUB_ACTIONS) {
    # On GitHub runners, prefer PROCESSOR_ARCHITECTURE or fall back to 64-bit detection
    $arch = if ($env:PROCESSOR_ARCHITECTURE -match '64' -or [Environment]::Is64BitProcess) { 'win64' } else { 'win32' }
} else {
    $arch = if ($env:PROCESSOR_ARCHITECTURE -match '64') { 'win64' } else { 'win32' }
}

# Name of the final folder/zip
$baseName = "FluentYTDL-v$version-$arch-$date"
if ($Mode -eq 'onefile') { $baseName += "-full" } else { $baseName += "-portable" }

# Create a clean staging directory in release/temp
$stagingDir = Join-Path $releaseDir "temp_$baseName"
if (Test-Path $stagingDir) { Remove-Item $stagingDir -Recurse -Force }
New-Item -ItemType Directory -Path $stagingDir | Out-Null

# A. Copy Executable
if ($Mode -eq 'onefile') {
    $exeSrc = Join-Path $root "dist\FluentYTDL.exe"
    if (-not (Test-Path $exeSrc)) { throw "Build failed: $exeSrc not found" }
    Copy-Item $exeSrc -Destination $stagingDir
} else {
    # onedir: copy directory contents
    $dirSrc = Join-Path $root "dist\FluentYTDL"
    if (-not (Test-Path $dirSrc)) { throw "Build failed: $dirSrc not found" }
    Copy-Item "$dirSrc\*" -Destination $stagingDir -Recurse
}

# B. Copy Tools (if flavor is full)
if ($Flavor -eq 'full') {
    if (Test-Path $toolSource) {
        $binTarget = Join-Path $stagingDir "bin"
        if (-not (Test-Path $binTarget)) { New-Item -ItemType Directory -Path $binTarget | Out-Null }
        
        Write-Host "Copying tools from $toolSource to $binTarget..."
        Copy-Item "$toolSource\*" -Destination $binTarget -Recurse -Force
    } else {
        Write-Warning "Flavor is full, but no tools found at assets\bin. Package will be empty of tools."
    }
}

# C. Copy Documentation (User Manual)
Write-Host "Copying Documentation (User Manual)..." -ForegroundColor Gray
$manualSource = Join-Path $root "docs\manuals\USER_MANUAL.md"
$manualTargetDir = Join-Path $stagingDir "docs\manuals"

if (Test-Path $manualSource) {
    if (-not (Test-Path $manualTargetDir)) { New-Item -ItemType Directory -Path $manualTargetDir | Out-Null }
    Copy-Item $manualSource -Destination $manualTargetDir -Force
    Write-Host "Copied $manualSource to $manualTargetDir" -ForegroundColor Gray
} else {
    Write-Warning "User manual not found at $manualSource. Package will not include it."
}

# --- 4. Package Zip ---

if ($NoZip) {
    Write-Host "`n[3/3] Zip skipped." -ForegroundColor Green
    Write-Host "Output available at: $stagingDir" -ForegroundColor Green
    # Open explorer to the folder
    Invoke-Item $stagingDir
    exit 0
}

Write-Host "`n[3/3] Creating Zip Archive..." -ForegroundColor Cyan

$zipPath = Join-Path $releaseDir "$baseName.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Write-Host "Zipping $stagingDir -> $zipPath"
Compress-Archive -Path "$stagingDir\*" -DestinationPath $zipPath -Force

# Cleanup staging
Remove-Item $stagingDir -Recurse -Force

Write-Host "------------------------------------------" -ForegroundColor Green
Write-Host "Success! Package created:" -ForegroundColor Green
Write-Host "$zipPath" -ForegroundColor Green
Write-Host "------------------------------------------" -ForegroundColor Green

# Emit artifact metadata for CI
$meta = [PSCustomObject]@{
    version = $version
    name = $baseName
    zip = (Split-Path $zipPath -Leaf)
    path = $zipPath
    date = $date
}
$metaJson = $meta | ConvertTo-Json -Depth 4
$metaPath = Join-Path $releaseDir 'artifact-info.json'
Set-Content -Path $metaPath -Value $metaJson -Encoding UTF8
Write-Host "Wrote artifact metadata: $metaPath"

# In CI we should not open Explorer
if ($env:GITHUB_ACTIONS) {
    Write-Host "CI detected: skipping Invoke-Item/explorer open"
} else {
    Invoke-Item $releaseDir
}
