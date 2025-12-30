# 文件名: scripts/package.ps1
param (
    [string]$VersionTag = "v0.0.0-dev" # 默认版本
)

$ErrorActionPreference = "Stop"
$Workspace = "$PSScriptRoot\.."
$ReleaseDir = "$Workspace\release"

Write-Host ">> [Step 1] 清理旧构建..." -ForegroundColor Cyan
if (Test-Path $ReleaseDir) { Remove-Item $ReleaseDir -Recurse -Force }
if (Test-Path "$Workspace\build") { Remove-Item "$Workspace\build" -Recurse -Force }
if (Test-Path "$Workspace\dist") { Remove-Item "$Workspace\dist" -Recurse -Force }
New-Item -ItemType Directory -Path $ReleaseDir | Out-Null

Write-Host ">> [Step 2] 开始 PyInstaller 打包..." -ForegroundColor Cyan
# 确保你处于虚拟环境或已安装 pyinstaller
pyinstaller --noconfirm --onedir --windowed --clean `
    --name "FluentYTDL" `
    --add-data "$Workspace\assets\bin;bin" `
    --add-data "$Workspace\assets\logo.png;assets" `
    "$Workspace\main.py" 
# ↑↑↑ 注意：请确认 main.py 的路径是否正确，根据你实际结构调整

if (-not $?) { throw "PyInstaller 打包失败" }

Write-Host ">> [Step 3] 制作 Zip 包..." -ForegroundColor Cyan
$ZipName = "FluentYTDL-$VersionTag-win-x64.zip"
$SourceDir = "$Workspace\dist\FluentYTDL"
Compress-Archive -Path "$SourceDir\*" -DestinationPath "$ReleaseDir\$ZipName"

Write-Host ">> 打包完成! 产物位于: release\$ZipName" -ForegroundColor Green
