function Format-Invoice {
    param([string]$Customer, [object[]]$Items)
    $linhas = @()
    $linhas += "Cliente: $Customer"
    $total = 0
    foreach ($i in $Items) {
        $sub = $i.Qty * $i.Price
        $total += $sub
        $linhas += ("{0} x{1} = {2}" -f $i.Name, $i.Qty, $sub.ToString('F2', [Globalization.CultureInfo]::InvariantCulture))
    }
    $linhas += ("Total: " + $total.ToString('F2', [Globalization.CultureInfo]::InvariantCulture))
    return ($linhas -join "`n")
}
