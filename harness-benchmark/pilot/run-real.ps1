param(
  [string[]]$Agents = @("orca","aider","marshall","pi"),
  [string[]]$Tasks = @(),
  [int]$Reps = 3,
  [string]$Base = "",
  [string]$Saida = "results-real.csv"
)
$root    = Split-Path -Parent $MyInvocation.MyCommand.Path
$hc      = if ($Base) { Join-Path $root $Base } else { Join-Path $root "real\source\benchmarks\harness-comparison" }
$fixture = Join-Path $hc "fixture"
$M       = "claude-haiku-5-5"
$yml     = Join-Path $root "aider-models.yml"
$SAFETY  = "Do not use shell or code execution and do not start a server. Use only the registered workspace tools. Your entire final response must be only the requested terminal line, with no explanation, markdown, code fence, or trailing punctuation."
$multi   = @('cross-file-comparison','cross-format-join','log-diagnosis','schema-diff','cross-file-config-edit','configuration-precedence','graph-reasoning')

$lista = (Get-Content $hc\tasks.json -Raw -Encoding UTF8 | ConvertFrom-Json).tasks
if ($Tasks.Count -gt 0) { $lista = @($lista | Where-Object { $Tasks -contains $_.id }) }
$rows = @()

function Build-Prompt($t) {
  if ($t.mode -eq 'read') { $perm = 'Do not edit, write, create, delete, or rename any file.' }
  else { $perm = 'You may edit only these files: ' + (@($t.allowed_changes) -join ', ') + '. Do not change any other file.' }
  return "$($t.prompt) $perm $SAFETY"
}

function Get-Snapshot($dir) {
  $h = @{}
  foreach ($f in (Get-ChildItem $dir -Recurse -File)) {
    $rel = $f.FullName.Substring($dir.Length + 1).Replace('\','/')
    $h[$rel] = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
  }
  return $h
}

function Test-Workspace($t, $dir, $before) {
  $after = Get-Snapshot $dir
  $keys = @(@($before.Keys) + @($after.Keys) | Sort-Object -Unique)
  $changed = @()
  foreach ($k in $keys) {
    if ($k -match '^\.') { continue }
    if ($before[$k] -ne $after[$k]) { $changed += $k }
  }
  $allowed = @($t.allowed_changes | Where-Object { $_ })
  $errs = @()
  $changedKey = (@($changed | Sort-Object)) -join '|'
  $allowedKey = (@($allowed | Sort-Object)) -join '|'
  if ($changedKey -ne $allowedKey) { $errs += "mudou: $($changed -join ', ')" }
  foreach ($c in @($t.checks | Where-Object { $_ })) {
    $p = Join-Path $dir $c.path
    if (-not (Test-Path $p)) { $errs += "falta $($c.path)"; continue }
    $txt = Get-Content $p -Raw -Encoding UTF8
    foreach ($x in @($c.contains | Where-Object { $_ })) { if (-not $txt.Contains($x)) { $errs += "sem '$x'" } }
    foreach ($x in @($c.not_contains | Where-Object { $_ })) { if ($txt.Contains($x)) { $errs += "ainda tem '$x'" } }
  }
  return [pscustomobject]@{ ok = ($errs.Count -eq 0); erros = ($errs -join ' | ') }
}

function Get-Answer($agent, $text) {
  $lines = $text -split "`r?`n"
  if ($agent -eq 'pi') {
    $ans = ''
    foreach ($l in $lines) {
      if ($l -notmatch '"type":"message_end"') { continue }
      try { $o = $l | ConvertFrom-Json } catch { continue }
      if ($o.message.role -eq 'assistant' -and $o.message.stopReason -eq 'stop') {
        $ans = (@($o.message.content) | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }) -join "`n"
      }
    }
    return $ans
  }
  if ($agent -eq 'orca') {
    $r = $lines | Where-Object { $_ -match '^\{"type":"result"' } | Select-Object -Last 1
    if ($r) { return ($r | ConvertFrom-Json).message }
    return ''
  }
  if ($agent -eq 'marshall') { return (@($lines | Where-Object { $_ -notmatch '^MARSHALL_USAGE ' }) -join "`n") }
  return (@($lines | Where-Object { $_ -notmatch '^Tokens:' -and $_ -notmatch '^Applied edit' }) -join "`n")
}

function Get-LastLine($s) {
  $l = @(($s -split "`r?`n") | Where-Object { $_.Trim() -ne '' })
  if ($l.Count -eq 0) { return '' }
  return $l[-1].Trim()
}

function ToNum($s) {
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
      if ($l) { $o = $l | ConvertFrom-Json; $u.tin=[double]$o.usage.inputTokens; $u.tout=[double]$o.usage.outputTokens; $u.tcr=[double]$o.usage.cacheReadTokens; $u.tcw=[double]$o.usage.cacheCreateTokens; $u.it=[double]$o.modelSteps }
    }
    "marshall" {
      $l = $lines | Where-Object { $_ -match '^MARSHALL_USAGE ' } | Select-Object -Last 1
      if ($l) { $o = ($l -replace '^MARSHALL_USAGE ','') | ConvertFrom-Json; $u.tin=[double]$o.session.inputTokens; $u.tout=[double]$o.session.outputTokens }
    }
    "aider" {
      $t = [regex]::Matches($text, 'Tokens: (\S+) sent, (\S+) received') | Select-Object -Last 1
      if ($t) { $u.tin = ToNum $t.Groups[1].Value; $u.tout = ToNum $t.Groups[2].Value }
      $c = [regex]::Matches($text, 'Cost: \$([\d\.]+) message, \$([\d\.]+) session') | Select-Object -Last 1
      if ($c) { $u.cost = [double]$c.Groups[2].Value }
    }
  }
  return $u
}

function Get-EstCost($u) {
  return ($u.tin * 0.1 + $u.tout * 0.5 + $u.tcr * 0.01 + $u.tcw * 0.125) / 1000000
}

$logs = Join-Path $root "real\logs"
$prompts = Join-Path $root "real\prompts"
New-Item -ItemType Directory -Force -Path $logs, $prompts | Out-Null

foreach ($rep in 1..$Reps) {
foreach ($t in $lista) {
  foreach ($a in $Agents) {
    $ws = Join-Path $root "real\runs\$a\$($t.id)-r$rep"
    if (Test-Path $ws) { Remove-Item $ws -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $ws | Out-Null
    Copy-Item -Recurse -Force "$fixture\*" $ws
    Remove-Item (Join-Path $ws 'AGENTS.md'), (Join-Path $ws 'CLAUDE.md') -Force -ErrorAction SilentlyContinue

    $prompt = Build-Prompt $t
    $pf = Join-Path $prompts "$($t.id).txt"
    [IO.File]::WriteAllText($pf, $prompt, (New-Object Text.UTF8Encoding $false))
    $log = Join-Path $logs "$a-$($t.id)-r$rep.log"
    $before = Get-Snapshot $ws

    $tools = @('read_file','grep','glob'); $toolsPi = @('read','grep','find','ls')
    if ($t.mode -eq 'edit') { $tools += @('edit_file','write_file'); $toolsPi += @('edit','write') }

    Write-Host "`n>>> $a / $($t.id)" -ForegroundColor Cyan
    Push-Location $ws
    $sw = [Diagnostics.Stopwatch]::StartNew()
    switch ($a) {
      "orca" {
        $args = @('--provider','anthropic','--model',$M,'--workspace',$ws,'--no-session','--json','--bare','--tools',($tools -join ','),'--effort','low','--max-output-tokens','1536','--max-steps','24','--prompt-cache')
        if ($t.mode -eq 'edit') { $args += '--yolo' }
        $args += @('--prompt-file', $pf)
        & orcacode @args > $log 2>&1
      }
      "pi" {
        & pi -p --mode json --provider anthropic --model $M --no-session --tools ($toolsPi -join ',') $prompt > $log 2>&1
      }
      "aider" {
        $files = @(Get-ChildItem $ws -Recurse -File | ForEach-Object { $_.FullName.Substring($ws.Length + 1) })
        $args = @('--model',"anthropic/$M",'--model-settings-file',$yml,'--no-git','--no-auto-commits','--yes-always') + $files + @('--message-file',$pf)
        & aider @args > $log 2>&1
      }
      "marshall" {
        & marshall -p claude -m $M --safety yolo --message $prompt $ws > $log 2>&1
      }
    }
    $sw.Stop()
    Pop-Location

    $text = if (Test-Path $log) { Get-Content $log -Raw -Encoding UTF8 } else { '' }
    $resp = Get-LastLine (Get-Answer $a $text)
    $respOk = ($resp -ceq ([string]$t.expected).Trim())
    $val = Test-Workspace $t $ws $before
    $u = Get-Usage $a $text
    $faixa = if ($t.id -like 'big-*') { 'grande' } elseif ($multi -contains $t.category) { 'multi-arquivo' } else { 'curta' }
    $rows += [pscustomobject]@{
      agente = $a; tarefa = $t.id; categoria = $t.category; faixa = $faixa; modo = $t.mode; repeticao = $rep
      resposta_correta = $respOk; workspace_ok = $val.ok; sucesso = ($respOk -and $val.ok)
      resposta = $resp; esperado = $t.expected; erros = $val.erros
      segundos = [math]::Round($sw.Elapsed.TotalSeconds, 1)
      entrada = $u.tin; saida = $u.tout; cache_leitura = $u.tcr; cache_escrita = $u.tcw
      custo_est_usd = [math]::Round((Get-EstCost $u), 6); custo_reportado_usd = $u.cost
    }
    Write-Host ("   rep={0} resposta_ok={1} workspace_ok={2} tempo={3}s" -f $rep, $respOk, $val.ok, [math]::Round($sw.Elapsed.TotalSeconds,1))
  }
}
}

$csv = Join-Path $root $Saida
$rows | Export-Csv -NoTypeInformation -Encoding utf8 $csv
$rows | Group-Object agente, faixa | ForEach-Object {
  $g = $_.Group
  $ok = @($g | Where-Object { $_.sucesso -eq $true }).Count
  $custo = ($g | Measure-Object -Property custo_est_usd -Sum).Sum
  [pscustomobject]@{ agente = $g[0].agente; faixa = $g[0].faixa; acertos = "$ok/$($g.Count)"; custo_total = [math]::Round($custo, 6); custo_por_acerto = $(if ($ok -gt 0) { [math]::Round($custo / $ok, 6) } else { 'n/a' }) }
} | Sort-Object agente, faixa | Format-Table -AutoSize
"CSV: $csv"
