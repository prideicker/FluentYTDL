param(
  [string]$Dist = "dist/FluentYTDL",
  [string]$Out = ""
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ([string]::IsNullOrWhiteSpace($Out)) {
  Write-Host "Packaging $Dist -> installer/*.zip"
} else {
  Write-Host "Packaging $Dist -> $Out"
}

if ([string]::IsNullOrWhiteSpace($Out)) {
  python .\scripts\package_zip.py --dist $Dist
} else {
  python .\scripts\package_zip.py --dist $Dist --out $Out
}
