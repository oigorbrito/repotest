function Get-Total {
    param([object[]]$Items)
    $t = 0
    foreach ($i in $Items) { $t += $i.Qty * $i.Price }
    return $t
}
