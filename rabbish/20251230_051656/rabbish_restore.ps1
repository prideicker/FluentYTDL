param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

$items = @(
    @{Src = Join-Path $ScriptDir 'build_FluentYTDL'; Target = 'D:\\YouTube\\FluentYTDL\\build\\FluentYTDL'},
    @{Src = Join-Path $ScriptDir '.venv'; Target = 'D:\\YouTube\\FluentYTDL\\.venv'}
)

if ($DryRun) {
    Write-Host "DRYRUN: Would restore the following:" -ForegroundColor Cyan
    foreach ($i in $items) { Write-Host "DRYRUN: $($i.Src) -> $($i.Target) : Exists=$(Test-Path $($i.Src))" }
    exit 0
}

foreach ($i in $items) {
    if (Test-Path $i.Src) {
        $parent = Split-Path $i.Target -Parent
        if (-not (Test-Path $parent)) { New-Item -Path $parent -ItemType Directory | Out-Null }
        Move-Item -LiteralPath $i.Src -Destination $i.Target -Force -ErrorAction Stop
        "Restored: $($i.Src) -> $($i.Target) on $(Get-Date)" | Out-File (Join-Path $ScriptDir 'restore_log.txt') -Encoding utf8 -Append
        Write-Host "Restored: $($i.Src) -> $($i.Target)" -ForegroundColor Green
    } else {
        Write-Host "Nothing to restore at: $($i.Src)" -ForegroundColor Yellow
    }
}
