# Teste Comparativo 2 — Idempotência e fencing real

**Data:** 18/11/2026 · **Ambiente:** Windows, Node v26.10.0, Python 3.12.10, processos locais, SQLite real, efeitos simulados em arquivo.
**Escopo:** somente `D:\projetos\durability-benchmark\test-2\`. Repositórios originais não foram modificados.
**Origens:** FineCode `ad41b5c344d5399982718720db975b1e020e2c40`; metaO `23fc5c659ae5f0606e9e6774108c44636e29b0ac`.
**Antes/depois:** HEAD idêntico e `git status` idêntico nos dois repositórios (`results.json → origins`).

## Resumo

| Mecanismo | Classificação | Motivo principal |
|---|---|---|
| FineCode `runtime.memo()` | **PARCIAL** | Primeiro-escritor-vence dentro de uma instância e persistência antes do reinício comprovadas. Não há exactly-once. Duas instâncias sobre o mesmo DB executam o mesmo efeito 3/3. |
| metaO `SQLiteMissionStore.replace()` (OCC) | **FALHOU** | Cópia obsoleta aceita e sobrescreve conteúdo mais novo, 3/3. |
| metaO fencing do ledger | **FALHOU** | Worker A obsoleto publica evento, substitui a missão e conclui a execução de B, 3/3. `UNIQUE(mission_id, sequence)` não impede nada disso. |

A tentativa anterior de `test-2` (preservada em `tentativa-anterior/`) não executou os cenários do FineCode: o import por caminho de arquivo travou. Com import por nome de pacote (`--conditions=source`) o runtime carrega normalmente (1,3 s), e todos os cenários foram executados nesta rodada.

---

## 1. FineCode `runtime.memo()`

### Implementação real (inspecionada)

`packages/durable/src/harness/scheduler.ts`:

```ts
// scheduler.ts:2014–2029 — memo dentro do runtime da tarefa
memo: ((name, ...rest) => {
  if (rest.length === 1) {
    return this.#read(invocation, async () => memoOf(this.#live.get(invocation.taskId), name));
  }
  const candidate = rest[0];
  return this.#gated(invocation, (tx, current) => {
    const winner = memoOf(current, name);
    if (winner !== undefined) return winner;
    tx.setTask({ ...current, memos: { ...current.memos, [name]: candidate } });
    return candidate;
  }, rest[1]);
}),
```

- **Quando persiste:** em `#gated` (scheduler.ts:2188), que chama `session.commitWith` → um commit de storage próprio, por chamada de `memo`. Não há `runtime.commit()` envolvendo o memo.
- **Quando recupera:** `memoOf(this.#live.get(taskId), name)` (scheduler.ts:2302). Lê do mapa `#live` **em memória do processo** (`scheduler.ts:256`), não do banco.
- **Associação à tarefa:** o memo é o campo `memos` do próprio registro da tarefa (`record.memos[name]`). Por isso o memo é removido quando o outcome é decidido (scheduler.ts:2334–2337).
- **Transação com o checkpoint:** **não há.** `sleepUntil` (checkpoint) é outro `#gated`/commit. Memo e checkpoint são gravados em transações distintas. Evidência no snapshot pós-crash (abaixo).
- **Comportamento em encerramento abrupto:** a transação SQLite é `BEGIN IMMEDIATE … COMMIT` (`chord/src/sqlite/node.ts:139–158`); o que foi commitado sobrevive ao `SIGKILL`; o que não foi, se perde. Na abertura, tarefas `running` voltam para `pending` e `restarts` é incrementado (`scheduler.ts:352–390`), e a fase reexecuta a partir do último checkpoint.
- **Efeito externo:** fica fora de qualquer transação do FineCode.

### Experimento

Arquivos: `finecode-run/memo-bench.ts` (orquestrador + filhos reais), `raw/finecode/<cenário>/rep<n>/` (trace, log de efeitos, bancos, stdout/stderr). Processos morrem por `process.kill(pid, 'SIGKILL')` logo após o `await` do memo ou do efeito. O trace grava o ponto de crash antes de morrer. Cada efeito é uma linha com UUID único.

Padrões de fase comparados:
- **intent-first** (usado pelo Teste 1): `memo(k)` leitura → `memo(k, true)` → efeito → checkpoint.
- **effect-first**: leitura → efeito → `memo(k, true)` → checkpoint.

| Cenário (3 reps) | Descrição | Efeitos executados | Duplicados | Perdidos | Valor do memo recuperado | Resultado final |
|---|---|---|---|---|---|---|
| **A** (intent) | crash após `memo(unit_2)` gravado, antes do efeito | 2 | 0 | **1** (`unit_2`) | `unit_2 = true` | `completed`, `units=3` |
| **B** (effect-first) | crash após efeito de `unit_2`, antes do memo | 4 | **1** (`unit_2` ×2) | 0 | nenhum | `completed` |
| **B2** (intent, controle) | crash após efeito de `unit_2` (memo já gravado) | 3 | 0 | 0 | `unit_2 = true` | `completed` |
| **C** | parada graciosa após `unit_2` (memo+efeito+checkpoint confirmados) e reinício | 3 | 0 | 0 | — (nenhuma reexecução) | `completed` |
| **D** | mesma chave, valores diferentes; intra-processo e após reinício | N/A | N/A | N/A | `memo(k,'v1')`, `memo(k,'v2')` → `v1`; 8 chamadas paralelas → `b0` em todas; após reinício `v1`, `memo(k,'v3')` → `v1` | `completed` |
| **E-intent** (2 instâncias) | duas instâncias sobre o mesmo DB, sem atraso | 6 | **3** | 0 | — | 2× `completed` ou 1× `Session failed` |
| **E-intent-widened** | igual, com 300 ms entre leitura do memo e efeito | 6 | **3** | 0 | — | idem |
| **E-effect** | duas instâncias, padrão effect-first | 6 (5 em 1 rep) | 3 (2 em 1 rep) | 0 | — | idem |

Resultados por repetição: `raw/finecode/finecode-results.json` e `results.json → mechanisms → finecode.runtime.memo → scenarios`. Todas as repetições de A, B, B2, C, D, E foram executadas (nenhum "não executado").

**Evidência de persistência (snapshot copiado logo após o crash, incluindo `-wal`):** `raw/finecode/db-snapshots-after-crash.txt`

- A: `status=running, checkpoint n=2, memos={unit_1:true, unit_2:true}` → memo de `unit_2` persistido, checkpoint ainda em 2.
- B: `checkpoint n=2, memos={unit_1:true}` → sem memo de `unit_2`, efeito já executado.

**Causa da duplicação em E:** `raw/finecode/E-intent-widened/rep1/trace.jsonl`. Ambas as instâncias leem `unit_1` como `null` e gravam `winner: true` **na própria memória**. Depois uma conclui a tarefa e a outra falha com `Task 7 is already terminal` (`transaction.ts:769`, relatado via `onReport` e registrado como `session_failed`). Motivo: `#gated` decide com base em `this.#live` (scheduler.ts:2198, memória do processo). O upsert de tarefa (`storage.ts:823–830`) sobrescreve o registro inteiro sem checar versão. `Harness.open` não tem lock entre processos.

### Garantia efetivamente obtida

- **Dentro de uma instância, primeiro-escritor-vence por nome e por tarefa:** COMPROVADO (D).
- **Persistência antes do reinício:** COMPROVADO (A, B2, C, D).
- **At-most-once:** obtido pelo padrão intent-first. Crash na janela memo→efeito **perde** o efeito (A, 3/3).
- **At-least-once:** obtido pelo padrão effect-first. Crash na janela efeito→memo **duplica** o efeito (B, 3/3).
- **Exactly-once:** **NÃO obtido**, em nenhum dos padrões. O memo sozinho não fecha a janela; o destino do efeito também não deduplica (é um append de arquivo).
- **Unicidade entre instâncias:** **FALHOU** (E, 3/3 por variante).

### Limitações

1. Memo e efeito não são atômicos. Não existe transação que una memo, efeito e checkpoint.
2. Não há proteção entre processos: duas instâncias sobre o mesmo DB executam o mesmo efeito.
3. Crash testado é de processo (`SIGKILL`). Falha de energia/SO com `synchronous` não foi testada.
4. Efeito testado é um arquivo local. Um destino externo que aceite chave idempotente não foi testado.
5. Na plataforma Windows, `SIGKILL` aparece como `exit code 1` (`signal null`). O ponto de crash foi confirmado por evento `crash` no trace, não só pelo código de saída.

### Alteração mínima necessária (não aplicada; não validada)

- Para uso com memo como *intenção*: a chave `memo(name)` deve ser passada como **chave idempotente ao destino do efeito**, e o destino deve deduplicar por ela.
- Para unicidade entre instâncias: (a) lock/lease de instância por DB no `Harness.open`, ou (b) ler a tarefa **dentro** da transação de storage (`tx.task(id)`) no `#gated` do memo, mais checagem de versão no upsert de tarefa (`WHERE` sobre revisão anterior). Só (b) isolado não basta: o upsert também precisa checar versão.

---

## 2. metaO `SQLiteMissionStore.replace()` (OCC)

### Implementação real

`src/metao/sqlite_store.py:507–524`:

```python
def replace(self, record: MissionRecord) -> MissionRecord:
    with closing(self._connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT revision FROM mission_records WHERE mission_id = ?", (record.mission_id,)
        ).fetchone()
        if row is None:
            raise MissionNotFound(record.mission_id)
        updated = replace(record, revision=int(row[0]) + 1)     # ignora record.revision
        raw = _record_to_json(updated)
        connection.execute(
            "UPDATE mission_records SET status=?, revision=?, schema_version=?, record_json=? WHERE mission_id=?",
            (updated.status.value, updated.revision, _SCHEMA_VERSION, raw, updated.mission_id),
        )
    return updated
```

O `BEGIN IMMEDIATE` serializa o read-modify-write, mas a revisão que o chamador leu **não** entra na condição. `record.revision` é descartado.

### Experimento (3 repetições)

Missão criada na revisão 1; duas cópias carregadas; cópia 1 gravada (revisão 2); cópia 2, ainda na revisão 1, gravada.

| Rep | Revisão da cópia obsoleta | `replace()` | Banco final | Veredito |
|---|---|---|---|---|
| 1 | 1 | **aceito** | rev 3, `objective='stale writer 2'` (sobrescreveu `rev2 by writer 1`) | FAILED_SILENT_OVERWRITE |
| 2 | 1 | **aceito** | idem | idem |
| 3 | 1 | **aceito** | idem | idem |

Dados: `raw/metao/occ_rep*/metao.db`, `raw/metao/metao-results.json → occ`.

**Prototipo isolado (não aplicado ao projeto):** o SQL proposto abaixo, executado em banco de teste separado, aceitou a atualização da cópia atual e **rejeitou** a obsoleta em 3/3 (`raw/metao/occ_prototype_rep*/`).

```sql
UPDATE mission_records SET status=?, revision=?, schema_version=?, record_json=?
WHERE mission_id=? AND revision=?      -- revision = record.revision lido pelo chamador
-- sucesso somente se cursor.rowcount == 1; caso contrário, levantar conflito de concorrência
```

Mesma semântica sem checagem em `InMemoryMissionStore.replace` (`mission_store.py:118`).

### Garantia efetivamente obtida

Exclusão mútua do trecho de escrita (`BEGIN IMMEDIATE`) e numeração monotônica de revisão. **Não** há controle otimista: a escrita não verifica a revisão base, e o chamador recebe sucesso com revisão 3 sobre conteúdo que nunca viu.

### Limitação

Qualquer chamador que mantenha uma cópia e grave depois perde atualizações silenciosamente. O erro não aparece nem para o chamador nem no banco.

### Alteração mínima necessária

A condição `WHERE revision=?` com o valor lido pelo chamador e verificação de `rowcount == 1`, como acima. Isso é a única mudança necessária no SQL. Quem chama precisa garantir que `record.revision` é a revisão lida.

---

## 3. metaO fencing do ledger

### Estruturas reais (inspecionadas)

- **Missão:** `mission_records(mission_id PK, status, revision CHECK>=1, schema_version, record_json)` (`sqlite_store.py:452`).
- **Execução/posse:** `active_mission_executions(mission_id PK, execution_id, orchestrator_id, attempt_number, status, cancel_requested, …)` (`sqlite_execution_handle.py:40`). Único registro ativo por missão. Este é o único mecanismo de "propriedade" persistido.
- **Ativação:** `activate()` faz `ON CONFLICT(mission_id) DO UPDATE SET execution_id=excluded.execution_id, …` (`sqlite_execution_handle.py:112–157`). Sobrescreve a posse sem checar a execução anterior.
- **Conclusão:** `complete(mission_id, …)` filtra só por `mission_id` (`sqlite_execution_handle.py:210–230`). Não recebe `execution_id`.
- **Evento:** `append(mission_id, kind, payload)` calcula `MAX(sequence)+1` e insere. **Não** recebe worker, execução nem token (`sqlite_event_ledger.py:84–125`). `UNIQUE(mission_id, sequence)` (linha 44) só impede sequência duplicada.
- **Fencing token:** `FencingToken`, `Lease` e `reject_stale_worker` existem em `runtime.py:26–75`, mas **nenhum store os usa**. A única referência fora do próprio módulo é um teste unitário (`tests/unit/test_block_g_runtime_invariants.py`).

### Experimento (3 repetições, mesmo arquivo SQLite para todos os stores)

1. A ativa a execução (geração 1) e lê a missão.
2. A fica suspenso.
3. B ativa a execução (geração 2), publica evento, grava missão (revisão 2), conclui a execução.
4. A volta e tenta: publicar evento (`append`), substituir a missão pela cópia obsoleta, concluir a execução, vincular execução externa pelo id antigo.

| Operação de A (obsoleto) | Resultado (3/3) | Efeito |
|---|---|---|
| `ledger.append(...)` com geração 1 | **aceito**, sequência 4 (não utilizada) | evento de A na linha do tempo |
| `missions.replace(cópia obsoleta)` | **aceito**, revisão 3 | sobrescreveu `advanced by B` com `stale write by A` |
| `handles.complete(mission_id)` | **aceito** | execução de B marcada `COMPLETED` |
| `handles.bind_external_execution(exec-A)` | rejeitado: `ActiveExecutionNotFound` | rejeição **incidental**: `execution_id` mudou, não há checagem de token |
| `reject_stale_worker(gen 2, gen 1)` chamado diretamente | levanta `StaleWorkerError` | correto isolado, mas **não ligado** a nenhum store |

Evento de B na posse: `activate(B)` aceito, `active_execution = exec-B`. Nenhuma checagem sobre a execução anterior.

Dados: `raw/metao/fencing_rep*/metao.db`, `raw/metao/metao-results.json → fencing`.

**Prototipo isolado (não aplicado):** `INSERT … SELECT … WHERE EXISTS (SELECT 1 FROM active_mission_executions WHERE mission_id=? AND execution_id=? AND status='ACTIVE')` dentro de `BEGIN IMMEDIATE`. Rejeitou A (`stale_A_accepted=False`) e aceitou B em 3/3 (`fencing_prototype`).

**Sobre "sequência não utilizada":** A conseguiu publicar com `sequence = MAX+1`, que não estava usada. Isso confirma que `UNIQUE(mission_id, sequence)` não é fencing. A única proteção possível é validar a propriedade na mesma transação.

### Garantia efetivamente obtida

Unicidade de `(mission_id, sequence)` e serialização de cada `append`/`replace` por `BEGIN IMMEDIATE`. **Nenhuma** validação de propriedade: o armazenamento não sabe quem é o detentor atual para publicar ou substituir.

### Limitações

- O teste opera no nível dos stores (SQL real), não em um runtime de workers completo. Simula A e B pela sequência de chamadas.
- A concorrência real entre processos de metaO (ledger) não foi exercitada. O argumento de serialização vem da leitura do código (`BEGIN IMMEDIATE`).

### Alteração mínima necessária

1. Token/geração persistida por missão, em tabela própria ou na linha de `active_mission_executions`, incrementada atomicamente em `activate()`, com recusa se houver posse ativa não expirada.
2. `append`, `replace` e `complete` recebem `(execution_id, token)` e verificam a posse dentro da mesma transação `BEGIN IMMEDIATE` (como no protótipo validado).
3. `reject_stale_worker` passa a ser chamado pelos stores, ou sua lógica é movida para a camada de storage.

---

## Respostas objetivas

**1. Podemos reutilizar `runtime.memo()`? Com quais garantias?**
**Sim, com restrições.** Serve como registro durável de decisão/intenção por tarefa, dentro de uma única instância `Harness`. Garantias obtidas: primeiro-escritor-vence por chave (intra-processo), persistência antes do reinício, at-most-once com padrão intent-first ou at-least-once com effect-first (escolha que decide qual falha é aceita). **Não** dá exactly-once. **Não** é seguro com duas instâncias sobre o mesmo DB. Para exactly-once é preciso chave idempotente no destino do efeito.

**2. O metaO possui OCC efetivo em `replace()`?**
**Não.** 3/3 atualizações obsoletas foram aceitas silenciosamente e sobrescreveram conteúdo mais novo. O `BEGIN IMMEDIATE` serializa, mas não compara revisão.

**3. O metaO impede efetivamente a escrita de workers obsoletos?**
**Não.** 3/3: A obsoleto publicou evento com sequência nova, substituiu a missão e concluiu a execução de B. A única rejeição observada (`bind_external_execution`) foi incidental, pela mudança de `execution_id`. `reject_stale_worker` está correto, mas não é usado por nenhum store.

**4. Quais mecanismos estão prontos para incorporação e quais precisam de adaptação?**
- **Pronto (com ressalva de contrato):** nenhum dos três está pronto como garantia geral de execução, idempotência ou fencing.
- **Adaptar, memo:** tratar como intenção durável por tarefa. Passar a chave do memo como idempotency key ao destino do efeito, e impedir mais de uma instância sobre o mesmo DB (lock/lease) antes de reutilizar.
- **Adaptar, OCC de `replace()`:** cláusula `WHERE revision=?` com verificação de `rowcount`, validada isoladamente.
- **Adaptar, fencing do ledger:** token persistido validado na mesma transação de `append`/`replace`/`complete`, validado isoladamente para `append`.
- **Não usar como fencing:** `UNIQUE(mission_id, sequence)`.

---

## Reprodução

```
cd D:\projetos\durability-benchmark\test-2\finecode-run
node --conditions=source --experimental-strip-types --no-warnings memo-bench.ts          # ~75 s, 8 cenários x 3 reps

cd D:\projetos\durability-benchmark\test-2\metao-run
set PYTHONDONTWRITEBYTECODE=1 && python run_metao.py                                      # OCC + fencing + protótipos

cd D:\projetos\durability-benchmark\test-2
python consolidate.py                                                                     # gera results.json a partir de raw/
```

Pré-requisito FineCode: `finecode-run/node_modules` é um link para `D:\projetos\FineCode\node_modules` (somente leitura pelo runtime). Nenhuma API paga ou serviço externo foi usado.

## Artefatos

- `REPORT.md`, `results.json` (consolidado)
- `raw/finecode/`: `finecode-results.json`, traces, efeitos, bancos, snapshots pós-crash, stdout/stderr por processo
- `raw/metao/`: `metao-results.json`, bancos `occ_rep*`, `fencing_rep*`, protótipos
- `finecode-run/`, `metao-run/`: scripts reproduzíveis
- `tentativa-anterior/`: relatório e brutos da tentativa anterior, preservados sem alteração

## Fora do escopo (não usados, não alterados)

No diretório pai `durability-benchmark\` há pastas de 18/11 (`copies/`, `driver/`, `evbench/`, `finecode/`, `metao/`, `runs/`, `raw/origin-snapshot-before.txt`, `mkj.ps1`) criadas por execuções anteriores fora de `test-2`. Não as usei nem as modifiquei. Os artefatos do Teste 1 (`_run0-previous-2026-11-18/`) também não foram tocados.
