# Baseline report — TASK 02 / Flipt

**Veredito: BLOQUEADO** — a área foi criada e os pré-requisitos locais básicos foram identificados, mas o clone do commit fixo falhou por indisponibilidade de rede. Sem checkout, não há evidência reprodutível para estado Git, hashes do código, testes nem diagnóstico arquitetural. Nenhum resultado foi inferido ou inventado.

## 1. Ambiente e commit

| Item | Resultado observado |
|---|---|
| Área isolada | `tasks/flipt-task02/` criada; `source/` não foi criado |
| Repositório pretendido | `https://github.com/flipt-io/flipt` |
| Commit-base requerido | `0eaf98f050d86247bfe9bd7e41178865cb585060` |
| Commit associado informado | `e2bd19dafa7166c96b082fb2a59eb54b4be0d778` |
| Clone | Falhou, exit code 128; proxy `127.0.0.1:443` não conectou ao GitHub |
| Git | `git version 2.56.0.windows.2` |
| Go | `go version go1.27.0 windows/amd64` |
| Docker | `Docker version 29.9.3, build 5457199` |
| Disco D: | 93,581,025,280 bytes livres no registro inicial |
| Sistema operacional | Não obtido: `Get-CimInstance Win32_OperatingSystem` retornou `Acesso negado 1` |
| Repositório pai | `D:\projetos\pi-benchmark` não é um checkout Git (`git rev-parse` falhou) |

A captura dos comandos e do erro de clone está em `evidence/environment.json` e `evidence/clone.log`. Não há `git status` ou `git rev-parse HEAD` do Flipt: nenhum repositório foi obtido. Portanto não se pode confirmar que o clone está no SHA-base.

## 2. Resultado dos testes de baseline

Nenhum comando Go foi executado. A ausência do checkout impede execução sem usar uma fonte diferente da solicitada, o que quebraria a reprodutibilidade. Assim, não há durações, exit codes de testes, contagens de testes aprovados/reprovados ou falhas de compilação para classificar. A limitação é ambiental (conexão ao GitHub pelo proxy), não uma falha atribuível à tarefa ou ao código.

| Comando solicitado | Estado | Classificação |
|---|---|---|
| `go test ./internal/cache/...` | Não executado | Bloqueado antes do checkout |
| `go test ./internal/storage/cache/...` | Não executado | Bloqueado antes do checkout |
| `go test ./internal/server/middleware/grpc/...` | Não executado | Bloqueado antes do checkout |
| `go test ./internal/server/...` | Não executado | Bloqueado antes do checkout |
| `go test ./...` | Não executado | Bloqueado antes do checkout |

## 3. Diagnóstico arquitetural

A inspeção de código não foi possível no commit indicado. Não se atribuem comportamento ou referências de arquivo/linha com base em outras revisões, resultados de busca do branch padrão ou implementações externas.

| Questão | Resultado verificável no commit-base |
|---|---|
| Onde flags são consultadas em avaliações | Indeterminado; fonte indisponível |
| Onde ocorre o cache atual | Indeterminado; fonte indisponível |
| Interpretação de `Cache-Control: no-store` | Indeterminada; fonte indisponível |
| Serialização atual | Indeterminada; fonte indisponível |
| Comportamentos atuais que devem ser preservados | Indeterminados; requer leitura do código e testes da revisão exata |
| Referências a arquivos e linhas | Não disponíveis; não inventadas |

O diagnóstico permanece pendente para quando o mesmo commit puder ser disponibilizado localmente e validado por SHA.

## 4. Lacunas dos testes oficiais

Não foi possível inspecionar os testes oficiais no commit-base. A tabela abaixo é uma proposta de cobertura independente baseada nos requisitos desta tarefa; não afirma ausência nos testes oficiais. Antes de usá-la, comparar cada caso com os testes existentes no SHA fixo e manter cenários realmente adicionais.

## 5. Matriz de testes independentes propostos

| Teste proposto | Comportamento esperado | Ponto de inserção sugerido | Risco coberto |
|---|---|---|---|
| Cache miss de flag | Primeira leitura delega ao storage e retorna o valor correto | Pacote que implementa cache de avaliações, teste externo ao cache | Cache não consultado ou miss tratado como valor válido |
| Cache hit de flag | Segunda leitura equivalente usa o valor cacheado sem nova leitura subjacente | Mesmo pacote, contador/fake de storage | Cache ineficaz ou chave incompatível |
| Isolamento por namespace e chave | Valores de namespaces e chaves diferentes nunca se cruzam | Teste de unidade do componente de cache | Colisão de chaves e vazamento entre namespaces |
| Round trip Protobuf | Serializar e desserializar preserva campos, valores, tipos e ordem semanticamente relevante | Teste do codec/cache serializado | Perda/corrupção de dados ou incompatibilidade de codec |
| Regras de avaliação em JSON | Payload JSON das regras produz a decisão e razão esperadas em caso válido e inválido | Teste de avaliação com fixture JSON própria | Interpretação divergente de regras serializadas |
| Falha de leitura do cache | Erro no cache segue a política explícita (fallback ao storage ou erro propagado) sem resposta silenciosamente incorreta | Teste de avaliação com cache fake que falha no get | Erros de cache mascarados ou indisponibilidade indevida |
| Falha de serialização | Erro de encode não grava bytes parciais nem altera a resposta válida da avaliação | Teste do adaptador/codec com serializador que falha | Corrupção persistente e erro mascarado |
| `no-store` impede gravação | Requisição marcada não faz set/write no cache, embora responda normalmente | Teste do fluxo HTTP→gateway→RPC com cache fake observável | Persistência de resposta que solicitou não ser armazenada |
| `no-store` não contamina requisições seguintes | Requisição posterior sem a diretiva pode ler/escrever normalmente; o estado da primeira não vaza | Teste sequencial no handler/gateway com contextos distintos | Diretiva armazenada em estado global ou contexto reutilizado |
| Metadados HTTP encaminhados pelo gateway | Header requerido chega ao contexto gRPC com nome/valor preservados conforme contrato | Teste do gateway com backend RPC de captura de metadata | Perda ou normalização incorreta de metadata |
| Avaliação nos dois tipos de request | Requests de avaliação por variante retornam resultados coerentes e compartilham apenas cache compatível | Testes de integração dos dois RPCs/handlers de avaliação | Implementar comportamento só em uma rota |
| Cache desabilitado | Leituras continuam corretas via storage e nenhuma operação de cache acontece | Teste de configuração do serviço de avaliação | Regressão de compatibilidade e dependência não opcional do cache |
| Concorrência e atualização de flag | Leituras concorrentes não corrompem dados; após atualização, a regra de invalidação/consistência observada é respeitada | Teste concorrente do storage/cache com sincronização controlada | Corridas, dados obsoletos e invalidação incompleta |
| Erros do storage subjacente | Falha do storage é propagada/classificada conforme contrato e não é gravada no cache como sucesso | Avaliação com storage fake que retorna erro | Cacheamento de falhas ou conversão em resultado falso |

Os pontos de inserção são indicativos e precisam ser ajustados depois de localizar a implementação e os limites entre pacotes no commit-base. Não foram criados testes nem alterado código.

## 6. Riscos e limitações

- Acesso ao GitHub via Git está bloqueado nesta sessão; sem o clone não existe baseline reproduzível.
- Versão de Go está registrada, mas não se confirmou se ela é a versão exigida pelo `go.mod`/toolchain do commit.
- Docker está instalado, mas não foi consultado o estado do daemon nem executados containers.
- Informação detalhada do Windows foi negada pelo sistema.
- Não há hashes SHA-256 dos arquivos relevantes porque os arquivos de produção não foram obtidos. Calcular hash em outro checkout violaria a identidade exigida.
- A matriz propõe cobertura; a comparação com os testes oficiais depende do checkout.

## 7. Integridade

- Nenhum arquivo do repositório original do usuário foi modificado; somente esta nova pasta de tarefa e suas evidências foram criadas.
- Não houve checkout e, portanto, não é possível declarar SHA atual do Flipt ou integridade do código-base.
- Nenhum arquivo de produção foi obtido ou alterado.
- `git clone` não deixou diretório `source/` parcial (verificado após a falha).
- Arquivos temporários criados e removidos: nenhum identificado. O log de clone foi preservado.
- Não houve commit nem push.

**Veredito final: BLOQUEADO.** O gate exige commit correto, ambiente reproduzível e classificação das falhas do baseline. O commit correto não pôde ser obtido e os testes não puderam iniciar; portanto, aprovar seria incorreto. Para retomar, é necessário restabelecer acesso ao GitHub ou disponibilizar um bundle/clone local comprovadamente contendo o SHA-base; então validar o SHA e executar novamente as etapas pendentes.
