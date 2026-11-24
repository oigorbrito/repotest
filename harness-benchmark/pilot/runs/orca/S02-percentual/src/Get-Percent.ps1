function Get-Percent {
    param([int]$Part, [int]$Total)
    if ($Total -eq 0) { return 0 }
    return [math]::Round([double]$Part / [double]$Total * 100, 1)
}
