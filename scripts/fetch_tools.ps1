# 文件名: scripts/fetch_tools.ps1
# 作用: 健壮的工具获取脚本，采用“本地优先，下载兜底”的冗余策略。

param (
    [string]$BaseDir = "$PSScriptRoot\..\assets\bin"
)

$ErrorActionPreference = "SilentlyContinue" # 允许我们自定义错误处理

# 1. 定义路径和状态变量
$ffmpegDir = Join-Path -Path $BaseDir -ChildPath "ffmpeg"
$ytDlpDir = Join-Path -Path $BaseDir -ChildPath "yt-dlp"
$ffmpegPath = Join-Path -Path $ffmpegDir -ChildPath "ffmpeg.exe"
$ytDlpPath = Join-Path -Path $ytDlpDir -ChildPath "yt-dlp.exe"

# --- 阶段一：检查本地 (主轮胎) ---
Write-Host ">> [Phase 1] Checking for existing local tools..." -ForegroundColor Cyan
if ((Test-Path $ffmpegPath) -and (Test-Path $ytDlpPath)) {
    Write-Host "   Success: Local ffmpeg.exe and yt-dlp.exe found." -ForegroundColor Green
    exit 0
}
Write-Host "   Notice: Local tools not found or incomplete. Proceeding to download fallback..." -ForegroundColor Yellow

# --- 阶段二：下载 (备胎) ---
# 确保目标目录存在
New-Item -ItemType Directory -Force -Path $ffmpegDir | Out-Null
New-Item -ItemType Directory -Force -Path $ytDlpDir | Out-Null

# 下载 yt-dlp (如果不存在)
if (-not (Test-Path $ytDlpPath)) {
    Write-Host ">> [Phase 2.1] Downloading yt-dlp..." -ForegroundColor Cyan
    try {
        $apiUrl = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
        $releaseInfo = Invoke-RestMethod -Uri $apiUrl -UseBasicParsing
        $asset = $releaseInfo.assets | Where-Object { $_.name -eq 'yt-dlp.exe' }
        if ($asset) {
            Write-Host "   Found yt-dlp.exe at $($asset.browser_download_url)"
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $ytDlpPath -UseBasicParsing
            Write-Host "   yt-dlp downloaded successfully." -ForegroundColor Green
        } else {
            Write-Warning "   Could not find yt-dlp.exe in the latest GitHub release assets."
        }
    } catch {
        Write-Warning "   Failed to download yt-dlp. Error: $($_.Exception.Message)"
    }
}

# 下载 ffmpeg (如果不存在)
if (-not (Test-Path $ffmpegPath)) {
    Write-Host ">> [Phase 2.2] Downloading ffmpeg..." -ForegroundColor Cyan
    try {
        $apiUrl = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
        $releaseInfo = Invoke-RestMethod -Uri $apiUrl -UseBasicParsing
        $asset = $releaseInfo.assets | Where-Object { $_.name -like '*win64-gpl*' -and $_.name -notlike '*shared*' } | Select-Object -First 1
        
        if ($asset) {
            Write-Host "   Found ffmpeg build: $($asset.name)"
            Write-Host "   URL: $($asset.browser_download_url)"
            $zipPath = Join-Path -Path $PSScriptRoot -ChildPath "ffmpeg-temp.zip"
            
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing
            Write-Host "   Downloaded. Extracting..."
            
            # 解压到临时目录，然后只移动我们需要的 ffmpeg.exe
            $extractTempDir = Join-Path -Path $PSScriptRoot -ChildPath "ffmpeg-extract-temp"
            if (Test-Path $extractTempDir) { Remove-Item $extractTempDir -Recurse -Force }
            New-Item -ItemType Directory -Force -Path $extractTempDir | Out-Null
            
            Expand-Archive -Path $zipPath -DestinationPath $extractTempDir -Force
            
            # 在解压文件中找到 ffmpeg.exe
            $nestedFfmpeg = Get-ChildItem -Path $extractTempDir -Filter "ffmpeg.exe" -Recurse | Select-Object -First 1
            
            if ($nestedFfmpeg) {
                Move-Item -Path $nestedFfmpeg.FullName -Destination $ffmpegPath -Force
                Write-Host "   ffmpeg.exe extracted and moved successfully." -ForegroundColor Green
            } else {
                Write-Warning "   Could not find ffmpeg.exe within the downloaded archive."
            }

            # 清理临时文件和目录
            Remove-Item $zipPath -Force
            Remove-Item $extractTempDir -Recurse -Force

        } else {
            Write-Warning "   Could not find a suitable ffmpeg build in the latest GitHub release assets."
        }
    } catch {
        Write-Warning "   Failed to download or process ffmpeg. Error: $($_.Exception.Message)"
    }
}

# --- 阶段三：最终验证 ---
Write-Host ">> [Phase 3] Final verification..." -ForegroundColor Cyan
$ffmpegOk = Test-Path $ffmpegPath
$ytDlpOk = Test-Path $ytDlpPath

if ($ffmpegOk -and $ytDlpOk) {
    Write-Host ">> All tools are ready!" -ForegroundColor Green
    exit 0
} else {
    Write-Error "FATAL: Tool preparation failed after all attempts."
    if (-not $ffmpegOk) { Write-Error "   ffmpeg.exe is still missing." }
    if (-not $ytDlpOk) { Write-Error "   yt-dlp.exe is still missing." }
    exit 1
}
