param(
  [ValidateSet('full','shell')]
  [string]$Flavor = 'full',
  [switch]$NoZip
)

# Minimal onefile build script per spec
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Build FluentYTDL (Flavor=$Flavor)" -ForegroundColor Cyan

# Clean
if (Test-Path (Join-Path $root 'build')) { Remove-Item -LiteralPath (Join-Path $root 'build') -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path (Join-Path $root 'dist')) { Remove-Item -LiteralPath (Join-Path $root 'dist') -Recurse -Force -ErrorAction SilentlyContinue }

# Resolve python
$python = $env:FLUENTYTDL_PYTHON
if ([string]::IsNullOrWhiteSpace($python)) {
  if (Get-Command py -ErrorAction SilentlyContinue) { $python = 'py -3' } else { $python = 'python' }
}
Write-Host "Using python: $python"

# PyInstaller onefile build (do NOT bundle assets/bin via add-data)
$specPaths = Join-Path $root 'src'
$entry = Join-Path $root 'main.py'
if (-not (Test-Path $entry)) { throw "Entry not found: $entry" }

$cmd = "$python -m PyInstaller --noconfirm --clean --onefile --name FluentYTDL --paths `"$specPaths`" `"$entry`""
Write-Host $cmd
Invoke-Expression $cmd
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit=$LASTEXITCODE)" }

# Post processing: if Full, copy bundled tools to dist/bin (same level as exe)
$distExe = Join-Path $root 'dist\FluentYTDL.exe'
if (-not (Test-Path $distExe)) { throw "Expected exe not found: $distExe" }

if ($Flavor -eq 'full') {
  $src1 = Join-Path $root 'src\fluentytdl\assets\bin'
  $src2 = Join-Path $root 'assets\bin'
  if (Test-Path $src1) { $sourceBin = $src1 } elseif (Test-Path $src2) { $sourceBin = $src2 } else { $sourceBin = $null }

  if ($null -ne $sourceBin) {
    $destBin = Join-Path $root 'dist\bin'
    if (-not (Test-Path $destBin)) { New-Item -ItemType Directory -Path $destBin | Out-Null }
    Copy-Item -Path (Join-Path $sourceBin '*') -Destination $destBin -Recurse -Force
    Write-Host "Copied tools to: $destBin" -ForegroundColor Green
  } else {
    Write-Host "Warning: no bundled tools found to copy" -ForegroundColor Yellow
  }
} else {
  Write-Host "Flavor=shell: skipping tool copy" -ForegroundColor Gray
}

if (-not $NoZip) {
  # Zip dist
  $outZip = Join-Path $root ("FluentYTDL-{0}.zip" -f $Flavor)
  if (Test-Path $outZip) { Remove-Item -LiteralPath $outZip -Force }
  Write-Host "Creating zip: $outZip"
  Compress-Archive -LiteralPath (Join-Path $root 'dist\*') -DestinationPath $outZip -Force
  Write-Host "Build complete: $outZip" -ForegroundColor Cyan
} else {
  Write-Host "Skipping zip step as -NoZip was provided" -ForegroundColor Gray
}
exit 0
