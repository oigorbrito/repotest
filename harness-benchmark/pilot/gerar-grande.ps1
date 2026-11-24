$root = "D:\projetos\harness-benchmark\pilot"
$base = Join-Path $root "big"
$fx = Join-Path $base "fixture\services"
Remove-Item (Join-Path $base "fixture") -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $fx | Out-Null

$N = 300
$pad = ("lorem ipsum dolor sit amet consectetur " * 90)
$somaLimit = 0; $ativos = 0; $maxLimit = -1; $maxId = ''; $canary = 0; $owner217 = ''; $team0 = 0

for ($i = 1; $i -le $N; $i++) {
  $id = "svc-{0:000}" -f $i
  $status = if ($i % 3 -eq 0) { 'inactive' } else { 'active' }
  $limit = ($i * 37) % 1000 + 1
  $owner = "team-" + ($i % 7)
  $notes = $pad
  if ($i % 37 -eq 0) { $notes = "canary deployment window. " + $notes; $canary++ }
  $json = @"
{
  "id": "$id",
  "owner": "$owner",
  "status": "$status",
  "limit": $limit,
  "notes": "$notes"
}
"@
  Set-Content -Encoding utf8 (Join-Path $fx "$id.json") -Value $json

  if ($status -eq 'active') { $somaLimit += $limit; $ativos++ }
  if ($limit -gt $maxLimit) { $maxLimit = $limit; $maxId = $id }
  if ($i -eq 217) { $owner217 = $owner }
  if ($owner -eq 'team-0') { $team0++ }
}

$tarefas = @"
{
  "schema_version": 2,
  "tasks": [
    {
      "id": "big-sum",
      "category": "cross-file-large-aggregate",
      "mode": "read",
      "prompt": "Sum the limit field of every services/*.json file whose status is active. End with exactly: total_limit=<n>.",
      "expected": "total_limit=$somaLimit"
    },
    {
      "id": "big-max",
      "category": "cross-file-large-search",
      "mode": "read",
      "prompt": "Find the service with the highest limit across services/*.json. If two services tie, choose the lower id. End with exactly: service=<id>; limit=<n>.",
      "expected": "service=$maxId; limit=$maxLimit"
    },
    {
      "id": "big-owner",
      "category": "cross-file-large-lookup",
      "mode": "read",
      "prompt": "Find the owner of service svc-217, then count how many services have that same owner. End with exactly: owner=<name>; count=<n>.",
      "expected": "owner=$owner217; count=$team0"
    },
    {
      "id": "big-canary",
      "category": "cross-file-large-count",
      "mode": "read",
      "prompt": "Count the services whose notes field contains the word canary. End with exactly: canary=<n>.",
      "expected": "canary=$canary"
    },
    {
      "id": "big-edit",
      "category": "cross-file-large-edit",
      "mode": "edit",
      "prompt": "Set the limit of service svc-042 to 999 in services/svc-042.json. Change nothing else. End with exactly: changed=services/svc-042.json; limit=999.",
      "expected": "changed=services/svc-042.json; limit=999",
      "allowed_changes": ["services/svc-042.json"],
      "checks": [
        {
          "path": "services/svc-042.json",
          "contains": ["\"limit\": 999"],
          "not_contains": ["\"limit\": 555"]
        }
      ]
    }
  ]
}
"@
Set-Content -Encoding utf8 (Join-Path $base "tasks.json") -Value $tarefas

"Gerados $N arquivos em $fx"
"Esperados: total_limit=$somaLimit | service=$maxId; limit=$maxLimit | owner=$owner217; count=$team0 | canary=$canary"
