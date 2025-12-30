param(
  [ValidateSet('onedir','onefile')]
  [string]$Mode = 'onedir',

  [ValidateSet('full','shell')]
  [string]$Flavor = 'full',

  [switch]$AutoInstallPyInstaller
)

# Simple compatibility wrapper for legacy workflows that call `package.ps1` at repo root.
# Delegates to scripts\package_v2.ps1 and forwards parameters.

$extra = @()
if ($AutoInstallPyInstaller) { $extra += '-AutoInstallPyInstaller' }

$ps1 = Join-Path $PSScriptRoot 'scripts\package_v2.ps1'
if (-not (Test-Path $ps1)) { throw "Compatibility wrapper failed: $ps1 not found" }

$cmd = "pwsh -NoProfile -ExecutionPolicy Bypass -File `"$ps1`" -Mode $Mode -Flavor $Flavor $($extra -join ' ')"
Write-Host "Invoking: $cmd"
Invoke-Expression $cmd
