function Get-Percent {
    param([int]$Part, [int]$Total)
    if ($Total -eq 0) { return 0 }
    return [math]::Round([int]($Part / $Total * 100), 1)
}
