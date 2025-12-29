# Install githooks from the repository into .git/hooks
$RepoRoot = (Get-Location)
$Source = Join-Path $RepoRoot "githooks"
$Dest = Join-Path $RepoRoot ".git\hooks"

if (-not (Test-Path $Source)) {
    Write-Host "No githooks directory found at $Source" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $Dest)) {
    New-Item -ItemType Directory -Path $Dest | Out-Null
}

Get-ChildItem -Path $Source -File | ForEach-Object {
    $dst = Join-Path $Dest $_.Name
    Copy-Item -Path $_.FullName -Destination $dst -Force
    try {
        # Try to set executable bit (Git for Windows respects script extension/shell)
        & git update-index --add --chmod=+x "$dst" 2>$null
    } catch {
        # ignore
    }
    Write-Host "Installed hook: $_.Name"
}

Write-Host "Githooks installed to $Dest" -ForegroundColor Green
