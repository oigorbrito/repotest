$root = "D:\projetos\harness-benchmark\pilot"
$real = Join-Path $root "real"
New-Item -ItemType Directory -Force -Path $real | Out-Null
if (-not (Test-Path (Join-Path $real "source"))) {
  git clone --depth 1 https://github.com/oigorbrito/EvCore (Join-Path $real "source")
}
$tasks = Join-Path $real "source\benchmarks\harness-comparison\tasks.json"
if (Test-Path $tasks) { "OK: tarefas em $tasks" } else { throw "tasks.json nao encontrado" }
