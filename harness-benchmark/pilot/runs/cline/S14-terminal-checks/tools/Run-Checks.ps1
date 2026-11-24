$ErrorActionPreference = 'Stop'

$base = Split-Path -Parent $PSScriptRoot
$checksDir = Join-Path $base 'checks'
$relatorioDir = Join-Path $base 'relatorio'
$arq = Join-Path $relatorioDir 'resultados.txt'

if (-not (Test-Path -LiteralPath $relatorioDir)) {
    New-Item -ItemType Directory -Path $relatorioDir | Out-Null
}

$linhas = @()
$scripts = Get-ChildItem -LiteralPath $checksDir -Filter '*.ps1' -File | Sort-Object Name

foreach ($script in $scripts) {
    $processo = Start-Process -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script.FullName) `
        -Wait -PassThru -NoNewWindow

    $nome = $script.BaseName
    if ($processo.ExitCode -eq 0) {
        $linhas += "OK $nome"
    } else {
        $linhas += "FALHOU $nome"
    }
}

$utf8SemBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($arq, [string[]]$linhas, $utf8SemBom)

