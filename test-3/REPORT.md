# Teste Comparativo 3 — Correção e validação das garantias de durabilidade

**Data:** 18–19/11/2026 · **Ambiente:** Windows, Node v26.10.0 (`node:sqlite`), Python 3.12.10 (SQLite 3.49.1), processos locais.
**Escopo:** `D:\projetos\durability-benchmark\test-3\`. Nenhum repositório original foi alterado (HEAD e `git status` idênticos antes e depois). Nenhum commit, branch ou push. Nenhuma API paga.

## Resumo

| Mecanismo | Veredito | Por quê |
|---|---|---|
| FineCode `runtime.memo()` — fence de propriedade no storage | **APROVADO COM LIMITAÇÕES** | Elimina a execução concorrente da mesma chave (E: 3 → 0 duplicatas, 10/10). Sem exactly-once; o padrão effect-first continua duplicando em takeover (G). |
| metaO OCC em `replace()` | **APROVADO COM LIMITAÇÕES** | Zero atualizações perdidas (era 31–45 por repetição). Exige que o chamador trate `MissionRevisionConflict`. |
| metaO fencing por token (append/replace/complete/bind) | **REPROVADO como garantia de sistema**; **APROVADO COM LIMITAÇÕES nos caminhos que apresentam token** | Worker obsoleto com token: rejeitado 10/10, nenhuma escrita (antes: aceito 3/4 em 10/10). Mas escritas sem token após a conclusão da execução continuam sem fence, e o operador atual ainda grava nesses caminhos. |

Os três patches estão em `patches/`, separados por mecanismo. Nenhum foi integrado aos projetos originais.

---

## Etapa 1 — Reconciliação com o Teste 2

Relido: `test-2/REPORT.md`, `test-2/results.json`, `memo-bench.ts`, `run_metao.py`, traces e snapshots.

- **Recomputação dos brutos do Teste 2:** 0 divergências entre `effects.log` e `finecode-results.json`. Os veredictos do metaO (`FAILED_SILENT_OVERWRITE` ×3, `fencing A publish accepted` ×3) conferem com `metao-results.json`.
- **Causa do FineCode confirmada no código:** `#gated` decide com `this.#live` (memória do processo, `scheduler.ts:2198`); o upsert de tarefa sobrescreve sem checar versão (`storage.ts:823–830`); `Task 7 is already terminal` vem de `transaction.ts:769`.
- **Causa do metaO confirmada:** `replace()` descarta `record.revision` (`sqlite_store.py`); `activate()` sobrescreve a posse (`ON CONFLICT … DO UPDATE`); `complete()` não recebe identidade; `reject_stale_worker` não é chamado por nenhum store.
- **Correção de um erro do Teste 2 no próprio benchmark:** o `snapshot` de WAL foi copiado corretamente só na 2ª versão (o `db.sqlite` sozinho não basta). Isso já estava corrigido no Teste 2.
- Não repeti auditorias já concluídas.

---

## Etapa 2 — Correções isoladas

Cópias de trabalho: `work/finecode` (corrigida), `work/finecode-baseline` (linha de base), `work/metao` (corrigida), `work/metao-baseline` (linha de base). Cada cópia tem repositório git descartável com commit `baseline`, usado para gerar os patches. As cópias do FineCode usam junções para o `node_modules` do original (somente leitura), e os pacotes de workspace apontam para a própria cópia (verificado pelo `import.meta.resolve`).

### A. FineCode `runtime.memo()` — fence de propriedade no storage

**Menor alteração que resolve a falha:** a falha está no storage, não no `memo`. O `memo` decide com memória do processo, e isso só é seguro se nenhuma outra instância escrever no mesmo banco. Então a correção garante exclusividade de escrita no próprio commit:

- `durable_metadata` ganha `owner_epoch` (migração v3, `ALTER TABLE … ADD COLUMN`).
- `SqliteStorage.open()` incrementa a época em transação própria e guarda a época obtida.
- `SqliteStorage.commit()` lê `owner_epoch` **na mesma transação** de escrita e lança `StaleStorageOwnerError` se não for a corrente. A transação faz rollback: nada é gravado.

```ts
// storage.ts — dentro da transação de commit, antes de qualquer escrita
if (Number(metadata.owner_epoch) !== this.ownerEpoch) {
  throw new StaleStorageOwnerError(this.ownerEpoch, Number(metadata.owner_epoch));
}
```

- Preservado: persistência, semântica de primeiro valor vencedor (`memoOf`), API do `memo`, formato das tarefas.
- Alterado: duas asserções de versão de schema (2 → 3) em `sqlite-migrations.test.ts` e `sqlite-cloudflare.test.ts`.
- Novo: `test/sqlite-owner-fence.test.ts` (3 testes: instância superseded rejeitada sem gravar nada; várias aberturas em sequência fencing todas as anteriores; banco v2 migrado e protegido).

Não prometi exactly-once. Ver limitações.

Patch: `patches/finecode-owner-fence.patch` (+111 / −7 em `src` e `test`, incluindo 71 linhas de teste novo).

### B. metaO OCC em `replace()`

```python
# sqlite_store.py — replace(): fence e revisão dentro da mesma transação
check_fence(connection, record.mission_id, fencing_token)
row = SELECT revision ... WHERE mission_id=?
if current != record.revision: raise MissionRevisionConflict(...)
updated = replace(record, revision=record.revision + 1)
cursor = UPDATE mission_records SET ... WHERE mission_id=? AND revision=?   # record.revision
if cursor.rowcount != 1: raise MissionRevisionConflict(...)
```

- A revisão é incrementada atomicamente com a condição `WHERE … AND revision = ?`, e exige `rowcount == 1`.
- `InMemoryMissionStore.replace` aplica a mesma regra (mantém o contrato do `MissionStorePort`).
- Nova exceção `MissionRevisionConflict` (`mission_store.py`), sem escrita em caso de conflito.

Patch: `patches/metao-occ-revision.patch` (`mission_store.py`, `sqlite_store.py`). **Observação:** `sqlite_store.py` também contém a checagem de fencing de `replace()`; por isso o patch de fencing também toca essa função. Os dois patches se sobrepõem nesse ponto.

### C. metaO fencing do token persistido

Estrutura:

- `active_mission_executions.fencing_token` (migração com `ALTER TABLE`, mesmo padrão já usado para `external_execution_id`).
- `activate()` emite o próximo token dentro de `BEGIN IMMEDIATE`: `token = anterior + 1`. A linha persiste, então o token é monotônico inclusive após reinício.
- `ActiveExecutionHandle.fencing_token: int = 0` (campo com valor padrão, compatível).

Validação (`src/metao/fencing.py`, `check_fence`), chamada **dentro da transação** de cada escrita, antes de qualquer alteração:

- **Com token:** deve ser igual ao token atual da missão; senão `StaleWorkerError`, sem escrita.
- **Sem token:** rejeitada enquanto houver execução `ACTIVE`; permitida fora de execução ativa (comportamento anterior). **Exceção:** `CANCELLATION_REQUESTED` do ledger é permitido sem token, porque cancelar é um pedido de qualquer chamador, não escrita de worker. Sem essa exceção, o próprio CLI de cancelamento falhou (`test_cli_cross_invocation_cancel…`).

Caminhos de escrita cobertos:

| Caminho | Fencing com token | Sem token durante execução ativa | Observação |
|---|---|---|---|
| `SQLiteMissionStore.replace` | sim | rejeitada | OCC também se aplica |
| `SQLiteEventLedger.append` | sim | rejeitada, exceto `CANCELLATION_REQUESTED` | ledger em arquivo separado: com token, falha fechada (sem tabela de handles, rejeita) |
| `SQLiteExecutionHandleStore.complete` | sim | rejeitada | operador passa o token |
| `SQLiteExecutionHandleStore.bind_external_execution` | sim | rejeitada | operador passa o token |
| `activate` | emite token | — | aquisição, não é escrita protegida |
| `request_cancel`, `mark_cancel_delegated` | **não** | — | intencional: pedido de controle, não de worker |
| `InMemoryExecutionHandleStore` | sim (mesma regra) | rejeitada | espelho em memória, sob o lock |
| `InMemoryEventLedger` | não | — | processo local, sem ownership; registrado como lacuna |

Operador (`operator.py`): guarda o token de cada tentativa ativada (`_fencing_tokens`, sob o lock existente) e o usa em `bind` e `complete` da mesma tentativa.

Patch: `patches/metao-fencing.patch` (`fencing.py` novo, `execution_handle.py`, `sqlite_execution_handle.py`, `sqlite_event_ledger.py`, `operator.py`, e testes).

**Testes:**

- Sete testes existentes (9 chamadas) assumiam escrita sem token após ativação. Atualizei cada chamada para apresentar o token do dono (1, 2 ou 0 na tabela legada), preservando a intenção do teste. Não alterei nenhuma asserção de resultado.
- Novo `tests/unit/test_t3_fencing_and_occ.py` (19 testes): OCC (SQLite e memória, conflito entre conexões separadas), token monotônico após reinício, append/replace/complete/bind rejeitados sem escrita, reativação do mesmo id com token antigo rejeitada, escrita sem token rejeitada durante execução ativa, rollback de append com payload inválido, residual documentado.

---

## Etapa 3 — Benchmark com processos reais

Tudo roda em processos separados, SQLite real, cada processo com seu próprio handle. Nenhuma simulação em memória.

### 3.1 FineCode (`bench-baseline/memo-bench.ts`, idêntico em `bench-fixed/`), 10 repetições por cenário

Cada variante é um processo real; crashes são `SIGKILL` no ponto de `await` do memo ou do efeito, gravados no trace antes da morte.

| Cenário | Linha de base: duplicatas por repetição | Corrigida: duplicatas | Corrigida: perdidos | Corrigida: instâncias superseded |
|---|---|---|---|---|
| A — crash após memo, antes do efeito | 0 | 0 | 1 (esperado, intent-first) | — |
| B — crash após efeito, antes do memo | 1 | 1 (esperado, effect-first) | 0 | — |
| B2 — crash após efeito com memo | 0 | 0 | 0 | — |
| C — parada graciosa e reinício | 0 | 0 | 0 | — |
| D — mesma chave, valores diferentes | 0 | 0 | N/A (sem efeitos) | — |
| **E-intent** — duas instâncias, sem atraso | **3** (9/10), 2 (1/10) | **0** (10/10) | 0 | 10/10 |
| **E-intent-widened** — 300 ms entre leitura e efeito | **3** (10/10) | **0** (10/10) | 0 | 10/10 |
| **E-effect** — duas instâncias, effect-first | **2–3** (10/10) | **0** (10/10) | 0 | 10/10 |
| **F** — A pausado após leitura do memo; B vivo; A liberado | **1** (10/10) | **0** (10/10) | 0 | 10/10 |
| F2 — A pausado após memo, antes do efeito | 0 | 0 | 0 | 10/10 |
| **G** — A pausado após efeito, antes do memo (effect-first) | **2** (10/10) | **1** (10/10) | 0 | 10/10 |

Evidência de mecanismo (versão corrigida): `superseded` = `SQLite storage epoch 2 is superseded by epoch 3; a newer instance owns this database`. Na linha de base, o erro `Task 7 is already terminal` aparece em lugar disso.

**Leitura:** a correção impede a execução concorrente da mesma chave (E, F). O residual de G é esperado: no padrão effect-first, o efeito acontece antes do memo, então o dono legítimo (B) repete o efeito que A já tinha feito antes da perda de posse. O fence não consegue evitar isso.

### 3.2 metaO (`bench-metao/worker.py`, `run_bench.py`)

**OCC — 4 processos concorrentes, 15 atualizações cada, 10 repetições.** Cada processo lê, altera e tenta gravar com a revisão lida. Atualização perdida = sucesso reportado cujo marcador não aparece no estado final.

| | Linha de base | Corrigida |
|---|---|---|
| Atualizações perdidas, por repetição | 31–45 | **0** (10/10) |
| Conflitos detectados e reexecutados | — | 81 no total |
| Revisão final = 1 + sucessos | sim | sim |
| Integridade SQLite | ok | ok |

**Append concorrente — 4 processos × 25 eventos, 10 repetições.** Linha de base e corrigida: 100 eventos, sequências 1..100 únicas e contíguas, sem erro, 10/10. Sem regressão.

**Complete concorrente — 3 processos completando a execução B em loop, enquanto C ativa outra execução (20 repetições).**

| | Linha de base | Corrigida |
|---|---|---|
| Escritas de B que caíram sobre a execução de C | 33–84 por repetição, **20/20** repetições | **0** em 20/20 |
| Estado final da execução | `e2 COMPLETED` (20/20) | `e2 ACTIVE` (20/20) |
| Completions de B aceitas / rejeitadas | 1326 / 10 | 217 / 5878 |

Aceitas na corrigida = completions de B aceitas antes da ativação de C (legítimas). Uma métrica inicial contava uma releitura pós-commit que mostrava `e2` como violação. Corrigi a métrica para contar apenas escritas com `COMPLETED/SUCCEEDED` sobre execução alheia, e reexecutei.

**Worker obsoleto — A ativa, lê a cópia, fica suspenso; B assume, grava e fica ativo; A é liberado (10 repetições).**

| | Linha de base | Corrigida |
|---|---|---|
| Tentativas de A aceitas (append, replace, complete, bind) | 3 de 4, **10/10** | **0**, 10/10 |
| Estado final | `objective=by A`; execução de B marcada `COMPLETED/FAILED` | `objective=by B`; execução de B `ACTIVE`, token 2 |
| Motivo da rejeição | — | `StaleWorkerError` (append, replace, complete); `bind` por `ActiveExecutionNotFound` (o `execution_id` de A já não existe na linha) |

Nota sobre `bind`: a rejeição nesse cenário é pela busca do `execution_id`, não pelo token. O caminho pelo token com id reativado é coberto pelo teste unitário `test_reactivated_execution_id_cannot_bind_with_its_old_token`.

**Janelas de crash (5 repetições por janela).** Crash dentro da transação: `os._exit` disparado pelo `set_trace_callback` antes do statement, portanto com transação aberta e não commitada.

| Janela | Linha de base | Corrigida |
|---|---|---|
| Crash antes do commit (append, replace, complete, activate) | estado inalterado; retry aceito | idem |
| Crash após commit (append) | evento persistido; **retry duplica o evento** (2 eventos) | idem |
| Crash após commit (replace) | persistido | idem |

Ou seja, a correção não muda o comportamento de crash. Ela não torna retries idempotentes: após commit, o retry de um append duplica o evento nas duas versões. Isso é limitação conhecida, sem chave de idempotência no ledger.

Limite do teste de crash: `os._exit` simula queda do processo, não queda de energia. Não testei `fsync`.

### 3.3 Repetições e determinismo

- FineCode: 10 repetições por cenário, com 3 variantes de E e 3 de takeover. Resultados consistentes entre repetições (ver contagens acima).
- metaO: OCC, append, suspended = 10; complete race = 20; crash windows = 5 por janela.
- O número de repetições é suficiente para detectar comportamento não determinístico nos cenários de corrida (a linha de base falhou de forma consistente em todas as repetições, e a corrigida passou em todas). Não é análise estatística.

---

## Etapa 4 — Avaliação

### Compatibilidade e cobertura de testes

| | FineCode | metaO |
|---|---|---|
| Suíte completa, linha de base | 1249 passam; 1 falha que exige provedor Codex real (serviço externo, não executado); 5 ignorados | 812 passam; 1 falha pré-existente (`test_operator_initialization_e2e`: subprocesso não carrega o plugin de teste); 12 erros de coleta (`crewai`, `langgraph` não instalados) |
| Suíte completa, corrigida | 1252 passam (+3); mesma falha de provedor externo | 831 passam (+19); mesmo conjunto de falhas |
| Mudanças em testes existentes | 2 asserções de versão de schema (2→3) | 9 chamadas em 7 testes passam a apresentar o token do dono |
| Mudança de schema | v2 → v3 (coluna `owner_epoch`) | coluna `fencing_token` (ALTER TABLE, default 0) |
| Quebra de compatibilidade | **Build antigo não abre banco v3** (`newer than supported`); reversão exige restaurar o banco | Escrita sem token durante execução ativa passa a ser rejeitada |

**Nota de ambiente (FineCode):** as cópias de trabalho não receberam, no início, os 739 arquivos ignorados pelo Git (catálogos de modelos em `packages/ai/src/providers/data/`). Corrigi copiando-os do original (somente leitura) para ambas as cópias, e só então rodei as suítes finais. Os números da linha de base foram refeitos.

Timeout intermitente: `harness-ownership › tracks ownership chains deeper than the call stack` estourou 60 s em uma execução completa de cada árvore e passou isoladamente 8/8 em cada uma. Não conto como regressão, mas registro como instabilidade sob carga.

Tratamento de `MissionRevisionConflict`: nenhum chamador do operador captura essa exceção. Com o OCC, um conflito aparece como exceção onde antes havia sobrescrita silenciosa. Isso é o comportamento desejado, mas o operador não faz retry. Recomendo um retry no operador antes de adotar.

### Custo operacional (medido)

Processo único, SQLite local, 500 operações, 5 repetições, mediana (`raw/metao-cost.jsonl`):

| Operação | Linha de base | Corrigida | Variação |
|---|---|---|---|
| append | 11 034 µs | 11 053 µs | +0,2% |
| replace | 12 167 µs | 12 157 µs | −0,1% |

O custo é dominado pelo commit do SQLite. A validação adiciona uma consulta indexada por chave primária dentro da mesma transação. Para o FineCode, o custo estrutural é uma atualização a mais por abertura de storage e a comparação de uma coluna já lida no mesmo `SELECT`; **não medi isso separadamente**.

### Complexidade adicionada

| | FineCode | metaO |
|---|---|---|
| Diff de `src` | +111 / −7 (incluindo testes) | +~160 em `src` (fencing.py 50 linhas) |
| Novos arquivos | 1 teste | `fencing.py`, 1 arquivo de teste |
| Mecanismos duplicados | nenhum | regra de fencing em duas implementações (SQL e memória); documentada |
| Abstração nova | nenhuma | `check_fence` e um tipo de exceção; sem framework |

Não adicionei abstração genérica. O helper `check_fence` é usado nas quatro escritas do SQLite; a versão em memória replica a regra sob o lock. A duplicação é a menor possível e fica registrada como risco de manutenção.

---

## Etapa 5 — Critérios de aprovação

**FineCode `runtime.memo()` — APROVADO COM LIMITAÇÕES**

- Cenários críticos (E, F): passaram, 10/10. A duplicata caiu de 3 para 0.
- Escrita obsoleta: não ocorre após o takeover (superseded rejeitado antes de qualquer gravação).
- Duplicação dentro dos limites declarados: sim para intent-first (A perde o efeito, B2 não duplica). Effect-first duplica em takeover (G, residual declarado).
- Recuperação reproduzível: sim (A, B2, C, D).
- Limitações documentadas: abaixo.

**metaO OCC — APROVADO COM LIMITAÇÕES**

- Escrita obsoleta: 0 (era 31–45 perdas por repetição).
- Recuperação: integridade ok; conflito não grava nada.
- Limitação: chamador precisa tratar `MissionRevisionConflict`; o operador ainda não faz retry.

**metaO fencing — REPROVADO como garantia de sistema**

- Passa nos caminhos com token: worker obsoleto rejeitado 10/10, complete race 0/20, append e crash windows sem regressão.
- **Falha no critério "não houver escrita obsoleta":** escritas **sem token após a conclusão da execução** continuam sem fence. Isso é alcançável pelo código atual:
  - `ObservableMissionOperator` grava projeções de eventos (`EVIDENCE_RECORDED` etc.) sem token depois da execução. Um operador obsoleto que termine tarde pode gravar eventos depois do dono mais novo ter concluído.
  - `operator.run` grava o resultado da missão sem token. Quando a execução já foi concluída, o OCC é a única proteção.
- Teste de residual: `test_unowned_writes_are_allowed_after_the_owner_completes` documenta o comportamento (não o aprova).
- Para aprovar: o operador deve apresentar o token também nas projeções e na gravação final da missão, e a regra "sem token" deve ser removida ou restrita a escritas de controle.

---

## Quais mecanismos preservar, adaptar e descartar

| Mecanismo | Decisão |
|---|---|
| FineCode owner fence (`owner_epoch` no commit) | **Preservar.** Menor correção que resolve a falha. Adaptar: documentar que abrir o storage para inspeção **substitui** a instância em execução (ver limitações). |
| FineCode `memo()` em si | **Preservar sem mudança.** A API e a semântica de primeiro valor vencedor estão corretas dentro de uma instância. |
| metaO OCC em `replace()` | **Preservar.** Adaptar o operador para tratar o conflito com retry. |
| metaO token persistido (`activate` + `check_fence`) | **Preservar** para os caminhos de worker. **Adaptar** o operador para apresentar o token nas projeções e na gravação final. |
| Regra "sem token durante execução ativa" | **Adaptar.** Funciona, mas é uma política. Precisa de uma lista explícita de escritas de controle (hoje só `CANCELLATION_REQUESTED`). |
| `reject_stale_worker` isolado (runtime.py) | **Descartar como mecanismo.** Substituído pela validação na transação. Pode ficar como função pura, mas não deve ser tratado como fencing. |
| `UNIQUE(mission_id, sequence)` como fencing | **Descartar** como fencing. Continua útil para integridade de sequência. |

---

## Limitações e cenários não testados

**Ambiente**
- Somente Windows; Node v26.10.0; Python 3.12.10; SQLite 3.49.1. Git com `core.autocrlf=true` no ambiente: os blobs do repositório são LF; as cópias de trabalho foram normalizadas para LF e os patches gerados a partir dos blobs do `HEAD`.
- `provider-session-cache-e2e` exige provedor Codex real. Não executado (serviço externo proibido por este teste).
- Crash simulado por `SIGKILL` (FineCode) e `os._exit` (metaO). Não simulei queda de energia nem falha de `fsync`.
- Não testei SQLite sobre sistemas de arquivos de rede (SMB/NFS), onde o locking difere.

**FineCode**
- Abrir o storage para qualquer finalidade (inclusive inspeção) substitui a instância em execução. Não há abertura somente leitura.
- Storages JSONL e Cloudflare Durable Object não receberam a correção. Não foram testados.
- O `dist/` de `packages/durable` não foi recompilado na cópia. Consumidores que usam `dist` (e não a fonte) não recebem a correção até uma recompilação.
- Efeito in-flight de instância substituída ainda pode completar (F2 mostra o efeito do dono executado uma vez). Isso é esperado.
- Memo e checkpoint continuam em transações separadas; o efeito externo continua fora de transação. Exactly-once não foi obtido, nem prometido.
- Effect-first duplica em takeover (G). Não há como corrigir isso sem idempotência no destino.

**metaO**
- Escritas sem token após a conclusão da execução continuam sem fence (ver Etapa 5).
- Ledger em arquivo diferente do de handles: com token, falha fechada; sem token, não é fencing.
- `InMemoryEventLedger` não tem fencing.
- `request_cancel` e `mark_cancel_delegated` não têm fencing, por projeto.
- `bind` com `execution_id` antigo é rejeitado pela busca, não pelo token (salvo id reativado, coberto por teste unitário).
- Retry após commit de append duplica o evento. Não há chave de idempotência no ledger.
- Lease com expiração não existe: a posse muda só quando alguém ativa uma execução nova. Um worker vivo e lento só é barrado quando tenta escrever.
- `crewai`, `langgraph` e dependências ausentes: 12 módulos de integração não rodaram.

**Benchmark**
- Número de repetições: 10 a 20, sem análise estatística. Consistência entre repetições é o critério usado.
- Tempos de custo medidos em uma máquina, uma execução de 5 repetições.

---

## Entregáveis

- `REPORT.md` (este arquivo) e `results.json` (consolidado por `consolidate.py`).
- `patches/finecode-owner-fence.patch`, `patches/metao-fencing.patch`, `patches/metao-occ-revision.patch`. Gerados por `tools/make_patches.sh` a partir dos blobs LF do `HEAD` original. **Ordem de aplicação no metaO: `metao-fencing.patch` e depois `metao-occ-revision.patch`** (o OCC importa `fencing.py` e a chamada de fence fica em `sqlite_store.replace()`). Verificado: aplicam sobre os blobs originais, a árvore resultante é idêntica à corrigida, e os testes passam (48 metaO; 99 SQLite FineCode).
- `raw/finecode-baseline/`, `raw/finecode-fixed/`: `bench-results.json`, traces, logs de efeito, bancos, stdout/stderr por processo.
- `raw/metao-baseline/`, `raw/metao-fixed/`: `bench.json` (métricas por repetição), logs de processo, snapshots.
- `raw/*-pytest*.log`, `raw/durable-full-*.log`: suítes completas (linha de base e corrigida). `raw/baseline/durable-full-vitest.log` e `raw/fixed-durable-*.log` são execuções anteriores à cópia dos arquivos ignorados e ficam como histórico. `raw/*-failures*.txt`: conjuntos de falhas comparados.
- `raw/metao-cost.jsonl`: custo por operação.
- Histórico (superado, mantido por rastreabilidade): `raw/metao-bench.log` é a 1ª bateria completa; suas métricas de `complete_race` (contagem por `execution_id` pós-commit) e de `crash_windows` (marcador `SET status=?` que não casava) foram substituídas pela 2ª execução, `raw/metao-bench-2.log`. `raw/metao-baseline/bench.json` e `raw/metao-fixed/bench.json` já contêm os valores corrigidos (mescla por cenário). `raw/metao-fixed-pytest-1.log` é a 1ª suíte, antes do ajuste de `CANCELLATION_REQUESTED`.
- `baseline-test2-hashes.txt`: manifesto de 300 arquivos do Teste 2 (verificado: idêntico ao final; bancos SQLite ficaram fora do manifesto).
- Testes reproduzíveis: `bench-baseline/memo-bench.ts`, `bench-fixed/memo-bench.ts` (idênticos; cada um com junção para o `node_modules` da árvore testada), `bench-metao/worker.py`, `bench-metao/run_bench.py`, `bench-metao/cost.py`.

**Reprodução**

```
:: FineCode (linha de base e corrigida); cada pasta resolve para a própria árvore
cd test-3\bench-baseline
set BENCH_LABEL=finecode-baseline
node --conditions=source --experimental-strip-types --no-warnings memo-bench.ts 10

cd ..\bench-fixed
set BENCH_LABEL=finecode-fixed
node --conditions=source --experimental-strip-types --no-warnings memo-bench.ts 10

:: metaO (linha de base e corrigida)
cd ..\bench-metao
python run_bench.py 10          :: METAO_BENCH_ONLY=complete_race,crash_windows para um subconjunto
python cost.py ..\work\metao 500

cd ..
python consolidate.py
```

Nota: `work/finecode*/node_modules` são árvores de junções; `work/rebuild-nm.ps1 -copy <caminho>` as reconstrói. Não remova essas pastas com `rm -rf`: as junções apontam para o `node_modules` do original.

## Integração

Nenhuma correção foi integrada aos projetos originais. Os patches exigem revisão, recompilação do `dist` do durable e ajustes do operador (Etapa 5) antes de qualquer integração.
