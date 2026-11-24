# Incidente de preparação — invocação acidental do Pi original

**Data:** 2026-11-18, ~18:19 (horário local)
**Agente:** `pi-original` (Pi TypeScript 1.5.2)
**Cwd:** `tasks/flipt-task02/agents/pi-original/flipt`
**Classificação:** execução acidental de preparação. **Não é execução do benchmark e não deve ser contada como tal.**

## O que aconteceu

Para verificar a prontidão das CLIs, rodei `pi doctor` nos dois binários. No Pi TypeScript (1.5.2) não existe o subcomando `doctor`. A palavra foi tratada como mensagem em linguagem natural e enviada ao modelo. O agente então executou comandos de leitura e respondeu.

Ao Pi-Rust, `doctor` é um subcomando real (saída de tabela com configurações e credenciais). Nenhuma sessão foi criada para o Pi-Rust.

## Impacto medido

| Item | Valor |
|---|---|
| Turnos de modelo | 3 |
| Chamadas de ferramenta | 2 (`bash`), ambas de leitura: `pwd`, `git status`, `git log`, `ls`, `rg`, versões de `go`, `node`, `docker`, `make` |
| Tokens de saída | 867 (+189 de raciocínio) |
| Tokens de entrada | 8 (+9.557 lidos do cache, +2.005 gravados no cache) |
| Custo | US$ 0,00078 (somado do campo `usage` da sessão) |
| Alterações no repositório | Nenhuma. `git status` do clone continua limpo |
| Efeito colateral fora da área | Arquivo de sessão criado em `~/.pi/agent/sessions/…pi-original-flipt--/`. `prompt-history.jsonl` não foi alterado |

## Preservação

- Cópia da sessão (sem alteração): `evidence/preparation/incident-session-pi-original-doctor.jsonl`, SHA-256 `d51b1d53…1a87b`.
- Saída do comando: `evidence/preparation/doctor-pi-original.txt`.
- O arquivo original em `~/.pi/agent/sessions/` foi mantido, por ser log de custo e tokens.

## Causa

Erro meu: assumi que `doctor` existia nas duas CLIs. Não verifiquei com `--help` antes de executar.

## Medidas adotadas

1. Prontidão agora usa `pi auth check --provider anthropic --model claude-haiku-5-5 --json` (`evidence/preparation/auth-check-*.json`). Ambos retornaram `ready`. Esse comando só verifica credenciais.
2. Nenhum comando de prontidão que não seja `--help`, `--version`, `--list-models`, `auth check` ou `doctor` (apenas no Pi-Rust) será usado daqui em diante.
3. Os dois agentes passam a usar `--session-dir` próprio dentro de `evidence/<agente>/sessions`, para que as sessões não se misturem em `~/.pi/agent/sessions`.
4. Este incidente deve constar como erro operacional nos registros de execução do Pi original (`evidence/pi-original/run-record.json`). Ele consome parte do orçamento, mas não invalida a comparação.
