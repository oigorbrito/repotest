# Telemetria por execução (rodada 4)

- `runs.jsonl`: uma linha JSON por execução (72). Campos: bloco, harness, modelo, tarefa, repetição,
  código de saída, aprovação, aprovação legítima (sem alterar teste), resultado (`outcome`), arquivos
  alterados (código, testes, novos), sobreposição com OOM, totais (ferramentas, erros, resgates de
  texto, erros de API, tokens quando o harness registra, pico de contexto do Mingbird) e a lista
  ordenada de eventos (chamadas, resultados, respostas só em texto).
- `SUMMARY.md`: tabela agregada por bloco, gerada por `summarize.py`.
- `extract.py`: gera `runs.jsonl` a partir de `r4/` (logs, `.pytest`, `.changes`, `results.csv`)
  e das sessões JSONL do little-coder.

Casamento de sessão: cada (modelo, tarefa, repetição) é uma única execução. A sessão é identificada
pelo nome do diretório de trabalho e pelo modelo gravado nas mensagens. Verificado contra a coluna
`tools` do CSV do runner: 36 de 36 execuções do little-coder batem.

Limites:
- Mingbird não registra tokens no log; o único indicador é o `ctx: usado/limite`. Tokens do
  little-coder vêm do campo `usage` das mensagens do assistente.
- Tempo por chamada: o Mingbird registra `+Ns` a partir do início; o little-coder não grava tempo
  por evento na sessão, então `t_s` do little-coder é só o tempo relativo entre mensagens.
- Os eventos do Mingbird são lidos do log em texto. Linhas em formato desconhecido são ignoradas.

Reproduzir:
```bash
python3 docs/handoff/spike/telemetry/extract.py --spike <spike> --sessions /root/.pi/agent/sessions --out docs/handoff/spike/telemetry/runs.jsonl
python3 docs/handoff/spike/telemetry/summarize.py docs/handoff/spike/telemetry/runs.jsonl
```
