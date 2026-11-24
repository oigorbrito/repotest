. "$PSScriptRoot\src\Orders.ps1"
. "$PSScriptRoot\src\Report.ps1"
$items = @( @{ Qty=2; Price=1.5 }, @{ Qty=1; Price=10 } )
$fail = @()
if (-not (Get-Command Get-OrderTotal -ErrorAction SilentlyContinue)) { $fail += "Get-OrderTotal nao existe" }
elseif ((Get-OrderTotal -Items $items) -ne 13) { $fail += "Get-OrderTotal retornou valor errado" }
if (Get-Command Get-Total -ErrorAction SilentlyContinue) { $fail += "Get-Total ainda existe" }
foreach ($f in 'Orders.ps1','Report.ps1') {
  $txt = Get-Content (Join-Path $PSScriptRoot "src\$f") -Raw
  if ($txt -match 'Get-Total\b') { $fail += "$f ainda referencia Get-Total" }
}
if ((Build-Report -Items $items) -ne 'Total do pedido: 13.00') { $fail += "Build-Report retornou valor errado" }
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
