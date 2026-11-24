# Mapa de acoplamento FineCore / supervisor — v0

## Escopo e estado de evidência

Fonte: https://github.com/oigorbrito/FineCore
Revisão inspecionada: d2011bc752842c66fc508d65c03c011c959cc8df, branch main.
Cópia de leitura: C:/Users/igorb/AppData/Local/Temp/finecore-read-ia8DnX.
As linhas abaixo se referem exclusivamente a essa revisão.

Estado: CODE_INSPECTED / DESIGN_PROPOSED. Nenhuma integração foi implementada,
compilada ou executada nesta etapa. Testes existentes citados foram localizados,
não executados. Não há autorização de alteração de core ou escolha final de transporte.

## Resultado executivo

O supervisor pode permanecer fora do FineCore. Há duas fronteiras existentes:
CLI bidirecional com aprovações e SDK Rust com extensões/sessões. Nenhuma exige,
por si só, misturar os códigos dos projetos ou alterar o loop.

A preferência anterior por CLI era uma proposta prematura: a seleção fica aberta
até a qualificação das lacunas abaixo. O desenho mínimo é:

Supervisor: tarefa, política, orçamento, ambiente, decisão e evidências autoritativas
  -> adaptador: tradução do protocolo/capacidades, sem autoridade própria
    -> FineCore: modelo, ferramentas e lifecycle de execução
  <- resultado de runtime + artefatos + observações
Supervisor -> verificador confiável -> decisão -> promoção separada, se autorizada

Monitor de progresso é uma entrada da política, não um segundo controlador de
permissões ou outro verificador de aceitação. Nenhum doador precisa ser importado
para descrever essa fronteira.

## A1 — Preparação e despacho

### CLI

- crates/cli/src/run_args.rs:115-127: seleção de ferramentas e bare.
- crates/cli/src/run_args.rs:269-278: stdio exige JSON e não pode compartilhar
  stdin com prompt recebido por -p -.
- crates/cli/src/headless.rs:368-390: metadata de execução.
- crates/cli/src/headless.rs:391: agent.run_context.

O adaptador futuro pode configurar processo, cwd descartável, ambiente reduzido,
prompt por arquivo/argumento e stdin reservado a aprovações. Não considerar
metadata como atestado de sandbox nem readiness funcional do provider.

### SDK

- crates/sdk/src/harness.rs:72-108: HarnessBuilder.workspace/state_dir/build.
- crates/sdk/src/agent.rs:107-146: limits, tools, extension, policy.
- crates/sdk/src/session/builder.rs:97-105: environment/open.
- crates/sdk/src/session/mod.rs:245-251: run_outcome; :280-288: start.

Bridge Rust externa ao core pode montar essas APIs. WorkspaceBuilder valida
um diretório; isso não transforma o host em sandbox. O estado do harness também
precisa ficar fora dos artefatos promovíveis e protegido contra o executor.

Alteração FineCore: não demonstrada como necessária para despacho básico.
Lacuna: handshake/capacidades/identidade de build do adaptador ainda inexistentes.
Prova futura: erro de preparação não dispara modelo nem ferramenta.

## A2 — Autorização antes da ferramenta

### CLI: existe controle, não apenas observação

- crates/cli/src/stdio_approval.rs:70-74: from_process.
- :95-103: needs_answer cobre GATED_TOOLS, não todas as ferramentas.
- :106-139: read_decisions correlaciona respostas por id; EOF nega pendentes.
- :152-185: before_tool emite approval_request e espera decisão.
- crates/cli/src/approval.rs:19-29: lista GATED_TOOLS.
- crates/cli/src/headless.rs:195-228: instalação da aprovação depende do modo
  e de auto_approve; plan/read-only são instalados antes.

Protocolo existente:
stdout: approval_request com id, tool_call_id, tool_name, input.
stdin: approval com id e decision allow/deny/always.

Perfil estrito proposto: não enviar always, não habilitar auto-approve/auto/yolo,
não presumir que ferramentas não listadas são cobertas. Configuração efetiva,
plugins e ferramentas extras precisam de allowlist e teste, não só prompt.
EOF é deny; mensagem malformada é ignorada e não equivale a um deny imediato.
Timeout e cancelamento de pedidos sem resposta precisam ser qualificados.

### SDK: seam before_tool não é sempre o input efetivo

- crates/harness-core/src/extension.rs:116-127: Continue/Rewrite/Deny.
- crates/harness-core/src/dispatcher.rs:113-144: hooks recebem call original;
  Rewrite é guardado em variável e o input efetivo só é escolhido após os hooks.
- crates/tool-extensions/src/plugin_hooks.rs:100-118: plugins podem devolver Rewrite.
- crates/cli/src/headless.rs:214-228: plugins precedem StdioApprovals.

Consequência CODE_INSPECTED: uma aprovação stdio pode ver os argumentos originais,
enquanto a ferramenta recebe a reescrita guardada pelo dispatcher. Não houve
reprodução executada, avaliação de exploit ou garantia universal de impacto.

- crates/harness-core/src/dispatcher.rs:340-353: around_tool recebe job.input.
- crates/cli/src/auto_approval.rs:202 em diante: exemplo de review no around_tool;
  a existência desse exemplo não autoriza usar revisão por LLM como segurança.

Opções sem mudar core:
1. CLI restrita sem plugins/reescritas e sem ferramentas extras não auditadas.
2. Bridge SDK com gate determinístico no input efetivo e cadeia de wrappers
   controlada. Um wrapper posterior também pode alterar input: validar junto à
   chamada ou restringir toda a cadeia; around_tool sozinho não é garantia.

Prova futura: propor comando permitido, reescrever para comando proibido e
confirmar que o efeito proibido não ocorre. Decisão deve registrar input hash.
Não implementar contorno ou patch do dispatcher nesta etapa.

## A3 — Isolamento e capacidades

- crates/sdk/src/environment.rs:14-35: SessionEnvironment e limites de escopo.
- :40-56: sandbox(binding_id, handle, workspace).
- :58-80: network_off adiciona informação sobre sandbox que o host já isolou;
  não configura firewall nem desliga rede por si só.
- :117-149: valida capacidades e conflitos com executor explícito.

Provisionar e encerrar sandbox é responsabilidade do host. Ferramentas custom,
extensões, MCP, skills e memória não passam automaticamente pelo mesmo enclosure.

CLI em cwd descartável não impede shell de acessar o host. SDK com ambiente
Sandbox só cobre o conjunto explicitamente roteado. Prova futura: sentinela
externa, rede negada efetiva e tentativa por ferramenta custom/subagente.

Alteração core: não demonstrada como necessária; backend/host com capacidades
comprovadas pode fornecer a fronteira. Sem backend qualificado: BLOCKED, não seguro.

## A4 — Eventos, diagnóstico e integridade

- crates/cli/src/headless.rs:148-150: serialização dos eventos JSON.
- :406-423: summary/status/usage; :425-431: código de saída.
- crates/sdk/src/run.rs:237-264: RunOutcome preserva execution, persistence e perdas.
- :284-307: RunEvent::Overflow e semântica de ordenação aproximada.
- :337-364: cancellation_token/events/take_events/dropped_events.

Preferir RunHandle.outcome/run_outcome a finish/run para não descartar accounting
parcial em falhas. Não inferir auditoria completa de um fluxo sem gaps declarados;
o caminho CLI não foi demonstrado equivalente à contagem de perdas do SDK.

Evidência autoritativa deve ser externa ao workspace gravável. Redigir argumentos,
saídas e credenciais antes de persistir; não copiar transcripts por padrão.
Prova futura: consumidor lento, falha de persistência, JSON parcial e resumo ausente.

## A5 — Cancelamento e término real

- crates/cli/src/headless.rs:320-332: ctrl_c/shutdown_signal cancelam token.
- crates/sdk/src/run.rs:132-145: token filho de token do chamador.
- :375-388: outcome aguarda task; Drop apenas solicita cancelamento.
- crates/tools/src/core_tools/pgroup.rs:5-19: killpg Unix best-effort.
- :22-26: implementação não-Unix de kill_group é vazia; comentário limita
  kill_on_drop/start_kill ao filho direto.

Conclusão restrita: esse helper não comprova término de netos no Windows. Não é
uma prova de que todos os caminhos vazam processos. O supervisor deve observar
fim da execução e do enclosure; solicitação/Drop não bastam.

Alteração core: ainda indeterminada. Job Object/encerramento do sandbox no host
são candidatos externos, não capacidades já validadas.
Prova futura: filho cria neto que escreve sentinela; após cancelamento confirmado,
nenhuma escrita nova. Qualificar separadamente por sistema operacional.

## A6 — Subagentes e ferramentas aninhadas

- crates/sdk/src/run.rs:73-79: extensão de RunRequest não se instala nos filhos.
- crates/cli/src/headless.rs:280-301: CLI clona aprovação stdio e entrega hooks
  explicitamente ao factory de subagentes.
- crates/cli/src/runtime/subagents.rs:38-49: composição dos hooks dos filhos.
- crates/tools/src/subagent/spawn.rs:241-257: factory explícito e retry interno.

A CLI já propaga stdio nesse caminho, mas isso não prova herança de toda política,
limites agregados ou cobertura de todos os executores aninhados. A bridge SDK
precisa montar a propagação explicitamente ou desabilitar filhos inicialmente.
Prova futura: chamada proibida do filho e consumo agregado acima do limite.

## A7 — Resultado, verificação e promoção

- crates/harness-core/src/agent_loop.rs:63-66: Final retorna texto com Ok.
- crates/sdk/src/run.rs:268-270: is_success combina execução e persistência,
  não aceitação independente da tarefa.
- crates/cli/src/headless.rs:400-405: success é classificação do run.

Acoplamento proposto: somente depois do término observado, supervisor identifica
artefato, roda verificador confiável fora da autoridade do executor e confere
identidade antes/depois. Nenhum desses retornos autoriza ACCEPTED sozinho.

Não foi localizada, nos caminhos examinados, API de promoção independente que
substitua essa responsabilidade. Não se afirma ausência universal no repositório.
Alteração core: não demonstrada necessária; verificação/promoção ficam no supervisor.
Prova futura: falso sucesso, teste adulterado, receipt obsoleto e drift da base.

## Comparação de transportes — decisão em aberto

| Critério | CLI + stdio | Bridge SDK externa |
| --- | --- | --- |
| Separação por processo | Já oferecida pela CLI | Exige host/bridge e protocolo próprios |
| Gate externo | Existente, limitado a gated tools e modos | Hooks públicos, cadeia sob controle do host |
| Input pós-rewrite | Stdio vê call original no caminho examinado | around_tool recebe input efetivo naquele estágio |
| Accounting parcial | Summary/eventos; equivalência ainda não qualificada | RunOutcome explícito |
| Sandbox | Enclosure externo ao processo | SessionEnvironment com backend do host |
| Subagentes | Propagação stdio explícita no caminho inspecionado | Montagem explícita; RunRequest sozinho não herda |
| Dependência | Binário/protocolo fixados | Crates Rust/revisão fixados na bridge |
| Mudança no loop | Não demonstrada necessária | Não demonstrada necessária |

## Menor próximo passo defensável

Revisar e aceitar o mapa, especialmente cobertura de aprovação e isolamento.
Depois definir um protocolo de qualificação de seams, não um novo supervisor:
Q1 correlação/EOF; Q2 input reescrito; Q3 isolamento; Q4 cancelamento de netos;
Q5 perda de eventos; Q6 herança; Q7 falso sucesso/artefato alterado.
Somente depois selecionar CLI/SDK e escrever adaptador. Não executar esses testes
nem portar código como consequência automática deste documento.
