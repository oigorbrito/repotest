function Build-Invoice {
    param([object[]]$Items)
    $total = 0.0
    foreach ($i in $Items) { $total += $i.Qty * $i.Price }
    return "Total: " + (Format-Money -Amount $total)
}
