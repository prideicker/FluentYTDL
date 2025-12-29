# Cleanup helper: terminate common tool processes and remove old dist\FluentYTDL
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$path = Join-Path $root 'dist\FluentYTDL'
$exeNames = @('yt-dlp.exe','ffmpeg.exe','deno.exe')

Write-Host "Target path: $path"

function Kill-Tools {
  foreach ($e in $exeNames) {
    try {
      Write-Host "Attempting to terminate process: $e"
      Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','taskkill /F /IM '+$e -NoNewWindow -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue
    } catch {
      Write-Host ("Ignore kill error for {0}: {1}" -f $e, $_.Exception.Message)
    }
  }
}

if (-not (Test-Path $path)) {
  Write-Host "No old dist present: $path"
  exit 0
}

Kill-Tools

$maxAttempts = 6
for ($i = 0; $i -lt $maxAttempts; $i++) {
  if (-not (Test-Path $path)) { Write-Host "Path already removed."; exit 0 }
  try {
    Write-Host "Attempting Remove-Item (attempt $($i+1))..."
    Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
    Write-Host "Removed: $path"
    exit 0
  } catch {
    Write-Host "Remove attempt ($($i+1)) failed: $($_.Exception.Message)"
    Start-Sleep -Seconds (2 * ($i + 1))
    Kill-Tools
  }
}

if (Test-Path $path) {
  Write-Warning "Failed to remove after $maxAttempts attempts: $path"
  exit 2
}
