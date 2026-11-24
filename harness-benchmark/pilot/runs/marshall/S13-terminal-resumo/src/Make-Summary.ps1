$ErrorActionPreference = 'Stop'

$base    = Split-Path -Parent $PSScriptRoot
$entrada = Join-Path $base 'data\vendas.csv'
$pasta   = Join-Path $base 'saida'
$saida   = Join-Path $pasta 'resumo.txt'

$cultura = [System.Globalization.CultureInfo]::InvariantCulture
$totais  = @{}

foreach ($linha in (Import-Csv -Path $entrada -Encoding UTF8)) {
    $cat = $linha.categoria.Trim()
    $val = [decimal]::Parse($linha.valor.Trim(), [System.Globalization.NumberStyles]::Float, $cultura)
    if ($totais.ContainsKey($cat)) {
        $totais[$cat] += $val
    } else {
        $totais[$cat] = $val
    }
}

$categorias = [string[]]@($totais.Keys)
[Array]::Sort($categorias, [StringComparer]::Ordinal)

$linhas = foreach ($cat in $categorias) {
    '{0};{1}' -f $cat, $totais[$cat].ToString('F2', $cultura)
}

if (-not (Test-Path $pasta)) { New-Item -ItemType Directory -Path $pasta | Out-Null }
$utf8SemBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($saida, [string[]]$linhas, $utf8SemBom)
