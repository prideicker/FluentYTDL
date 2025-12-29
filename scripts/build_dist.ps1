param(
  [ValidateSet('full','shell')]
  [string]$Flavor = 'full'
)

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Building FluentYTDL (Flavor=$Flavor)" -ForegroundColor Cyan

# Clean previous dist/build
if (Test-Path (Join-Path $root 'build')) { Remove-Item -LiteralPath (Join-Path $root 'build') -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path (Join-Path $root 'dist')) { Remove-Item -LiteralPath (Join-Path $root 'dist') -Recurse -Force -ErrorAction SilentlyContinue }

# Run pyinstaller onefile
$specPaths = Join-Path $root 'src'
$entry = Join-Path $root 'main.py'
if (-not (Test-Path $entry)) { throw "Entry not found: $entry" }

$py = 'py -3'
if (Get-Command py -ErrorAction SilentlyContinue) { $py = 'py -3' } elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = 'python' }

$cmd = "$py -m PyInstaller --onefile --noconfirm --windowed --name FluentYTDL --paths `"$specPaths`" `"$entry`""
Write-Host $cmd
Invoke-Expression $cmd
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit=$LASTEXITCODE)" }

# Post-copy: when Flavor=full, copy assets/bin -> dist/bin
if ($Flavor -eq 'full') {
  $source = Join-Path $root 'src\fluentytdl\assets\bin'
  if (Test-Path $source) {
    $dest = Join-Path $root 'dist\bin'
    if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest | Out-Null }
    Copy-Item -Path (Join-Path $source '*') -Destination $dest -Recurse -Force
    Write-Host "Copied bundled tools to: $dest" -ForegroundColor Green
  } else {
    Write-Host "Warning: source assets/bin not found: $source" -ForegroundColor Yellow
  }
}

Write-Host "Build finished. See dist folder." -ForegroundColor Cyan
exit 0
