$root = 'D:\projetos\durability-benchmark\copies\FineCode'
$map = @{
 'node_modules\@earendil-works\chord'='packages\chord';
 'node_modules\@earendil-works\pi-agent-core'='packages\agent';
 'node_modules\@earendil-works\pi-ai'='packages\ai';
 'node_modules\@earendil-works\pi-codemode'='packages\codemode';
 'node_modules\@earendil-works\pi-durable'='packages\durable';
 'node_modules\@earendil-works\pi-env'='packages\env';
 'node_modules\@earendil-works\pi-evals'='packages\evals';
 'node_modules\@earendil-works\pi-mcp'='packages\mcp';
 'node_modules\@earendil-works\pi-telemetry'='packages\telemetry';
 'node_modules\@earendil-works\pi-tui'='packages\tui';
 'node_modules\finecode'='packages\coding-agent';
}
foreach ($k in $map.Keys) {
  $p = Join-Path $root $k
  if (Test-Path $p) { (Get-Item $p).Attributes = 'Directory' ; cmd /c "rmdir `"$p`"" 2>$null | Out-Null; if (Test-Path $p) { Remove-Item -Recurse -Force $p } }
  $t = Join-Path $root $map[$k]
  New-Item -ItemType Junction -Path $p -Target $t | Out-Null
  Write-Output "junction $k -> $($map[$k])"
}
