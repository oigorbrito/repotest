$ErrorActionPreference = 'Stop'

# Pasta do projeto = pai da pasta tools
$base      = Split-Path -Parent $PSScriptRoot
$pastaChecks = Join-Path $base 'checks'
$pastaRel  = Join-Path $base 'relatorio'
$arquivo   = Join-Path $pastaRel 'resultados.txt'

if (-not (Test-Path $pastaRel)) { New-Item -ItemType Directory -Path $pastaRel | Out-Null }

$scripts = Get-ChildItem -Path $pastaChecks -Filter '*.ps1' -File | Sort-Object -Property Name

$linhas = foreach ($s in $scripts) {
    $nome = [System.IO.Path]::GetFileNameWithoutExtension($s.Name)
    $p = Start-Process -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $s.FullName) `
        -Wait -PassThru -NoNewWindow
    if ($p.ExitCode -eq 0) { "OK $nome" } else { "FALHOU $nome" }
}

Set-Content -Path $arquivo -Value $linhas -Encoding ASCII
Get-Content -Path $arquivo
