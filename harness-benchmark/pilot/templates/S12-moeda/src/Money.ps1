function Format-Money {
    param([double]$Amount)
    return $Amount.ToString('F2', [Globalization.CultureInfo]::InvariantCulture)
}
