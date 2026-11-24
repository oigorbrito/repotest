$base = Split-Path -Parent $PSScriptRoot
$pasta = Join-Path $base 'checks'
$relatorio = Join-Path $base 'relatorio'
$arq = Join-Path $relatorio 'resultados.txt'

if (-not (Test-Path $relatorio)) { New-Item -ItemType Directory -Path $relatorio | Out-Null }

$linhas = @()
$scripts = Get-ChildItem -Path $pasta -Filter '*.ps1' -File | Sort-Object -Property Name
foreach ($s in $scripts) {
    $nome = [System.IO.Path]::GetFileNameWithoutExtension($s.Name)
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $s.FullName) -Wait -PassThru -NoNewWindow
    $codigo = $p.ExitCode
    if ($codigo -eq 0) {
        $linhas += "OK $nome"
    } else {
        $linhas += "FALHOU $nome"
    }
}

Set-Content -Path $arq -Value $linhas -Encoding ASCII
