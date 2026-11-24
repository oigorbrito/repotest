function Format-Money {
    param($Value)
    return $Value.ToString('F2', [Globalization.CultureInfo]::InvariantCulture)
}

function Format-InvoiceLine {
    param($Item, $Subtotal)
    return ("{0} x{1} = {2}" -f $Item.Name, $Item.Qty, (Format-Money $Subtotal))
}

function Get-InvoiceSubtotal {
    param($Item)
    return $Item.Qty * $Item.Price
}

function Get-InvoiceTotal {
    param([object[]]$Items)
    $total = 0
    foreach ($i in $Items) {
        $total += (Get-InvoiceSubtotal $i)
    }
    return $total
}

function Format-Invoice {
    param([string]$Customer, [object[]]$Items)
    $linhas = @()
    $linhas += "Cliente: $Customer"
    foreach ($i in $Items) {
        $linhas += (Format-InvoiceLine $i (Get-InvoiceSubtotal $i))
    }
    $linhas += ("Total: " + (Format-Money (Get-InvoiceTotal $Items)))
    return ($linhas -join "`n")
}
