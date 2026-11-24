function Format-Money {
    param([double]$Amount, [string]$Currency = 'BRL')
    return "$Currency " + $Amount.ToString('F2', [Globalization.CultureInfo]::InvariantCulture)
}
