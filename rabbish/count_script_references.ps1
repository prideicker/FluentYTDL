$scripts = Get-ChildItem -Path 'D:\YouTube\FluentYTDL\scripts' -File | Select-Object -ExpandProperty Name
foreach ($s in $scripts) {
    $pattern = [regex]::Escape($s)
    $matches = Select-String -Path 'D:\YouTube\FluentYTDL\**\*' -Pattern $pattern -SimpleMatch -ErrorAction SilentlyContinue
    $external = $matches | Where-Object { $_.Path -notlike "*\scripts\$s" }
    $count = ($external | Measure-Object).Count
    Write-Host "$s -> external references: $count"
}
