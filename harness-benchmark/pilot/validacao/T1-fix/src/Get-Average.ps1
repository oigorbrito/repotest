function Get-Average {
    param([double[]]$Values)
    if ($Values.Count -eq 0) { return 0 }
    return ($Values | Measure-Object -Average).Average
}
