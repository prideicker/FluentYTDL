$files=@(
 'D:\YouTube\FluentYTDL\scripts\package.ps1',
 'D:\YouTube\FluentYTDL\scripts\package_menu.ps1',
 'D:\YouTube\FluentYTDL\scripts\package_zip.ps1',
 'D:\YouTube\FluentYTDL\scripts\build_windows.ps1',
 'D:\YouTube\FluentYTDL\scripts\build.ps1',
 'D:\YouTube\FluentYTDL\scripts\build_dist.ps1'
)
foreach ($f in $files) {
    Write-Host "Checking: $f"
    try {
        $content = Get-Content $f -Raw
        [scriptblock]::Create($content) | Out-Null
        Write-Host "  PARSE OK"
    } catch {
        Write-Host "  PARSE ERROR: $($_.Exception.Message)"
    }
}
