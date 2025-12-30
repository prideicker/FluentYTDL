param(
  [Parameter(Mandatory=$false)][string]$Url,
  [Parameter(Mandatory=$false)][string]$ChecksumUrl,
  [Parameter(Mandatory=$false)][string]$GitHubRepo, # in format owner/repo
  [Parameter(Mandatory=$false)][string]$ReleaseTag = 'latest',
  [Parameter(Mandatory=$false)][string]$AssetNamePattern = '*tools*.zip',
  [Parameter(Mandatory=$false)][string]$Dest = "$PSScriptRoot\..\assets\bin",
  [switch]$Force,
  [int]$Retries = 3
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Log { param($m) Write-Host "[fetch-tools] $m" }

# Ensure HTTPS for Url
if ($Url -and -not $Url.StartsWith('https://')) {
  throw "Url must use HTTPS"
}

# If GitHubRepo is provided, resolve asset URL via GitHub API
if (-not $Url -and $GitHubRepo) {
  $token = $env:GITHUB_TOKEN
  $api = "https://api.github.com/repos/$GitHubRepo/releases"
  if ($ReleaseTag -eq 'latest') {
    $api = "$api/latest"
  } else {
    $api = "$api/tags/$ReleaseTag"
  }
  Write-Log "Fetching release metadata from $api"
  $hdr = @{ 'User-Agent' = 'fetch-tools-script' }
  if ($token) { $hdr['Authorization'] = "token $token" }

  $release = Invoke-RestMethod -Uri $api -Headers $hdr -ErrorAction Stop
  $asset = $release.assets | Where-Object { $_.name -like $AssetNamePattern } | Select-Object -First 1
  if (-not $asset) { throw "No asset matching pattern '$AssetNamePattern' found in $GitHubRepo release tag '$ReleaseTag'" }
  $Url = $asset.browser_download_url
  # Try to find checksum asset too (name ending with .sha256 or .sha256.txt)
  $checksumAsset = $release.assets | Where-Object { $_.name -match '\.sha256(\.txt)?$' } | Select-Object -First 1
  if ($checksumAsset) { $ChecksumUrl = $checksumAsset.browser_download_url }
}

if (-not $Url) { throw "Either -Url or -GitHubRepo must be provided" }

# Prepare paths
$tempDir = Join-Path $env:TEMP ([System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $tempDir | Out-Null
$zipPath = Join-Path $tempDir ([System.IO.Path]::GetFileName($Url))

function Download-WithRetry($u,$outPath) {
  for ($i=0;$i -lt $Retries;$i++) {
    try {
      Write-Log "Downloading $u -> $outPath (attempt $($i+1))"
      Invoke-WebRequest -Uri $u -OutFile $outPath -UseBasicParsing -Headers @{ 'User-Agent' = 'fetch-tools-script' }
      return
    } catch {
      Write-Log "Download failed: $($_.Exception.Message)"
      Start-Sleep -Seconds (2 * ($i + 1))
    }
  }
  throw "Failed to download $u after $Retries attempts"
}

Download-WithRetry $Url $zipPath

# Download checksum if provided or infer
$checksumText = $null
if ($ChecksumUrl) {
  $chkPath = Join-Path $tempDir ([System.IO.Path]::GetFileName($ChecksumUrl))
  Download-WithRetry $ChecksumUrl $chkPath
  $checksumText = Get-Content -Path $chkPath -Raw
} else {
  # Try to infer .sha256 by appending
  $guess = "$Url.sha256"
  try { Download-WithRetry $guess (Join-Path $tempDir ([System.IO.Path]::GetFileName($guess))); $checksumText = Get-Content -Path (Join-Path $tempDir ([System.IO.Path]::GetFileName($guess))) -Raw } catch {}
}

# Verify checksum if available
if ($checksumText) {
  Write-Log "Verifying checksum"
  # Extract first 64 hex chars as sha256
  $shaLine = ($checksumText -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })[0]
  if ($shaLine -match "([a-fA-F0-9]{64})") { $expected = $Matches[1].ToLower() } else { throw "Could not parse sha256 from checksum file" }
  $actualBytes = Get-FileHash -Algorithm SHA256 -Path $zipPath
  if ($actualBytes.Hash.ToLower() -ne $expected) { throw "Checksum mismatch: expected $expected, actual $($actualBytes.Hash)" }
  Write-Log "Checksum OK"
} else {
  Write-Log "No checksum found; skipping verification (not recommended)"
}

# Extract to temp staging and verify structure
$staging = Join-Path $tempDir "staging"
New-Item -ItemType Directory -Path $staging | Out-Null
Write-Log "Extracting $zipPath to $staging"
Expand-Archive -Path $zipPath -DestinationPath $staging -Force

# Optional: basic validation - ensure at least one exe present
$exeFound = Get-ChildItem -Path $staging -Recurse -Include *.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $exeFound) { Write-Log "Warning: no .exe found in tools package; proceeding but check package contents" }

# Move to destination
if (-not (Test-Path $Dest)) { New-Item -ItemType Directory -Path $Dest | Out-Null }
if ($Force -and (Test-Path $Dest)) {
  Write-Log "Removing existing dest: $Dest"
  Remove-Item -Recurse -Force -Path $Dest
  New-Item -ItemType Directory -Path $Dest | Out-Null
}

Write-Log "Copying tools to $Dest"
Copy-Item -Path (Join-Path $staging '*') -Destination $Dest -Recurse -Force

# Cleanup
Remove-Item -Recurse -Force $tempDir
Write-Log "Done. Tools installed to $Dest"
exit 0