$root = "D:\projetos\harness-benchmark\pilot"
$tp = "$root\templates"
$rf = "$root\templates\ref"
function W($path, $content) {
  New-Item -ItemType Directory -Force -Path (Split-Path $path) | Out-Null
  Set-Content -Encoding utf8 -Path $path -Value $content
}

# ---------- Referencias do piloto (T1-T3) ----------
W "$rf\T1-fix\src\Get-Average.ps1" @'
function Get-Average {
    param([double[]]$Values)
    if ($Values.Count -eq 0) { return 0 }
    return ($Values | Measure-Object -Average).Average
}
'@
W "$rf\T2-impl\src\Format-Duration.ps1" @'
function Format-Duration {
    param([int]$Seconds)
    $h = [int][math]::Floor($Seconds / 3600)
    $m = [int][math]::Floor(($Seconds % 3600) / 60)
    $s = [int]($Seconds % 60)
    return ("{0}h {1:00}m {2:00}s" -f $h, $m, $s)
}
'@
W "$rf\T3-bug\src\Parse-Csv.ps1" @'
function Parse-CsvLine {
    param([string]$Line)
    $campos = @()
    $atual = New-Object System.Text.StringBuilder
    $aspas = $false
    for ($i = 0; $i -lt $Line.Length; $i++) {
        $c = $Line[$i]
        if ($aspas) {
            if ($c -eq '"') {
                if ($i + 1 -lt $Line.Length -and $Line[$i+1] -eq '"') { [void]$atual.Append('"'); $i++ }
                else { $aspas = $false }
            } else { [void]$atual.Append($c) }
        } else {
            if ($c -eq '"') { $aspas = $true }
            elseif ($c -eq ',') { $campos += $atual.ToString(); [void]$atual.Clear() }
            else { [void]$atual.Append($c) }
        }
    }
    $campos += $atual.ToString()
    return $campos
}
'@

# ---------- S01 correcao simples: palindromo ----------
W "$tp\S01-palindromo\TASK.md" @'
Corrija src\Test-Palindrome.ps1. A função Test-Palindrome deve dizer se o texto é um palíndromo, ignorando diferenças de maiúsculas e minúsculas e espaços. Exemplos: 'Ana' -> $true; 'A man a plan a canal Panama' -> $true; 'abc' -> $false. Não altere tests.ps1. Ao final, rode .\tests.ps1 e confirme que a saída é PASS.
'@
W "$tp\S01-palindromo\src\Test-Palindrome.ps1" @'
function Test-Palindrome {
    param([string]$Text)
    $arr = $Text.ToCharArray()
    [array]::Reverse($arr)
    return ((-join $arr) -ceq $Text)
}
'@
W "$tp\S01-palindromo\tests.ps1" @'
. "$PSScriptRoot\src\Test-Palindrome.ps1"
$casos = @(
  @('ana', $true), @('Ana', $true), @('arara', $true),
  @('A man a plan a canal Panama', $true), @('abc', $false), @('ab', $false)
)
$fail = @()
foreach ($c in $casos) {
  $r = [bool](Test-Palindrome -Text $c[0])
  if ($r -ne $c[1]) { $fail += "'$($c[0])' -> $r" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
'@
W "$rf\S01-palindromo\src\Test-Palindrome.ps1" @'
function Test-Palindrome {
    param([string]$Text)
    $s = ($Text -replace '\s', '').ToLowerInvariant()
    $arr = $s.ToCharArray()
    [array]::Reverse($arr)
    return ((-join $arr) -eq $s)
}
'@

# ---------- S02 correcao simples: percentual ----------
W "$tp\S02-percentual\TASK.md" @'
Corrija src\Get-Percent.ps1. Get-Percent -Part -Total deve retornar o percentual com 1 casa decimal (ex.: 1 de 3 -> 33.3; 2 de 3 -> 66.7). Se -Total for 0, retorna 0. Não altere tests.ps1. Ao final, rode .\tests.ps1 e confirme que a saída é PASS.
'@
W "$tp\S02-percentual\src\Get-Percent.ps1" @'
function Get-Percent {
    param([int]$Part, [int]$Total)
    if ($Total -eq 0) { return 0 }
    return [math]::Round([int]($Part / $Total * 100), 1)
}
'@
W "$tp\S02-percentual\tests.ps1" @'
. "$PSScriptRoot\src\Get-Percent.ps1"
$casos = @( @(1,3,33.3), @(2,3,66.7), @(1,2,50), @(0,5,0), @(5,0,0) )
$fail = @()
foreach ($c in $casos) {
  $r = Get-Percent -Part $c[0] -Total $c[1]
  if ($r -ne $c[2]) { $fail += "$($c[0])/$($c[1]) -> $r (esperado $($c[2]))" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
'@
W "$rf\S02-percentual\src\Get-Percent.ps1" @'
function Get-Percent {
    param([int]$Part, [int]$Total)
    if ($Total -eq 0) { return 0 }
    return [math]::Round(($Part / $Total * 100), 1)
}
'@

# ---------- S03 implementacao: mediana ----------
W "$tp\S03-mediana\TASK.md" @'
Implemente Get-Median em src\Get-Median.ps1. Recebe -Values (números) e retorna a mediana: para quantidade ímpar, o valor do meio; para quantidade par, a média dos dois valores do meio. Lista vazia retorna $null. Não altere a entrada. Não altere tests.ps1. Ao final, rode .\tests.ps1 e confirme que a saída é PASS.
'@
W "$tp\S03-mediana\src\Get-Median.ps1" @'
function Get-Median {
    param([double[]]$Values)
    throw "nao implementado"
}
'@
W "$tp\S03-mediana\tests.ps1" @'
. "$PSScriptRoot\src\Get-Median.ps1"
$casos = @( @(@(3,1,2), 2), @(@(4,1,3,2), 2.5), @(@(7), 7), @(@(5,5,1,9), 5) )
$fail = @()
foreach ($c in $casos) {
  $r = Get-Median -Values $c[0]
  if ($r -ne $c[1]) { $fail += "[$($c[0] -join ',')] -> $r (esperado $($c[1]))" }
}
$vazio = Get-Median -Values @()
if ($null -ne $vazio) { $fail += "lista vazia deveria retornar null" }
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
'@
W "$rf\S03-mediana\src\Get-Median.ps1" @'
function Get-Median {
    param([double[]]$Values)
    if ($null -eq $Values -or $Values.Count -eq 0) { return $null }
    $s = @($Values | Sort-Object)
    $n = $s.Count
    $h = [int][math]::Floor($n / 2)
    if ($n % 2 -eq 1) { return $s[$h] }
    return ($s[$h - 1] + $s[$h]) / 2
}
'@

# ---------- S04 implementacao: algarismos romanos ----------
W "$tp\S04-romano\TASK.md" @'
Implemente Get-RomanNumeral em src\Get-RomanNumeral.ps1. Recebe -Number (inteiro de 1 a 3999) e retorna o número em algarismos romanos (ex.: 1994 -> MCMXCIV). Fora desse intervalo, a função deve lançar erro. Não altere tests.ps1. Ao final, rode .\tests.ps1 e confirme que a saída é PASS.
'@
W "$tp\S04-romano\src\Get-RomanNumeral.ps1" @'
function Get-RomanNumeral {
    param([int]$Number)
    throw "nao implementado"
}
'@
W "$tp\S04-romano\tests.ps1" @'
. "$PSScriptRoot\src\Get-RomanNumeral.ps1"
$casos = @( @(1,'I'), @(4,'IV'), @(9,'IX'), @(14,'XIV'), @(1994,'MCMXCIV'), @(3999,'MMMCMXCIX') )
$fail = @()
foreach ($c in $casos) {
  $r = Get-RomanNumeral -Number $c[0]
  if ($r -ne $c[1]) { $fail += "$($c[0]) -> '$r' (esperado '$($c[1])')" }
}
foreach ($n in 0, 4000) {
  $lancou = $false
  try { Get-RomanNumeral -Number $n | Out-Null } catch { $lancou = $true }
  if (-not $lancou) { $fail += "$n deveria lancar erro" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
'@
W "$rf\S04-romano\src\Get-RomanNumeral.ps1" @'
function Get-RomanNumeral {
    param([int]$Number)
    if ($Number -lt 1 -or $Number -gt 3999) { throw "fora do intervalo 1-3999" }
    $tab = @(
        @(1000,'M'), @(900,'CM'), @(500,'D'), @(400,'CD'), @(100,'C'), @(90,'XC'),
        @(50,'L'), @(40,'XL'), @(10,'X'), @(9,'IX'), @(5,'V'), @(4,'IV'), @(1,'I')
    )
    $out = ''
    foreach ($p in $tab) {
        while ($Number -ge $p[0]) { $out += $p[1]; $Number -= $p[0] }
    }
    return $out
}
'@

# ---------- S05 implementacao: slug ----------
W "$tp\S05-slug\TASK.md" @'
Implemente New-Slug em src\New-Slug.ps1. Recebe -Text e retorna um slug: letras minúsculas a-z e dígitos 0-9 são mantidos; qualquer sequência de outros caracteres vira um único '-'; hífens no início e no fim são removidos. Exemplos: 'Teste   de  Slug' -> 'teste-de-slug'; '!!!' -> ''. Não altere tests.ps1. Ao final, rode .\tests.ps1 e confirme que a saída é PASS.
'@
W "$tp\S05-slug\src\New-Slug.ps1" @'
function New-Slug {
    param([string]$Text)
    throw "nao implementado"
}
'@
W "$tp\S05-slug\tests.ps1" @'
. "$PSScriptRoot\src\New-Slug.ps1"
$casos = @(
  @('Ola Mundo!', 'ola-mundo'), @('  Teste   de  Slug  ', 'teste-de-slug'),
  @('A--B__C', 'a-b-c'), @('123 abc', '123-abc'), @('!!!', '')
)
$fail = @()
foreach ($c in $casos) {
  $r = New-Slug -Text $c[0]
  if ($r -ne $c[1]) { $fail += "'$($c[0])' -> '$r' (esperado '$($c[1])')" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
'@
W "$rf\S05-slug\src\New-Slug.ps1" @'
function New-Slug {
    param([string]$Text)
    $s = $Text.ToLowerInvariant() -replace '[^a-z0-9]+', '-'
    return $s.Trim('-')
}
'@

# ---------- S06 bug: contagem de palavras ----------
W "$tp\S06-contagem\TASK.md" @'
Corrija src\Get-WordCount.ps1. Get-WordCount -Text deve contar palavras, onde palavra é uma sequência de letras (A-Z, a-z) ou dígitos (0-9). Sequências só de pontuação ou símbolos não contam. Exemplos: 'Ola, mundo!!' -> 2; '-- --' -> 0; 'a-b c' -> 3. Não altere tests.ps1. Ao final, rode .\tests.ps1 e confirme que a saída é PASS.
'@
W "$tp\S06-contagem\src\Get-WordCount.ps1" @'
function Get-WordCount {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return 0 }
    return ($Text -split '\s+' | Where-Object { $_ -ne '' }).Count
}
'@
W "$tp\S06-contagem\tests.ps1" @'
. "$PSScriptRoot\src\Get-WordCount.ps1"
$casos = @( @('Ola, mundo!!', 2), @('-- --', 0), @('a-b c', 3), @('', 0), @('123 abc.', 2) )
$fail = @()
foreach ($c in $casos) {
  $r = Get-WordCount -Text $c[0]
  if ($r -ne $c[1]) { $fail += "'$($c[0])' -> $r (esperado $($c[1]))" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
'@
W "$rf\S06-contagem\src\Get-WordCount.ps1" @'
function Get-WordCount {
    param([string]$Text)
    return ([regex]::Matches($Text, '[A-Za-z0-9]+')).Count
}
'@

# ---------- S07 bug: uniao de intervalos ----------
W "$tp\S07-intervalos\TASK.md" @'
Corrija src\Merge-Ranges.ps1. Merge-Ranges -Ranges recebe intervalos semiabertos [início, fim) como arrays @(início, fim) e deve uni-los, retornando a lista ordenada sem sobreposições. Intervalos que se encostam (fim de um igual ao início do outro) também devem ser unidos. Exemplo: @(1,3),@(3,5) -> 1-5. Não altere tests.ps1. Ao final, rode .\tests.ps1 e confirme que a saída é PASS.
'@
W "$tp\S07-intervalos\src\Merge-Ranges.ps1" @'
function Merge-Ranges {
    param([object[]]$Ranges)
    $sorted = @($Ranges | Sort-Object { $_[0] })
    $out = @()
    foreach ($r in $sorted) {
        if ($out.Count -gt 0 -and $r[0] -lt $out[-1][1]) {
            if ($r[1] -gt $out[-1][1]) { $out[-1][1] = $r[1] }
        } else {
            $out += ,@($r[0], $r[1])
        }
    }
    return ,$out
}
'@
W "$tp\S07-intervalos\tests.ps1" @'
. "$PSScriptRoot\src\Merge-Ranges.ps1"
$casos = @(
  @{ In = @(@(1,3),@(3,5)); Out = '1-5' },
  @{ In = @(@(1,2),@(4,6)); Out = '1-2,4-6' },
  @{ In = @(@(5,7),@(1,3),@(2,6)); Out = '1-7' },
  @{ In = @(); Out = '' }
)
$fail = @()
foreach ($c in $casos) {
  $r = @(Merge-Ranges -Ranges $c.In) | ForEach-Object { "$($_[0])-$($_[1])" }
  $txt = ($r -join ',')
  if ($txt -ne $c.Out) { $fail += "'$txt' (esperado '$($c.Out)')" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
'@
W "$rf\S07-intervalos\src\Merge-Ranges.ps1" @'
function Merge-Ranges {
    param([object[]]$Ranges)
    $sorted = @($Ranges | Sort-Object { $_[0] })
    $out = @()
    foreach ($r in $sorted) {
        if ($out.Count -gt 0 -and $r[0] -le $out[-1][1]) {
            if ($r[1] -gt $out[-1][1]) { $out[-1][1] = $r[1] }
        } else {
            $out += ,@($r[0], $r[1])
        }
    }
    return ,$out
}
'@

# ---------- S08 bug: leitura de configuracao ----------
W "$tp\S08-config\TASK.md" @'
Corrija src\Read-KeyValue.ps1. Read-KeyValue -Text lê um texto no formato chave=valor, uma por linha, e retorna uma hashtable. Regras: linhas vazias e linhas que começam com '#' (depois de espaços) são ignoradas; o separador é o primeiro '='; o valor inclui tudo que vem depois dele, inclusive '=' e '#', e é aparado nas pontas. Não altere tests.ps1. Ao final, rode .\tests.ps1 e confirme que a saída é PASS.
'@
W "$tp\S08-config\src\Read-KeyValue.ps1" @'
function Read-KeyValue {
    param([string]$Text)
    $h = @{}
    foreach ($line in ($Text -split "`n")) {
        $l = $line.Split('#')[0].Trim()
        if ($l -eq '') { continue }
        $parts = $l.Split('=')
        $h[$parts[0].Trim()] = $parts[1].Trim()
    }
    return $h
}
'@
W "$tp\S08-config\tests.ps1" @'
. "$PSScriptRoot\src\Read-KeyValue.ps1"
$texto = "# comentario`nnome = app`nurl=http://x.com/a?b=1#frag`n`n  porta=8080  # nao e comentario"
$h = Read-KeyValue -Text $texto
$fail = @()
if ($h['nome'] -ne 'app') { $fail += "nome -> '$($h['nome'])'" }
if ($h['url'] -ne 'http://x.com/a?b=1#frag') { $fail += "url -> '$($h['url'])'" }
if ($h['porta'] -ne '8080  # nao e comentario') { $fail += "porta -> '$($h['porta'])'" }
if ($h.Count -ne 3) { $fail += "numero de chaves: $($h.Count) (esperado 3)" }
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
'@
W "$rf\S08-config\src\Read-KeyValue.ps1" @'
function Read-KeyValue {
    param([string]$Text)
    $h = @{}
    foreach ($line in ($Text -split "`r?`n")) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $i = $t.IndexOf('=')
        if ($i -lt 1) { continue }
        $h[$t.Substring(0, $i).Trim()] = $t.Substring($i + 1).Trim()
    }
    return $h
}
'@

Write-Host "Bloco A criado: T1-T3 (refs) e S01-S08." -ForegroundColor Green
