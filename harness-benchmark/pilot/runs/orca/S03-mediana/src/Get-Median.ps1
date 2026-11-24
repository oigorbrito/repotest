function Get-Median {
    param([double[]]$Values)
    if ($null -eq $Values -or $Values.Length -eq 0) { return $null }
    # Copia para nao alterar o array de entrada.
    $sorted = New-Object double[] $Values.Length
    [Array]::Copy($Values, $sorted, $Values.Length)
    [Array]::Sort($sorted)
    $n = $sorted.Length
    $mid = [int][math]::Floor($n / 2)
    if ($n % 2 -eq 1) { return $sorted[$mid] }
    return ($sorted[$mid - 1] + $sorted[$mid]) / 2
}
