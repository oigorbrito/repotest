# Gera saida\resumo.txt a partir de data\vendas.csv, somando valores por categoria
$ErrorActionPreference = 'Stop'

$raiz = Split-Path $PSScriptRoot -Parent
$entrada = Join-Path $raiz 'data\vendas.csv'
$pastaSaida = Join-Path $raiz 'saida'
$arquivoSaida = Join-Path $pastaSaida 'resumo.txt'

$cultura = [System.Globalization.CultureInfo]::InvariantCulture

$totais = @{}
Import-Csv -Path $entrada | ForEach-Object {
    $categoria = $_.categoria
    $valor = [decimal]::Parse($_.valor, $cultura)
    if ($totais.ContainsKey($categoria)) {
        $totais[$categoria] += $valor
    }
    else {
        $totais[$categoria] = $valor
    }
}

$linhas = foreach ($categoria in ($totais.Keys | Sort-Object)) {
    '{0};{1}' -f $categoria, $totais[$categoria].ToString('F2', $cultura)
}

if (-not (Test-Path $pastaSaida)) {
    New-Item -ItemType Directory -Path $pastaSaida | Out-Null
}

$conteudo = ($linhas -join "`n") + "`n"
[System.IO.File]::WriteAllText($arquivoSaida, $conteudo, (New-Object System.Text.UTF8Encoding($false)))
