param(
  [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function U { param([string]$t) return $t }
function Pause-IfNeeded { if (-not $NoPause) { [void](Read-Host "Press ENTER to continue...") } }

function Show-Menu {
  Clear-Host
  Write-Host "=========================================`n  FluentYTDL Build Menu`n==========================================" -ForegroundColor Cyan
  Write-Host "1) Full + Onedir (recommended)"
  Write-Host "2) Shell + Onedir"
  Write-Host "3) Full + Onefile"
  Write-Host "4) Shell + Onefile"
  Write-Host "0) Exit"
}

while ($true) {
  Show-Menu
  $sel = Read-Host "Choose (0-4)"
  switch ($sel) {
    '0' { exit 0 }
    '1' { $Flavor='full'; $Mode='onedir' }
    '2' { $Flavor='shell'; $Mode='onedir' }
    '3' { $Flavor='full'; $Mode='onefile' }
    '4' { $Flavor='shell'; $Mode='onefile' }
    default { Write-Host "Invalid selection" -ForegroundColor Yellow; Pause-IfNeeded; continue }
  }

  $py = Read-Host "Optional: Python command to use (leave empty to auto-detect)"
  $args = @('-Mode',$Mode,'-Flavor',$Flavor)
  if (-not [string]::IsNullOrWhiteSpace($py)) { $args += @('-Python',$py) }

  Write-Host "Starting build with Mode=$Mode Flavor=$Flavor" -ForegroundColor Green
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build.ps1') @args
  $rc = $LASTEXITCODE
  if ($rc -ne 0) { Write-Host "Build failed with exit code $rc" -ForegroundColor Red }
  Pause-IfNeeded
}
