. "$PSScriptRoot\src\Get-Percent.ps1"
$casos = @( @(1,3,33.3), @(2,3,66.7), @(1,2,50), @(0,5,0), @(5,0,0) )
$fail = @()
foreach ($c in $casos) {
  $r = Get-Percent -Part $c[0] -Total $c[1]
  if ($r -ne $c[2]) { $fail += "$($c[0])/$($c[1]) -> $r (esperado $($c[2]))" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
