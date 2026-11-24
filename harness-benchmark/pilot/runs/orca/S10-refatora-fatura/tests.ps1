. "$PSScriptRoot\src\Format-Invoice.ps1"
$items = @( @{ Name='Caneta'; Qty=2; Price=1.5 }, @{ Name='Caderno'; Qty=1; Price=10 } )
$esperado = "Cliente: Ana`nCaneta x2 = 3.00`nCaderno x1 = 10.00`nTotal: 13.00"
$fail = @()
$r = Format-Invoice -Customer 'Ana' -Items $items
if ($r -ne $esperado) { $fail += "saida diferente: $r" }
$txt = Get-Content (Join-Path $PSScriptRoot 'src\Format-Invoice.ps1') -Raw
$n = ([regex]::Matches($txt, '(?m)^\s*function ')).Count
if ($n -lt 4) { $fail += "esperadas pelo menos 4 funcoes no arquivo, encontradas $n" }
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
