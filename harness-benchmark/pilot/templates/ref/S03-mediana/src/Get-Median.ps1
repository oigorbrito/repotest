function Get-Median {
    param([double[]]$Values)
    if ($null -eq $Values -or $Values.Count -eq 0) { return $null }
    $s = @($Values | Sort-Object)
    $n = $s.Count
    $h = [int][math]::Floor($n / 2)
    if ($n % 2 -eq 1) { return $s[$h] }
    return ($s[$h - 1] + $s[$h]) / 2
}
