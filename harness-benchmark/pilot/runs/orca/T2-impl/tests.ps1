. "$PSScriptRoot\src\Format-Duration.ps1"
$casos = @{ 3723 = "1h 02m 03s"; 59 = "0h 00m 59s"; 0 = "0h 00m 00s"; 36000 = "10h 00m 00s" }
$fail = @()
foreach ($k in $casos.Keys) {
  $r = Format-Duration -Seconds $k
  if ($r -ne $casos[$k]) { $fail += "$k -> '$r' (esperado '$($casos[$k])')" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
