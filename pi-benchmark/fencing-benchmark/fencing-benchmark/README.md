# Benchmark de fencing — execução real

Compara quatro implementações de fencing contra processos **reais** de Redis, ZooKeeper, etcd e PostgreSQL,
no protocolo do pedido: escritor antigo suspenso (D2), retomado após adoção (C4), aquisição e commit concorrentes,
reinício do coordenador (monotonicidade), falha do coordenador durante a operação (idempotência e disponibilidade),
expiração antes e depois do sucessor, controle negativo, failover do Redis e corridas determinísticas.

- **Resultados e classificação:** [RESULTS.md](RESULTS.md)
- **Métricas estruturadas e proveniência:** `results.json`
- **Dados brutos (uma linha por repetição):** `raw/`

Nada em `mh/`, FineCode ou FineCore foi alterado. Nenhum commit, push ou merge foi feito.

## Candidatos

| Nome nos resultados | Origem do código | Estado |
|---|---|---|
| 1. StatePact Redis | `statepact==0.1.2` (PyPI, sem modificação), `RedisBackend` | testado |
| 2. ZooKeeper + Redis Lua | **reimplementado a partir da especificação** (`bench/backends.py::ZkRedisBackend`) | testado |
| 3. etcd + PostgreSQL | **reimplementado a partir da especificação** (`bench/backends.py::EtcdPgBackend`, variante v2) | testado |
| 4. StatePact PostgreSQL | `statepact==0.1.2` (PyPI, sem modificação), `PostgresBackend` | testado |
| ablação | etcd + PG v1: concessão fora do lock de fence | só corridas |

Os candidatos 2 e 3 não têm código de referência nos repositórios acessíveis (`mh`, `rusky`) nem no PyPI/npm.
Os resultados descrevem esses desenhos, não um produto específico.

## Requisitos (versões usadas)

- Ubuntu 24.04, 4 vCPU, 16 GB, `pid_max` 32768.
- apt: `redis-server` 7.0.15, `postgresql` 16.15, `etcd-server` 3.4.30, `zookeeperd` 3.9.1 (traz o Java).
- Python 3.13 com `statepact[postgres]==0.1.2` (asyncpg 0.32.0), `kazoo` 2.11.0, `redis` 8.1.0, `psycopg[binary]` 3.3.9.

Os SHA-256 dos artefatos do StatePact e de cada arquivo do benchmark estão em `results.json › provenance`.

## Reprodução

```bash
# 1. serviços do sistema (uma vez)
apt-get install -y redis-server postgresql etcd-server zookeeperd

# 2. ambiente Python (uma vez), dentro de fencing-benchmark/
python3 -m venv .venv
.venv/bin/pip install "statepact[postgres]==0.1.2" kazoo redis "psycopg[binary]"

# 3. serviços reais (idempotente)
scripts/start_services.sh

# 4. execução completa: 100 repetições por cenário, corridas, failover, 1000 ciclos de latência
REPS=100 PERF_OPS=1000 scripts/run_all.sh        # ~1h30 em 4 vCPU; logs em raw/logs/

# 5. resultados: results.json (gerado) e RESULTS.md (escrito a partir dele)
```

Verificação rápida de que todos os caminhos de código rodam: `REPS=2 PERF_OPS=20 scripts/run_all.sh` (~10 min).
Execução parcial:
`.venv/bin/python bench/harness.py --impl IMPL --phase scenarios|race|failover|perf --reps N --out raw [--only D2,C4]`
(IMPL: `statepact-redis`, `zk-redis-lua`, `etcd-pg`, `etcd-pg-v1`, `statepact-pg`).

Observação: o `run_all.sh` roda o `analyze.py` ao final e depois derruba os serviços. O veredito fica em
`bench/verdicts.json` e é mesclado ao `results.json` a cada análise.

## Estrutura

```
README.md             este arquivo
RESULTS.md            comparação, classificações, limitações, gate para mh
results.json          métricas, proveniência, veredito por implementação, gate
raw/<impl>/           uma linha JSON por repetição; race-*.jsonl; FAILOVER.jsonl; perf.json
raw/logs/             logs de cada trilha, logs dos serviços e dos workers
raw/statepact-src/    sdist e wheel do StatePact 0.1.2 testados, descompactados para inspeção
raw/superseded/       dados de execuções com defeito de harness (não usados nas métricas)
bench/                código do harness: backends.py, worker.py, proc.py, harness.py, analyze.py, verdicts.json
scripts/              svc.py (gerenciador dos serviços reais), start_services.sh, run_all.sh
patches/              adaptações necessárias para rodar os candidatos (nenhuma; ver patches/README.md)
work/                 diretórios de dados dos serviços e pidfiles (gerados; não são evidência)
```

`bench/` fica na raiz de propósito: os workers são criados a partir desses arquivos durante a execução.

## Como o experimento funciona

- **Processos.** A e B são processos separados (`bench/worker.py`) conversando com o driver por stdin/stdout.
  "Suspenso" = `SIGSTOP` enquanto A segura a lease; "retomado" = `SIGCONT`.
- **Falha do coordenador.** `SIGKILL` no grupo de processos inteiro do serviço (sem desligamento limpo). O restart reusa o
  mesmo diretório de dados. Redis com `appendonly yes` e `appendfsync always`; PostgreSQL com `fsync=on`.
- **TTL da lease = 2 s** em todos os candidatos. O escritor espera TTL + 0,8 s para garantir a expiração.
- **Chave de idempotência.** Todo commit do cenário FAIL carrega uma; o cliente reenvia com a mesma chave.
- **Recurso novo por repetição**, para que nenhum estado vaze entre repetições.
- **Controle negativo.** A mesma sequência, com `fenced=False` no commit do escritor antigo. Se o benchmark não detecta a
  escrita obsoleta nesse controle, a execução é inválida.
- **Repetições inválidas** (infraestrutura abortou) ficam no raw e são reportadas à parte; não entram nas taxas.

## Limitações do harness

- O TTL usa o relógio do host compartilhado; desvio de relógio entre processos não é modelado.
- Um nó por coordenador. Não há cluster Redis, ensemble ZooKeeper nem cluster etcd.
- O failover do Redis é feito com uma réplica promovida à mão (`REPLICAOF NO ONE`), sem Sentinel.
- Não há injeção de partição de rede: as falhas são SIGSTOP e SIGKILL.
- A latência é medida com um cliente em host ocioso. Não é teste de throughput.
