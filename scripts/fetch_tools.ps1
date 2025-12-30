# 文件名: scripts/fetch_tools.ps1
# 作用: 全自动、高安全地从官方 GitHub Release 源获取项目所需的全部外部工具。
#
# v4 (最终版) 更新:
# - 新增 Deno 的自动下载功能，从 denoland/deno 的官方 Release 获取。
# - 统一所有工具 (yt-dlp, ffmpeg, deno) 的下载逻辑，全部使用 GitHub API。

param (
    [string]$TargetDir = "$PSScriptRoot\..\assets\bin"
)

$ErrorActionPreference = "Stop"
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
$TempDir = "$PSScriptRoot\temp_tools"

# --- 函数定义 ---

function Invoke-Download([string]$Uri, [string]$OutFile) {
    Write-Host "    Downloading: $Uri" -ForegroundColor Gray
    Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing -TimeoutSec 600
}

function Verify-Checksum([string]$FilePath, [string]$ExpectedHash, [string]$Algorithm = "SHA256") {
    Write-Host "    Verifying checksum for: $(Split-Path $FilePath -Leaf)" -ForegroundColor Gray
    $actualHash = (Get-FileHash $FilePath -Algorithm $Algorithm).Hash.ToUpper()
    if ($actualHash -ne $ExpectedHash.ToUpper()) {
        throw "Checksum mismatch for `"$FilePath`". Expected '$ExpectedHash', but got '$actualHash'."
    }
    Write-Host "    [OK] Checksum valid." -ForegroundColor Green
}

# --- 脚本执行 ---

# 阶段一：检查本地工具
Write-Host ">> [1/5] Checking for existing local tools..." -ForegroundColor Cyan
if ((Test-Path "$TargetDir\ffmpeg\ffmpeg.exe") -and (Test-Path "$TargetDir\yt-dlp\yt-dlp.exe") -and (Test-Path "$TargetDir\deno\deno.exe")) {
    Write-Host ">> Success: All required tools are already present." -ForegroundColor Green
    exit 0
}

# 清理并创建临时下载目录
if (Test-Path $TempDir) { Remove-Item $TempDir -Recurse -Force }
New-Item -ItemType Directory -Path $TempDir | Out-Null

# 阶段二：获取 yt-dlp
Write-Host "`n>> [2/5] Fetching latest yt-dlp from GitHub..." -ForegroundColor Cyan
try {
    $releaseInfo = Invoke-RestMethod -Uri "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
    $exeAsset = $releaseInfo.assets | Where-Object { $_.name -eq 'yt-dlp.exe' }
    $checksumAsset = $releaseInfo.assets | Where-Object { $_.name -eq 'SHA2-256SUMS' }

    $checksumsFile = Join-Path $TempDir "yt-dlp-SHA2-256SUMS.txt"
    Invoke-Download -Uri $checksumAsset.browser_download_url -OutFile $checksumsFile
    
    $exePath = Join-Path $TempDir "yt-dlp.exe"
    Invoke-Download -Uri $exeAsset.browser_download_url -OutFile $exePath

    $expectedHashLine = Get-Content $checksumsFile | Select-String -Pattern "yt-dlp.exe"
    $expectedHash = ($expectedHashLine -split ' ')[0]
    Verify-Checksum -FilePath $exePath -ExpectedHash $expectedHash
} catch {
    throw "Failed to fetch yt-dlp. Error: $_ "
}

# 阶段三：获取 ffmpeg
Write-Host "`n>> [3/5] Fetching latest ffmpeg from GitHub (BtbN)..." -ForegroundColor Cyan
try {
    $releaseInfo = Invoke-RestMethod -Uri "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
    $zipAsset = $releaseInfo.assets | Where-Object { $_.name -like '*win64-gpl-shared*.zip' } | Select-Object -First 1
    $checksumAsset = $releaseInfo.assets | Where-Object { $_.name -eq 'sha256sum.txt' }
    
    if (-not $zipAsset) { throw "Could not find a suitable ffmpeg zip asset in the latest release." }

    $checksumsFile = Join-Path $TempDir "ffmpeg-sha256sum.txt"
    Invoke-Download -Uri $ffmpegChecksumAsset.browser_download_url -OutFile $checksumsFile

    $zipPath = Join-Path $TempDir $zipAsset.name
    Invoke-Download -Uri $zipAsset.browser_download_url -OutFile $zipPath
    
    $expectedHashLine = Get-Content $checksumsFile | Select-String -Pattern $zipAsset.name
    $expectedHash = ($expectedHashLine -split ' ')[0]
    Verify-Checksum -FilePath $zipPath -ExpectedHash $expectedHash
} catch {
    throw "Failed to fetch ffmpeg. Error: $_ "
}

# 阶段四：获取 deno
Write-Host "`n>> [4/5] Fetching latest deno from GitHub..." -ForegroundColor Cyan
try {
    $releaseInfo = Invoke-RestMethod -Uri "https://api.github.com/repos/denoland/deno/releases/latest"
    $zipAsset = $releaseInfo.assets | Where-Object { $_.name -eq 'deno-x86_64-pc-windows-msvc.zip' }
    $checksumAsset = $releaseInfo.assets | Where-Object { $_.name -eq "$($zipAsset.name).sha256" }

    $checksumFile = Join-Path $TempDir "deno.sha256"
    Invoke-Download -Uri $checksumAsset.browser_download_url -OutFile $checksumFile

    $zipPath = Join-Path $TempDir $zipAsset.name
    Invoke-Download -Uri $zipAsset.browser_download_url -OutFile $zipPath

    $expectedHash = (Get-Content $checksumFile) -split ' ' | Select-Object -First 1
    Verify-Checksum -FilePath $zipPath -ExpectedHash $expectedHash
} catch {
    throw "Failed to fetch deno. Error: $_ "
}


# 阶段五：解压和部署
Write-Host "`n>> [5/5] Deploying all tools to $TargetDir..." -ForegroundColor Cyan
if (Test-Path $TargetDir) { Remove-Item $TargetDir -Recurse -Force }
$ytDlpTargetDir = New-Item -ItemType Directory -Path (Join-Path $TargetDir "yt-dlp") -Force
$ffmpegTargetDir = New-Item -ItemType Directory -Path (Join-Path $TargetDir "ffmpeg") -Force
$denoTargetDir = New-Item -ItemType Directory -Path (Join-Path $TargetDir "deno") -Force

# 部署 yt-dlp
Move-Item -Path (Join-Path $TempDir "yt-dlp.exe") -Destination $ytDlpTargetDir

# 部署 ffmpeg
$ffmpegZipPath = Get-ChildItem -Path $TempDir -Filter '*win64-gpl-shared*.zip' | Select-Object -First 1
$ffmpegExtractPath = Join-Path $TempDir "ffmpeg_extracted"
New-Item -ItemType Directory -Path $ffmpegExtractPath | Out-Null
Expand-Archive -Path $ffmpegZipPath.FullName -DestinationPath $ffmpegExtractPath -Force
Move-Item -Path (Join-Path $ffmpegExtractPath "*\bin\ffmpeg.exe") -Destination $ffmpegTargetDir
Move-Item -Path (Join-Path $ffmpegExtractPath "*\bin\ffprobe.exe") -Destination $ffmpegTargetDir

# 部署 deno
$denoZipPath = Join-Path $TempDir "deno-x86_64-pc-windows-msvc.zip"
Expand-Archive -Path $denoZipPath -DestinationPath $denoTargetDir -Force

# 清理临时目录
Remove-Item $TempDir -Recurse -Force

Write-Host "`n>> Success! All tools (deno, ffmpeg, yt-dlp) are now ready." -ForegroundColor Green