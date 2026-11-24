# Resultados — benchmark comparativo de fencing (execução real)

Todos os números vêm de `raw/` e foram agregados em `results.json` por `bench/analyze.py`.
Cada repetição usa serviços reais (Redis, ZooKeeper, etcd, PostgreSQL) e processos A/B separados
(suspensão com SIGSTOP, falha com SIGKILL). Nada foi commitado; `mh` e `rusky` permanecem nos commits originais.

## 1. Classificação

| # | Implementação | Origem do código | Classificação | Motivo em uma frase |
|---|---|---|---|---|
| 1 | StatePact Redis | `statepact==0.1.2` (PyPI, sem modificação) | **APROVADA COM LIMITAÇÕES** | Nenhuma violação nos cenários obrigatórios; escritor expirado sem sucessor é aceito; janela de replicação assíncrona não excluída. |
| 2 | ZooKeeper + Redis Lua | reimplementado a partir da especificação | **REPROVADA** | Escrita obsoleta aceita 100/100 numa janela entre a concessão no ZooKeeper e o registro do fence no Redis. |
| 3 | etcd + PostgreSQL | reimplementado a partir da especificação | **APROVADA COM LIMITAÇÕES** | Concessão serializada com o commit (0/100 violações); escritor expirado sem sucessor é aceito; failover do PostgreSQL não testado. |
| 4 | StatePact PostgreSQL | `statepact==0.1.2` (PyPI, sem modificação) | **REPROVADA** | No caminho `backend.acquire_lease()`, a escrita obsoleta é aceita depois que a concessão do sucessor já foi commitada (100/100). |

Ninguém ficou como **APROVADA** sem limitações. Nenhum candidato ficou **NÃO TESTADO** nos cenários obrigatórios.
Os itens NÃO TESTADO estão listados na seção 8.

**Recomendação para `mh`: nenhuma alteração nesta etapa.** Motivo na seção 7.

## 2. Versões, commit SHA, configuração e repetições

| Item | Valor |
|---|---|
| Host | Ubuntu 24.04.5, kernel 6.18.44, 4 vCPU, 16 GB |
| Redis | 7.0.15 (apt), AOF `appendfsync always`, réplica por `REPLICAOF` |
| ZooKeeper | 3.9.1 (zookeeperd, Ubuntu), standalone, `tickTime=500`, cliente kazoo 2.11.0 |
| etcd | 3.4.30 (apt), nó único |
| PostgreSQL | 16.15 (apt), `fsync=on`, `synchronous_commit=on`; duas instâncias (uma por candidato) |
| StatePact | 0.1.2 — SHA-256 sdist `c36f00e5…`, wheel `1794ac8d…`. Não há commit git para este pacote; a identidade é o artefato publicado |
| Python / drivers | 3.13.18; redis-py 8.1.0; psycopg 3.3.9; asyncpg 0.32.0 |
| Código do harness | SHA-256 de cada arquivo em `results.json › provenance.benchmark_files_sha256` (sem commit, conforme pedido) |
| `mh` | HEAD `188c8884…`, árvore limpa antes e depois |
| `rusky` | HEAD `d4ba8989…`, árvore limpa |
| Lease TTL | 2 s em todos os candidatos (etcd exige TTL inteira) |
| Repetições | **100 por cenário por implementação**, todas válidas (0 invalidadas), exceto onde indicado |
| Latência | 1000 ciclos acquire→commit→release por implementação, um cliente, host ocioso |

## 3. Cenários obrigatórios (N = 100 por implementação)

| Cenário | 1 StatePact Redis | 2 ZK + Redis Lua | 3 etcd + PG | 4 StatePact PG | Critério |
|---|---|---|---|---|---|
| **D2** escritor suspenso durante a gravação | obsoleta aceita **0** · rejeição indevida **0** · monotonicidade **0** | 0 · 0 · 0 | 0 · 0 · 0 | 0 · 0 · 0 | obsoleta rejeitada, válida aceita, estado final = B |
| **C4** retomado após adoção e liberação | 0 · 0 · 0 | 0 · 0 · 0 | 0 · 0 · 0 | 0 · 0 · 0 | obsoleta rejeitada, estado final = B |
| **Expiração, antes do sucessor** | **100 aceitas** | **100 aceitas** | **100 aceitas** | **100 aceitas** | ver limitação L1 |
| **Expiração, depois do sucessor** | 0 aceitas | 0 aceitas | 0 aceitas | 0 aceitas | obsoleta rejeitada |
| **Concorrência** (aquisição ∥ commit) | estado final obsoleto **0** | 0 | 0 | 0 | estado final ≠ escrita obsoleta |
| **Reinício** do coordenador (kill -9) | monotonicidade violada **0**; perda **0** | 0 ; 0 | 0 ; 0 | 0 ; 0 | token novo > antigo; dado durável |
| **Falha** do coordenador durante o commit | duplicações **0**; perdas **0**; retry OK 100 | 0 ; 0 ; 100 | 0 ; 0 ; 100 | 0 ; 0 ; 100 | efeito aplicado exatamente 1 vez |
| **Controle negativo** (sem validação) | obsoleta **detectada 100/100** | 100/100 | 100/100 | 100/100 | o benchmark precisa detectar |
| **Failover** do Redis (só Redis) | regressão de token **0**; obsoleta aceita **0**; N = 100 | 0 ; 0 ; N = 99 válidas¹ | não aplicável² | não aplicável² | token monotônico após promoção |

¹ Uma repetição sem sucessor (o B não obteve lease em 25 s) foi excluída; detalhes na seção 9.
² Sem topologia de réplica para PostgreSQL nesta execução (ver seção 8).

**Leitura.** A propriedade de fencing em si (rejeitar o escritor obsoleto depois que o sucessor existe, sem duplicação nem perda)
se mantém nos quatro candidatos nos cenários de sequência. Os diferenciadores aparecem em duas situações:
a corrida de aquisição com commit (seção 4) e o escritor expirado sem sucessor (limitação L1).

## 4. Corridas determinísticas (N = 100 cada, zero inválidas)

Uma corrida é forçada: o commit de A é segurado no meio do caminho por um lock de linha segurado por um
auxiliar, enquanto B adquire a lease. Isso responde às perguntas feitas no pedido.

| Variante | A bloqueado no commit | B concluído antes do commit de A | Escrita obsoleta aceita depois da concessão |
|---|---|---|---|
| **StatePact PG, `backend.acquire_lease()` direto** | 100/100 | **100/100** | **100/100** |
| StatePact PG, `TransactionManager.lease()` (API pública) | 100/100 | 0/100 (B fica atrás de A) | 0/100 |
| etcd + PG v2 (candidato) | 100/100 | 0/100 (B fica atrás de A) | 0/100 |
| etcd + PG v1 (ablação: concessão fora do lock) | 100/100 | 100/100 | **100/100** (janela) |
| ZK + Redis Lua (janela ZK→Redis) | — | 100/100 | **100/100** (janela) |
| Redis (StatePact) | — | — | não se aplica: concessão e fence são um único `EVAL` atômico |

**Pergunta do pedido: "a leitura do token pode observar o token antigo enquanto uma aquisição concorrente já está ocorrendo?"**
**Sim.** O `_commit_locked()` do StatePact PostgreSQL lê `statepact_leases.token` com um `SELECT` comum, sem `FOR UPDATE`
e sem o lock de lease. Sob READ COMMITTED, esse `SELECT` enxerga o token antigo enquanto `acquire_lease()` mantém a
linha com o token novo ainda não commitado. A escrita antiga é aceita e persiste depois que a concessão do sucessor já foi commitada.

**Por que o caminho público não tem a corrida.** `TransactionManager.lease()` chama `backend.ensure_resource()` antes de
`acquire_lease()`. Essa função pega o mesmo lock de commit (`_COMMIT_LOCK`). Então a aquisição fica serializada com o commit,
mas por um efeito colateral de `ensure_resource()`, não por uma garantia de fencing. Quem chama `backend.acquire_lease()`
diretamente — a operação nomeada no pedido — não tem essa proteção.

**Por que o etcd + PG v2 passa.** A concessão no etcd acontece dentro da transação que segura o `FOR UPDATE` da linha de fence,
o mesmo lock que o commit usa. A ablação v1 (concessão fora do lock) falha 100/100, o que prova que o teste detecta a janela.

**ZooKeeper + Redis Lua.** O token vem do ZooKeeper, e a validação está dentro do `EVAL`. O Lua não enxerga o ZooKeeper.
Entre a concessão no ZooKeeper e o registro do fence no Redis existe uma janela em que o sucessor já tem a lease, mas o storage
ainda não a conhece. Isso é consequência do desenho de duas stores, e não de um detalhe de implementação.

**Efeito no estado final.** Nas corridas e no cenário de concorrência, a escrita obsoleta aceita na janela foi sempre
sobrescrita pela escrita do sucessor, e nenhuma escrita obsoleta ficou como estado final (CONC: 0/100 nos quatro).
A falha é do critério de **rejeição**, não de perda de dados observada.

## 5. Latência (1000 ciclos por implementação, um cliente, round trip medido no driver, ms)

| Operação | p50 | p95 | p99 |
|---|---|---|---|
| acquire — StatePact Redis | 0,76 | 1,22 | 1,48 |
| acquire — ZK + Redis Lua | 2,32 | 3,17 | 4,65 |
| acquire — etcd + PG | 3,49 | 4,66 | 5,55 |
| acquire — StatePact PG | 1,52 | 2,27 | 2,86 |
| commit — StatePact Redis | 1,35 | 2,07 | 2,42 |
| commit — ZK + Redis Lua | 0,60 | 0,87 | 1,49 |
| commit — etcd + PG | 1,03 | 1,42 | 1,76 |
| commit — StatePact PG | 2,89 | 4,24 | 5,35 |
| release — StatePact Redis | 0,54 | 0,83 | 1,12 |
| release — ZK + Redis Lua | 0,88 | 1,24 | 1,73 |
| release — etcd + PG | 1,76 | 2,30 | 3,86 |
| release — StatePact PG | 0,65 | 1,04 | 2,71 |

Zero falhas e zero commits não-OK nos 4000 ciclos.

## 6. Disponibilidade e recuperação

**Falha do coordenador durante o commit** (`kill -9`, o cliente reenvia com a mesma chave de idempotência). Indisponibilidade =
do kill até a primeira leitura bem-sucedida após o restart, em ms (p50 / p95 / p99):

| Candidato | p50 | p95 | p99 | Observação |
|---|---|---|---|---|
| StatePact Redis | 259 | 263 | 282 | 30/100 primeiras tentativas falharam por infraestrutura; 100/100 aplicadas exatamente 1 vez |
| ZK + Redis Lua | 158 | **4108** | 5008 | 9 repetições com cauda de 3,5–5 s; não reproduzidas isoladamente (ver seção 9) |
| etcd + PG | 260 | 263 | 278 | 2/100 primeiras tentativas falharam; 100/100 aplicadas exatamente 1 vez |
| StatePact PG | 161 | 266 | 276 | 91/100 primeiras tentativas falharam (o commit estava em voo); 100/100 aplicadas 1 vez |

**Reinício do coordenador de lease** (kill -9 + start, mediana): StatePact Redis 157 ms; ZK + Redis 558 ms (reinicia ZooKeeper e
Redis do commit); etcd + PG 1722 ms (reinicia etcd e o PostgreSQL do commit); StatePact PG 152 ms. Em todos, token monotônico e
valor anterior preservado (0 violações, 0 perdas em 100 repetições).

**Nota.** Os serviços rodam como instância única. A disponibilidade medida é a de um nó, sem réplica HA
(nenhum candidato foi testado em cluster de produção).

## 7. Custo operacional e dependências

| Candidato | Componentes que precisam ficar no ar | RSS em repouso (nesta máquina) | Observação operacional |
|---|---|---|---|
| StatePact Redis | 1 Redis (+1 réplica para failover) | 32 MB (2 processos) | um único sistema guarda lease, fence e dados; Redis ≥ 7 com Lua |
| ZK + Redis Lua | ZooKeeper (ensemble de ≥ 3 em produção) + 1 Redis (+1 réplica) | 204 MB (ZooKeeper 176 MB) | dois sistemas com estados separados; JVM; dois modos de falha |
| etcd + PG | etcd (≥ 3 em produção) + PostgreSQL | 81 MB (etcd 47, PG 33) | dois sistemas; a serialização exige o PG disponível para toda aquisição |
| StatePact PG | 1 PostgreSQL | 33 MB (postmaster) | um único sistema; depende de `pg_advisory_xact_lock` e de `asyncpg` |

Os valores de RSS são do processo principal de cada serviço, em repouso, no mesmo host. Não medem ensembles.

## 8. Limitações e itens NÃO TESTADOS

**Limitações que valem para os quatro candidatos**

- **L1. Escritor expirado sem sucessor é aceito (100/100 nos quatro).** Todos validam só o token contra o high-water mark.
  Nenhum verifica, no commit, se a lease ainda está válida. Um escritor cuja lease expirou pode gravar enquanto ninguém mais
  tiver adquirido a lease. Para o protocolo pedido isso só vira violação quando há sucessor, mas é uma exposição real.
  A correção é checar a validade da lease dentro da mesma transação ou script do commit. Não implementei isso.

**Limitações específicas**

- **StatePact Redis.** A replicação é assíncrona. Com a réplica sincronizada e um kill imediato após a aquisição, 100 repetições
  não mostraram perda (0 regressões). Isso não exclui a perda: a janela existe em teoria e depende do atraso de replicação
  e de quando o master cai. Não testei `WAIT`, replicação síncrona nem Sentinel.
- **etcd + PG v2.** A aquisição fica serializada com o commit, mas o acquire mantém a transação do PostgreSQL aberta durante a
  chamada ao etcd. Isso custa latência de aquisição (p50 3,5 ms, o mais alto dos quatro).
- **ZK + Redis Lua.** A janela entre a concessão e o registro não é eliminável dentro do desenho especificado.

**NÃO TESTADO**

- Failover do PostgreSQL (não há réplica streaming nesta execução). Isso afeta as classificações 3 e 4 nesse eixo.
- ZooKeeper e etcd em ensemble/cluster multi-nó, com perda de quórum.
- Partições de rede. As falhas injetadas são SIGSTOP (suspensão) e SIGKILL (crash), não partição.
- Desvio de relógio entre processos (o TTL usa o relógio do host compartilhado).
- Throughput sob concorrência: a latência é de um cliente, em host ocioso.
- Versões de StatePact diferentes de 0.1.2.
- ZooKeeper e etcd "de receita" (ex.: locks do Curator). Os candidatos 2 e 3 são implementações da especificação deste pedido.

## 9. Registro de problemas encontrados e corrigidos durante a execução

Os resultados finais vêm sempre da versão corrigida. Os problemas abaixo afetaram execuções anteriores e foram tratados como:

1. **Grupo de processos errado no gerenciador de serviços.** O PGID era lido logo após o `Popen`, antes de o filho executar `setsid()`,
   e podia apontar para o grupo do pai. Um `kill` podia derrubar serviços vizinhos. Corrigido (`pgid = pid`); todos os serviços
   foram reconstruídos do zero.
2. **PostgreSQL não reiniciava após `kill -9`.** `postmaster.pid` e o lock do socket ficavam para trás, e o PID de `pid_max = 32768`
   era reaproveitado. Corrigido: remover os arquivos obsoletos quando a porta está fechada.
3. **Transação aberta no etcd + PG.** Conexão em modo não-autocommit deixava um `FOR UPDATE` aberto, travando o processo seguinte.
   Corrigido com `autocommit=True` e `BEGIN`/`COMMIT` explícitos.
4. **Sessão kazoo expirada em laço.** Após SIGSTOP, o cliente ZooKeeper não criava nova sessão. Corrigido recriando o cliente.
5. **Setup não verificado.** Uma falha silenciosa de setup corrompia a repetição seguinte. Corrigido com retry e verificação.
6. **Failover com réplica não sincronizada (artefato do harness).** A réplica reiniciada era promovida antes de terminar o resync.
   O primeiro run do StatePact Redis mostrou 59 regressões de token em 60 repetições; isso era artefato, não comportamento do Redis.
   Corrigido esperando a réplica alcançar o master antes de cada repetição. O run anterior foi descartado (o arquivo foi sobrescrito;
   o estado observado ao interromper está registrado aqui) e refeito.
7. **etcd + PG v1 deixava a concessão fora do lock.** Isso não cumpria o requisito "bloqueio que coordene a aquisição". Substituído
   pela v2 (serializada); a v1 foi mantida como ablação e falha 100/100, o que valida o teste.
8. **Corrida do StatePact PG inicialmente mal desenhada.** A espera síncrona pelo B travava o harness. Refeita com o B em modo
   não-bloqueante, o que levou à descoberta de `ensure_resource()` e dos dois caminhos (seção 4).
9. **Failover ZK: uma repetição sem sucessor.** Na primeira repetição do rerun, o B não obteve lease em 25 s (`held`), e não havia
   nós de lock residuais depois. A causa não foi identificada. Essa repetição não mede a sucessão, então foi excluída das taxas
   e registrada em `results.json`. É a única exclusão do conjunto.
10. **ZK FAIL: cauda de 3,5–5 s em 9 repetições.** O restart isolado do Redis leva 0,16 s (kill 0,05 s + start 0,11 s). A cauda
    apareceu durante a execução paralela das quatro trilhas. Hipótese: contenção de CPU, não confirmada. Reporto a cauda como medida.
11. **`analyze.py`.** O carregador de `perf.json` lia o JSON como JSONL. Corrigido e rodado de novo.

## 10. Recomendação e gate para `mh`

**Não recomendo nenhuma alteração em `mh` nesta etapa.** Três motivos, por evidência:

1. Nenhum candidato está APROVADO sem limitações. Os dois APROVADOS COM LIMITAÇÕES (StatePact Redis e etcd + PG v2)
   exigem a correção de L1 antes de qualquer adoção.
2. O ganho sobre o comportamento atual de `mh` não foi medido. O mecanismo atual (`gateway/control_store.py`, lease com
   CAS por `fence`) não fez parte deste benchmark, então não há como afirmar ganho.
3. Pela leitura do código (não medida), `mh` ainda não aplica o fence no caminho do turno: o próprio `lease_acquire`
   documenta "fencing is not yet wired into the turn path (deferred)", e `app.py` marca o modo de enforcement como
   "flip to enforce only after observe shows it's safe". Além disso, a checagem de checkpoint é um `lease_still_held` seguido
   de escrita, que é o padrão de leitura prévia que o pedido rejeita.

Idempotência e recuperação de `mh` não foram tocadas: nenhum arquivo de `mh` foi alterado, e os testes de idempotência deste
benchmark (FAIL: 0 duplicações em 400 repetições) são evidência separada, sem efeito sobre `mh`.

**Próximo passo sugerido:** adicionar o lease atual de `mh` como quinto candidato, com o mesmo protocolo, e implementar a
checagem de validade da lease no commit (correção de L1) para os candidatos aprovados com limitações. Só então comparar com o
comportamento atual e decidir.

## 11. Arquivos

- `results.json` — métricas, proveniência, veredito e justificativa por implementação, e o gate.
- `raw/<impl>/*.jsonl` — uma linha por repetição, com tokens, status de cada commit, tempos e indicadores.
- `raw/<impl>/race-*.jsonl`, `raw/<impl>/FAILOVER.jsonl`, `raw/<impl>/perf.json` — corridas, failover e latência.
- `raw/logs/` — logs de execução de cada trilha e logs dos serviços.
- `raw/superseded/` — dados de execuções com defeito de harness, guardados só para transparência.
