# Soma os valores de data\vendas.csv por categoria e grava saida\resumo.txt
# no formato 'categoria;total' (ordem alfabetica, 2 casas decimais com ponto).
$ErrorActionPreference = 'Stop'

$base = Split-Path -Parent $PSScriptRoot
$entrada = Join-Path $base 'data\vendas.csv'
$pastaSaida = Join-Path $base 'saida'
$saida = Join-Path $pastaSaida 'resumo.txt'
$cultura = [System.Globalization.CultureInfo]::InvariantCulture

if (-not (Test-Path -LiteralPath $entrada)) {
    throw "Arquivo de entrada nao encontrado: $entrada"
}

$totais = @{}
foreach ($linha in Import-Csv -LiteralPath $entrada) {
    $categoria = $linha.categoria.Trim()
    $valor = [decimal]::Parse($linha.valor.Trim(), $cultura)
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

if (-not (Test-Path -LiteralPath $pastaSaida)) {
    New-Item -ItemType Directory -Path $pastaSaida | Out-Null
}

$utf8SemBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($saida, [string[]]@($linhas), $utf8SemBom)
Write-Host "Gerado: $saida"
