param([switch]$DryRun)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$items = @(
"package_menu.ps1",
"package_zip.ps1",
"package_zip.py",
"package.ps1",
"package.cmd"
)
if ($DryRun) {
    Write-Host "DRYRUN: Restore list:" -ForegroundColor Cyan
    foreach ($f in $items) { Write-Host (("DRYRUN: {0} -> {1} : Exists={2}") -f (Join-Path $ScriptDir $f), (Join-Path "D:\YouTube\FluentYTDL" ("scripts\\" + $f)), (Test-Path (Join-Path $ScriptDir $f))) }
    exit 0
}
foreach ($f in $items) {
    $src = Join-Path $ScriptDir $f
    $dst = Join-Path "D:\YouTube\FluentYTDL" ("scripts\\" + $f)
    if (Test-Path $src) {
        $parent = Split-Path $dst -Parent
        if (-not (Test-Path $parent)) { New-Item -Path $parent -ItemType Directory | Out-Null }
        Move-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop
        (("Restored: {0} -> {1} on {2}") -f $src, $dst, (Get-Date)) | Out-File (Join-Path $ScriptDir 'restore_log.txt') -Encoding utf8 -Append
        Write-Host (("Restored: {0} -> {1}") -f $src, $dst) -ForegroundColor Green
    } else {
        Write-Host (("Nothing to restore at: {0}") -f $src) -ForegroundColor Yellow
    }
}
