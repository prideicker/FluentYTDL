$pairs=@(
 @{src='D:\YouTube\FluentYTDL\scripts\move_build_and_venv_to_rabbish.ps1'; dst='D:\YouTube\FluentYTDL\rabbish\move_build_and_venv_to_rabbish.ps1'},
 @{src='D:\YouTube\FluentYTDL\scripts\move_build_to_rabbish.ps1'; dst='D:\YouTube\FluentYTDL\rabbish\move_build_to_rabbish.ps1'},
 @{src='D:\YouTube\FluentYTDL\scripts\move_old_package_to_rabbish.ps1'; dst='D:\YouTube\FluentYTDL\rabbish\move_old_package_to_rabbish.ps1'}
)

foreach($p in $pairs) {
    if (Test-Path $p.src) {
        Move-Item -LiteralPath $p.src -Destination $p.dst -Force
        Write-Host "Moved: $($p.src) -> $($p.dst)"
    } else {
        Write-Host "Missing: $($p.src)"
    }
}
