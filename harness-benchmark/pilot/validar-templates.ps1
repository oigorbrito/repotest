$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$tasks = Get-ChildItem (Join-Path $root "templates") -Directory | Where-Object { $_.Name -ne "ref" } | Sort-Object Name
foreach ($t in $tasks) {
  $ref = Join-Path $root "templates\ref\$($t.Name)"
  if (-not (Test-Path $ref)) { "{0,-22} sem referencia" -f $t.Name; continue }
  $tmp = Join-Path $root "validacao\$($t.Name)"
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  Copy-Item -Recurse -Force (Join-Path $t.FullName "*") $tmp
  $stub = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $tmp "tests.ps1") 2>&1 | Out-String
  $stubOk = ($LASTEXITCODE -eq 0)
  Copy-Item -Recurse -Force (Join-Path $ref "*") $tmp
  $refOut = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $tmp "tests.ps1") 2>&1 | Out-String
  $refOk = ($LASTEXITCODE -eq 0)
  $status = if ((-not $stubOk) -and $refOk) { "OK" } else { "REVISAR" }
  "{0,-22} stub_passa={1,-5} ref_passa={2,-5} {3}" -f $t.Name, $stubOk, $refOk, $status
  if ($status -ne "OK") { "   stub: " + $stub.Trim(); "   ref:  " + $refOut.Trim() }
}
