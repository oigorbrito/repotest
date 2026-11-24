#requires -Version 5.1
<#
Pi (TypeScript) vs pi-rs (Rust) ??? benchmark local, sem prompts/model calls.
Executa apenas comandos de diagn??stico/CLI. N??O faz chamadas a providers.
Padr??es: Pi = "pi"; pi-rs = "pirs".
Se seus execut??veis tiverem outros nomes:
  .\benchmark-pi-vs-pirs.ps1 -PiExe "C:\caminho\pi.cmd" -RustExe "C:\caminho\pirs.exe"
#>

[CmdletBinding()]
param(
    [string]$PiExe = "pi",
    [string]$RustExe = "pirs",
    [int]$Repeats = 10,
    [int]$HelpRepeats = 3,
    [int]$TimeoutSeconds = 20,
    [string]$OutputRoot = (Join-Path $PSScriptRoot "results")
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Resolve-Executable([string]$Name) {
    if (Test-Path -LiteralPath $Name -PathType Leaf) {
        return (Resolve-Path -LiteralPath $Name).Path
    }
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandType -in @("Application", "ExternalScript") } |
        Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    return $null
}

function Invoke-CapturedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$Timeout,
        [string]$WorkingDirectory,
        [hashtable]$Environment = @{}
    )

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $FilePath
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true

    # Os argumentos deste benchmark s??o flags/valores simples, sem espa??os.
    # Arguments + EnvironmentVariables mant??m compatibilidade com Windows PowerShell 5.1.
    $quotedArgs = foreach ($arg in $Arguments) {
        '"' + ([string]$arg).Replace('"', '\\"') + '"'
    }
    $psi.Arguments = ($quotedArgs -join " ")
    foreach ($key in $Environment.Keys) {
        $psi.EnvironmentVariables[$key] = [string]$Environment[$key]
    }

    $p = [System.Diagnostics.Process]::new()
    $p.StartInfo = $psi
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        [void]$p.Start()
        $stdoutTask = $p.StandardOutput.ReadToEndAsync()
        $stderrTask = $p.StandardError.ReadToEndAsync()
        $finished = $p.WaitForExit($Timeout * 1000)
        if (-not $finished) {
            try { $p.Kill($true) } catch { try { $p.Kill() } catch {} }
            $p.WaitForExit()
            $sw.Stop()
            return [pscustomobject]@{
                ExitCode = 124; Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 4)
                TimedOut = $true; StdOut = ""; StdErr = "TIMEOUT"
                PeakWorkingSetMB = $null
            }
        }
        $p.WaitForExit()
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        $peak = $null
        try { $peak = [math]::Round($p.PeakWorkingSet64 / 1MB, 2) } catch {}
        $sw.Stop()
        return [pscustomobject]@{
            ExitCode = $p.ExitCode; Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 4)
            TimedOut = $false; StdOut = $stdout; StdErr = $stderr
            PeakWorkingSetMB = $peak
        }
    }
    catch {
        $sw.Stop()
        return [pscustomobject]@{
            ExitCode = 998; Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 4)
            TimedOut = $false; StdOut = ""; StdErr = $_.Exception.Message
            PeakWorkingSetMB = $null
        }
    }
    finally {
        $p.Dispose()
    }
}

function Add-Result {
    param(
        [string]$Harness, [string]$Test, [int]$Iteration,
        [object]$Run, [bool]$Pass, [string]$Detail
    )
    $script:Rows.Add([pscustomobject]@{
        Timestamp = (Get-Date).ToString("o")
        Harness = $Harness
        Test = $Test
        Iteration = $Iteration
        Pass = $Pass
        ExitCode = $Run.ExitCode
        Seconds = $Run.Seconds
        PeakWorkingSetMB = $Run.PeakWorkingSetMB
        TimedOut = $Run.TimedOut
        Detail = $Detail
        StdOut = (($Run.StdOut -replace "`r","") -replace "`n"," | ").Trim()
        StdErr = (($Run.StdErr -replace "`r","") -replace "`n"," | ").Trim()
    })
}

function Run-Test {
    param(
        [string]$Harness, [string]$Exe, [string]$Test, [string[]]$Args,
        [int]$Iteration = 1, [string]$Cwd, [hashtable]$Env = @{},
        [scriptblock]$Validator
    )
    $run = Invoke-CapturedProcess -FilePath $Exe -Arguments $Args `
        -Timeout $TimeoutSeconds -WorkingDirectory $Cwd -Environment $Env
    $valid = $false
    $detail = ""
    if ($Validator) {
        $valid = [bool](& $Validator $run)
        $detail = "validator"
    } else {
        $valid = ($run.ExitCode -eq 0 -and -not $run.TimedOut)
        $detail = "exit code esperado 0"
    }
    Add-Result -Harness $Harness -Test $Test -Iteration $Iteration -Run $run -Pass $valid -Detail $detail
    $state = if ($valid) { "PASS" } else { "FAIL" }
    $color = if ($valid) { "Green" } else { "Red" }
    Write-Host ("{0,-8} {1,-24} #{2,-2} {3,-4} {4,8:N3}s exit={5}" -f $Harness,$Test,$Iteration,$state,$run.Seconds,$run.ExitCode) -ForegroundColor $color
    return $run
}

$piPath = Resolve-Executable $PiExe
$rustPath = Resolve-Executable $RustExe
if (-not $piPath -or -not $rustPath) {
    Write-Host "N??o encontrei os dois execut??veis." -ForegroundColor Red
    Write-Host "Pi original: $PiExe => $piPath"
    Write-Host "Pi-RS:       $RustExe => $rustPath"
    Write-Host "Confira com: Get-Command pi,pirs"
    Write-Host "Se necess??rio, passe -PiExe e -RustExe com o caminho completo."
    exit 3
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = Join-Path $OutputRoot $stamp
$null = New-Item -ItemType Directory -Force -Path $outDir
$work = Join-Path $outDir "isolated-work"
$homePi = Join-Path $outDir "home-pi"
$homeRs = Join-Path $outDir "home-pirs"
foreach ($d in @($work,$homePi,$homeRs)) { $null = New-Item -ItemType Directory -Force -Path $d }

$script:Rows = [System.Collections.Generic.List[object]]::new()
$meta = [ordered]@{
    Started = (Get-Date).ToString("o")
    Computer = $env:COMPUTERNAME
    OS = [System.Environment]::OSVersion.VersionString
    PowerShell = $PSVersionTable.PSVersion.ToString()
    PiExecutable = $piPath
    PiRsExecutable = $rustPath
    Repeats = $Repeats
    HelpRepeats = $HelpRepeats
    Note = "Sem chamadas a modelos/providers; testes CLI locais."
}
$meta | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $outDir "environment.json") -Encoding UTF8

$harnesses = @(
    [pscustomobject]@{ Name="PI"; Exe=$piPath; Home=$homePi },
    [pscustomobject]@{ Name="PI_RS"; Exe=$rustPath; Home=$homeRs }
)

Write-Host "`n=== PI vs PI-RS | benchmark local sem modelo ===" -ForegroundColor Cyan
Write-Host "Pi:    $piPath"
Write-Host "Pi-RS: $rustPath"
Write-Host "Sa??da: $outDir`n"

foreach ($h in $harnesses) {
    $envIso = @{
        "HOME" = $h.Home
        "USERPROFILE" = $h.Home
        "APPDATA" = (Join-Path $h.Home "AppData\Roaming")
        "LOCALAPPDATA" = (Join-Path $h.Home "AppData\Local")
        "XDG_CONFIG_HOME" = (Join-Path $h.Home ".config")
        "XDG_DATA_HOME" = (Join-Path $h.Home ".local\share")
        "XDG_STATE_HOME" = (Join-Path $h.Home ".local\state")
    }
    foreach ($v in $envIso.Values) { $null = New-Item -ItemType Directory -Force -Path $v }

    Write-Host "`n--- $($h.Name) ---" -ForegroundColor Yellow

    # 1) Vers??o: deve terminar com sucesso e imprimir algo.
    $versionValidator = {
        param($r)
        ($r.ExitCode -eq 0 -and -not $r.TimedOut -and
         (($r.StdOut + $r.StdErr).Trim().Length -gt 0))
    }
    $v = Run-Test $h.Name $h.Exe "version" @("--version") 1 $work $envIso $versionValidator

    # 2) Ajuda: aceita help com c??digo 0; alguns CLIs podem retornar outro c??digo.
    for ($i=1; $i -le $HelpRepeats; $i++) {
        $helpValidator = {
            param($r)
            (-not $r.TimedOut -and
             (($r.StdOut + $r.StdErr) -match "(?i)usage|commands|options|help"))
        }
        [void](Run-Test $h.Name $h.Exe "help" @("--help") $i $work $envIso $helpValidator)
    }

    # 3) Inicializa????o repetida: vers??o ?? um probe sem rede e sem infer??ncia de modelo.
    for ($i=1; $i -le $Repeats; $i++) {
        [void](Run-Test $h.Name $h.Exe "cold-start-version" @("--version") $i $work $envIso $versionValidator)
    }

    # 4) Flag inv??lida: mede tratamento de erro. Espera-se falha n??o-zero, sem timeout.
    $badValidator = {
        param($r)
        (-not $r.TimedOut -and $r.ExitCode -ne 0)
    }
    [void](Run-Test $h.Name $h.Exe "invalid-flag" @("--__benchmark_invalid_flag__") 1 $work $envIso $badValidator)

    # 5) Diret??rio de configura????o isolado: confirma que os probes b??sicos n??o falham
    # quando HOME/XDG apontam para um perfil tempor??rio. N??o l?? credenciais reais.
    $isolatedValidator = {
        param($r)
        ($r.ExitCode -eq 0 -and -not $r.TimedOut)
    }
    [void](Run-Test $h.Name $h.Exe "isolated-home" @("--version") 1 $work $envIso $isolatedValidator)

    # 6) Verifica????o de integridade do perfil isolado: invent??rio e JSON fixture
    # sint??tico; n??o passa tokens reais ao execut??vel e n??o simula login OAuth.
    $authDir = Join-Path $h.Home ".pi\agent"
    $null = New-Item -ItemType Directory -Force -Path $authDir
    $fixture = Join-Path $authDir "auth.json"
    '{"benchmark_fixture":{"type":"synthetic","credential":"NOT_A_REAL_SECRET"}}' |
        Set-Content -LiteralPath $fixture -Encoding UTF8
    $fixtureOk = $false
    try {
        $parsed = Get-Content -LiteralPath $fixture -Raw | ConvertFrom-Json
        $fixtureOk = ($parsed.benchmark_fixture.type -eq "synthetic")
    } catch {}
    $fakeRun = [pscustomobject]@{
        ExitCode = 0; Seconds = 0.0; TimedOut = $false
        StdOut = ""; StdErr = ""; PeakWorkingSetMB = $null
    }
    Add-Result $h.Name "synthetic-auth-json-parse" 1 $fakeRun $fixtureOk "PowerShell JSON parse; n??o testa OAuth/API real"
    Write-Host ("{0,-8} {1,-24} #{2,-2} {3,-4}" -f $h.Name,"synthetic-auth-json-parse",1,($(if($fixtureOk){"PASS"}else{"FAIL"}))) -ForegroundColor $(if($fixtureOk){"Green"}else{"Red"})
}

# Exporta????o bruta
$csvPath = Join-Path $outDir "detailed-results.csv"
$script:Rows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $csvPath

# Resumo agregado
$summary = foreach ($group in ($script:Rows | Group-Object Harness,Test)) {
    $items = @($group.Group)
    $times = @($items | Where-Object { $_.Seconds -ne $null } | ForEach-Object { [double]$_.Seconds } | Sort-Object)
    $median = if ($times.Count) {
        if ($times.Count % 2) { $times[[int][math]::Floor($times.Count/2)] }
        else { ($times[$times.Count/2-1] + $times[$times.Count/2]) / 2 }
    } else { $null }
    [pscustomobject]@{
        Group = $group.Name
        Runs = $items.Count
        Pass = @($items | Where-Object Pass).Count
        Fail = @($items | Where-Object { -not $_.Pass }).Count
        PassRatePct = if ($items.Count) { [math]::Round((@($items | Where-Object Pass).Count / $items.Count)*100,1) } else { 0 }
        MedianSeconds = if ($null -ne $median) { [math]::Round($median,4) } else { $null }
        MaxSeconds = if ($times.Count) { [math]::Round(($times | Measure-Object -Maximum).Maximum,4) } else { $null }
    }
}
$summaryPath = Join-Path $outDir "summary.csv"
$summary | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $summaryPath

$byHarness = foreach ($h in @("PI","PI_RS")) {
    $items = @($script:Rows | Where-Object Harness -eq $h)
    $pass = @($items | Where-Object Pass).Count
    $secs = @($items | ForEach-Object { [double]$_.Seconds } | Sort-Object)
    $med = if ($secs.Count % 2) { $secs[[int][math]::Floor($secs.Count/2)] } elseif ($secs.Count) { ($secs[$secs.Count/2-1]+$secs[$secs.Count/2])/2 } else { 0 }
    [pscustomobject]@{
        Harness = $h
        Pass = $pass
        Total = $items.Count
        PassRatePct = if ($items.Count) {[math]::Round($pass/$items.Count*100,1)} else {0}
        MedianSeconds = [math]::Round($med,4)
        Timeouts = @($items | Where-Object TimedOut).Count
    }
}
$report = @()
$report += "PI vs PI-RS - RELATORIO DE BENCHMARK LOCAL"
$report += "Gerado: $(Get-Date -Format o)"
$report += "Executaveis: PI=$piPath ; PI_RS=$rustPath"
$report += ""
$report += "RESUMO"
$report += ($byHarness | Format-Table -AutoSize | Out-String)
$report += "RESULTADOS POR TESTE"
$report += ($summary | Format-Table -AutoSize | Out-String)
$report += "LIMITACOES"
$report += "- Nenhuma chamada a modelo/provider foi feita."
$report += "- Teste de auth.json valida apenas JSON sintetico; nao prova OAuth, refresh, login/logout ou chamada autenticada."
$report += "- O perfil isolado e usado nos probes CLI; variaveis HOME/XDG podem nao ser respeitadas igualmente por todas as builds Windows."
$report += "- Memoria de processos muito curtos pode nao ser capturada; PeakWorkingSetMB e apenas indicativo."
$report += "- Para comparar comportamento real de login, e necessario adicionar testes especificos conforme os comandos de auth suportados por cada build."
$report | Set-Content (Join-Path $outDir "report.txt") -Encoding UTF8

Write-Host "`n=== RESUMO ===" -ForegroundColor Cyan
$byHarness | Format-Table -AutoSize
Write-Host "Arquivos gerados em: $outDir" -ForegroundColor Green
Write-Host " - report.txt"
Write-Host " - summary.csv"
Write-Host " - detailed-results.csv"
Write-Host " - environment.json"
Write-Host "`nImportante: esta primeira bateria mede CLI/startup/erro/perfil isolado. NAO declara vencedor em autenticacao OAuth real." -ForegroundColor Yellow
