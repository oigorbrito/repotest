# Executa cada script da pasta checks em um processo PowerShell separado,
# em ordem alfabetica, e grava relatorio\resultados.txt.
$base = Split-Path -Parent $PSScriptRoot
$pastaChecks = Join-Path $base 'checks'
$pastaRelatorio = Join-Path $base 'relatorio'
$arquivoResultados = Join-Path $pastaRelatorio 'resultados.txt'

if (-not (Test-Path $pastaRelatorio)) {
    New-Item -ItemType Directory -Path $pastaRelatorio | Out-Null
}

$scripts = Get-ChildItem -Path $pastaChecks -Filter '*.ps1' -File | Sort-Object -Property Name

$linhas = New-Object System.Collections.Generic.List[string]
foreach ($script in $scripts) {
    $nome = [System.IO.Path]::GetFileNameWithoutExtension($script.Name)
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script.FullName
    $codigo = $LASTEXITCODE
    if ($codigo -eq 0) {
        $linhas.Add("OK $nome")
    } else {
        $linhas.Add("FALHOU $nome")
    }
}

[System.IO.File]::WriteAllLines($arquivoResultados, $linhas.ToArray(), (New-Object System.Text.UTF8Encoding($false)))
Write-Output "Resultados gravados em $arquivoResultados"
