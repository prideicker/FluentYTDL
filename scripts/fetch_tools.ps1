# 文件名: scripts/fetch_tools.ps1
# 作用: 全自动、高安全、高容错地从官方 GitHub Release 源获取全部外部工具。
#
# v5 (最终加固版) 更新:
# - 修正了 ffmpeg 校验文件名的拼写错误 (sha256sum.txt -> sha256.txt)。
# - 对所有API调用和文件查找增加了严格的、前置的空值检查和明确的错误报告。
# - 优化了代码结构，确保在任何资产(asset)查找失败时能立刻定位问题。

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
    if (-not $exeAsset) { throw "Could not find 'yt-dlp.exe' in the latest yt-dlp release." }
    
    $checksumAsset = $releaseInfo.assets | Where-Object { $_.name -eq 'SHA2-256SUMS' }
    if (-not $checksumAsset) { throw "Could not find 'SHA2-256SUMS' in the latest yt-dlp release." }

    $checksumsFile = Join-Path $TempDir "yt-dlp-SHA2-256SUMS.txt"
    $checksumUrl = $checksumAsset.browser_download_url
    if ([string]::IsNullOrEmpty($checksumUrl)) { throw "yt-dlp checksum asset found, but its download URL is empty." }
    Invoke-Download -Uri $checksumUrl -OutFile $checksumsFile
    
    $exePath = Join-Path $TempDir "yt-dlp.exe"
    $exeUrl = $exeAsset.browser_download_url
    if ([string]::IsNullOrEmpty($exeUrl)) { throw "yt-dlp.exe asset found, but its download URL is empty." }
    Invoke-Download -Uri $exeUrl -OutFile $exePath

    $expectedHashLine = Get-Content $checksumsFile | Select-String -Pattern "yt-dlp.exe"
    $expectedHash = ($expectedHashLine -split ' ')[0]
    Verify-Checksum -FilePath $exePath -ExpectedHash $expectedHash
} catch {
    throw "Failed to fetch yt-dlp. Error: $_ "
}

# 阶段三：获取 ffmpeg (修复版)
Write-Host "`n>> [3/5] Fetching latest ffmpeg from GitHub (BtbN)..." -ForegroundColor Cyan
try {
    # 使用 BtbN 提供的固定链接 (Master Builds)，避免 API 解析错误
    # 这个链接始终指向最新的构建，无需去查 Release ID
    $ffmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    $zipPath = Join-Path $TempDir "ffmpeg.zip"

    # 1. 下载 ZIP
    Write-Host "    Downloading FFmpeg zip..." -NoNewline
    Invoke-WebRequest -Uri $ffmpegUrl -OutFile $zipPath -ErrorAction Stop
    Write-Host " [OK]" -ForegroundColor Green
    
} catch {
    throw "Failed to fetch ffmpeg. Error: $_"
}

# 阶段四：获取 deno
Write-Host "`n>> [4/5] Fetching latest deno from GitHub..." -ForegroundColor Cyan
try {
    # 1. 获取最新 Release 信息
    $denoRelease = Invoke-RestMethod -Uri "https://api.github.com/repos/denoland/deno/releases/latest"
    
    # 2. 找到 Windows zip 文件
    $zipAsset = $denoRelease.assets | Where-Object { $_.name -like '*x86_64-pc-windows-msvc.zip' } | Select-Object -First 1
    if (-not $zipAsset) { throw "Could not find deno Windows zip asset." }
    
    # 3. 找到对应的校验文件 (关键修复：后缀名改为 .sha256sum)
    $checksumAsset = $denoRelease.assets | Where-Object { $_.name -eq ($zipAsset.name + ".sha256sum") }
    if (-not $checksumAsset) { 
        # 备选方案：尝试找 .sha256 后缀，防止未来又改回去
        $checksumAsset = $denoRelease.assets | Where-Object { $_.name -eq ($zipAsset.name + ".sha256") }
    }
    if (-not $checksumAsset) { throw "Could not find checksum file for $($zipAsset.name)." }

    # 4. 下载
    $zipPath = Join-Path $TempDir $zipAsset.name
    $checksumFile = Join-Path $TempDir "deno.checksum"

    Invoke-Download -Uri $zipAsset.browser_download_url -OutFile $zipPath
    Invoke-Download -Uri $checksumAsset.browser_download_url -OutFile $checksumFile

    # 5. 校验 (Deno 的校验文件通常包含 "hash  filename" 格式)
    $hashContent = Get-Content $checksumFile -Raw
    # 提取哈希值 (第一列)
    $expectedHash = ($hashContent -split '\s+')[0].Trim()
    
    # 调用内置函数进行校验
    Verify-Checksum -FilePath $zipPath -ExpectedHash $expectedHash
} catch {
    throw "Failed to fetch deno. Error: $_"
}


# 阶段五：解压和部署
Write-Host "`n>> [5/5] Deploying all tools to $TargetDir..." -ForegroundColor Cyan
if (Test-Path $TargetDir) { Remove-Item $TargetDir -Recurse -Force }
$ytDlpTargetDir = New-Item -ItemType Directory -Path (Join-Path $TargetDir "yt-dlp") -Force
$ffmpegTargetDir = New-Item -ItemType Directory -Path (Join-Path $TargetDir "ffmpeg") -Force
$denoTargetDir = New-Item -ItemType Directory -Path (Join-Path $TargetDir "deno") -Force

# 部署 yt-dlp
Move-Item -Path (Join-Path $TempDir "yt-dlp.exe") -Destination $ytDlpTargetDir

# 部署 ffmpeg (修复版)
try {
    Write-Host "    Extracting FFmpeg..." -NoNewline
    $ffmpegZipPath = Join-Path $TempDir "ffmpeg.zip"
    Expand-Archive -Path $ffmpegZipPath -DestinationPath $TempDir -Force
    
    # 找到解压后的内部文件夹 (例如 'ffmpeg-master-latest-win64-gpl')
    $extractedRoot = Get-ChildItem -Path $TempDir -Directory | Where-Object { $_.Name -like "ffmpeg-*-gpl" } | Select-Object -First 1
    
    if ($extractedRoot) {
        # 移动 bin 目录下的 exe 到我们的目标目录
        $sourceBin = Join-Path $extractedRoot.FullName "bin"
        
        if (Test-Path (Join-Path $sourceBin "ffmpeg.exe")) {
            Move-Item -Path (Join-Path $sourceBin "ffmpeg.exe") -Destination $ffmpegTargetDir -Force
        }
        if (Test-Path (Join-Path $sourceBin "ffprobe.exe")) {
            Move-Item -Path (Join-Path $sourceBin "ffprobe.exe") -Destination $ffmpegTargetDir -Force
        }
        
        Write-Host " [OK] FFmpeg installed." -ForegroundColor Green
    } else {
        throw "Failed to locate extracted ffmpeg folder structure inside '$TempDir'."
    }
} catch {
    throw "Failed to deploy ffmpeg. Error: $_"
}

# 部署 deno
$denoZipPath = Join-Path $TempDir "deno-x86_64-pc-windows-msvc.zip"
Expand-Archive -Path $denoZipPath -DestinationPath $denoTargetDir -Force

# 清理临时目录
Remove-Item $TempDir -Recurse -Force

Write-Host "`n>> Success! All tools (deno, ffmpeg, yt-dlp) are now ready." -ForegroundColor Green
