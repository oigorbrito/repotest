function Build-Report {
    param([object[]]$Items)
    $total = Get-OrderTotal -Items $Items
    return "Total do pedido: " + $total.ToString('F2', [Globalization.CultureInfo]::InvariantCulture)
}
