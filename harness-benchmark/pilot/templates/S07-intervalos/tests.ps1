. "$PSScriptRoot\src\Merge-Ranges.ps1"
$casos = @(
  @{ In = @(@(1,3),@(3,5)); Out = '1-5' },
  @{ In = @(@(1,2),@(4,6)); Out = '1-2,4-6' },
  @{ In = @(@(5,7),@(1,3),@(2,6)); Out = '1-7' },
  @{ In = @(); Out = '' }
)
$fail = @()
foreach ($c in $casos) {
  $res = Merge-Ranges -Ranges $c.In
  $partes = @()
  foreach ($item in $res) { $partes += "$($item[0])-$($item[1])" }
  $txt = ($partes -join ',')
  if ($txt -ne $c.Out) { $fail += "'$txt' (esperado '$($c.Out)')" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1

