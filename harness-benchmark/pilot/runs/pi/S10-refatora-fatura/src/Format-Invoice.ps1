function Format-Money {
    param($Value)
    return $Value.ToString('F2', [Globalization.CultureInfo]::InvariantCulture)
}

function Format-InvoiceLine {
    param([object]$Item)
    $sub = $Item.Qty * $Item.Price
    return ("{0} x{1} = {2}" -f $Item.Name, $Item.Qty, (Format-Money $sub))
}

function Get-InvoiceTotal {
    param([object[]]$Items)
    $total = 0
    foreach ($i in $Items) {
        $total += $i.Qty * $i.Price
    }
    return $total
}

function Format-Invoice {
    param([string]$Customer, [object[]]$Items)
    $linhas = @()
    $linhas += "Cliente: $Customer"
    foreach ($i in $Items) {
        $linhas += Format-InvoiceLine $i
    }
    $linhas += ("Total: " + (Format-Money (Get-InvoiceTotal $Items)))
    return ($linhas -join "`n")
}
