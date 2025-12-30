param(
  [switch]$NoPause,
  [switch]$AutoInstallPyInstaller
)

$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
Set-Location $root

# Keep console encoding predictable (best-effort on Windows PowerShell 5.1).
try {
  $utf8 = New-Object System.Text.UTF8Encoding($false)
  [Console]::OutputEncoding = $utf8
  [Console]::InputEncoding = $utf8
  $OutputEncoding = $utf8
} catch {
}

function U {
  param([Parameter(Mandatory=$true)][string]$Text)
  return [regex]::Replace(
    $Text,
    '\\u([0-9a-fA-F]{4})',
    {
      param($m)
      [char][Convert]::ToInt32($m.Groups[1].Value, 16)
    }
  )
}

function Pause-IfNeeded {
  if (-not $NoPause) {
    [void](Read-Host (U "\u6309\u56de\u8f66\u952e\u7ee7\u7eed"))
  }
}

function Show-Menu {
  if (-not [Console]::IsInputRedirected) {
    Clear-Host
  }
  Write-Host ""
  Write-Host "==========================================" -ForegroundColor Cyan
  Write-Host (U "  FluentYTDL \u6253\u5305\u83dc\u5355") -ForegroundColor Cyan
  Write-Host "==========================================" -ForegroundColor Cyan
  Write-Host ""
  Write-Host (U "  1) \u5168\u91cf\u7248 (full)  + \u76ee\u5f55\u7248 (onedir)  (\u81ea\u5e26\u5de5\u5177\uff0c\u5f00\u7bb1\u5373\u7528)")
  Write-Host (U "  2) \u58f3\u5b50\u7248 (shell) + \u76ee\u5f55\u7248 (onedir)  (\u4ec5\u7a0b\u5e8f\u58f3\u5b50\uff0c\u4f9d\u8d56\u5916\u90e8\u5de5\u5177)")
  Write-Host (U "  3) \u5168\u91cf\u7248 (full)  + \u5355\u6587\u4ef6 (onefile) (\u5355\u4e2a exe\uff0c\u81ea\u5e26\u5de5\u5177)")
  Write-Host (U "  4) \u58f3\u5b50\u7248 (shell) + \u5355\u6587\u4ef6 (onefile) (\u5355\u4e2a exe\uff0c\u4ec5\u7a0b\u5e8f\u58f3\u5b50)")
  Write-Host ""
  Write-Host (U "  5) \u4ec5\u6784\u5efa       (\u5168\u91cf\u7248 full + \u76ee\u5f55\u7248 onedir)")
  Write-Host (U "  6) \u4ec5\u6253\u5305 zip  (\u5168\u91cf\u7248 full + \u76ee\u5f55\u7248 onedir\uff0c\u4f7f\u7528\u73b0\u6709 dist \u4ea7\u7269)")
  Write-Host ""
  Write-Host (U "  0) \u9000\u51fa")
  Write-Host ""
}

function Format-Flavor {
  param([string]$Flavor)
  if ($Flavor -eq 'shell') { return (U "\u58f3\u5b50\u7248 (shell)") }
  return (U "\u5168\u91cf\u7248 (full)")
}

function Format-Mode {
  param([string]$Mode)
  if ($Mode -eq 'onefile') { return (U "\u5355\u6587\u4ef6 (onefile)") }
  return (U "\u76ee\u5f55\u7248 (onedir)")
}

function Read-Selection {
  while ($true) {
    $sel = Read-Host (U "\u8bf7\u9009\u62e9 (0-6)")
    if ($sel -match '^[0-6]$') {
      return [int]$sel
    }
    Write-Host ((U "\u65e0\u6548\u9009\u62e9\uff1a") + $sel) -ForegroundColor Yellow
  }
}

function Read-OptionalPython {
  Write-Host ""
  Write-Host (U "\u53ef\u9009\uff1a\u6307\u5b9a Python \u8def\u5f84\u6216\u547d\u4ee4 (\u76f4\u63a5\u56de\u8f66\u8868\u793a\u81ea\u52a8\u63a2\u6d4b)") -ForegroundColor DarkGray
  $py = Read-Host (U "Python (\u53ef\u7559\u7a7a)")
  if ([string]::IsNullOrWhiteSpace($py)) {
    return ""
  }
  return $py.Trim()
}

$packagePs1 = Join-Path $root 'package.ps1'
if (-not (Test-Path $packagePs1)) {
  Write-Host ((U "\u7f3a\u5c11\u6587\u4ef6\uff1a") + $packagePs1) -ForegroundColor Red
  Pause-IfNeeded
  exit 1
}

while ($true) {
  Show-Menu
  $sel = Read-Selection
  if ($sel -eq 0) {
    exit 0
  }

  $mode = 'onedir'
  $flavor = 'full'
  $extra = @()

  switch ($sel) {
    1 { $flavor = 'full';  $mode = 'onedir' }
    2 { $flavor = 'shell'; $mode = 'onedir' }
    3 { $flavor = 'full';  $mode = 'onefile' }
    4 { $flavor = 'shell'; $mode = 'onefile' }
    5 { $flavor = 'full';  $mode = 'onedir';  $extra += '-NoZip' }
    6 { $flavor = 'full';  $mode = 'onedir';  $extra += '-NoBuild' }
  }

  $python = Read-OptionalPython

  Write-Host ""
  Write-Host ((U "\u5df2\u9009\u62e9\uff1a") + ("{0} + {1}" -f (Format-Flavor -Flavor $flavor), (Format-Mode -Mode $mode))) -ForegroundColor Green
  Write-Host ""
  Write-Host (U "\u5f00\u59cb\u6267\u884c...") -ForegroundColor Cyan
  Write-Host ""

  $args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $packagePs1, '-Flavor', $flavor, '-Mode', $mode)
  $args += $extra
  if (-not [string]::IsNullOrWhiteSpace($python)) {
    $args += @('-Python', $python)
  }
  if ($AutoInstallPyInstaller) {
    $args += '-AutoInstallPyInstaller'
  }

  & powershell @args
  $exitCode = $LASTEXITCODE

  Write-Host ""
  if ($exitCode -ne 0) {
    Write-Host ((U "\u5931\u8d25") + " (ExitCode=$exitCode)" + (U "\uff0c\u8bf7\u67e5\u770b\u4e0a\u65b9\u8f93\u51fa\u65e5\u5fd7\u3002")) -ForegroundColor Red
  } else {
    Write-Host (U "\u6210\u529f\u3002") -ForegroundColor Green
  }
  Pause-IfNeeded
}
