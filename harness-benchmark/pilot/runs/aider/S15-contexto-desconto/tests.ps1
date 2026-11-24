. "$PSScriptRoot\src\Get-Discount.ps1"
$casos = @( @(40,0), @(50,2.5), @(99,4.95), @(100,15), @(200,30) )
$fail = @()
foreach ($c in $casos) {
  $r = [double](Get-Discount -Amount $c[0])
  if ([math]::Abs($r - $c[1]) -gt 0.0001) { $fail += "$($c[0]) -> $r (esperado $($c[1]))" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
