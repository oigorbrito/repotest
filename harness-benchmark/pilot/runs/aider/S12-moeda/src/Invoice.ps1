function Build-Invoice {
    param(
        [object[]]$Items,
        [string]$Currency = 'BRL'
    )
    $total = 0.0
    foreach ($i in $Items) { $total += $i.Qty * $i.Price }
    return "Total: " + (Format-Money -Amount $total -Currency $Currency)
}
