$arq = Join-Path $PSScriptRoot 'saida\resumo.txt'
if (-not (Test-Path $arq)) { "FAIL: saida\resumo.txt nao foi gerado"; exit 1 }
$real = ((Get-Content $arq -Raw) -replace "`r", '').Trim()
$esperado = "alimentos;15.00`nbebidas;4.00`nlimpeza;7.25"
if ($real -eq $esperado) { "PASS"; exit 0 }
"FAIL: saida='$real'"; exit 1
