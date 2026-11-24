# Schemas de saída usados pelo coletor (`run-agent.py`)

Regra: nenhum campo foi presumido igual entre as CLIs. Cada campo abaixo tem uma **origem**
e um **estado de validação**. Campo não encontrado é gravado como `unavailable`, nunca como zero.

## Pi original (TypeScript 1.5.2)

| Campo coletado | Caminho no JSON (`--mode json`) | Origem | Estado |
|---|---|---|---|
| tipo de evento | `type` | `docs/json.md` | documentado |
| fim de mensagem do assistente | `type == "message_end"` e `message.role == "assistant"` | `docs/json.md` ("authoritative final message") | documentado |
| tokens de entrada / saída | `message.usage.input`, `message.usage.output` | `docs/message-types.md` (interface `Usage`) | documentado + sessão real |
| tokens de cache | `message.usage.cacheRead`, `message.usage.cacheWrite` | idem | documentado + sessão real |
| total de tokens | `message.usage.totalTokens` | idem | documentado + sessão real |
| custo total | `message.usage.cost.total` | idem | documentado + sessão real (incidente) |
| custo do provedor ou estimativa | `message.usage.cost.totalFromProvider` | sessão real: `false` | sessão real |
| chamadas de ferramenta | `type == "tool_execution_start"`, campo `toolName` | `docs/json.md` | documentado |
| fim do run | `type == "agent_end"`, `type == "agent_settled"` (campo `aborted`) | `docs/json.md` | documentado |
| parcial em andamento | `type == "message_update"`, `usage.cost.total` (cumulativo) | `docs/json.md` | documentado |

Evidência real: `evidence/preparation/incident-session-pi-original-doctor.jsonl` (sessão de 3 turnos,
campos `usage` com `input`, `output`, `cacheRead`, `cacheWrite`, `totalTokens`, `cost.*`, `reasoning`).
O formato de **stdout JSON** foi confirmado apenas pela documentação, não por uma execução gravada.

## Pi-Rust 0.12.16 (commit e9dd2b54)

| Campo coletado | Caminho | Origem | Estado |
|---|---|---|---|
| tipo de evento | `type` (serde `snake_case`) | `crates/pi-agent/src/types.rs:223` | código |
| fim de mensagem | `type == "message_end"`, `message` | `pi-agent/src/types.rs` (`AgentEvent`) | código |
| `Message::Assistant` serializado com `role` | `impl Serialize for Message` | `crates/pi-ai/src/types.rs:365` | código |
| `Usage` camelCase | `input`, `output`, `cacheRead`, `cacheWrite`, `totalTokens`, `cost` | `crates/pi-ai/src/types.rs:91-105` (`rename_all = "camelCase"`) | código |
| `Cost.total` e `totalFromProvider` | `cost.total`, `cost.totalFromProvider` | `crates/pi-ai/src/types.rs:73-89` | código |
| chamadas de ferramenta | `tool_execution_start` com `toolName` (`rename_all_fields = "camelCase"`) | `pi-agent/src/types.rs:245-251` | código |
| JSON de saída | `to_json()` por evento | `pi-coding-agent/src/agent_session/events.rs:167-181` | código |

**Estado: NÃO VALIDADO EM EXECUÇÃO REAL.** Todos os campos acima foram confirmados por leitura do código-fonte
(compilado no binário do commit). Como nenhum agente pode ser iniciado nesta etapa, não há saída gravada do Pi-Rust.
O wrapper recusa rodar o Pi-Rust sem `--allow-unvalidated-usage` (`run-agent.py`, `AGENTS["pi-rust"]["runtime_validated"]`).
A validação exige um piloto autorizado, com saída real comparada a esta tabela.

Campos do Pi-Rust que **não** existem no Pi original e não são coletados como equivalentes: `CacheMiss` (evento
específico), `RunLimit` (`--max-turns`/`--max-cost`, não usados), `reasoning` (opcional, coletado só se presente).

## Como o wrapper usa estes campos

- **Custo acumulado para o teto:** soma de `message_end.message.usage.cost.total` das mensagens do assistente,
  mais o custo parcial da mensagem em andamento (`message_update.usage.cost.total`), para interromper antes do fim.
- **Controle de custo** (`result.json: cost_control`):
  - `enforced`: todas as mensagens do assistente trouxeram custo;
  - `partial`: algumas trouxeram, outras não (o teto pode ser ultrapassado sem aviso);
  - `unavailable`: nenhuma trouxe custo (o teto **não** é aplicado).
- **Tokens e custo totais:** `unavailable` se o campo faltou em todas as mensagens; `{partial_sum, messages_with_field,
  assistant_messages}` se faltou em algumas; soma completa só se presente em todas.
