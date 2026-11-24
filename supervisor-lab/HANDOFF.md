# Handoff — estudo de supervisor independente com FineCore por adaptador

## Pedido e direção do usuário

O usuário quer um novo projeto refinado, sem apego a um supervisor específico.
FineCore será conectado por adaptador. SMAG, SMAG-ReX, Pathlayer, Agent Efficiency
e Agent Loop Guard são fontes de mecanismos, não frameworks a empilhar.

Correção explícita de direção: primeiro localizar no código onde o supervisor
acopla e produzir uma análise defensável. NÃO começar misturando código,
transplantando implementações ou construindo protótipo antes desse mapeamento.

Último pedido: produzir handoff. Isto não é pedido de fechamento de projeto,
publicação, commit, push, merge ou implementação.

## Onde continuar

Diretório independente criado: D:/projetos/supervisor-lab/
Nome provisório, sem Git inicializado por esta sessão e sem implementação.
Arquivos:
- README.md: escopo e ordem atual de trabalho.
- COUPLING-MAP.md: principal entregável; seams FineCore, linhas e lacunas.
- CONTRACT.md: contrato proposto, NÃO aprovado; preferência inicial CLI suspensa.
- scenarios.json: 15 cenários propostos; todos NOT_EXECUTED, limiares/repetições TBD.
- SOURCES.json: fontes, SHAs e execução focada observada.
- QUALIFICATION-PROTOCOL.md: protocolo Q1–Q7 e gate G0, NÃO executado (v0).
- HANDOFF.md: este registro.

## Atenção crítica: diretório original não corresponde ao remoto atual

Cwd da sessão: D:/projetos/smag-rex.
O conteúdo local é o monorepo SMAG antigo, não a árvore SMAG-ReX atual.
Por autorização explícita do usuário, origin foi trocado de
https://github.com/oigorbrito/smag.git para
https://github.com/oigorbrito/smag-rex.git.
Isso alterou somente a configuração de URL; não houve checkout, reset, merge,
pull, fetch, push ou migração de conteúdo pela sessão.

Estado local observado:
- branch: codex/ollama-local-adapter-evidence
- HEAD: 5b73e034668904d3cc5871e9940e4bdbdc95b4f7
- 8 arquivos modificados sob packages/smag-governance:
  README.md; src/executor-discovery.mjs; src/runtime-rebuild.mjs;
  src/smag-core.mjs; src/startup-readiness.mjs;
  test/executor-discovery.test.mjs; test/runtime-rebuild.test.mjs;
  test/startup-readiness.test.mjs.
- .vs/ não rastreado, incluindo estado SQLite/editor.
Essas alterações já existiam; foram preservadas, não editadas pela sessão.
Não descartar ou tentar sincronizar este diretório com origin automaticamente.
As refs remotas locais podem pertencer ao remoto anterior.

O patch não commitado adiciona Aider, não demonstra integração Ollama apesar do
nome da branch. Inclui --message, --yes-always, --no-auto-commits, descoberta e
readiness. Commits locais anteriores contêm contrato neutro de executor,
provider layer e capability boundary. Trabalho útil como candidato de mecanismo,
não como pacote para transplantar integralmente.

## Fontes fixadas / cópias de inspeção

Todas as cópias abaixo foram clones temporários rasos da branch padrão;
não alteram o cwd original. Caminhos podem desaparecer; reverificar antes de usar.

1. SMAG local: 5b73e034668904d3cc5871e9940e4bdbdc95b4f7 + patch sujo acima.
   Proveniência original: https://github.com/oigorbrito/smag
2. SMAG-ReX: https://github.com/oigorbrito/smag-rex
   main: c7b2d6a4a20350a6e7d520e2ee540a096242e070
   C:/Users/igorb/AppData/Local/Temp/smag-rex-read-aXRi9G
3. FineCore: https://github.com/oigorbrito/FineCore
   main: d2011bc752842c66fc508d65c03c011c959cc8df
   C:/Users/igorb/AppData/Local/Temp/finecore-read-ia8DnX
4. Pathlayer: https://github.com/PathlayerLabs/pathlayer
   e93b8d2026b2c625185ff1448b98daee50067b4a
   C:/Users/igorb/AppData/Local/Temp/supervisor-review-mbzWhw
5. Agent Efficiency: https://github.com/agent-efficiency/agent-efficiency
   bd531d5652ce413f5985e00330c1eb17a0a843e4
   C:/Users/igorb/AppData/Local/Temp/supervisor-review-BYZkvZ
6. Agent Loop Guard: https://github.com/RIMUMURUDEV/agent-loop-guard
   595f9042be5692492db5b5555be556652aba95f2
   C:/Users/igorb/AppData/Local/Temp/supervisor-review-8BuvA4

## Conclusões restritas de inspeção

SMAG e SMAG-ReX NÃO têm cores idênticos. SMAG local é governança Node/JavaScript;
SMAG-ReX retém SWE-ReX Python e acrescenta src/smag_rex; também tem API Express,
React e runtime TypeScript próprio. Presença de adaptadores TS não herda
qualificações históricas Python. Verificações documentais não foram reexecutadas.

FineCore é workspace Rust derivado do Orca Harness. finecore.rs inclui main.rs.
Não inferir medições/releases FineCore a partir dos números upstream do README.

COUPLING-MAP.md contém referências detalhadas. Pontos centrais:
- SDK: HarnessBuilder.workspace/state_dir, AgentBuilder.tools/limits/extension,
  SessionBuilder.environment/open, Session.start/run_outcome.
- CLI: --json e --approvals stdio permitem supervisão bidirecional existente.
  approval_request sai no stdout; approval allow/deny/always entra no stdin.
  Não dividir stdin entre prompt e respostas. EOF nega pendentes.
  JSON malformado é ignorado; não equivale a deny imediato.
- StdioApprovals cobre GATED_TOOLS, não todas as ferramentas. Auto/yolo e
  auto-approve afetam instalação/bypass do gate. Não enviar always em perfil estrito.
- Dispatcher before_tool recebe call original; Rewrite é aplicado depois dos
  hooks. Plugins podem reescrever. Stdio pode aprovar input diferente do executado.
  Estado: CODE_INSPECTED, não exploit reproduzido. Não chamar isso de vulnerabilidade
  universal nem corrigir core por inferência.
- around_tool recebe input efetivo daquele estágio. Wrappers posteriores podem
  alterá-lo; ter around_tool não garante validação final sozinho.
- SessionEnvironment.sandbox liga ferramentas built-in ao backend do host;
  provisionar/encerrar sandbox continua fora do SDK. Custom tools/MCP/extensões
  não ficam automaticamente isoladas. network_off é nota de ambiente já isolado,
  não firewall configurado pelo método.
- SDK RunOutcome distingue execução/persistência/dropped_events; preferir caminho
  detalhado para não perder accounting parcial. Overflow é perda explícita.
- Drop de RunHandle solicita cancelamento, não comprova término.
- pgroup.rs usa killpg Unix best-effort; helper não-Unix é vazio, filho direto
  pode ser encerrado por outros mecanismos. Não demonstrado término de netos Windows.
- CLI propaga gate stdio explicitamente no caminho examinado dos subagentes;
  extensão RunRequest no SDK não é herdada automaticamente pelos filhos.
- ModelResponse::Final / summary success / exit 0 não equivalem a tarefa aceita.
- Não há necessidade demonstrada de alterar loop para integração básica.
  CLI vs bridge SDK ainda NÃO escolhido.

## Candidatos por mecanismo, não incorporação aprovada

- SMAG: lifecycle, contrato neutro, staging/auditoria/promoção.
- SMAG-ReX: fronteiras pequenas de autoridade/execução/aceitação.
  acceptance.py usa IndependentVerification(passed); isso sozinho não impõe
  independência nem proveniência do verificador.
- Pathlayer: estagnação condicionada a evidência, repetição, histerese.
  Ausência de medição não vira stall. Isso não autoriza aceitar sem evidência.
- Agent Efficiency: recibos vinculados a workspace/configuração e invalidade por
  drift. Hooks deliberadamente fail-open; não transplantar essa regra para
  segurança/aceitação obrigatória.
- Agent Loop Guard: fingerprints e política MCP; não importar stack completa.
  Canonicalização heurística precisa de avaliação de falsos positivos.

Licenças declaradas nos manifestos: Pathlayer/Loop Guard Apache-2.0,
Agent Efficiency MIT. Isso não é auditoria completa de licença/proveniência;
revisar antes de copiar código. Nenhum código foi copiado para o laboratório.

## Execução realmente realizada

Windows; Python 3.12.10; Node v26.10.0.

SMAG local:
node --test packages/smag-governance/test/executor-discovery.test.mjs packages/smag-governance/test/runtime-rebuild.test.mjs packages/smag-governance/test/startup-readiness.test.mjs packages/smag-governance/test/executor-contract.test.mjs packages/smag-governance/test/capability-boundary.test.mjs packages/smag-governance/test/embedded-runtime-adapter.test.mjs packages/smag-governance/test/provider-layer.test.mjs
Resultado: 40 testes, 39 passaram, 1 falhou.
Falha: runtime-rebuild.test.mjs:55 espera regex /codex or opencode|not validated/,
mas mensagem agora diz codex, opencode, or aider. Não corrigido.
Não houve gate npm test completo, bun typecheck nem Aider/Ollama real E2E.

Pathlayer (cwd clone correspondente):
python -m pytest -o addopts='' -q tests/test_loop.py tests/test_no_progress.py tests/test_retry.py
144 passaram. addopts de cobertura desativado deliberadamente para escopo focal;
não representa gate de cobertura ou suíte inteira.

Agent Loop Guard:
python -m pytest -q tests/unit/test_loop_detector.py tests/unit/test_mcp_policy.py
8 passaram. Não é prova de firewall/sandbox integrado nem de stack inteira.

Agent Efficiency:
PYTHONPATH=plugins/agent-efficiency/src python -m unittest discover -s tests -p test_verification.py
23 testes, 22 com erro. Maioria: os.fchmod ausente no Python Windows;
também PermissionError ao remover objetos Git em um teste. Não houve patch,
shim, rerun Linux nem qualificação Windows. Não classificar como PASS.

Validação documental local: JSON parseável, 6 registros de fonte com SHA de
40 hex, 15 IDs únicos e todos NOT_EXECUTED. Isto não valida comportamento.

FineCore e SMAG-ReX: código/documentação inspecionados; NÃO compilados/testados
nesta revisão. Não houve comparação pareada entre candidatos, medição de ganho,
chamadas reais de modelo ou implementação de adaptador.

## Próxima unidade defensável

1. Ler COUPLING-MAP.md e revisar cobertura/limites com o usuário.
2. Produzir protocolo de qualificação dos seams, ainda sem portar código:
   Q1 correlação/EOF/timeout de aprovações;
   Q2 aprovação vs input reescrito;
   Q3 isolamento e caminhos alternativos;
   Q4 término observado de descendentes por SO;
   Q5 eventos perdidos/JSON parcial/persistência;
   Q6 herança de política e orçamento agregado;
   Q7 falso sucesso e identidade do artefato verificado.
3. Definir ambiente, capacidades, expectativas e limiares antes de executar.
4. Somente então selecionar CLI/SDK e obter escopo de implementação.

Não transformar automaticamente esta lista em autorização de teste de modelo,
provisionamento externo, patches upstream, criação de projeto Git, commits ou push.

## Regras para o próximo agente

- Não confundir origin atual com proveniência da árvore local suja.
- Não sobrescrever D:/projetos/smag-rex nem apagar .vs por aparência.
- Não afirmar implementação/teste de supervisor; só documentação produzida.
- Revalidar refs antes de trabalho sensível a branch; não atualizar SHAs históricos
  por inferência ou comparar resultados de ambientes diferentes como benchmark justo.
- DOCUMENTED != CODE_CONFIRMED != EXECUTED != ACCEPTED.
- Contrato, cenários e mapa são propostas; nenhuma integração aprovada.
- A próxima tarefa é refinar/qualificar o acoplamento, não combinar frameworks.
