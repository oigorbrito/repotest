function Get-Average {
    param([double[]]$Values)
    return ($Values | Measure-Object -Average).Average
}
