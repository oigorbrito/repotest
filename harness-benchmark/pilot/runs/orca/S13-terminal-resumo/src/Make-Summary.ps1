# Soma os valores de data\vendas.csv por categoria e grava saida\resumo.txt
# Formato de cada linha: categoria;total (ponto decimal, 2 casas), ordem alfabetica.
$ErrorActionPreference = 'Stop'

$base = Split-Path -Parent $PSScriptRoot
$entrada = Join-Path $base 'data\vendas.csv'
$saidaDir = Join-Path $base 'saida'
$saida = Join-Path $saidaDir 'resumo.txt'

if (-not (Test-Path -LiteralPath $entrada)) {
    Write-Error "Arquivo de entrada nao encontrado: $entrada"
    exit 1
}

$cultura = [System.Globalization.CultureInfo]::InvariantCulture
$totais = @{}

foreach ($linha in (Import-Csv -LiteralPath $entrada -Encoding UTF8)) {
    $categoria = ([string]$linha.categoria).Trim()
    $valor = [decimal]::Parse(([string]$linha.valor).Trim(), [System.Globalization.NumberStyles]::Float, $cultura)
    if ($totais.ContainsKey($categoria)) {
        $totais[$categoria] += $valor
    } else {
        $totais[$categoria] = $valor
    }
}

$linhas = foreach ($categoria in ($totais.Keys | Sort-Object)) {
    '{0};{1}' -f $categoria, $totais[$categoria].ToString('F2', $cultura)
}

if (-not (Test-Path -LiteralPath $saidaDir)) {
    New-Item -ItemType Directory -Path $saidaDir | Out-Null
}

[System.IO.File]::WriteAllText($saida, (($linhas -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
Write-Output "Gerado: $saida"
