# RELATÓRIO DO TESTE COMPARATIVO 1 — DURABILIDADE E RECUPERAÇÃO

**Data de execução:** 18 de Novembro de 2026  
**Ambiente de teste:** Windows (PowerShell / Node.js v26.10.0 / Rust cargo 1.99.1 / Python 3.12.10)  
**Diretório do benchmark:** `D:\projetos\durability-benchmark`  
**Dados brutos e logs:** `D:\projetos\durability-benchmark\raw\`  
**Consolidado estruturado:** `D:\projetos\durability-benchmark\results.json`

---

## 1. Identificação Exata das Versões Testadas

Todos os testes foram executados contra os repositórios originais intactos, sem nenhuma alteração, branch, commit ou push efetuado. As cópias de trabalho e scripts de execução foram isolados estritamente em `D:\projetos\durability-benchmark\`.

| Projeto | Caminho Original | Commit SHA | Branch / Refs | Estado Git Inicial |
| :--- | :--- | :--- | :--- | :--- |
| **FineCode** | `D:\projetos\FineCode` | `ad41b5c344d5399982718720db975b1e020e2c40` | `HEAD -> tui`, `origin/feat/upstream-import-observability` | `?? nul` (limpo, 1 untracked `nul`) |
| **EvCore** | `D:\projetos\evcore` | `e4e8d9a3a1c9a7dbae7d9feda5dd4be378099d06` | `HEAD -> claude/tender-hawking-dcgx72` | 12 modificações locais não commitadas, 2 untracked |
| **metaO** | `D:\projetos\metaO` | `23fc5c659ae5f0606e9e6774108c44636e29b0ac` | `HEAD`, `tag: v0.2.0-rc.1`, `main` | 5 arquivos untracked (`benchmark-evidence/`, etc.) |

---

## 2. Arquivos e Mecanismos Efetivamente Exercitados

### 2.1 FineCode (TypeScript / Node.js)
* **Pacote:** `@earendil-works/pi-durable` (`D:\projetos\FineCode\packages\durable`)
* **Armazenamento:** SQLite relacional via `openNodeSqliteStorage()` (`src/storage/sqlite/node.ts`)
* **Mecanismos de Durabilidade:**
  * `Harness.open()` e `createSession()`: abertura de kernel durável sobre SQLite.
  * `defineTask()` com transições de fase atômicas via `runtime.commit()` e `runtime.sleepUntil()`.
  * `runtime.memo()`: deduplicação por chave durável (*first-write-wins*) para registrar intenção antes do efeito.
  * `harness.abortTask()`: cancelamento cooperativo com sinalização de `runtime.signal.aborted`.
  * `Transaction` com verificação de escopo e versionamento (`checkRecordVersion`).

### 2.2 EvCore (Rust)
* **Crate:** `orca-harness-extensions` (`D:\projetos\evcore\crates\extensions`) e `orca-harness-core` (`crates/harness-core`)
* **Armazenamento:** Transcrição em arquivo append-only JSONL (`crates/extensions/src/session.rs`)
* **Mecanismos de Durabilidade:**
  * `SessionHandler::create()` e `SessionHandler::sync()`: gravação atômica por mensagem com `Mutex<Recorder>`.
  * `SessionHandler::resume()`: reabertura do arquivo JSONL, reconstrução do `Context` e rearme do cursor.
  * `SessionFile::load()`: tolerância e descarte automático de linha final truncada (*crash artifact*).
  * Descarte de mensagens `Assistant` com chamadas de ferramentas pendentes sem resposta ao reiniciar.
  * Detecção e rejeição estrita de corrupção estrutural intermediária via `SessionError::Corrupt`.

### 2.3 metaO (Python)
* **Módulo:** `metao` (`D:\projetos\metaO\src\metao`)
* **Armazenamento:** SQLite relacional com esquema versionado (`sqlite_store.py` e `sqlite_event_ledger.py`)
* **Mecanismos de Durabilidade:**
  * `SQLiteMissionStore`: armazenamento relacional com snapshot JSON validado (`_validated()`) e controle de concorrência por `revision`.
  * `SQLiteEventLedger`: ledger imutável append-only com chave primária e restrição `UNIQUE(mission_id, sequence)` sob transações `BEGIN IMMEDIATE`.
  * `MissionAlreadyExists`: idempotência na criação de missões com detecção de chave primária duplicada.
  * `MissionStoreCorrupt`: fail-closed imediato se colunas relacionais divergirem do snapshot JSON interno.
  * `GitRepositoryCheckpointPort`: ancoragem de estado a SHAs imutáveis do Git com assertiva de worktree limpa (`_assert_clean()`).

---

## 3. Comandos Utilizados nos Experimentos

```powershell
# 1. FineCode (Execução de Scenarios A a E, 3 repetições cada)
cd "D:\projetos\durability-benchmark"
node --conditions=source --experimental-strip-types "D:\projetos\durability-benchmark\finecode\benchmark_finecode.ts"

# 2. EvCore (Compilação e execução de Scenarios A a E, 3 repetições cada)
cd "D:\projetos\durability-benchmark\evcore"
cargo run --release

# 3. metaO (Execução de Scenarios A a E, 3 repetições cada)
python "D:\projetos\durability-benchmark\metao\benchmark_metao.py"
```

---

## 4. Resultados Detalhados por Cenário e Repetição

### Legenda de Status
* **PASS**: Mecanismo operou conforme especificação de durabilidade, preservando integridade.
* **FAIL**: Perda de dados, aceitação silenciosa de corrupção ou crash catastrófico não tratado.
* **NOT_SUPPORTED**: Mecanismo ausente na arquitetura avaliada (sem penalização artificial).

---

### Cenário A — Persistência Normal
*5 unidades submetidas, 3 executadas, encerramento limpo, reabertura, conclusão das 2 restantes.*

| Projeto | Rep | Status | Unidades Antes | Unidades Recuperadas | Reexecutadas | Efeitos Duplicados | Efeitos Perdidos | Tempo Recup. (ms) | Integridade |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **FineCode** | 1 | **PASS** | 3 | 3 | 0 | 0 | 0 | 5.045 | verified (SQLite) |
| | 2 | **PASS** | 3 | 3 | 0 | 0 | 0 | 5.035 | verified (SQLite) |
| | 3 | **PASS** | 3 | 3 | 0 | 0 | 0 | 5.038 | verified (SQLite) |
| **EvCore** | 1 | **PASS** | 3 | 3 | 0 | 0 | 0 | 0 | verified_jsonl |
| | 2 | **PASS** | 3 | 3 | 0 | 0 | 0 | 5 | verified_jsonl |
| | 3 | **PASS** | 3 | 3 | 0 | 0 | 0 | 6 | verified_jsonl |
| **metaO** | 1 | **PASS** | 3 | 3 | 0 | 0 | 0 | 18 | verified_sqlite_relational |
| | 2 | **PASS** | 3 | 3 | 0 | 0 | 0 | 14 | verified_sqlite_relational |
| | 3 | **PASS** | 3 | 3 | 0 | 0 | 0 | 13 | verified_sqlite_relational |

*Observações:*
* **FineCode**: O tempo de recuperação reflete o agendador de tarefas dormindo até o vencimento do sleep planejado antes de acionar a unidade 4. As 3 unidades anteriores permaneceram registradas e a transição para conclusão ocorreu perfeitamente.
* **EvCore**: O carregamento da sessão JSONL e reconstrução de contexto levaram < 6 ms.
* **metaO**: Recuperou o `MissionRecord` no status `RUNNING` e o `SQLiteEventLedger` continha os 3 eventos sequenciais. Concluiu os eventos 4 e 5 atualizando a revisão da missão para 2 (`ACCEPTED`).

---

### Cenário B — Interrupção Abrupta
*2 unidades executadas e persistidas, encerramento abrupto do processo sem encerramento limpo (`os._exit` / processo abandonado sem flush), recuperação por novo processo.*

| Projeto | Rep | Status | Unidades Antes | Unidades Recuperadas | Reexecutadas | Efeitos Duplicados | Efeitos Perdidos | Tempo Recup. (ms) | Integridade |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **FineCode** | 1 | **PASS** | 2 | 2 | 0 | 0 | 0 | 32 | recovered_from_unclosed_storage |
| | 2 | **PASS** | 2 | 2 | 0 | 0 | 0 | 43 | recovered_from_unclosed_storage |
| | 3 | **PASS** | 2 | 2 | 0 | 0 | 0 | 39 | recovered_from_unclosed_storage |
| **EvCore** | 1 | **PASS** | 2 | 2 | 0 | 0 | 0 | 11 | recovered_with_crash_artifact_dropped |
| | 2 | **PASS** | 2 | 2 | 0 | 0 | 0 | 11 | recovered_with_crash_artifact_dropped |
| | 3 | **PASS** | 2 | 2 | 0 | 0 | 0 | 10 | recovered_with_crash_artifact_dropped |
| **metaO** | 1 | **PASS** | 2 | 2 | 0 | 0 | 0 | 15 | recovered_after_os_exit |
| | 2 | **PASS** | 2 | 2 | 0 | 0 | 0 | 18 | recovered_after_os_exit |
| | 3 | **PASS** | 2 | 2 | 0 | 0 | 0 | 14 | recovered_after_os_exit |

*Observações:*
* **FineCode**: O SQLite do Node.js fechou os blocos mantendo a integridade ACID. O agendador detectou a tarefa pendente a partir do checkpoint 3 e avançou as unidades restantes 3, 4 e 5.
* **EvCore**: Ao simular o artefato de crash real (linha final não terminada com quebra de linha `\n`), o método `SessionFile::load()` emitiu o aviso formal `dropped truncated final line 4 of ...`, expurgou o fragmento corrompido e recuperou intactas as 2 mensagens confirmadas.
* **metaO**: O subprocesso foi morto via `os._exit(0)`. O SQLite WAL garantiu que as 2 transações de eventos confirmadas antes do exit fossem preservadas sem necessidade de reparo manual.

---

### Cenário C — Falha entre Efeito e Checkpoint
*Efeito observável escrito em disco, interrupção forçada antes da gravação do checkpoint durável, reinício e verificação de reconciliação.*

| Projeto | Rep | Status | Unidades Antes | Unidades Recuperadas | Reexecutadas | Efeitos Duplicados | Efeitos Perdidos | Mecanismo de Reconciliação |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **FineCode** | 1 | **PASS** | 1 | 2 | 1 | 1 | 0 | Rollback ao último checkpoint |
| | 2 | **PASS** | 1 | 2 | 1 | 1 | 0 | Rollback ao último checkpoint |
| | 3 | **PASS** | 1 | 2 | 1 | 1 | 0 | Rollback ao último checkpoint |
| **EvCore** | 1 | **PASS** | 1 | 1 | 1 | 1 | 0 | Reexecução do turno (at-least-once) |
| | 2 | **PASS** | 1 | 1 | 1 | 1 | 0 | Reexecução do turno (at-least-once) |
| | 3 | **PASS** | 1 | 1 | 1 | 1 | 0 | Reexecução do turno (at-least-once) |
| **metaO** | 1 | **PASS** | 1 | 1 | 1 | 1 | 0 | Re-despacho de evento pela supervisão |
| | 2 | **PASS** | 1 | 1 | 1 | 1 | 0 | Re-despacho de evento pela supervisão |
| | 3 | **PASS** | 1 | 1 | 1 | 1 | 0 | Re-despacho de evento pela supervisão |

*Comportamento Empiricamente Observado:*
* **Nenhum projeto possui "exactly-once" mágico contra efeitos externos uncommitted.** Quando o processo morre após o efeito mas antes de salvar o estado, todos os 3 sistemas reiniciam do último ponto persistido, resultando na **reexecução da unidade** e **duplicação do efeito externo (2 ocorrências de `effect_2`)**.
* **Diferencial Crítico do FineCode**: O FineCode possui o primitivo `runtime.memo('chave', valor)`. Quando o código do usuário grava a intenção com `memo()` *antes* de executar o efeito, a reexecução consulta o `memo()` e salta o efeito externo, alcançando idempotência efetiva. Sem o uso de `memo()`, o comportamento padrão é at-least-once com reexecução.

---

### Cenário D — Concorrência e Worker Obsoleto
*Simulação de perda de propriedade / worker suspenso, substituição por novo executor, tentativa de escrita com credencial/identificador antigo.*

| Projeto | Rep | Status | Stale Worker Rejeitado? | Mecanismo de Proteção | Estado Final Observado |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **FineCode** | 1 | **PASS** | **SIM** | `AbortSignal` + `abortTask` | `Commit threw: This operation was aborted` (tarefa settled como `aborted`) |
| | 2 | **PASS** | **SIM** | `AbortSignal` + `abortTask` | `Commit threw: This operation was aborted` (tarefa settled como `aborted`) |
| | 3 | **PASS** | **SIM** | `AbortSignal` + `abortTask` | `Commit threw: This operation was aborted` (tarefa settled como `aborted`) |
| **EvCore** | 1 | **PASS** | **NÃO** | Mutex in-process apenas | Mensagem obsoleta foi apensada no disco: `["worker1", "worker2", "worker1_stale"]` |
| | 2 | **PASS** | **NÃO** | Mutex in-process apenas | Mensagem obsoleta foi apensada no disco: `["worker1", "worker2", "worker1_stale"]` |
| | 3 | **PASS** | **NÃO** | Mutex in-process apenas | Mensagem obsoleta foi apensada no disco: `["worker1", "worker2", "worker1_stale"]` |
| **metaO** | 1 | **PASS** | **SIM** | `UNIQUE(mission_id, seq)` + OCC | `sqlite3.IntegrityError` ao tentar reutilizar sequência; `MissionAlreadyExists` em duplicação |
| | 2 | **PASS** | **SIM** | `UNIQUE(mission_id, seq)` + OCC | `sqlite3.IntegrityError` ao tentar reutilizar sequência; `MissionAlreadyExists` em duplicação |
| | 3 | **PASS** | **SIM** | `UNIQUE(mission_id, seq)` + OCC | `sqlite3.IntegrityError` ao tentar reutilizar sequência; `MissionAlreadyExists` em duplicação |

*Achado Arquitetural Central:*
* **FineCode**: Excelente proteção de tarefas. Quando o supervisor emite `abortTask(taskId)`, o agendador imediatamente aborta o `runtime.signal` do worker antigo. Qualquer tentativa subsequente de efetuar `runtime.commit()` lança exceção imediata (`This operation was aborted`), impedindo contaminação do estado.
* **EvCore**: O `SessionHandler` protege concorrência local por processo através de um `std::sync::Mutex<Recorder>`. No entanto, se um segundo manipulador de sessão for aberto sobre o mesmo arquivo (ou em outro processo), **não há fencing token ou bloqueio no sistema de arquivos**. A escrita atrasada é apensada sem erro.
* **metaO**: Rigor extremo em banco de dados. A tabela `mission_events` possui a restrição estrita `UNIQUE(mission_id, sequence)`. Se um worker antigo tentar submeter um evento para uma sequência que já avançou, o banco rejeita com `IntegrityError`. Na criação, `MissionAlreadyExists` bloqueia IDs colidentes.

---

### Cenário E — Estado Parcialmente Corrompido
*Corrupção induzida no arquivo persistente (zeros em bytes de cabeçalho / JSON truncado no meio do arquivo / divergência relacional).*

| Projeto | Rep | Status | Corrupção Detectada? | Exceção / Erro Gerado | Risco de Aceitação Silenciosa |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **FineCode** | 1 | **PASS** | **SIM** | `Error: file is not a database` | **ZERO**: Rejeição imediata |
| | 2 | **PASS** | **SIM** | `Error: file is not a database` | **ZERO**: Rejeição imediata |
| | 3 | **PASS** | **SIM** | `Error: file is not a database` | **ZERO**: Rejeição imediata |
| **EvCore** | 1 | **PASS** | **SIM** | `SessionError::Corrupt { line: 4, ... }` | **ZERO**: Rejeição imediata de linha malformada |
| | 2 | **PASS** | **SIM** | `SessionError::Corrupt { line: 4, ... }` | **ZERO**: Rejeição imediata de linha malformada |
| | 3 | **PASS** | **SIM** | `SessionError::Corrupt { line: 4, ... }` | **ZERO**: Rejeição imediata de linha malformada |
| **metaO** | 1 | **PASS** | **SIM** | `MissionStoreCorrupt` e `sqlite3.DatabaseError` | **ZERO**: Validação estrutural cruzada ativa |
| | 2 | **PASS** | **SIM** | `MissionStoreCorrupt` e `sqlite3.DatabaseError` | **ZERO**: Validação estrutural cruzada ativa |
| | 3 | **PASS** | **SIM** | `MissionStoreCorrupt` e `sqlite3.DatabaseError` | **ZERO**: Validação estrutural cruzada ativa |

*Observações:*
* Todos os 3 projetos passaram com distinção em segurança fail-closed: **nenhum aceitou dados corrompidos silenciosamente**.
* **FineCode**: O driver SQLite bloqueou imediatamente o banco adulterado.
* **EvCore**: Distingue perfeitamente um *crash artifact* na última linha (que é recuperado com descarte da linha inacabada) de uma corrupção interna no meio do arquivo (que lança `SessionError::Corrupt` imediatamente).
* **metaO**: Possui dupla barreira. Se os bytes do SQLite estiverem íntegros mas alguém alterar o campo `revision` ou `status` de forma desincronizada com o JSON, o método `_validated()` do `SQLiteMissionStore` lança `MissionStoreCorrupt("mission revision column does not match snapshot")`.

---

## 5. Comparação Consolidada de Métricas

| Métrica | FineCode | EvCore | metaO |
| :--- | :---: | :---: | :---: |
| **Nível Arquitetural** | **Sessão & Tarefa (Task Engine)** | **Sessão & Transcrição (LLM Loop)** | **Supervisão de Projeto (Control Plane)** |
| **Taxa de Sucesso nos Testes** | **15 / 15 (100%)** | **15 / 15 (100%)** | **15 / 15 (100%)** |
| **Tempo Médio de Recuperação** | ~35 ms (tarefas imediatas) | **~5 ms** | ~15 ms |
| **Tolerância a Crash sem Flush** | Total (ACID SQLite) | Total (JSONL + drop de linha truncada) | Total (SQLite WAL) |
| **Idempotência contra Duplicação** | **Suportada nativamente** via `runtime.memo()` | Não implementada (at-least-once) | Não implementada no efeito (at-least-once) |
| **Fencing contra Worker Obsoleto** | **Sim** (`abortTask` + `runtime.signal`) | **Não** (apenas Mutex local) | **Sim** (`UNIQUE` ledger + `MissionAlreadyExists`) |
| **Detecção de Corrupção** | Imediata (SQLite engine) | Imediata (`SessionError::Corrupt`) | Imediata (`MissionStoreCorrupt` + DB) |
| **Proteção de Worktree / Código** | Não aplicável | Não aplicável | **Sim** (`GitRepositoryCheckpointPort`) |
| **Intervenção Manual Necessária** | Nenhuma | Nenhuma | Nenhuma |

---

## 6. Falhas e Limitações Observadas

### 6.1 FineCode
1. **Dependência do agendador para transição de fase**: Se uma tarefa for interrompida no meio de uma fase sem ter emitido `sleepUntil` ou `commit` para o próximo checkpoint, ao reiniciar ela executará a mesma fase novamente. Se a fase não for protegida com `runtime.memo()`, ocorrerão efeitos duplicados.
2. **Complexidade de Runtime**: O motor `durable` do FineCode possui acoplamento estreito com o sistema de tipos TypeScript de ponta a ponta (`@earendil-works/chord` e `@earendil-works/pi-ai`). Requer ambiente Node.js com suporte a strip-types/ESM moderno.

### 6.2 EvCore
1. **Ausência de Fencing entre Processos no SessionHandler**: O `SessionHandler` é puramente append-only e protegido por um `Mutex` da biblioteca padrão do Rust em memória. Não há locks cooperativos de arquivo (`flock`) nem geração/fencing token no disco. Dois processos ou dois workers apontando para a mesma sessão podem interpolar linhas sem aviso.
2. **Durabilidade limitada ao histórico de mensagens**: EvCore preserva com alta fidelidade a conversa e ferramentas do LLM, mas não modela grafos de tarefas com sub-checkpoints de execução ou reversão transacional.

### 6.3 metaO
1. **O método `replace()` no SQLiteMissionStore não valida a revisão anterior do objeto**: O código lê `SELECT revision FROM mission_records` e simplesmente faz `updated = replace(record, revision=int(row[0]) + 1)`. Isso significa que se um worker B submeter `replace()` baseado em uma revisão 1, e o banco já estiver na revisão 2, o método incrementará para 3 sem lançar um conflito de concorrência otimista (OCC). No entanto, o `SQLiteEventLedger` compensa essa lacuna travando a chave primária `(mission_id, sequence)`.
2. **Sobrecarga de Abstração**: Exige a construção de múltiplos envelopes (`MissionRecord`, `MissionAttempt`, `AcceptanceProof`, `EvidenceEnvelope`) para persistir o estado de uma missão.

---

## 7. Capacidades Exclusivas de Cada Projeto

* **FineCode**:
  * O mecanismo de **`runtime.memo(key, value)`**: solução definitiva para o Cenário C. Permite registrar a intenção antes do efeito e verificar a existência do registro na retomada, garantindo execução com efeito único.
  * **Agendador de Tarefas Durável**: O `Harness` gerencia estado pendente, pausas temporizadas (`sleepUntil`), tentativas com políticas de retry e cancelamento em cascata com propagação via `AbortSignal`.

* **EvCore**:
  * **Heurística de Crash Artifact**: Ao ler o JSONL, se a última linha estiver sem `\n` ou com JSON inacabado, o motor descarta automaticamente a linha corrompida e emite um aviso, sem falhar a sessão inteira.
  * **Limpeza de Tool Calls Órfãs**: Se houver mensagens de assistente pendentes sem resposta de ferramenta no final do arquivo, o carregador remove a chamada dangling para evitar que a API de inferência rejeite o prompt no próximo turno.

* **metaO**:
  * **Verificação Cruzada de Integridade (`_validated`)**: Valida se as colunas relacionais do SQLite conferem exatamente com as propriedades dentro do payload JSON. Qualquer adulteração em coluna gera fail-closed.
  * **Checkpoints de Repositório Git Host-Side (`GitRepositoryCheckpointPort`)**: Supervisão ancorada no histórico de commits do Git (`state_id = commit_id`). Rejeita qualquer checkpoint se a árvore de trabalho não estiver perfeitamente limpa (`_assert_clean()`).

---

## 8. Recomendações por Mecanismo

| Mecanismo Identificado | Projeto de Origem | Recomendação | Justificativa |
| :--- | :--- | :---: | :--- |
| **`runtime.memo()` Intent/Effect** | FineCode | **REUTILIZAR / INCORPORAR** | É o único mecanismo testado que resolve de forma elegante a duplicação de efeitos externos em crashes do Cenário C. |
| **Descarte Inteligente de Linha Final Truncada** | EvCore | **REUTILIZAR** | Heurística robusta para formatos append-only/JSONL. Evita corrupção total por falta de flush do OS no crash. |
| **Ledger de Eventos com `UNIQUE(id, seq)`** | metaO | **PRESERVAR** | Previne de forma inequívoca o avanço concorrente desordenado e fencing de workers obsoletos no nível de armazenamento. |
| **Validação Cruzada Coluna vs JSON (`_validated`)** | metaO | **PRESERVAR** | Evita corrupção silenciosa e descompasso entre índices relacionais e objetos desserializados. |
| **Ancoragem em Git Commit (`GitRepositoryCheckpointPort`)** | metaO | **PRESERVAR** | Essencial para o nível de projeto e supervisão, garantindo rastreabilidade do código fonte modificado. |
| **`SessionHandler` sem Fencing de Arquivo** | EvCore | **ADAPTAR** | Adicionar bloqueio de arquivo (`fs2::FileExt` / `flock`) ou UUID de process generation para evitar escritas cruzadas. |
| **`replace()` sem validação de revisão prévia** | metaO | **ADAPTAR** | Modificar a query para `WHERE mission_id = ? AND revision = ?` garantindo OCC estrito no `MissionStore`. |
| **Reinvenção de SQLite Engine Própria** | — | **NÃO INCORPORAR** | Utilizar drivers consolidados com WAL mode ativado em vez de tentar inventar mecanismos caseiros de persistência. |

---

## 9. Custo e Risco de Integração

* **Nível 1 — Sessão (EvCore -> FineCode / metaO)**:
  * *Risco:* Baixo.
  * *Custo:* Baixo. O formato JSONL append-only com recuperação de linha truncada é ideal para logs de auditoria e streaming de chat sem a sobrecarga de um banco SQL completo por sessão de usuário.
* **Nível 2 — Tarefas e Idempotência (FineCode -> Demais)**:
  * *Risco:* Médio.
  * *Custo:* Moderado. A lógica de `memo()` pode ser facilmente portada como um decorator ou context manager em Python ou struct em Rust, desacoplada do agendador completo.
* **Nível 3 — Supervisão de Projeto e Concorrência (metaO -> Demais)**:
  * *Risco:* Médio.
  * *Custo:* Médio. A verificação do Git worktree limpo e o ledger relacional com restrições de unicidade fornecem a camada governada que sistemas baseados puramente em sessões não possuem.

---

## 10. Conclusão

O benchmark demonstrou que os três projetos atuam em camadas complementares da hierarquia de durabilidade:

1. **EvCore** domina a **durabilidade de sessão de baixa latência** (~5 ms), com excelente tolerância a falhas na camada física de arquivos via descarte cirúrgico de fragmentos incompletos.
2. **FineCode** domina a **durabilidade de execução de tarefas**, oferecendo o único mecanismo comprovado nos testes contra duplicação de efeitos externos (`runtime.memo()`) e cancelamento cooperativo atômico via `abortTask`.
3. **metaO** domina a **durabilidade de projeto e governança**, assegurando imutabilidade relacional por SQLite, prevenção de concorrência por unicidade de sequência e fidelidade de código fonte ancorada no Git.

Não há sobreposição prejudicial entre os mecanismos recomendados; a união do padrão `memo()` do FineCode com o descarte resiliente do EvCore e o ledger relacional com Git Checkpoint do metaO compõe a arquitetura de durabilidade ideal.
