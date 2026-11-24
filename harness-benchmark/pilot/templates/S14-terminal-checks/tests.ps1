$arq = Join-Path $PSScriptRoot 'relatorio\resultados.txt'
if (-not (Test-Path $arq)) { "FAIL: relatorio\resultados.txt nao foi gerado"; exit 1 }
$real = ((Get-Content $arq -Raw) -replace "`r", '').Trim()
$esperado = "OK check-a`nFALHOU check-b`nOK check-c"
if ($real -eq $esperado) { "PASS"; exit 0 }
"FAIL: relatorio='$real'"; exit 1
