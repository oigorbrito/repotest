function Get-Median {
    param([double[]]$Values)

    if ($null -eq $Values -or $Values.Count -eq 0) {
        return $null
    }

    # Ordena uma cópia para não alterar a entrada.
    $sorted = @($Values | Sort-Object)
    $n = $sorted.Count
    $meio = [math]::Floor($n / 2)

    if ($n % 2 -eq 1) {
        return $sorted[$meio]
    }

    return ($sorted[$meio - 1] + $sorted[$meio]) / 2
}
