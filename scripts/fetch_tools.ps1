# 文件名: scripts/fetch_tools.ps1
# 作用: 全自动、高安全地从官方源获取最新的外部工具。
#
# 工作逻辑:
# 1. 检查本地 `assets/bin` 目录是否已有所需工具。
# 2. 对于 yt-dlp:
#    a. 访问 GitHub API 获取最新 Release 信息。
#    b. 自动下载 yt-dlp.exe 和官方校验和文件。
#    c. 校验文件，确保安全。
# 3. 对于 ffmpeg:
#    a. 从社区信赖的 gyan.dev 下载一个指定的稳定版本。
#    b. 下载对应的校验和文件。
#    c. 校验文件，确保安全。
# 4. 解压 ffmpeg 并将所有工具放置到正确的 `assets/bin` 子目录中。

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
Write-Host ">> [1/4] Checking for existing local tools..." -ForegroundColor Cyan
if ((Test-Path "$TargetDir\ffmpeg\ffmpeg.exe") -and (Test-Path "$TargetDir\yt-dlp\yt-dlp.exe")) {
    Write-Host ">> Success: All required tools are already present." -ForegroundColor Green
    exit 0
}

# 清理并创建临时下载目录
if (Test-Path $TempDir) { Remove-Item $TempDir -Recurse -Force }
New-Item -ItemType Directory -Path $TempDir | Out-Null

# 阶段二：获取 yt-dlp
Write-Host "`n>> [2/4] Fetching latest yt-dlp..." -ForegroundColor Cyan
try {
    $ytDlpReleaseInfo = Invoke-RestMethod -Uri "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
    
    $ytDlpExeAsset = $ytDlpReleaseInfo.assets | Where-Object { $_.name -eq 'yt-dlp.exe' }
    $ytDlpChecksumAsset = $ytDlpReleaseInfo.assets | Where-Object { $_.name -eq 'SHA2-256SUMS' }

    # 下载校验文件和主程序
    $checksumsFile = Join-Path $TempDir "SHA2-256SUMS.txt"
    Invoke-Download -Uri $ytDlpChecksumAsset.browser_download_url -OutFile $checksumsFile
    
    $ytDlpExePath = Join-Path $TempDir "yt-dlp.exe"
    Invoke-Download -Uri $ytDlpExeAsset.browser_download_url -OutFile $ytDlpExePath

    # 从校验文件中提取 yt-dlp.exe 的哈希值并验证
    $ytDlpExpectedHashLine = Get-Content $checksumsFile | Select-String -Pattern "yt-dlp.exe"
    $ytDlpExpectedHash = ($ytDlpExpectedHashLine -split ' ')[0]
    Verify-Checksum -FilePath $ytDlpExePath -ExpectedHash $ytDlpExpectedHash
} catch {
    throw "Failed to fetch yt-dlp. Error: $_"
}

# 阶段三：获取 ffmpeg
Write-Host "`n>> [3/4] Fetching ffmpeg..." -ForegroundColor Cyan
try {
    # 我们选择一个特定的、经过验证的稳定版本，以确保构建的稳定性。
    # 这里使用 gyan.dev 的 essentials 构建，因为它体积更小。
    $ffmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-7.0-essentials_build.zip"
    $ffmpegHashUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-7.0-essentials_build.zip.sha256"
    
    $ffmpegZipPath = Join-Path $TempDir "ffmpeg.zip"
    $ffmpegHashPath = Join-Path $TempDir "ffmpeg_hash.txt"

    # 下载校验文件和主程序
    Invoke-Download -Uri $ffmpegHashUrl -OutFile $ffmpegHashPath
    Invoke-Download -Uri $ffmpegUrl -OutFile $ffmpegZipPath
    
    # 提取哈希值并验证
    $ffmpegExpectedHash = (Get-Content $ffmpegHashPath) -split ' ' | Select-Object -First 1
    Verify-Checksum -FilePath $ffmpegZipPath -ExpectedHash $ffmpegExpectedHash
} catch {
    throw "Failed to fetch ffmpeg. Error: $_"
}

# 阶段四：解压和部署
Write-Host "`n>> [4/4] Deploying tools to $TargetDir..." -ForegroundColor Cyan
# 清理旧目录并创建
if (Test-Path $TargetDir) { Remove-Item $TargetDir -Recurse -Force }
$ytDlpTargetDir = New-Item -ItemType Directory -Path (Join-Path $TargetDir "yt-dlp") -Force
$ffmpegTargetDir = New-Item -ItemType Directory -Path (Join-Path $TargetDir "ffmpeg") -Force

# 解压 ffmpeg
$ffmpegExtractPath = Join-Path $TempDir "ffmpeg_extracted"
New-Item -ItemType Directory -Path $ffmpegExtractPath | Out-Null
Expand-Archive -Path $ffmpegZipPath -DestinationPath $ffmpegExtractPath -Force

# 移动工具到最终位置
Move-Item -Path (Join-Path $ffmpegExtractPath "*\bin\ffmpeg.exe") -Destination $ffmpegTargetDir
Move-Item -Path (Join-Path $ffmpegExtractPath "*\bin\ffprobe.exe") -Destination $ffmpegTargetDir
Move-Item -Path $ytDlpExePath -Destination $ytDlpTargetDir

# 清理临时目录
Remove-Item $TempDir -Recurse -Force

Write-Host "`n>> Success! All tools are ready." -ForegroundColor Green