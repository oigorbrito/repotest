. "$PSScriptRoot\src\Get-RomanNumeral.ps1"
$casos = @( @(1,'I'), @(4,'IV'), @(9,'IX'), @(14,'XIV'), @(1994,'MCMXCIV'), @(3999,'MMMCMXCIX') )
$fail = @()
foreach ($c in $casos) {
  $r = Get-RomanNumeral -Number $c[0]
  if ($r -ne $c[1]) { $fail += "$($c[0]) -> '$r' (esperado '$($c[1])')" }
}
foreach ($n in 0, 4000) {
  $lancou = $false
  try { Get-RomanNumeral -Number $n | Out-Null } catch { $lancou = $true }
  if (-not $lancou) { $fail += "$n deveria lancar erro" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
