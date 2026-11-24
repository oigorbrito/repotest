. "$PSScriptRoot\src\Users.ps1"
$fail = @()
if (-not (Get-Command Assert-NonEmpty -ErrorAction SilentlyContinue)) { $fail += "Assert-NonEmpty nao existe" }
if ((Set-UserName -Value '  ana ') -ne 'ana') { $fail += "Set-UserName nao devolveu 'ana'" }
foreach ($c in @(@('Set-UserName','Nome'), @('Set-UserEmail','Email'), @('Set-UserCity','Cidade'))) {
  $msg = $null
  try { & $c[0] -Value '  ' | Out-Null } catch { $msg = $_.Exception.Message }
  if (-not $msg) { $fail += "$($c[0]) aceitou valor vazio" }
  elseif ($msg -notmatch $c[1]) { $fail += "$($c[0]) mensagem sem '$($c[1])': $msg" }
}
$txt = Get-Content (Join-Path $PSScriptRoot 'src\Users.ps1') -Raw
if (([regex]::Matches($txt, 'IsNullOrWhiteSpace')).Count -ne 1) { $fail += "a verificacao de vazio ainda esta duplicada" }
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
