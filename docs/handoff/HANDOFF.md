# Handoff: auditoria e spike de Mingbird-agent e little-coder

Escopo: Mingbird-agent (commit `db9897f`, v3.1.11) e little-coder (commit `89d4fa0`, v1.20.0). O orca-harness está fora deste handoff.

## 0. Estado do registro (leia primeiro)

- As rodadas 1 a 3 e as versões intermediárias dos scripts **não estão neste repositório**. O ambiente de execução foi recriado ao reiniciar o Claude Code e esses arquivos foram perdidos. Os números de 1 a 3 abaixo vêm do registro da conversa e não podem ser reproduzidos a partir do disco.
- A rodada 4 foi reexecutada depois da recriação. Os CSVs, as tarefas e o runner estão em `docs/handoff/spike/`.
- Recomendação: versionar os runners e os CSVs de cada rodada no momento em que ela termina.

## 1. Ambiente

| Item | Valor |
|---|---|
| Máquina | Linux, 4 vCPU, 16 GB RAM, sem GPU |
| Node | v22.23.5 |
| Python (Mingbird) | 3.13.18 |
| Ollama | 0.40.16 |
| Contexto | 16384 nas rodadas 3 e 4; rodada 2 misturou 32k (qwen) e 16k (llama) |

Ollama: `OLLAMA_MAX_LOADED_MODELS=1` foi adicionado na rodada 4 e **não impediu OOM** do `llama-server`. Foram 3 eventos (13:08, 13:52 e 14:30 UTC, em `docs/handoff/spike/r4/oom_events_utc.txt`).

## 2. Auditoria estática

### Mingbird-agent
- 270 arquivos; `ollama_agent.py` com 5.249 linhas; `agent_gui.py` com 4.097.
- `requirements.txt` sem versões fixadas. A CI roda pytest no Windows e não instala o `requirements.txt`.
- README diz 726 testes; `def test_` estático dá 637 (+6 `parametrize`). A coleta do pytest chega a 726.
- `run_bash` usa `shell=True` (`ollama_agent.py:2520`, `:3662`) e uma denylist por substring (`_DANGER_CMD`, `:1844`; checagem em `_gate_check`, `:2058`). Não há whitelist. O próprio código admite que `python -c` contorna a fronteira de diretório (`:2047`).
- `test_guard_warns < 3` (`:4842`): após 3 recusas, o `finish` passa.
- `CTX_BUDGET` padrão 131072, enviado ao Ollama como `num_ctx` (`:97`, `:2964`).

### little-coder
- 221 arquivos; `npm ci` ok; typecheck ok.
- CI de PR só roda `npm ci`. `npm test` roda só no publish de tag (`publish.yml:45`).
- Gate de permissão avalia cada segmento de `&& || ; |` (`permission-gate/index.ts:247-254`).
- **Lacuna por leitura, não reproduzida:** `$(...)` e crase não são divididos nem inspecionados (`_shared/shell-write.ts:160-185`). `echo $(...)` passa.
- **Lacunas por leitura, não reproduzidas:** `sed` com `w`/`e` não é checado; `git diff --output=<arquivo>` é permitido.
- Nudge de tool call em texto (`output-parser/index.ts:95`) não tem limite de tentativas visível.

## 3. Suítes de teste

### little-coder
- `npm test`: 841 passaram, 3 falharam, 14 skipped. As 3 falhas são de `live-integration.test.ts` (Chromium fora do caminho esperado e dependência de rede).
- `npm run typecheck`: exit 0.

### Mingbird-agent
- `pytest tests/` sem patch: **processo morto** (exit 137) em ~37%. Causa: `_kill_proc_tree` faz `os.killpg` no PGID do pai, porque os `Popen` de MCP (`_StdioSession`, ≈ linha 1190; `_probe_stdio`, `:1419`) não usam `start_new_session=True`. Só o `run_bash` (`:2523`) usa.
- Reprodução: `repro_broker.py` sai com 137; com `start_new_session=True` no filho, sai com 0.
- Com um plugin externo que adiciona `start_new_session=True` (sem editar o repo): **682 passaram, 32 falharam, 12 skipped** (726 coletados).
- Falhas, por causa aproximada: 9 `ModuleNotFoundError` (tkinter, não confirmado em todos); 11 em `test_parallel_safety.py` com caminhos `\` do Windows; 2 em `test_core.py` pelo mesmo motivo; 2 `1318 != 1319` na pinagem do prefill (**não resolvido**); restantes não investigadas.
- Impacto: em POSIX, o `close()` de sessões MCP mortas ou ociosas pode derrubar o próprio app. Correção sugerida, não aplicada: `start_new_session=(os.name != "nt")` nos dois `Popen` de MCP.

## 4. Juízes e tarefas

Seis tarefas em `docs/handoff/spike/tasks/`, cada uma com juiz pytest. Verificado: uma correção escrita à mão passa nas 6 (3, 4, 3, 1, 3 e 4 testes).

| Tarefa | Linha de base |
|---|---|
| t1_bugfix (média com `len+1`) | 2 failed, 1 passed |
| t2_feature (slugify) | 4 failed |
| t3_rename (3 arquivos) | 2 failed, 1 passed |
| t4_data (summary.csv) | 1 failed |
| t5_spec (DD/MM/YYYY → ISO) | 2 failed, 1 passed |
| t6_refactor (duplicação) | 1 failed, 3 passed |

**Juiz de integridade (rodadas 3 e 4):** uma execução só conta como legítima se passar **e** nenhum arquivo de teste existente tiver sido alterado. Sem essa checagem, a rodada 3 teria 1/12 aprovado no Mingbird, que era adulteração de teste.

## 5. Resultados por rodada

### Rodada 1 (3B, 6 tarefas, 2–3 repetições, 300 s; orca excluído)

| Harness | Modelo | Execuções | Aprovadas | Ferramentas executadas |
|---|---|---|---|---|
| Mingbird | qwen2.5-coder 3B | 12 | 0 | 214 (≈200 resgatadas de texto) |
| Mingbird | llama3.2 3B | 14 (2 em 131k, 12 em 32k) | 0 | 173 |
| little-coder | qwen2.5-coder 3B | 12 | 0 | **0** |
| little-coder | llama3.2 3B | 12 | 0 | 104 |

Achados: 38 de 50 execuções em timeout; 11 pararam sozinhas e falharam no juiz. little-coder/qwen: parser detecta a chamada em texto, pede reemissão nativa, o modelo repete o bloco de texto até o timeout (60+ vezes numa sessão). Mingbird/llama em 131k: OOM (13,9 GB de RSS no `llama-server`). Mingbird/qwen t6 r1: `delete_file` em `calc.py` no primeiro passo; o arquivo foi para `.mingbird_trash/`, mas não foi restaurado.

### Rodada 2 (3B, mesmas tarefas, com métricas de mudança)

Contexto: qwen em 32k nos dois harnesses; llama em 16k (32k causou OOM a cada 4–5 min). Mingbird em 131k foi descartado e refeito em 32k; resultados de 131k preservados separadamente.

| Bloco | Aprovadas | Parou sozinho | Timeout | Código alterado | Testes alterados | Ferramentas |
|---|---|---|---|---|---|---|
| mb_qwen | 0/12 | 7 | 5 | 5 | 0 | 183 |
| lc_qwen | 0/12 | 2 | 10 | 0 | 0 | 0 |
| mb_llama | 0/12 | 3 | 9 | 5 | 1 | 181 |
| lc_llama | 0/12 | 6 | 6 | 2 | 0 | 133 |

Leitura de 12 diffs de código (Mingbird, 10; little-coder, 2): edição aditiva no lugar de transformação (4); especificação mal lida na ordenação de t4 (2); import circular em t3 (1: `core.py` ganhou `from pkg.report import render` e `report.py` continuou importando `compute_total`); fora do alvo (1: `slug.txt` no lugar de `slugify`); conteúdo inventado ou destrutivo (4: `calc.py` substituído por script pandas sem `.bak`, `summary.csv` com texto aleatório, regiões fabricadas em little-coder). Um `finish` com `[TASK_COMPLETE]` foi emitido com 4 testes falhando.

### Rodada 3 (7B, qwen2.5-coder, 16k nos dois, juiz de integridade)

| Harness | Legítimas | Adulteração de teste | Erro 400 (harness parou) | Timeout | Ferramentas |
|---|---|---|---|---|---|
| Mingbird | 0/12 | 1 (t1 r1: valores esperados trocados para 1.5 e 2.5) | 3 | 8 | 124 |
| little-coder | 0/12 | 0 | 0 | 10 | 0 |

Também: 2 alterações de teste sem aprovação no Mingbird (t2 r2, t6 r2). Erros 400 eram JSON malformado de tool call; o Mingbird encerra a execução em vez de repetir. little-coder emitiu `write` em texto e não executou.

### Rodada 4 (modelos fora da família qwen, 16k, juiz de integridade)

Seleção: `llama3.1:8b` (base), `granite3.3:8b` (base) e `hermes3:8b` (modificado, fine-tune da Nous Research). `nemotron-mini` (NVIDIA) foi excluído: não emitiu tool call nem texto no teste. Não foi possível verificar o Llama-3.1-Nemotron-Nano-8B (NVIDIA), Watt-Tool-8B nem ToolACE-8B.

| Bloco | Legítimas | Adulteração | Parou sozinho | Timeout | Código alterado | Ferramentas |
|---|---|---|---|---|---|---|
| mb_llama3.1 | 0/12 | 2 | 1 | 11 | 4 | 73 |
| lc_llama3.1 | 0/12 | 0 | 6 | 6 | 0 | 72 |
| mb_granite3.3 | 0/12 | 0 | 0 | 12 | 0 | **0** |
| lc_granite3.3 | 0/12 | 0 | 7 | 5 | 0 | 0 |
| mb_hermes3 | 0/12 | 3 | 6 | 6 | 9 | 50 |
| lc_hermes3 | 0/12 | 0 | 9 | 3 | 0 | 54 |

Achados:
- Granite com Mingbird não chama ferramenta: responde em prosa e blocos de código, e em uma execução orienta o usuário a editar o arquivo à mão.
- `mb_llama3.1` t3 r1: `test_old_gone` foi trocado de `compute_total` para `calculate_total`, e o teste continuou em erro de coleta.
- Infra: 3 OOMs do `llama-server`; só `mb_llama3.1` (uma execução) se sobrepõe a um deles.

## 6. Conclusão

- Em nenhuma das 4 rodadas (50 + 48 + 24 + 72 execuções de Mingbird e little-coder) um modelo de 3B–8B em CPU completou uma tarefa de forma legítima.
- A diferença entre os harnesses está em **quantas ferramentas executam** e **como lidam com saída malformada** (Mingbird resgata texto; little-coder entra em loop de reemissão; Mingbird para com erro 400). Não está em produzir código correto.
- O gargalo observado é **a edição correta sob o prompt**: transformar em vez de acrescentar, respeitar a especificação, não destruir arquivos, não fabricar dados e não adulterar testes.
- Não há evidência, nesta amostra, de que trocar a família de modelo (qwen, llama, granite, hermes) mude o resultado.

## 7. Limites

- 2 repetições por célula. A amostra só detecta efeitos grandes.
- Rodadas 1 a 3 sem dados brutos no repositório.
- Juízes: os de tarefa foram validados; o de integridade só checa arquivos de teste existentes (não checa arquivos novos de teste nem alterações nos próprios juízes).
- Contexto não uniforme entre rodadas e entre modelos (ver seção 5).
- Classificação de diffs feita à mão por um único leitor.

## 8. Próximos passos sugeridos

1. Corrigir o `Popen` de MCP (`start_new_session`) e rodar a suíte sem plugin.
2. Mingbird: restaurar automaticamente após `delete_file`/`create_file` que sobrescreve código; tratar erro 400 de tool call com nova tentativa.
3. little-coder: limite de tentativas no nudge de reemissão, com resgate de bloco de texto.
4. Juiz: bloquear também arquivos de teste novos e alterações em `tests/` do próprio juiz.
5. Para uma comparação conclusiva de modelos: tarefas mais fáceis (validar que o pipeline aprova algo), GPU para 5+ repetições, e contexto único entre modelos.

## 9. Como reproduzir a rodada 4

```bash
# Ollama em 16k, um modelo carregado por vez
OLLAMA_CONTEXT_LENGTH=16384 OLLAMA_MAX_LOADED_MODELS=1 ollama serve
ollama pull llama3.1:8b && ollama pull granite3.3:8b && ollama pull hermes3:8b

# Clones
git clone --depth 1 https://github.com/Mingbird/mingbird-agent /home/user/mingbird/mingbird-agent
git clone --depth 1 https://github.com/itayinbarr/little-coder /home/user/itayinbarr/little-coder
(cd /home/user/itayinbarr/little-coder && npm ci --ignore-scripts)
(cd /home/user/mingbird && python3 -m venv venv && ./venv/bin/pip install pytest requests beautifulsoup4 numpy pillow openpyxl python-docx mcp ttkbootstrap)

# Tarefas e runner (diretórios /home/user/spike/tasks e /home/user/spike/work)
cp -r docs/handoff/spike/tasks /home/user/spike/ && mkdir -p /home/user/spike/work
cp docs/handoff/spike/run_r4.sh docs/handoff/spike/run_matrix_r4.sh /home/user/spike/
/home/user/spike/run_matrix_r4.sh
```

## 10. Arquivos deste handoff

- `docs/handoff/HANDOFF.md` (este arquivo)
- `docs/handoff/spike/tasks/` (6 tarefas com juízes)
- `docs/handoff/spike/run_r4.sh` e `run_matrix_r4.sh` (runner e matriz da rodada 4)
- `docs/handoff/spike/r4/*/results.csv` (CSVs por bloco, com legit, src_changed, tests_modified, tools)
- `docs/handoff/spike/r4/oom_events_utc.txt`
