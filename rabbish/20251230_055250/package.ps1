param(
  [ValidateSet('onedir','onefile')]
  [string]$Mode = 'onedir',

  [ValidateSet('full','shell')]
  [string]$Flavor = 'full',

  [string]$Python = "",
  [string]$Dist = "",
  [string]$Out = "",

  [switch]$NoBuild,
  [switch]$NoZip,
  [switch]$SkipFetchTools,
  [switch]$AutoInstallPyInstaller
)

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# --- 1. 环境准备 ---

function Resolve-PythonCommand {
  param([string]$Override)
  if (-not [string]::IsNullOrWhiteSpace($Override)) { return $Override }
  $envPy = $env:FLUENTYTDL_PYTHON
  if (-not [string]::IsNullOrWhiteSpace($envPy)) { return $envPy }
  
  $candidates = @('python')
  if (Get-Command py -ErrorAction SilentlyContinue) {
    $candidates += @('py -3.12','py -3.11','py -3.10','py -3')
  }
  foreach ($c in $candidates) {
    if (Test-CanImport -PythonCmd $c -ModuleName 'PyInstaller') { return $c }
  }
  return $candidates[0]
}

function Test-CanImport {
  param([string]$PythonCmd, [string]$ModuleName)
  $code = "import importlib; import sys; m=importlib.import_module('$ModuleName'); print(getattr(m,'__version__','ok'))"
  try { $null = Invoke-Expression "$PythonCmd -c `"$code`"" 2>$null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}

function Read-ProjectVersion {
  param([string]$PyProjectPath)
  if (-not (Test-Path $PyProjectPath)) { return "0.0.0" }
  foreach ($line in Get-Content -LiteralPath $PyProjectPath -ErrorAction SilentlyContinue) {
    if ($line -match '^version\s*=\s*"([^"]+)"$) { return $Matches[1] }
  }
  return "0.0.0"
}

function Detect-WinArch {
  if ($env:PROCESSOR_ARCHITECTURE -match '64') { return 'win64' } else { return 'win32' }
}

$pythonCmd = Resolve-PythonCommand -Override $Python
$env:FLUENTYTDL_PYTHON = $pythonCmd

if ($SkipFetchTools) { $env:FLUENTYTDL_SKIP_FETCH_TOOLS = '1' }
else { Remove-Item Env:FLUENTYTDL_SKIP_FETCH_TOOLS -ErrorAction SilentlyContinue }

Write-Host "Using python: $pythonCmd" -ForegroundColor Cyan

# PyInstaller check
if (-not (Test-CanImport -PythonCmd $pythonCmd -ModuleName 'PyInstaller')) {
  if ($AutoInstallPyInstaller) {
    Write-Host "Installing PyInstaller..."
    Invoke-Expression "$pythonCmd -m pip install -U pyinstaller"
  } else {
    throw "PyInstaller not found. Run with -AutoInstallPyInstaller or install manually."
  }
}

# --- 2. 构建阶段 ---

if (-not $NoBuild) {
  Write-Host "`n[1/2] Build ($Mode - $Flavor)..." -ForegroundColor Cyan
  $buildScript = Join-Path $root 'scripts\build_windows.ps1'
  $buildCmd = "$buildScript -Flavor $Flavor -Mode $Mode"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "& $buildCmd"
  if ($LASTEXITCODE -ne 0) { throw "Build script failed." }
}

if ($NoZip) {
  Write-Host "`nDone (Zip skipped)." -ForegroundColor Green
  exit 0
}

# --- 3. 打包阶段 ---

Write-Host "`n[2/2] Package to Release..." -ForegroundColor Cyan

# 确定源工具目录 (优先根目录 assets\bin)
$SourceBin = Join-Path $root "assets\bin"
if (-not (Test-Path $SourceBin)) {
    $SourceBin = Join-Path $root "src\fluentytdl\assets\bin" 
}

# 确定版本信息
$version = Read-ProjectVersion -PyProjectPath (Join-Path $root 'pyproject.toml')
$arch = Detect-WinArch
$date = Get-Date -Format 'yyyyMMdd'

# 确定输出目录 (release)
$ReleaseDir = Join-Path $root "release"
if (-not (Test-Path $ReleaseDir)) { New-Item -ItemType Directory -Path $ReleaseDir | Out-Null }

# 获取构建产物路径
$lastBuildFile = Join-Path $root 'scripts\last_build_dist.txt'
if (Test-Path $lastBuildFile) {
    $BuildDist = (Get-Content $lastBuildFile).Trim()
} else {
    # Fallback guess
    $BuildDist = if ($Mode -eq 'onefile') { Join-Path $root 'dist' } else { Join-Path $root 'dist\FluentYTDL' }
}

if (-not (Test-Path $BuildDist)) { throw "Build output not found at: $BuildDist" }

# --- 分支逻辑 ---

if ($Mode -eq 'onedir') {
    # Onedir: 整个文件夹直接压缩
    
    $ZipName = "FluentYTDL-v$version-$arch-$date-folder.zip"
    $ZipPath = Join-Path $ReleaseDir $ZipName

    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    
    Write-Host "Zipping folder: $BuildDist -> $ZipPath"
    if ($BuildDist -eq $ReleaseDir) { throw "Source and Dest are same!" }
    
    Compress-Archive -Path "$BuildDist\*" -DestinationPath $ZipPath -Force
    Write-Host "Success: $ZipPath" -ForegroundColor Green

} elseif ($Mode -eq 'onefile') {
    # Onefile: dist 下只有 .exe
    # 我们需要在 release 目录创建一个临时结构来打包： exe + bin
    
    $ExePath = Join-Path $BuildDist "FluentYTDL.exe"
    if (-not (Test-Path $ExePath)) { 
        # try checking without subfolder if build script behaved differently
        $ExePath2 = Join-Path $root "dist\FluentYTDL.exe"
        if (Test-Path $ExePath2) { $ExePath = $ExePath2 }
        else { throw "EXE not found: $ExePath" }
    }
    
    # 复制 EXE 到 release 根目录方便直接取用
    Copy-Item $ExePath -Destination $ReleaseDir -Force
    Write-Host "Copied EXE to release folder."

    # 准备 Zip 包
    $ZipName = "FluentYTDL-v$version-$arch-$date-full.zip"
    # Ensure variables are valid strings
    if ([string]::IsNullOrWhiteSpace($ZipName)) { throw "Failed to generate ZipName" }
    
    $ZipPath = Join-Path $ReleaseDir $ZipName
    
    # SAFETY CHECK: prevent deleting release dir
    if ($ZipPath -eq $ReleaseDir -or $ZipPath -eq "$ReleaseDir\") {
        throw "Critical Error: ZipPath calculated as ReleaseDir. Aborting to prevent deletion."
    }

    # 创建临时目录用于打包
    $TempPkgDir = Join-Path $ReleaseDir "FluentYTDL-full"
    if (Test-Path $TempPkgDir) { Remove-Item $TempPkgDir -Recurse -Force }
    New-Item -ItemType Directory -Path $TempPkgDir | Out-Null
    
    # 1. 放入 EXE
    Copy-Item $ExePath -Destination $TempPkgDir
    
    # 2. 放入 bin (如果是 Full 模式)
    if ($Flavor -eq 'full') {
        if (Test-Path $SourceBin) {
            $DestBin = Join-Path $TempPkgDir "bin"
            New-Item -ItemType Directory -Path $DestBin | Out-Null
            Copy-Item "$SourceBin\*" -Destination $DestBin -Recurse -Force
            Write-Host "Included tools in zip: $DestBin"
        } else {
            Write-Warning "Flavor is full, but tools not found at $SourceBin"
        }
    }
    
    # 3. 压缩
    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    
    Write-Host "Zipping: $TempPkgDir -> $ZipPath"
    Compress-Archive -Path "$TempPkgDir\*" -DestinationPath $ZipPath -Force
    
    # 清理临时目录
    Remove-Item $TempPkgDir -Recurse -Force
    
    Write-Host "Success: $ZipPath" -ForegroundColor Green
}
