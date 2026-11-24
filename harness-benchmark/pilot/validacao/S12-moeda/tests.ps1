. "$PSScriptRoot\src\Money.ps1"
. "$PSScriptRoot\src\Invoice.ps1"
$items = @( @{ Qty=2; Price=1.5 }, @{ Qty=1; Price=10 } )
$obtidos = [ordered]@{
  'Format-Money padrao' = (Format-Money -Amount 10)
  'Format-Money USD'    = (Format-Money -Amount 10 -Currency USD)
  'Build-Invoice EUR'   = (Build-Invoice -Items $items -Currency EUR)
  'Build-Invoice padrao'= (Build-Invoice -Items $items)
}
$esperados = [ordered]@{
  'Format-Money padrao' = 'BRL 10.00'
  'Format-Money USD'    = 'USD 10.00'
  'Build-Invoice EUR'   = 'Total: EUR 13.00'
  'Build-Invoice padrao'= 'Total: BRL 13.00'
}
$fail = @()
foreach ($k in $esperados.Keys) {
  if ($obtidos[$k] -ne $esperados[$k]) { $fail += "$k -> '$($obtidos[$k])' (esperado '$($esperados[$k])')" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
