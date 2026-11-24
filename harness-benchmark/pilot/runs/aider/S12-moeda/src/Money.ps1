function Format-Money {
    param(
        [double]$Amount,
        [string]$Currency = 'BRL'
    )
    $valor = $Amount.ToString('F2', [Globalization.CultureInfo]::InvariantCulture)
    return "$Currency $valor"
}
