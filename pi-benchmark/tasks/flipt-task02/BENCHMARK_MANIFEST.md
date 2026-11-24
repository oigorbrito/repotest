# BENCHMARK MANIFEST — TASK 02 / Flipt (versão 2, após correções da auditoria)

**Instância:** `instance_flipt-io__flipt-e2bd19dafa7166c96b082fb2a59eb54b4be0d778`
**Repositório:** `flipt-io/flipt` (Go) · **Commit base:** `0eaf98f050d86247bfe9bd7e41178865cb585060`
**Versão anterior:** auditoria pré-execução com 6 FAIL (preservada em `evidence/audit/AUDIT_PRE_RUN.md`).

## 0. Estado

| Item | Estado |
|---|---|
| Ambientes dos agentes (cópias, SHA, isolamento por construção) | PASS |
| Prompts nativos, mesmas flags de modelo/provedor/raciocínio | PASS |
| Coleta automática (tokens, cache, custo, ferramentas, tempo, código de saída) | PASS para Pi original (documentado + sessão real); **pendente** para Pi-Rust (ver §5) |
| Teto de custo US$ 1 e timeout 3.600 s, externos aos dois agentes | PASS (testado com processos artificiais) |
| Detecção de alteração fora do workspace | PASS para o escopo de §6 (sem leitura, sem sandbox) |
| Sorteio da ordem, reproduzível | PASS (`draw-order.json`, verificado) |
| Avaliador: procedimento único | PASS (testado em modo controle) |
| Avaliador: resultado `fail_to_pass` | **BLOCKED** — patch de testes não autorizado (§7) |
| Exclusão do incidente dos dados | PASS (§8) |

**Estado geral: BLOCKED para execução do benchmark completo.** O Pi original pode ser executado como primeiro
agente da ordem sorteada assim que o operador aceitar os riscos de §6. O Pi-Rust só pode rodar após um piloto
autorizado que valide seu formato de saída (§5). Sem o patch de testes (§7), nenhum resultado final é possível.

---

## 1. Caminhos

| Papel | Caminho (relativo a `tasks/flipt-task02/`) |
|---|---|
| Origem (intacta) | `source/` |
| Agente Pi original | `agents/pi-original/flipt/` (cwd da execução) |
| Agente Pi-Rust | `agents/pi-rust/flipt/` (cwd da execução) |
| Avaliador (fora de `agents/`) | `evaluator/` |
| Scripts | `scripts/` |
| Evidências de preparação | `evidence/preparation/` |
| Execuções | `evidence/<agente>/runs/<run-id>/` |
| Controle de testes de infraestrutura | `evidence/infra-tests/` |

## 2. Ambiente

| Item | Valor |
|---|---|
| Sistema | Windows 11 Pro 10.0.26300 · MSYS2/MINGW64 |
| Git | 2.56.0.windows.2 · Go go1.27.0 windows/amd64 (`CGO_ENABLED=0`) |
| Python | 3.12.10 (wrapper, snapshot, sorteio, testes) |
| Node | v26.10.0 (CLI do Pi original) |
| Rust | cargo/rustc 1.99.1 (build do Pi-Rust) |
| Docker | daemon parado (testes Redis indisponíveis) |

### Agentes

| | Pi original | Pi-Rust |
|---|---|---|
| Versão | 1.5.2 | 0.12.16, commit `e9dd2b54ced9114ffa8db182e810ac300eafd67f` |
| Executável | `node` + `C:\Users\igorb\.pi\agent\install\releases\1.5.2\node_modules\@earendil-works\pi-coding-agent\dist\bundle\cli.js` | `tasks/flipt-task02/evidence/preparation/pi-rust-build/release/pi.exe` |
| Hash do executável | `e79626f2dd6f94aa45d30f3fa63cd84319a6eefcd150b353cfaf274366926774` (cli.js) | `700add90227c3adbc8f5d6e9ee2d9131bf89c79c2425a4d9577b72533d1a8ae1` |
| Build | — (distribuição npm, gerenciada pelo launcher) | `cargo build --release --locked -p pi-coding-agent`, árvore limpa; log em `evidence/preparation/pi-rust-build.log` |
| Variáveis de ambiente | `PI_MANAGED_INSTALL_ROOT` definida pelo wrapper (mesma que o launcher usa) | nenhuma extra |

Observação: o Pi original é chamado diretamente pelo `cli.js`, sem o `.cmd` nem o launcher, para evitar
quoting de argumentos do Windows e um processo a mais na árvore encerrada por timeout.

## 3. Prompts, modelo, provedor, parâmetros e contexto

**Prompts nativos preservados:** nenhum dos dois recebe `--system-prompt` nem `--append-system-prompt`.
Cada harness usa seu próprio prompt de sistema. Isso é intencional (autorização do operador) e faz
parte do que é medido. Não é controle de contexto idêntico.

**Mensagem do usuário (idêntica):** `Leia o TASK.md anexado e implemente a tarefa descrita nele, neste repositório.`
com o arquivo `@../TASK.md` anexado (resolvido a partir do cwd, `agents/<agente>/TASK.md`). `TASK.md` tem SHA-256
`097664f8333f5d51e53a8b7943673db7dd67c882b98962afde70c4e0bb58df4c`, idêntico nas três cópias.

**Flags idênticas nas duas CLIs** (conferidas na ajuda de cada uma):

```
--provider anthropic --model claude-haiku-5-5 --thinking medium --mode json
--no-extensions --no-mcp --no-skills --no-prompt-templates --no-themes --no-context-files --no-approve
--session-dir evidence/<agente>/runs/<run-id>/sessions -p @../TASK.md "<mensagem>"
```

| Parâmetro | Valor | Observação |
|---|---|---|
| Provedor | `anthropic` (credencial OAuth, `pi auth check` = `ready` nas duas CLIs) | |
| Modelo | `claude-haiku-5-5` (contexto 1M, saída 128K) | disponível nas duas CLIs |
| Raciocínio | `medium` | |
| Temperatura, max tokens | N/D | não expostos pelas CLIs; idênticos (ausentes) nos dois |
| Extensões, MCP, skills, temas, templates, contexto de projeto | desligados | evita `piBolt` do `settings.json` global no Pi original |
| Aprovação de arquivos de projeto | `--no-approve` | nenhum arquivo de projeto de outra origem é carregado |
| Sessões | `evidence/<agente>/runs/<run-id>/sessions` | isolamento de logs |
| Ambiente | `PI_CODING_AGENT`, `PI_REASONING_LEVEL`, `PI_SESSION_FILE`, `PI_SESSION_ID`, `PI_PROVIDER`, `PI_MODEL` removidas | herdadas desta sessão de preparação; registradas em `env_removed` |

**Contexto:** repositório no commit-base, `TASK.md`, árvore de trabalho limpa. Nenhum `AGENTS.md` ou `CLAUDE.md` no repositório.
O `settings.json` global é lido pelos dois (ex.: `compaction.enabled`); a diferença de comportamento entre os
harnesses não é controlada.

**Limite de ferramentas:** nenhum `--max-turns` nem `--max-cost` (o Pi original não tem essas flags; o Pi-Rust
tem, mas usá-las seria assimetria). Os limites são aplicados pelo wrapper aos dois.

## 4. Limites financeiro e de tempo (externos, aplicados pelo wrapper)

| Limite | Valor | Mecanismo |
|---|---|---|
| Custo por execução | **US$ 1,00** | soma de `message_end.message.usage.cost.total` mais o custo parcial em andamento (`message_update`); ao atingir o teto, `taskkill /F /T` na árvore |
| Tempo de parede | **3.600 s** | mesmo `taskkill`; registrado como `termination_reason = timeout` |
| Execução | **sequencial** | lock em `evidence/infra-tests/run.lock` (O_EXCL) e gate de ordem (§9) |

Limitação do teto: o custo de uma mensagem só é conhecido quando ela termina (ou pelo parcial do `message_update`).
Se o último turno for caro, o teto pode ser ultrapassado. O resultado registra `cost_cap_exceeded` quando isso acontece.
Se um provedor não informar custo, o controle fica `partial` ou `unavailable` e isso é registrado. O wrapper não
presume zero.

## 5. Coleta de métricas e seus limites

Executada por `scripts/run-agent.py`, que lê o stdout JSON em tempo real. Gera `evidence/<agente>/runs/<run-id>/`:

| Arquivo | Conteúdo |
|---|---|
| `stdout.raw`, `stderr.raw` | bytes exatos emitidos pela CLI |
| `result.json` | UTC de início e fim, duração, código de saída, `status`, `termination_reason`, tokens, cache, custo, ferramentas por tipo, `cost_control`, `cost_cap_exceeded`, mensagens do assistente, linhas não-JSON, bytes, erros, `env_removed` |
| `snapshot-pre.json`, `snapshot-post.json`, `isolation-diff.json` | §6 |
| `sessions/` | sessão nativa do agente |

Campos e origem por agente: `scripts/AGENT_SCHEMAS.md`.

**Pi original:** formato de `message_end`, `usage` (`input`, `output`, `cacheRead`, `cacheWrite`, `totalTokens`,
`cost.total`), `tool_execution_start.toolName`, `agent_end`, `agent_settled` — documentados em `docs/json.md` e
`docs/message-types.md`, e os campos de `usage` confirmados numa sessão real de 3 turnos.

**Pi-Rust:** mesmos nomes de evento e campos camelCase, confirmados **por leitura do código-fonte** do commit
`e9dd2b54` (`pi-ai/src/types.rs`, `pi-agent/src/types.rs`, `pi-coding-agent/src/agent_session/events.rs`).
**Não validado em execução real**: não há saída gravada do Pi-Rust. O wrapper recusa o Pi-Rust sem
`--allow-unvalidated-usage`. Validar exige um piloto autorizado, cuja saída seja comparada a `AGENT_SCHEMAS.md`.

**Métricas indisponíveis (nunca gravadas como zero):** temperatura, max tokens (não expostos); `reasoning`
quando ausente; `cacheWrite` quando ausente no evento; custo quando ausente. Tempo é o do wrapper (não há
timestamp por turno além do próprio stream).

**Não coletado:** tokens de cache do Pi-Rust (até a validação), custo por ferramenta, tempo por turno.

## 6. Isolamento

Ferramenta: `scripts/snapshot.py` (chamada por `run-agent.py` e por `scripts/check-isolation.sh`).

**Escopo do snapshot** (SHA-256 e metadados, ~3.500 entradas):
- todo o conteúdo de `tasks/flipt-task02/` (inclui `source/`, `agents/`, `evaluator/`, `scripts/`, manifests);
- `~/.pi/agent/` compartilhado: `auth.json`, `settings.json`, `models.json`, `models-store.json`,
  `prompt-history.jsonl`, `crashes.json` e a lista (sem hash) de `sessions/`.

**Excluídos** (artefatos de controle, cada um com motivo): `evidence/<agente>/runs/**` (saída da própria execução),
`evaluator/work/`, `evaluator/results/`, `evidence/infra-tests/`, `evidence/preparation/snapshot-*.json`,
`evidence/preparation/isolation-check-*`, `evidence/preparation/pi-rust-build/` (artefatos de build; a identidade
do binário está em §2), `__pycache__`, `.git/index` e `*.lock` (metadados do git que mudam com `git status`).

**Regra:** antes de cada execução, o snapshot deve ser idêntico ao baseline (senão a execução é recusada, código 5).
Após a execução, toda alteração fora de `agents/<agente>/flipt/` e `evidence/<agente>/` é **divergência**,
registrada em `isolation-diff.json`. Nada é restaurado nem apagado automaticamente.

**Limitações, declaradas:**
1. **Não é sandbox de segurança.** Os dois agentes rodam como `igorb`. Um agente pode ler o clone do outro, o
   avaliador e o patch de testes (se existirem). O snapshot detecta **alterações**, não **leituras**.
2. Alterações feitas por outro processo do usuário (ex.: uso do Pi em outro projeto) aparecem como divergências
   de `~/.pi/agent/sessions/` ou de `prompt-history.jsonl`. Não usar o Pi em paralelo durante uma execução.
3. Alterações dentro de `evidence/<agente>/` (fora de `runs/`) são permitidas por construção.
4. Não há isolamento de rede: o agente pode acessar a internet e consultar a implementação pública. A regra
   é do `TASK.md`, sem bloqueio técnico.

Isolamento real (recomendado antes de resultados publicáveis): executar cada agente com outro usuário do
Windows, sem permissão de leitura sobre `evaluator/` e sobre o outro clone, ou em contêiner (Docker parado).

## 7. Avaliação

Ferramenta: `evaluator/evaluate.py`, única para os dois agentes. Documentação completa: `evaluator/README.md`.

1. Confere `base_commit` e HEAD do clone.
2. Copia a árvore final (sem `.git`) para `evaluator/work/`.
3. Aplica `evaluator/private/test.patch` com `git apply`. **Ausente: resultado `BLOCKED` (código 3).**
4. `go test -json -count=1 -run '^(ids)$' ./...`, timeout 1.800 s.
5. Classifica cada identificador em `PASS`, `FAIL`, `NOT_RUN` ou `SKIP`. `resolved` exige todos os `fail_to_pass`
   em `PASS`, nenhum timeout e todos os `pass_to_pass` em `PASS`.

**Identificadores obtidos** (`evaluator/test-identifiers.json`, do dataset `ScaleAI/SWE-bench_Pro`):
`fail_to_pass` = 10 nomes; `pass_to_pass` = 0 nomes. Nenhum dos 10 existe no commit-base (verificado).

**Verificação no Windows (modo controle):** execução `control-1` com 4 identificadores existentes gerou
PASS, PASS, PASS e NOT_RUN, com os pacotes sem cgo listados em `build_failed_packages`
(`evaluator/results/control-1/control/result.json`). Não é resultado do benchmark.

**Resultado do benchmark:** `BLOCKED` (`test_patch_missing`). Não há resultado inferido.

## 8. Exclusão do incidente anterior

Em 2026-11-18 (~18:19), o Pi original recebeu uma chamada de modelo acidental (`pi doctor` inexistente). Custo
US$ 0,00078, 3 turnos, 2 leituras de `bash`, nenhuma alteração no repositório. Detalhes em
`evidence/preparation/INCIDENT-pi-original-doctor.md`.

**Excluído dos dados experimentais por construção e por regra:**
- sessão do incidente no diretório padrão `~/.pi/agent/sessions/…-pi-original-flipt--/`, que **não** é usado pelas execuções;
- o incidente não tem `runs/<run-id>/` e não contribui para nenhum `result.json`;
- `evidence/pi-original/run-record.json` o registra em `pre_run_incidents`, separado;
- nenhum comando de agregação deve somar esse diretório. `pi stats` não existe no Pi original 1.5.2.

**Ressalva:** o custo de US$ 0,00078 já está na conta do provedor. Qualquer total de custo da conta deve
subtrair esse valor e registrar a subtração.

Regras: nunca usar `--continue` ou `--resume`; nunca usar o diretório padrão de sessões.

## 9. Sorteio e ordem

Script: `scripts/draw-order.py`. Algoritmo: `random.Random(seed).shuffle()` sobre `["pi-original", "pi-rust"]` (Mersenne
Twister, CPython 3.12.10).

| Campo | Valor |
|---|---|
| Semente | `16561843088153416046` (gerada por `secrets.randbits(64)` e gravada) |
| Resultado | **1º pi-original, 2º pi-rust** |
| Arquivo | `evidence/preparation/draw-order.json` |
| Reprodução | `python scripts/draw-order.py verify evidence/preparation/draw-order.json` → `reproduzivel=True` |

**Gate:** `run-agent.py` recusa (código 6) um agente fora da ordem. Um agente é considerado concluído quando
existe `runs/<run-id>/result.json`. Um segundo agente só roda depois do primeiro.

## 10. Procedimento de execução (somente após liberação do operador)

Variáveis limpas no terminal:

```powershell
Remove-Item Env:PI_CODING_AGENT,Env:PI_REASONING_LEVEL,Env:PI_SESSION_FILE,Env:PI_SESSION_ID,Env:PI_PROVIDER,Env:PI_MODEL -ErrorAction SilentlyContinue
```

Passos, para cada agente em ordem:

```bash
cd /d/projetos/pi-benchmark/tasks/flipt-task02
python scripts/check-isolation.sh evidence/preparation/isolation-pre-<id>.txt  # deve estar OK
python scripts/run-agent.py --agent pi-original --run-id <id>                  # ou pi-rust (com --allow-unvalidated-usage após piloto)
python evaluator/evaluate.py --agent pi-original --run-id <id> --clone agents/pi-original/flipt   # BLOCKED até test.patch
```

Após a execução: `check-isolation.sh` (o agente que acabou de rodar terá árvore suja; isso é esperado e
registrado em `result.json` e no `git diff` salvo pelo operador). O outro agente deve permanecer OK.

**Uma execução por vez.** Lock e gate impedem paralelismo e ordem errada, mas não impedem o operador de
rodar um agente manualmente sem o wrapper. Isso não deve ocorrer.

## 11. Estado das correções da auditoria

| Item da auditoria | Correção aplicada | Verificação |
|---|---|---|
| 1. Comandos aplicáveis | flags conferidas nas duas ajudas; comando único no wrapper (`build_cmd`) | `test_dry_run_builds_same_flags_for_both_agents` |
| 2. Modelo/contexto | prompts nativos preservados; limitação declarada (§3) | flags idênticas (teste) |
| 3. Isolamento de diretórios | limitações declaradas (§6) | snapshot + `check-isolation.sh` |
| 4. Coleta | `run-agent.py` + `AGENT_SCHEMAS.md`; Pi-Rust pendente de piloto | 10 testes de coleta e monitoramento com processos artificiais |
| 5. Controle de custo e timeout | externos, aplicados aos dois | `T2Timeout`, `T3CostCap` (3 casos), `cost_cap_exceeded` |
| 6. Detecção fora do workspace | snapshot completo + exclusões justificadas | `T5ProtectedFileChange` (3 casos) |
| 7. Sorteio | `draw-order.py` com semente gravada + verificação | `T9Draw`; gate em `run-agent.py` (teste e CLI) |
| 8. Incidente excluído | sessões separadas; regra explícita (§8) | diretório de execução inexistente para o incidente |
| Avaliador | `evaluator/` criada; identificadores obtidos; procedimento único | `T10EvaluatorParser` (5 testes); controle `control-1`; bloqueio `blocked-check-1` |
| Gate de ordem, lock e fluxo completo | gates em `run-agent.py`; integração com clone real | `T11OrderAndLock` (3); `test_integration.py` (6) |

Testes: 32 no total. `scripts/tests/test_infra.py` (26: processos artificiais e entradas sintéticas) e
`scripts/tests/test_integration.py` (6: fluxo completo de `run-agent.main` com clone real do commit-base e agente artificial).
Resultado: `evidence/infra-tests/run-12.log` (OK, 32 testes).

## 12. Bloqueios remanescentes

1. **Patch de testes de referência não autorizado.** Sem ele, `fail_to_pass` (10 testes, inexistentes no base)
   não é executável. Resultado final: `BLOCKED`.
2. **Formato de saída do Pi-Rust não validado em execução.** Exige piloto autorizado (chamada real ao modelo).
3. **Isolamento por convenção** (§6). Recomendado: usuário Windows separado ou contêiner.
4. **Docker parado** e **sem cgo**: o baseline da tentativa 2 (`tasks/flipt-task02/BASELINE_REPORT.md`) lista os pacotes
   afetados. Não impedem a execução, mas impedem a compilação de `internal/cmd` no avaliador.
5. **Relógio do Windows** faz `internal/server/middleware/grpc` e `internal/server/auth` falharem por ambiente.
   Esses testes devem ser lidos com esse contexto.

## 13. Hashes dos arquivos relevantes

Arquivo completo: `evidence/preparation/hashes-final.txt` (gerado antes desta versão do manifesto; o próprio manifesto
e os snapshots não estão incluídos).

| Arquivo | SHA-256 |
|---|---|
| `scripts/run-agent.py` | `79a9a21f8867370fa23cbcc756e305c294f01ccbe3c256be10f5782dc8b87d97` |
| `scripts/snapshot.py` | `392994300baa0bf25c83b03c590942d54e12ee6e9992a4c20fb7c615cb2d4198` |
| `scripts/draw-order.py` | `3e95ef90e2d55fa7bff131c465ac908a98fdf864354f5fa9789fba3cccad95de` |
| `scripts/check-isolation.sh` | `f7fa8b9d6ef6c6720455de30af569a00e7b20be03b1d4e39f4f08d0f06010b0a` |
| `scripts/AGENT_SCHEMAS.md` | `b8a49b696400bf28f77d5b70f34b7e1d179c52288c8fec309be9bfabd6a893a6` |
| `scripts/tests/test_infra.py` | `94affe3f82574d0528c86d6a5169e16c8fb786898745faa8258814e89ccb0033` |
| `scripts/tests/test_integration.py` | `5050fd784480f5cfb34762517608d574a600a0af51356a6889c3ac59f9c51f47` |
| `scripts/tests/fake_agent.py` | `07a67bad669851b3e809a32f69d3af8b393421b6f2536beccaf60bb475e62f05` |
| `evaluator/evaluate.py` | `aa0d19d39b0f54e68199e43b39f6cfd504d65fcf7a1018db152375a1faed715a` |
| `evaluator/README.md` | `8073224f6b3cad391502f7f7396d548326b20c87268be2410249171cb359e9c0` |
| `evaluator/test-identifiers.json` | `f1a26cdf1d975b01ff339841e764b11e540aa012ddcd84088627a498093a9252` |
| `evidence/preparation/draw-order.json` | `091fd884d7e4a36723ef088c4e15d4cb963f57199029af22016995155faaf54e` |
| `TASK.md` (e cópias em `agents/*/`) | `097664f8333f5d51e53a8b7943673db7dd67c882b98962afde70c4e0bb58df4c` |
| Pi-Rust `pi.exe` | `700add90227c3adbc8f5d6e9ee2d9131bf89c79c2425a4d9577b72533d1a8ae1` |
| Pi original `cli.js` | `e79626f2dd6f94aa45d30f3fa63cd84319a6eefcd150b353cfaf274366926774` |
| `source/` HEAD | `0eaf98f050d86247bfe9bd7e41178865cb585060` |
