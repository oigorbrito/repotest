param([string[]]$Agents = @("pi","orca","marshall","cline","aider"), [string[]]$Tasks = @())
$root      = Split-Path -Parent $MyInvocation.MyCommand.Path
$M         = "claude-haiku-5-5"
$prompt    = "Leia o arquivo TASK.md desta pasta e execute a tarefa descrita nele."
$yml       = Join-Path $root "aider-models.yml"
$orcaFlags = @("--yolo")
$tasks     = @(Get-ChildItem (Join-Path $root "templates") -Directory | Where-Object { $_.Name -ne "ref" } | ForEach-Object { $_.Name } | Sort-Object)
if ($Tasks.Count -gt 0) { $tasks = $Tasks }
$rows      = @()

function Num($s) {
  if ($s -match 'k$') { return [double]($s -replace 'k$','') * 1000 }
  return [double]($s -replace ',','')
}

function Get-Usage($agent, $text) {
  $u = @{ tin=0.0; tout=0.0; tcr=0.0; tcw=0.0; cost=$null; it=$null }
  if (-not $text) { return $u }
  $lines = $text -split "`r?`n"
  switch ($agent) {
    "pi" {
      foreach ($line in $lines) {
        if ($line -notmatch '"type":"message_end"') { continue }
        try { $o = $line | ConvertFrom-Json } catch { continue }
        if ($o.message.role -ne "assistant" -or $o.message.stopReason -eq "error") { continue }
        $x = $o.message.usage
        $u.tin += [double]$x.input; $u.tout += [double]$x.output
        $u.tcr += [double]$x.cacheRead; $u.tcw += [double]$x.cacheWrite
        if ($null -eq $u.cost) { $u.cost = 0.0 }
        $u.cost += [double]$x.cost.total
      }
    }
    "orca" {
      $l = $lines | Where-Object { $_ -match '"type":"summary"' } | Select-Object -Last 1
      if ($l) {
        $o = $l | ConvertFrom-Json
        $u.tin = [double]$o.usage.inputTokens; $u.tout = [double]$o.usage.outputTokens
        $u.tcr = [double]$o.usage.cacheReadTokens; $u.tcw = [double]$o.usage.cacheCreateTokens
        $u.it = [double]$o.modelSteps
      }
    }
    "cline" {
      $l = $lines | Where-Object { $_ -match '"type":"run_result"' } | Select-Object -Last 1
      if ($l) {
        $o = $l | ConvertFrom-Json; $g = $o.aggregateUsage
        $u.tin = [double]$g.inputTokens; $u.tout = [double]$g.outputTokens
        $u.tcr = [double]$g.cacheReadTokens; $u.tcw = [double]$g.cacheWriteTokens
        $u.cost = [double]$g.totalCost; $u.it = [double]$o.iterations
      }
    }
    "marshall" {
      $l = $lines | Where-Object { $_ -match '^MARSHALL_USAGE ' } | Select-Object -Last 1
      if ($l) {
        $o = ($l -replace '^MARSHALL_USAGE ','') | ConvertFrom-Json
        $u.tin = [double]$o.session.inputTokens; $u.tout = [double]$o.session.outputTokens
      }
    }
    "aider" {
      $t = [regex]::Matches($text, 'Tokens: (\S+) sent, (\S+) received') | Select-Object -Last 1
      if ($t) { $u.tin = Num $t.Groups[1].Value; $u.tout = Num $t.Groups[2].Value }
      $c = [regex]::Matches($text, 'Cost: \$([\d\.]+) message, \$([\d\.]+) session') | Select-Object -Last 1
      if ($c) { $u.cost = [double]$c.Groups[2].Value }
    }
  }
  return $u
}

# Custo estimado pelo mesmo critério para todos (Haiku 5.5: US$ 0,10 entrada, 0,50 saída, 0,01 leitura de cache, 0,125 escrita de cache por milhão)
function Get-EstCost($u) {
  return ($u.tin * 0.1 + $u.tout * 0.5 + $u.tcr * 0.01 + $u.tcw * 0.125) / 1000000
}

foreach ($t in $tasks) {
  foreach ($a in $Agents) {
    $ws = Join-Path $root "runs\$a\$t"
    if (Test-Path $ws) { Remove-Item $ws -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $ws | Out-Null
    Copy-Item -Recurse -Force (Join-Path $root "templates\$t\*") $ws
    $log = Join-Path $ws "agent.log"
    $srcFiles = @(Get-ChildItem $ws -Recurse -File | Where-Object { $_.Name -ne "agent.log" } | ForEach-Object { $_.FullName.Substring($ws.Length + 1) })

    Write-Host "`n>>> $a / $t" -ForegroundColor Cyan
    $prompt = "Leia o arquivo $ws\TASK.md e execute a tarefa descrita nele. Trabalhe somente dentro de $ws."
    Push-Location $ws
    $sw = [Diagnostics.Stopwatch]::StartNew()
    switch ($a) {
      "pi"       { & pi -p --mode json --provider anthropic --model $M --no-session $prompt > $log 2>&1 }
      "orca"     { & orcacode --provider anthropic --model $M --no-session --json $orcaFlags -p $prompt > $log 2>&1 }
      "marshall" { & marshall -p claude -m $M --safety yolo --message $prompt . > $log 2>&1 }
      "cline"    { & cline -P anthropic -m $M --json -c "$ws" $prompt > $log 2>&1 }
      "aider"    { & aider --model "anthropic/$M" --model-settings-file $yml --no-git --no-auto-commits --yes-always $srcFiles --message-file TASK.md > $log 2>&1 }
    }
    $sw.Stop()
    Pop-Location

    $testOut = (& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ws "tests.ps1") 2>&1 | Out-String).Trim()
    $ok = ($LASTEXITCODE -eq 0)
    $u = Get-Usage $a (Get-Content -Raw $log -ErrorAction SilentlyContinue)
    $est = Get-EstCost $u
    $rows += [pscustomobject]@{
      agente = $a; tarefa = $t; sucesso = $ok
      segundos = [math]::Round($sw.Elapsed.TotalSeconds, 1)
      entrada = $u.tin; saida = $u.tout; cache_leitura = $u.tcr; cache_escrita = $u.tcw
      iteracoes = $u.it; custo_est_usd = [math]::Round($est, 6); custo_reportado_usd = $u.cost
      teste = $testOut; log = $log
    }
    Write-Host ("   sucesso={0}  tempo={1}s" -f $ok, [math]::Round($sw.Elapsed.TotalSeconds, 1))
  }
}

$csv = Join-Path $root "results.csv"
$rows | Export-Csv -NoTypeInformation -Encoding utf8 $csv
$rows | Format-Table agente, tarefa, sucesso, segundos, entrada, saida, custo_est_usd -AutoSize
$rows | Group-Object agente | ForEach-Object {
  $acertos = @($_.Group | Where-Object { $_.sucesso }).Count
  $custo = ($_.Group | Measure-Object -Property custo_est_usd -Sum).Sum
  $porAcerto = "n/a"
  if ($acertos -gt 0) { $porAcerto = [math]::Round($custo / $acertos, 6) }
  [pscustomobject]@{ agente = $_.Name; acertos = "$acertos/$($_.Count)"; custo_total_usd = [math]::Round($custo, 6); custo_por_acerto_usd = $porAcerto }
} | Format-Table -AutoSize
Write-Host "`nCSV: $csv"





