. "$PSScriptRoot\src\New-Slug.ps1"
$casos = @(
  @('Ola Mundo!', 'ola-mundo'), @('  Teste   de  Slug  ', 'teste-de-slug'),
  @('A--B__C', 'a-b-c'), @('123 abc', '123-abc'), @('!!!', '')
)
$fail = @()
foreach ($c in $casos) {
  $r = New-Slug -Text $c[0]
  if ($r -ne $c[1]) { $fail += "'$($c[0])' -> '$r' (esperado '$($c[1])')" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
