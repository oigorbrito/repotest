# Lê data\vendas.csv, soma valores por categoria e grava saida\resumo.txt
$base = Split-Path -Parent $PSScriptRoot
$entrada = Join-Path $base 'data\vendas.csv'
$saidaDir = Join-Path $base 'saida'
$saida = Join-Path $saidaDir 'resumo.txt'

$totais = @{}
Import-Csv -Path $entrada -Encoding UTF8 | ForEach-Object {
    $cat = $_.categoria.Trim()
    $val = [decimal]::Parse($_.valor.Trim(), [System.Globalization.CultureInfo]::InvariantCulture)
    if ($totais.ContainsKey($cat)) { $totais[$cat] += $val } else { $totais[$cat] = $val }
}

$linhas = foreach ($cat in ($totais.Keys | Sort-Object { $_ } -CaseSensitive:$false)) {
    '{0};{1}' -f $cat, $totais[$cat].ToString('F2', [System.Globalization.CultureInfo]::InvariantCulture)
}

if (-not (Test-Path $saidaDir)) { New-Item -ItemType Directory -Path $saidaDir | Out-Null }
[System.IO.File]::WriteAllLines($saida, [string[]]$linhas, (New-Object System.Text.UTF8Encoding($false)))
