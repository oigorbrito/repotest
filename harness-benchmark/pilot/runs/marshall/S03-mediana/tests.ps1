. "$PSScriptRoot\src\Get-Median.ps1"
$casos = @( @(@(3,1,2), 2), @(@(4,1,3,2), 2.5), @(@(7), 7), @(@(5,5,1,9), 5) )
$fail = @()
foreach ($c in $casos) {
  $r = Get-Median -Values $c[0]
  if ($r -ne $c[1]) { $fail += "[$($c[0] -join ',')] -> $r (esperado $($c[1]))" }
}
$vazio = Get-Median -Values @()
if ($null -ne $vazio) { $fail += "lista vazia deveria retornar null" }
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
