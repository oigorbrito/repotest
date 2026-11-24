function Get-Discount {
    param([double]$Amount)
    if ($Amount -gt 100) { return $Amount * 0.10 }
    return 0
}
