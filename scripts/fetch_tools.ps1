# 文件名: scripts/fetch_tools.ps1
# 作用：这是一个“验证脚本”，它不下载任何东西。
# 它只检查 Git 仓库中的工具是否完整，以确保 CI/CD 流程的稳定性。

param (
    [string]$BaseDir = "$PSScriptRoot\..\assets\bin"
)

$ErrorActionPreference = "Stop"
Write-Host ">> [Step 1] 正在验证本地工具..." -ForegroundColor Cyan

$ffmpegPath = Join-Path -Path $BaseDir -ChildPath "ffmpeg\ffmpeg.exe"
$ytDlpPath = Join-Path -Path $BaseDir -ChildPath "yt-dlp\yt-dlp.exe"

$ffmpegExists = Test-Path $ffmpegPath
$ytDlpExists = Test-Path $ytDlpPath

Write-Host "   检查 FFmpeg: $ffmpegPath"
Write-Host "   检查 yt-dlp: $ytDlpPath"

if ($ffmpegExists -and $ytDlpExists) {
    Write-Host ">> 所有必需的工具均已在仓库中找到，检查通过！" -ForegroundColor Green
    exit 0
} else {
    Write-Error "错误：一个或多个工具在 'assets/bin' 目录中缺失！"
    if (-not $ffmpegExists) { Write-Warning "找不到: $ffmpegPath" }
    if (-not $ytDlpExists) { Write-Warning "找不到: $ytDlpPath" }
    Write-Error "请确保 ffmpeg.exe 和 yt-dlp.exe 已被正确提交到 Git 仓库的 'assets/bin/<tool_name>/' 目录下。"
    exit 1
}