function Get-Median {
    param([double[]]$Values)

    if ($null -eq $Values -or $Values.Count -eq 0) {
        return $null
    }

    # Sort a copy so the caller's array is not modified.
    $sorted = @($Values | Sort-Object)
    $n = $sorted.Count
    $mid = [int][math]::Floor($n / 2)

    if ($n % 2 -eq 1) {
        return $sorted[$mid]
    }

    return ($sorted[$mid - 1] + $sorted[$mid]) / 2
}
