function Get-Percent {
    param([double]$Part, [double]$Total)
    if ($Total -eq 0) { return 0 }
    return [math]::Round(($Part / $Total * 100), 1)
}
