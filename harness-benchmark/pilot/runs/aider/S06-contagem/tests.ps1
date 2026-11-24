. "$PSScriptRoot\src\Get-WordCount.ps1"
$casos = @( @('Ola, mundo!!', 2), @('-- --', 0), @('a-b c', 3), @('', 0), @('123 abc.', 2) )
$fail = @()
foreach ($c in $casos) {
  $r = Get-WordCount -Text $c[0]
  if ($r -ne $c[1]) { $fail += "'$($c[0])' -> $r (esperado $($c[1]))" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
