. "$PSScriptRoot\src\Parse-Csv.ps1"
$casos = @(
  @{ In = 'a,b,c';           Out = @('a','b','c') },
  @{ In = 'a,"b,c",d';       Out = @('a','b,c','d') },
  @{ In = 'x,"say ""hi""",y'; Out = @('x','say "hi"','y') },
  @{ In = '"",z';            Out = @('','z') }
)
$fail = @()
foreach ($c in $casos) {
  $r = @(Parse-CsvLine -Line $c.In)
  if (($r -join '|') -ne ($c.Out -join '|')) { $fail += "'$($c.In)' -> '$($r -join '|')' (esperado '$($c.Out -join '|')')" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
