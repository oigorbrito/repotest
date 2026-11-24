# Auditoria final pré-execução — TASK 02 (`BENCHMARK_MANIFEST.md`)

Escopo: somente leitura. Nenhum agente foi iniciado. Nenhum arquivo de agente, do projeto de teste ou manifesto foi alterado. Único arquivo novo: este relatório. Um espelho de teste (`evidence/audit/iso-mirror/`) foi criado para testar o script de isolamento e removido ao final.

## Tabela

| # | Critério | Resultado | Evidência principal | Correção necessária |
|---|---|---|---|---|
| 1 | Seção Comandos aplicável aos dois agentes | **PASS** | Todas as flags usadas aparecem na ajuda das duas CLIs (`--provider`, `--model`, `--thinking`, `--mode`, `--no-extensions`, `--no-mcp`, `--no-skills`, `--no-prompt-templates`, `--no-themes`, `--no-context-files`, `--no-approve`, `--session-dir`, `-p`). `@path` é resolvido a partir do cwd (`pi/docs/cli.md:37,41`). Ressalva: o comando do Pi-Rust não foi executado (regra desta etapa) | Nenhuma. Validar com um piloto controlado antes do lote, se aprovado |
| 2 | Modelo, provedor, parâmetros e contexto idênticos | **FAIL** (parcial) | Modelo, provedor e `--thinking medium` são iguais. Temperatura e max tokens: N/D nos dois. **Contexto de sistema não é controlado**: cada harness usa seu próprio system prompt. O `settings.json` global (`compaction.enabled=true`) é lido pelos dois (`pi-rust/.../acp/settings.rs`), mas a política de compactação não foi comparada | Decidir: (a) impor o mesmo `--system-prompt` nos dois, ou (b) declarar explicitamente que o prompt de sistema faz parte do harness medido. Registrar o `settings.json` efetivo de cada um |
| 3 | Diretórios de trabalho isolados | **FAIL** | cwd correto em cada agente; `--session-dir` separa sessões. Porém: (i) ambos rodam como `igorb` e as pastas ficam sob `agents/`, então um agente lê o clone do outro; (ii) `auth.json` é compartilhado; (iii) `~/.pi/agent/prompt-history.jsonl` é global no Pi original. O manifesto afirma isolamento sem ressalva suficiente | Ver item 6. Declarar no manifesto que o isolamento é por convenção. Como correção forte: executar cada agente sob outro usuário Windows ou contêiner (Docker está parado) |
| 4 | Coleta de tokens, cache, custo, ferramentas, tempo e resultado | **FAIL** | Original: `usage` com `input`, `output`, `cacheRead`, `cacheWrite`, `cost.total` confirmado no incidente; `tool_execution_end` com `durationMs`; `agent_settled` (`docs/json.md`). Pi-Rust: mesmos nomes de evento no código (`agent_session/events.rs:130,183`) e `cacheRead` nas estatísticas, mas **o formato exato de `usage` no stdout JSON não foi verificado**. **Tempo**: só manual, sem timestamp automático. **Resultado final**: `N/D`, sem oráculo de teste definido (ver item 7). **Custo total**: o manifesto cita `pi stats --json`, mas essa opção **não existe** no Pi original 1.5.2 (`Error: Unknown option: --json`) | Criar um coletor que grave, por execução, horário de início e fim, somatório dos `usage` do stdout e das sessões, contagem de `tool_execution_start`, código de saída e resultado dos testes. Atualizar a fonte de custo do manifesto. Validar o formato do Pi-Rust antes do lote |
| 5 | Controle externo de custo e timeout | **FAIL** | Pi original sem `--max-cost`/`--max-turns` (ajuda). Timeout é "controlado pelo operador" (manual). Nenhum processo externo encerra a execução | Criar um wrapper que: inicie o processo, conte o tempo e encerre com `Stop-Process` ao exceder 3600 s; acumule `usage.cost.total` do stdout JSON e encerre ao passar do teto; registre o motivo do encerramento. Opcional: limite de gasto na conta do provedor (não verificado aqui). Teto de custo continua **DECISÃO PENDENTE** |
| 6 | Verificação de isolamento detecta alterações fora do workspace | **FAIL** | Teste com espelho descartável: T1 limpo → exit 0 (correto). T2 arquivo não rastreado no clone → exit 1 (detectado). T3 alteração rastreada → exit 1 (detectado). **T4 alteração em `agents/pi-rust/TASK.md` (fora do clone) → exit 0 (não detectado).** **T5 arquivo novo em `agents/pi-rust/` → exit 0 (não detectado).** | Estender `scripts/check-isolation.sh` para um snapshot de metadados (caminho, tamanho, mtime, SHA-256) de todo `tasks/flipt-task02/` excluindo apenas o clone do agente em execução e `evidence/<agente>/`. Incluir hash dos `TASK.md`. Para `~/.pi` e `~/.cargo`, registrar snapshot antes e depois (escopo a definir) |
| 7 | Sorteio da ordem registrável e reproduzível | **FAIL** | O manifesto só diz "sugestão: sorteio registrado". Não há script, semente nem registro | Criar `scripts/draw-order.py` com semente gravada antes do sorteio (ex.: `random.Random(seed).shuffle`), saída em `evidence/preparation/order.json` com semente, data e lista. Reexecutar com a mesma semente deve gerar a mesma ordem |
| 8 | Incidente anterior excluído dos dados | **PASS** (com ressalva) | Sessões em `--session-dir` separado (`evidence/<agente>/sessions`); incidente em `~/.pi/agent/sessions/…pi-original-flipt--` (diretório padrão, mesmo cwd). `--continue` não é usado. `run-record.json` marca o incidente em `pre_run_incidents` separado. Custo US$ 0,00078 **já está na conta do provedor** | Adicionar regra explícita no manifesto: (a) nunca usar o diretório padrão de sessões; (b) excluir `pre_run_incidents` de qualquer total; (c) não usar `--continue`/`--resume` |

## Resumo

| Resultado | Itens |
|---|---|
| PASS | 1, 8 |
| FAIL | 2, 3, 4, 5, 6, 7 |
| BLOCKED | Nenhum item bloqueado por impedimento técnico. O item 4 (resultado final) depende de uma decisão de escopo: o oráculo de testes |

**Bloqueio relevante (item 4 / resultado final):** o `fail_to_pass` e o `pass_to_pass` da instância não foram obtidos. Excluí esses campos na preparação para não expor o oráculo aos agentes, mas o benchmark precisa deles para medir sucesso. A solução segura é guardá-los em um local **somente do avaliador** (ex.: `tasks/flipt-task02/evaluator/`, fora de `agents/`), sem os incluir em `TASK.md`. Isso depende de autorização explícita, pois a regra original excluía "patches de teste de referência". Os nomes de teste não são patches, mas é preciso confirmar.

## Ordem de correção recomendada

1. Autorizar a obtenção dos nomes de teste para o avaliador (`fail_to_pass`/`pass_to_pass`) e definir o procedimento de avaliação pós-execução. Sem isso não há resultado final.
2. Escrever o wrapper de execução com timeout, teto de custo e coleta (itens 4 e 5). Validar o formato do Pi-Rust com um piloto, se autorizado.
3. Ampliar `check-isolation.sh` para detectar alterações fora dos clones (item 6).
4. Criar `draw-order.py` com semente registrada (item 7).
5. Decidir o contexto de sistema (item 2) e declarar o modelo de isolamento (item 3).
6. Atualizar o manifesto: fonte de custo, regra de exclusão do incidente e ressalvas de isolamento.

Estado: **não liberar para execução** até corrigir os itens 2–7.
