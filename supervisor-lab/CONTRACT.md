# Contrato proposto v0 — não implementado

## 1. Papéis

- Operador: define tarefa, política e critérios de aceitação antes da execução.
- Supervisor: aplica política, limites e lifecycle; consolida evidências e decisão.
- Adaptador: traduz o protocolo do executor; não aprova tarefas nem amplia autoridade.
- Executor (inicialmente FineCore): raciocina e usa ferramentas dentro da capacidade recebida.
- Monitor: produz sinais e pode solicitar parada; não concede permissões ou aceitação.
- Verificador: executa critérios sob configuração controlada pelo supervisor.
- Promoção: operação separada, explicitamente autorizada e vinculada ao artefato verificado.

A independência do verificador deve ser imposta: o executor não pode substituir
o programa, a configuração, os critérios ou os registros autoritativos do teste.
Testes editáveis pelo executor não podem ser a única fonte de aceitação.
Um booleano passed fornecido pelo executor não é verificação independente.

## 2. Identidades obrigatórias

TaskSpec:
- task_id, descrição, referência imutável da base;
- hash da política e dos critérios/implementação do verificador;
- escopo permitido e caminhos protegidos;
- limites de tempo/passos/recursos; custo desconhecido não é zero;
- configurações de executor/modelo/provider (sem segredos);
- modo de rede e isolamento exigido.

RunIdentity:
- run_id, attempt_id, adapter_id/version;
- executor_id/version/revision ou binary hash;
- identidade do ambiente e do workspace isolado;
- policy_hash e acceptance_spec_hash.

ArtifactIdentity:
- base_revision + manifesto SHA-256 dos arquivos relevantes produzidos;
- política explícita para arquivos não rastreados, ignorados e symlinks;
- identidade do ambiente e ferramentas necessárias à verificação;
- estado observado antes e depois do teste.

Hashes vinculam conteúdo; não provam autoria, isolamento ou confiança.
O executor não pode escrever no armazenamento autoritativo de evidências.

## 3. Interface mínima do adaptador

prepare(TaskSpec) -> PreparedRun:
- declara capacidades reais: eventos, cancelamento, isolamento, rede e retomada;
- capacidades desconhecidas não recebem true por conveniência;
- impede início se faltar capacidade obrigatória.

start(PreparedRun) -> RunHandle
events(RunHandle) -> Event stream
cancel(RunHandle, reason) -> solicitação registrada, não confirmação de término
collect(RunHandle) -> RuntimeOutcome
dispose(RunHandle) -> resultado de limpeza, preservando evidências necessárias

RuntimeOutcome.status:
COMPLETED | FAILED | TIMEOUT | CANCELLED | LIMIT_EXCEEDED | UNKNOWN

RuntimeOutcome inclui identidade, timestamps, causa, código de saída opcional,
usage/cost conhecidos ou desconhecidos, integridade do stream e referências a
artefatos. COMPLETED e exit_code=0 não significam ACCEPTED.

## 4. Lifecycle

CREATED -> PREPARED -> RUNNING -> EXECUTION_TERMINATED
        -> VERIFIED -> DECIDED

Falhas de preparação podem ir diretamente a DECIDED sem despacho.
Cancelamento só chega a EXECUTION_TERMINATED depois de término observado.
Falha em encerrar a árvore de processos impede limpeza/liberação silenciosa.
Estados de execução, verificação e decisão são campos separados.

Decision:
ACCEPTED | REJECTED | BLOCKED | INCONCLUSIVE

ACCEPTED exige:
1. execução terminada com COMPLETED;
2. política e escopo satisfeitos, sem violação crítica não resolvida;
3. verificação independente aprovada sobre o artefato atual;
4. nenhum drift entre artefato verificado e artefato decidido;
5. evidências obrigatórias íntegras e disponíveis.

Custo desconhecido não é aprovação de um teto monetário obrigatório.
Resultado de teste ausente, obsoleto ou ambientalmente inválido não é aprovação.
A evidência de orçamento deve distinguir uso medido de limites impostos.

## 5. Eventos e perda de observabilidade

Envelope: schema_version, run_id, attempt_id, event_id, sequence,
observed_at, producer e type. Dados brutos devem ser reduzidos/redigidos.
Não confundir a ordem de observação com a ordem causal de ferramentas paralelas.
Duplicatas precisam ser detectadas; sequência inválida não é silenciosamente reparada.

Tipos mínimos:
RUN_PREPARED, RUN_STARTED, TOOL_OBSERVED, MONITOR_SIGNAL, CANCEL_REQUESTED,
EXECUTION_TERMINATED, OBSERVATION_GAP, VERIFICATION_RECORDED, DECISION_RECORDED.

Eventos de observação não são mecanismo de autorização prévia.
Perdas e overflow viram OBSERVATION_GAP e degradam explicitamente a integridade.
Se o trecho perdido é necessário à aceitação, a decisão não pode ser ACCEPTED.
Evidência independente completa pode satisfazer apenas requisitos que ela realmente cobre.

## 6. FineCore — hipótese inicial de adaptador, seleção suspensa

Fonte inspecionada: d2011bc752842c66fc508d65c03c011c959cc8df.

Hipótese inicialmente sugerida: processo CLI com NDJSON, em ambiente descartável.
A escolha foi suspensa até revisar COUPLING-MAP.md, que compara CLI/stdio e
bridge SDK e registra limites de aprovação, reescrita e encerramento.
O parser deve distinguir metadata, eventos e summary, sem interpretar texto livre
como autoridade. Summary success e exit 0 mapeiam no máximo para COMPLETED.
Fim sem summary válido, JSON inválido ou identidades contraditórias: UNKNOWN.
Mapear cancelamento e limites apenas quando houver evidência do motivo.

O subprocesso não é sandbox. Não usar auto-approve como fronteira de segurança.
Rede, credenciais e acesso ao host devem ser restringidos fora do prompt.
Não habilitar MCP/plugins/subagentes sem política e capacidades explicitamente validadas.

Limitações a qualificar: handshake de readiness, framing/versão de NDJSON,
backpressure, timeout, encerramento de descendentes no Windows e preservação
dos eventos em falha. O protocolo CLI ainda não foi executado neste laboratório.

Alternativa de igual prioridade para avaliação: bridge Rust via SDK. RunOutcome separa execução/persistência
e registra dropped_events; uma bridge não pode omitir esses campos.
Extensões anexadas por RunRequest não são automaticamente herdadas por agentes
filhos: política de propagação precisa de teste próprio.

## 7. Seleção sem duplicação

Um único dono por decisão: política, orçamento, cancelamento e aceitação.
Detectores podem discordar; a arbitragem deve registrar regra e motivo.
Não criar dois retry loops independentes que multipliquem tentativas.

Candidatos a experimento:
- SMAG: lifecycle/contrato e controles de staging/promoção.
- SMAG-ReX: fronteiras pequenas de autoridade/execução/aceitação.
- Pathlayer: estagnação condicionada a evidências e histerese.
- Agent Efficiency: recibos vinculados ao workspace/configuração.
- Agent Loop Guard: política MCP e fingerprints, somente se preencherem lacuna.

Não portar tudo. Licença, proveniência, atribuições e limites precisam ser
revisados antes de copiar qualquer implementação.
