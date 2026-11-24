function Get-Discount {
    param([double]$Amount)
    if ($Amount -ge 100) { return $Amount * 0.15 }
    if ($Amount -ge 50) { return $Amount * 0.05 }
    return 0
}
