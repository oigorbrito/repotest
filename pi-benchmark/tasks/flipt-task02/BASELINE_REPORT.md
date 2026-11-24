# BASELINE REPORT — TASK 02 / Flipt

**Veredito: BLOQUEADO.** O commit-base foi obtido e validado, e todas as falhas do baseline foram classificadas. O bloqueio é do **ambiente**: neste host, pacotes centrais para a tarefa (`internal/cmd`, storage SQL, cache Redis) não compilam ou não executam, e dois pacotes da área de cache/gRPC falham de forma determinística por causa do próprio host. Detalhes e condições de desbloqueio na seção 8.

Tentativa anterior (BLOQUEADA por rede): preservada em `evidence/attempt1/`. Nesta tentativa a rede estava disponível e o clone foi feito.

---

## 1. Ambiente e commit

| Item | Valor observado |
|---|---|
| Área isolada | `tasks/flipt-task02/` (clone em `source/`) |
| Repositório | `https://github.com/flipt-io/flipt.git` (clone completo, não shallow) |
| Commit-base (checkout destacado) | `0eaf98f050d86247bfe9bd7e41178865cb585060` — `chore: upgrade dagger to 0.8.2 (#2009)` |
| `git rev-parse HEAD` | `0eaf98f050d86247bfe9bd7e41178865cb585060` (igual ao base) |
| Commit associado `e2bd19da…` | Existe no repositório; o base é ancestral dele (`git merge-base --is-ancestor`). Seu conteúdo **não foi inspecionado**. |
| `git status` após checkout | `nothing to commit, working tree clean` |
| Sistema | Windows 11 Pro 10.0.26300; 16.252 MB de RAM; 1 processador (modelo não capturado) |
| Disco D: | 239G total; 88G livres antes, 87G depois |
| Git | `git version 2.56.0.windows.2` |
| Go | `go version go1.27.0 windows/amd64`; `GOTOOLCHAIN=auto`; `go.mod` declara `go 1.20` |
| **`CGO_ENABLED`** | **0**; `gcc` ausente do PATH |
| Docker | CLI `29.9.3`, **daemon não ativo** (`docker info` falha no pipe `dockerDesktopLinuxEngine`; distro WSL `docker-desktop` parada) |
| WSL | `Ubuntu` parada, **sem Go instalado** (não há comparação Linux disponível) |
| `core.autocrlf` | **`true`** — working tree em CRLF, índice em LF (`git ls-files --eol`: `i/lf w/crlf`) |
| `go mod download` | Exit 0, 6m14s |

Arquivos de evidência: `evidence/environment-attempt2.json`, `evidence/go-env.txt`, `evidence/clone-attempt2.log`, `evidence/go-mod-download.log`.

---

## 2. Resultado dos testes de baseline

Todos executados em `source/` (commit-base), com `-count=1`, sem alteração de código. Logs completos em `evidence/`.

| # | Comando | Exit | Duração | Resultado | Classificação |
|---|---|---|---|---|---|
| 1 | `go test ./internal/cache/...` | **1** | 45 s | `memory` ok (4/4 PASS). `redis` FAIL: `TestSet`, `TestGet`, `TestDelete` | Redis: **ambiental** (Docker daemon ausente; testcontainers falha com `open //./pipe/docker_engine`). `internal/cache` sem testes. |
| 2 | `go test ./internal/storage/cache/...` | **0** | 5 s | ok — 5/5 PASS (`TestSetHandleMarshalError`, `TestGetHandleGetError`, `TestGetHandleUnmarshalError`, `TestGetEvaluationRules`, `TestGetEvaluationRulesCached`) | — |
| 3 | `go test ./internal/server/middleware/grpc/...` | **1** | 4 s | 38 testes top-level PASS; **2 FAIL**: `TestEvaluationUnaryInterceptor_Evaluation` (4 subtestes) e `TestEvaluationUnaryInterceptor_BatchEvaluation`. **Reproduzido 5/5** (`-count=5`) | **Ambiental provável** (relógio do host; ver 2.1). |
| 4 | `go test ./internal/server/...` | **1** | 10 s | ok: `server`, `audit`, `auth/method/{kubernetes,oidc,token}`, `evaluation`. **FAIL**: `server/auth` (`TestServer/ExpireAuthenticationSelf`, **5/5**) e `server/middleware/grpc` (item 3) | `server/auth`: **ambiental provável** (relógio; ver 2.1). |
| 5 | `go test ./...` | **1** | 97 s | **22 ok**, **16 FAIL** (10 por compilação, 6 por teste), 18 sem arquivos de teste | Ver tabela 2.2 |

### 2.1 Evidência de causa ambiental (relógio)

- `evidence/clock-resolution.txt` (Go 1.27.0, windows/amd64, 200.000 amostras): **200.000/200.000** deltas de `time.Now()` consecutivos são **zero**; `expiry_not_before=20000/20000`.
- Uma execução preliminar (saída mostrada no terminal, não gravada em arquivo) deu 199.998/200.000 zeros e menor delta não nulo de ≈0,58 ms.
- Relação com as falhas: `middleware.go` (teste) asserta `NotZero(RequestDurationMillis)` (`middleware_test.go:294`, `:336`), que depende de `end.Sub(start) > 0`. `server/auth/middleware.go:129` faz `ExpiresAt.Before(time.Now())`, e a expiração é gravada com `timestamppb.Now()` (`server/auth/server.go:161`). Com relógio grosso, `Before` é falso e a autenticação continua válida, o que é exatamente a falha observada.
- **Limitação:** não reproduzido em Linux (Go ausente no WSL). A classificação é "provável", não "confirmada".

### 2.2 Os 16 pacotes com FAIL em `go test ./...`

**Falhas de compilação (10)** — todas por `mattn/go-sqlite3` sem cgo:

```
internal\storage\sql\errors.go:44:19: undefined: sqlite3.Error
internal\storage\sql\errors.go:47:27: undefined: sqlite3.ErrConstraint
internal\storage\sql\errors.go:49:17: undefined: sqlite3.ErrConstraintForeignKey
internal\storage\sql\errors.go:51:17: undefined: sqlite3.ErrConstraintUnique
```

Pacotes: `cmd/flipt`, `internal/cmd`, `internal/storage/sql`, `…/sql/common`, `…/sql/mysql`, `…/sql/postgres`, `…/sql/sqlite`, `…/sql/testing`, `internal/storage/auth/sql`, `internal/storage/oplock/sql`. **Classificação: ambiental (CGO_ENABLED=0 sem gcc).** Consequência grave: `internal/cmd/grpc.go` (onde o cache é montado; seção 3) **não compila neste host**.

**Falhas de teste (6):**

| Pacote | Teste | Causa | Classificação |
|---|---|---|---|
| `internal/cache/redis` | `TestSet`, `TestGet`, `TestDelete` | Docker daemon ausente | Ambiental (confirmada pela mensagem) |
| `internal/gitfs` | `Test_FS` | Arquivos de `testdata` em CRLF (`autocrlf=true`); tamanho 8 vs 9 | **Ambiental, confirmada**: na variante `core.autocrlf=false` o teste **passa** (`evidence/variant-lf-test_FS.log`) |
| `internal/storage/fs/local` | `Test_SourceSubscribe` | `remove …a.features.yml: O arquivo já está sendo usado por outro processo` | Ambiental (lock de arquivo do Windows); persiste na variante LF |
| `internal/server/auth` | `TestServer/ExpireAuthenticationSelf` | Expiração não é "antes de agora" (2.1) | Ambiental provável |
| `internal/server/middleware/grpc` | `TestEvaluationUnaryInterceptor_Evaluation`, `_BatchEvaluation` | Duração zero (2.1). Persiste na variante LF, então não é CRLF | Ambiental provável |
| `internal/storage/auth/memory` | `TestAuthenticationStoreHarness/List_all_authentications_*` | Ordem divergente em listagem paginada. Persiste na variante LF | **Não classificada com certeza.** Hipótese: empates de `CreatedAt` pela resolução do relógio; não verificada |

**Resumo de classificação:** 0 falhas atribuídas ao código do commit-base com evidência direta. 5 de 6 falhas de teste e 10 de 10 falhas de build têm causa ambiental confirmada ou provável. 1 (`storage/auth/memory`) segue não classificada.

**Nenhuma falha foi tratada como falha da tarefa.**

### 2.3 Variante de diagnóstico (`source-lf-variant/`)

Clone separado com `core.autocrlf=false`, mesmo SHA. Usada apenas para separar causas (`evidence/variant-lf-tests.log`). Confirmou o caso CRLF (`Test_FS`) e mostrou que as demais falhas não dependem de CRLF. Não é área de agente.

---

## 3. Diagnóstico arquitetural

Referências no commit `0eaf98f0`. Linhas verificadas por leitura direta dos arquivos.

### 3.1 Onde as flags são consultadas durante avaliações

| Caminho | Consulta | Arquivo:linha |
|---|---|---|
| v2 `Variant` | `s.store.GetFlag` | `internal/server/evaluation/evaluation.go:24` |
| v2 `Boolean` | `s.store.GetFlag` e `GetEvaluationRollouts` | `evaluation.go:94`, `:128` |
| v2 `Batch` | `s.store.GetFlag` por item | `evaluation.go:252` |
| Legacy `Evaluate` | `s.store.GetFlag` | `internal/server/evaluator.go:19` |
| Legacy `BatchEvaluate` | `s.store.GetFlag` | `internal/server/evaluator.go:92` |
| Regras (legacy evaluator) | `e.store.GetEvaluationRules` | `internal/server/evaluation/legacy_evaluator.go:97` |
| Interface do storage de avaliação | `Storer` (GetFlag, GetEvaluationRules, GetEvaluationDistributions, GetEvaluationRollouts) | `internal/server/evaluation/server.go:14-19` |

O storage chega ao pacote de avaliação via `evalsrv := evaluation.New(logger, store)` em `internal/cmd/grpc.go:263`. `store` pode estar envolvido pelo cache de storage (3.2).

### 3.2 Onde ocorre o cache — duas camadas, uma delas inativa

**Camada A — cache de regras no storage (ATIVA quando `cache.enabled`).**
- `internal/cmd/grpc.go:247-255`: se `cfg.Cache.Enabled`, `store = storagecache.NewStore(store, cacher, logger)`.
- `internal/storage/cache/cache.go:15-19`: `Store` embute `storage.Store`.
- `:21-22`: chave `s:er:<namespace>:<flag>`.
- `:59-76`: **único método sobrescrito** é `GetEvaluationRules`. Não há `Delete` nem invalidação; escritas vão direto ao store subjacente.

**Camada B — cache de respostas gRPC (CODIFICADA, mas NÃO REGISTRADA por defeito de escopo).**
- Implementação: `internal/server/middleware/grpc/middleware.go:120-301` (`CacheUnaryInterceptor`), com chaves em `:406-412` (`f:`) e `:421-433` (`e:`).
- Registro: `internal/cmd/grpc.go:312-314`:
  ```go
  if cfg.Cache.Enabled && cacher != nil {
      interceptors = append(interceptors, middlewaregrpc.CacheUnaryInterceptor(cacher, logger))
  }
  ```
- **Defeito de escopo (leitura estática):** em `grpc.go:246` existe `var cacher cache.Cacher` (escopo da função). Dentro de `if cfg.Cache.Enabled {` (`:247`), a linha `cacher, cacheShutdown, err := getCache(ctx, cfg)` (`:248`) usa `:=`, que **declara um novo `cacher` no bloco**. A variável externa permanece `nil`, então `cacher != nil` em `:312` é falso e o interceptor **não é registrado**, mesmo com cache habilitado. A camada A continua funcionando, pois usa a variável interna (`:255`).
- **Não reproduzido dinamicamente:** `internal/cmd` não compila neste host (cgo). Confirmação exige ambiente com `gcc`/`CGO_ENABLED=1`.

**Backends (`cacher`):**
- Interface `Cacher` e chave `flipt:<md5>`: `internal/cache/cache.go:10-22`.
- Memória (`go-cache`, TTL de `cfg.Cache`): `internal/cache/memory/cache.go:19-39`.
- Redis (`go-redis/cache/v9`): `internal/cache/redis/cache.go:20-54`.
- Interceptor retorna direto se `cache == nil`: `middleware.go:124-126`.

### 3.3 `Cache-Control: no-store` é interpretado?

**Não.** Busca em todo o repositório (exceto `.git`), código e testes, por `no-store`, `cache-control` e `grpcgateway-cache`: **zero ocorrências**. O interceptor não lê metadata (`middleware.go` não contém `metadata.` nem `FromIncomingContext`).

**Caminho de propagação HTTP → gRPC (existe, mas o valor não é usado):**
- Gateway HTTP de avaliação: `internal/cmd/http.go:60` (`evaluateAPI = gateway.NewGatewayServeMux(logger)`), montado em `/evaluate/v1` (`http.go:138`).
- `internal/gateway/gateway.go:23-40` adiciona apenas opções de marshal; **não** define matcher de headers.
- Matcher padrão do grpc-gateway v2.16.2 (`runtime/mux.go:107-115`): headers "permanentes" recebem prefixo `grpcgateway-`. `Cache-Control` está na lista (`runtime/context.go:336`). Portanto `Cache-Control: no-store` chega ao contexto gRPC como metadata `grpcgateway-cache-control`, e ninguém a consulta.
- `Authorization` também é encaminhado (`context.go:153-155`).

### 3.4 Serialização atual

| Camada | Formato | Onde |
|---|---|---|
| Storage (regras) | **JSON** (`encoding/json`) de `[]*storage.EvaluationRule` | `storage/cache/cache.go:29` (marshal), `:50` (unmarshal) |
| Interceptor de avaliação (`flipt.EvaluationRequest`, legacy) | **Protobuf**: grava `*flipt.EvaluationResponse` direto | `middleware.go:145`, `:161` |
| Interceptor de avaliação (`evaluation.EvaluationRequest`, v2) | **Protobuf**: grava wrapper `evaluation.EvaluationResponse` (oneof Variant/Boolean) | `middleware.go:246`, `:270-285` |
| Interceptor de flag (`GetFlag`) | **Protobuf** de `*flipt.Flag` | `middleware.go:187`, `:203` |

Observações de risco:
- **Mesma chave para dois formatos.** `evaluationCacheKey` (`:421-433`) é usada tanto pelo caminho legacy (`:130`) quanto pelo v2 (`:231`). Requests legacy e v2 com mesmos namespace/flag/entity/context colidem na chave, mas gravam payloads de tipos diferentes (`flipt.EvaluationResponse` × `evaluation.EvaluationResponse`).
- **Variant e Boolean compartilham chave e tipo de request.** Ambos recebem `*evaluation.EvaluationRequest` (`rpc/flipt/evaluation/evaluation_grpc.pb.go`: `_EvaluationService_Variant_Handler` e `_Boolean_Handler`, ambos com `in := new(EvaluationRequest)`). O interceptor decide pelo tipo do request e **não usa `info.FullMethod`** (`middleware.go` contém `info.FullMethod` só na auditoria, `:349`). Uma resposta cacheada de Variant pode ser devolvida para uma chamada Boolean, e vice-versa. Hipótese forte; **não reproduzida** (exige ativar o interceptor, o que hoje não acontece por 3.2).
- **Chaves sem escape.** `fmt.Sprintf("e:%s:%s:%s:%s", …)` (`:429`) e `f:%s:%s` (`:409`) usam `:` como separador sem escape. Flag `a:b` + entity `c` e flag `a` + entity `b:c` produzem a mesma string antes do hash MD5 (`cache.go:21`).
- **`RequestId` vaza para o cache (risco, se a camada B for ativada).** A resposta copia `r.RequestId` (`evaluation/evaluation.go:57`), e a chave não inclui `RequestId`. `SetRequestIDIfNotBlank` (`rpc/flipt/evaluation/evaluation.go:23-35`) mantém um ID não vazio, então um hit devolveria o `request_id` da primeira chamada.
- **Erro de tipo sem verificação.** `middleware.go:161` e `:203` fazem `resp.(*flipt.EvaluationResponse)` / `resp.(*flipt.Flag)` sem `ok`; um tipo inesperado causa pânico.
- **Logs com variável errada.** `middleware.go:163`, `:169`, `:205`, `:211`, `:287`, `:293` logam `err` (sempre `nil` nesse ponto) em vez de `merr`/`cerr`.

### 3.5 Invalidação

- Flags/variantes: `Update/DeleteFlag` apagam `f:<ns>:<key>` (`middleware.go:216-222`); `Create/Update/DeleteVariant` apagam `f:<ns>:<flagKey>` (`:223-229`).
- **Respostas de avaliação (`e:`) não são invalidadas** por alterações de flag: a chave tem outro prefixo. Resultado: após `UpdateFlag`, a avaliação pode continuar devolvendo valor antigo até o TTL.
- **Regras de avaliação (`s:er:`) nunca são invalidadas.** Mudanças em rules, segments, constraints, rollouts ou distributions não apagam nada. Consistência depende só do TTL (`cfg.Cache.TTL`, valor padrão não verificado).

### 3.6 Comportamentos existentes a preservar

1. Cache desabilitado: store não é envolvido (`grpc.go:247`) e nenhum interceptor de cache é registrado.
2. Falha de leitura do cache não quebra a requisição: log e fallback ao handler/store (`storage/cache/cache.go:43-45`; `middleware.go:137-141`, `:178-181`, `:238-241`).
3. Falha de JSON/Protobuf não grava lixo: `set` retorna sem gravar (`storage/cache/cache.go:29-33`); erro de handler não é cacheado (`middleware.go:155-158`, `:197-199`, `:265-268`); erro do store não é cacheado (`storage/cache/cache.go:69-71`).
4. Formato das chaves é "backward compatible" (comentários em `middleware.go:407`, `:427`) e deve permanecer. Dados já gravados em Redis dependem disso.
5. Formato JSON de regras (`s:er:`) e Protobuf das respostas (`e:`, `f:`).
6. Ordem: interceptors de autenticação antes do cache (`grpc.go:309-312`, comentário "cache must come after auth interceptors").
7. `EvaluationUnaryInterceptor` define `RequestId` e timestamps em toda resposta (`middleware.go:91-118`; `rpc/flipt/evaluation/evaluation.go:120-136`).
8. Hash de chaves MD5 com prefixo `flipt:` (`internal/cache/cache.go:20-22`).

---

## 4. Lacunas dos testes oficiais

Avaliação feita pelos **nomes** dos testes e por trechos de setup. Não auditei integralmente o corpo de cada teste; onde não verifiquei, indico.

**Existente (nomes observados):**
- `internal/storage/cache`: erros de get, set (marshal) e unmarshal; regras cacheadas e não cacheadas.
- `middleware/grpc`: `TestCacheUnaryInterceptor_{GetFlag,UpdateFlag,DeleteFlag,CreateVariant,UpdateVariant,DeleteVariant,Evaluate,Evaluation_Variant,Evaluation_Boolean}`.
- `internal/cache/memory`: `TestSet`, `TestGet`, `TestDelete`. Redis tem os mesmos nomes, mas exige Docker.

**Lacunas identificadas (não cobertas pelos nomes ou pelo setup visto):**
1. **Nenhum teste de `no-store`/`Cache-Control`/metadata HTTP** (confirmado por busca no repositório). Esperado, pois a funcionalidade não existe no commit-base.
2. **Nenhum teste de montagem do servidor** que verifique se `CacheUnaryInterceptor` está registrado quando `cache.enabled=true`. O defeito de escopo (3.2) passaria despercebido. Além disso, `internal/cmd` não compila sem cgo.
3. **Variant × Boolean com mesma request.** Os testes `_Evaluation_Variant` e `_Evaluation_Boolean` parecem usar cache novo e uma única RPC por teste (confirmado pelo setup visto); a colisão cruzada não é exercida.
4. **Legacy × v2 com mesma chave** (3.4): sem teste de compatibilidade de payload.
5. **Colisão de chaves com `:`** (3.4): sem teste de fronteira.
6. **Invalidação de respostas `e:` após UpdateFlag/Rule**: nomes sugerem apenas remoção de `f:`. Não confirmado.
7. **Invalidação de regras `s:er:`** após mutações de rules/segments/rollouts: sem teste pelos nomes.
8. **`RequestId` em cache hit**: sem teste pelos nomes.
9. **Concorrência** (leitura concorrente + atualização): nenhum teste pelos nomes; sem `-race` registrado.
10. **Cache desabilitado** no nível de servidor: não verificado (depende de `internal/cmd`).

---

## 5. Matriz dos testes independentes propostos

**Status de todos: NÃO IMPLEMENTADOS** (conforme solicitado). Expectativas marcadas como **[falha atual]** são comportamentos que o código de hoje não cumpre; servem para documentar o risco e não devem ser usados como baseline verde. "Requisito" usa o texto do prompt, porque `tasks/task-02.md` ainda é esqueleto (ver seção 6).

| ID | Teste proposto | Comportamento esperado | Ponto de inserção | Risco coberto |
|---|---|---|---|---|
| T01 | Cache miss de flag (GetFlag) | Primeira chamada consulta store uma vez, responde corretamente e grava payload Protobuf válido | Pacote `middleware/grpc`, fake `Cacher` com spy + store mock | Miss tratado como valor; cache ineficaz |
| T02 | Cache hit de flag | Segunda chamada não chama o store e devolve o mesmo `Flag` | Mesmo pacote, memory cache real | Hit não usado; divergência de conteúdo |
| T03 | Isolamento por namespace e chave | Namespace `""` × `default` e flags diferentes geram chaves distintas; resposta de um nunca vaza para outro | Testes diretos de `flagCacheKey`/`evaluationCacheKey` e de interceptor | Vazamento entre namespaces |
| T04 | Colisão por separador `:` | Flag `a:b`/entity `c` ≠ flag `a`/entity `b:c` | `evaluationCacheKey` (`middleware.go:421`) | **[falha atual]** colisão de resposta |
| T05 | Round trip Protobuf (flag e wrapper de avaliação) | Marshal→unmarshal preserva oneof Variant/Boolean, timestamps e campos vazios | Helpers de serialização do interceptor | Corrupção/perda em serialização |
| T06 | Round trip JSON das regras | `[]*EvaluationRule` com distributions, segment, rollout sobrevive ida e volta sem perda | `storage/cache` (set/get) | Regras alteradas ao ler do cache |
| T07 | Regras em JSON: decisão igual com e sem cache | Mesmo request produz mesma decisão cacheado e não cacheado (Variant e Boolean, percentual e segmento) | Teste diferencial em `server/evaluation` com store wrapper | Interpretação divergente do payload cacheado |
| T08 | Falha de leitura do cache | `Get` retorna erro → resposta correta via store, nada é propagado ao cliente, log emitido | `middleware/grpc` com cacher que falha no `Get` | Erro mascarado ou indisponibilidade indevida (parcial: `TestGetHandleGetError` cobre só a camada A) |
| T09 | Falha de serialização | `Marshal` falha → não chama `Set`; resposta válida é devolvida | `middleware/grpc` com `proto.Marshal` injetado ou tipo inesperado | Bytes parciais gravados (parcial: `TestSetHandleMarshalError` cobre só a camada A) |
| T10 | Falha de `Set` do cache | `Set` falha → resposta do handler é devolvida normalmente | `middleware/grpc`, cacher com `Set` com erro | Falha de escrita quebrar a requisição |
| T11 | `no-store` impede gravação | Request com `grpcgateway-cache-control: no-store` → `Set` não é chamado e resposta é normal | Gateway HTTP (`/evaluate/v1`) → fake gRPC + cacher espião | Persistência de resposta que pediu não-armazenar. **[falha atual]** |
| T12 | `no-store` não contamina requests seguintes | Sequência: (1) `no-store` sem gravação; (2) sem header → grava e depois hit; (3) `no-store` de novo. Nenhum estado global vaza | Mesmo harness de T11, duas ou mais requests sequenciais | Estado global ou contexto reutilizado. **[falha atual]** no passo 1 |
| T13 | Metadados HTTP encaminhados pelo gateway | `Cache-Control` e `Authorization` chegam ao handler gRPC como `grpcgateway-cache-control` e `authorization`, com valor exato | Gateway com `gateway.NewGatewayServeMux` + `RegisterEvaluationServiceHandler` e backend que captura `metadata.FromIncomingContext` | Perda ou normalização de metadata (não depende de `internal/cmd`) |
| T14 | Avaliação nos dois tipos de request | Legacy `Evaluate`, v2 `Variant`, `Boolean` e `Batch` retornam o mesmo resultado com e sem cache | Servidor gRPC real (`bufconn`) com a cadeia completa de interceptors | Lógica implementada só em uma rota |
| T15 | Variant × Boolean com mesmo request | Chamar `Variant` e depois `Boolean` com o mesmo request devolve respostas do tipo certo | Servidor gRPC real, duas RPCs sequenciais, cache ativo | Payload de Variant servido para Boolean. **[falha atual]**, hipótese forte |
| T16 | Legacy × v2 com mesmo request | Chamadas legacy e v2 não lêem payload de outro tipo | Servidor gRPC real | Decodificação de payload incompatível |
| T17 | Cache desabilitado | `cache.enabled=false`: store não envolvido, nenhum interceptor de cache, resultados idênticos ao caso com cache | Construção do servidor (`internal/cmd`; exige cgo) ou teste de wiring | Regressão de compatibilidade; dependência obrigatória do cache |
| T18 | Wiring com cache habilitado | `cache.enabled=true` → `CacheUnaryInterceptor` presente na cadeia | `internal/cmd/grpc.go`, verificação da lista de interceptors (exige cgo) | Defeito de escopo em `grpc.go:248`. **[falha atual]** |
| T19 | Concorrência e consistência após atualização de flag | Com N goroutines lendo e uma atualizando: nenhuma leitura pós-`UpdateFlag` devolve valor antigo; `go test -race` limpo | Interceptor com memory cache real e store com mutex | Corridas, dados obsoletos (hoje o `e:` não é invalidado) |
| T20 | Erro do storage subjacente em GetFlag | Erro é propagado com a classificação esperada e **não** é gravado no cache; próxima chamada volta ao store | Interceptor + store fake que falha | Cacheamento de falha ou falha convertida em sucesso |
| T21 | Erro do storage em GetEvaluationRules | Erro não é cacheado (`s:er:`); próxima chamada consulta o store de novo | `storage/cache` com store fake | Cacheamento de falha |
| T22 | `RequestId` não vaza em cache hit | Duas chamadas com `request_id` diferentes recebem cada uma o seu ID | Interceptor com cache ativo | Vazamento de request_id entre clientes. **[falha atual]** se a camada B for ativada |
| T23 | Invalidação de regras (`s:er:`) | Após alteração de rule/segment/rollout, a próxima avaliação reflete a mudança (ou o teste documenta que depende de TTL) | `storage/cache` + store com escrita | Dados obsoletos por TTL |
| T24 | Chave determinística com contexto | Mesmo `context` em ordem de mapa diferente gera a mesma chave | `evaluationCacheKey` | Miss desnecessário ou chave instável |

---

## 6. Riscos e limitações

1. **`tasks/task-02.md` é esqueleto** ("Status: PENDENTE — conteúdo a definir"). O objetivo funcional não está especificado no repositório de benchmark. Os cenários desta análise seguem a lista do prompt. Antes de implementar, é preciso confirmar o requisito (principalmente o comportamento exato de `no-store` para leitura, não só para gravação).
2. **Ambiente não representativo para a tarefa:** `CGO_ENABLED=0` (sem `internal/cmd` e sem storage SQL), Docker parado (sem Redis), `autocrlf=true`, e host Windows com relógio grosso.
3. **Causas de falha não confirmadas em Linux:** relógio (2.1) e `storage/auth/memory` (não classificado).
4. **Defeito de wiring (3.2) não reproduzido dinamicamente.** Classificado por leitura estática do Go (`:=` sombreando variável externa).
5. **`go mod download` altera `go.work.sum`** (tracked, +709 linhas). O Go gera essas linhas; foram revertidas, mas qualquer `go mod download` futuro as reproduz. Os dois agentes devem partir do mesmo estado.
6. **`go.work.sum` não entra no diff de nenhum agente** sem ser deliberado: tratar como efeito de ambiente, não como mudança de código.
7. **Testes criam artefatos:** `Test_SourceSubscribe` deixou `testdata/a.features.yml` vazio após falhar. Ambos os agentes precisam de limpeza ou checagem de estado antes de cada execução.
8. **Versão de Go:** `go.mod` declara 1.20; o toolchain local é 1.27.0. Compilou sem problema, mas não há garantia de equivalência com a toolchain original do projeto.
9. **Dependência de rede:** o clone e o `go mod download` dependem do GitHub e do proxy Go (funcionaram nesta sessão; a tentativa 1 falhou por rede).
10. **Limites da análise:** não li integralmente o corpo dos testes oficiais; não inspecionei o commit `e2bd19da…`; não executei nenhum teste novo.

---

## 7. Integridade

- **Arquivos de produção:** `source/` está com `git status` limpo e HEAD = `0eaf98f050d86247bfe9bd7e41178865cb585060`. Nenhum arquivo do código foi editado.
- **Efeitos colaterais durante o baseline (revertidos):**
  - `source/go.work.sum` modificado por `go mod download`; restaurado com `git checkout`. Diff em `evidence/go.work.sum.diff.txt`, status em `evidence/status-before-cleanup.txt`.
  - `source/internal/storage/fs/local/testdata/a.features.yml` (vazio, sha256 `e3b0c442…b855`) criado por `Test_SourceSubscribe`; removido. Registro em `evidence/side-effects.txt`.
- **Arquivos temporários criados e removidos:** diretório `mktemp` com `main.go` de medição de relógio (removido após cada uma das duas execuções). Uma tentativa de gravar `clock-resolution.txt` em caminho relativo errado não criou arquivo; refeita com caminho absoluto.
- **Hashes:** `evidence/sha256-HEAD-blobs-LF.txt` (blobs do Git, LF canônico) e `evidence/sha256-relevant-files.txt` (working tree com CRLF; difere do blob, como esperado com `autocrlf=true`).
- **Preservados:**
  - Tentativa 1: `evidence/clone.log`, `environment.json`, `integrity.json` inalterados.
  - Relatório da tentativa 1: `evidence/attempt1/BASELINE_REPORT.attempt1-BLOQUEADO.md` (sha256 `9071a45c…a310`, igual ao original antes da substituição).
- **Variante LF:** `source-lf-variant/` mantido como evidência de diagnóstico (122 MB); não é área de agente. Contém `a.features.yml` gerado pelo teste, ainda não removido.
- **Commit e push:** nenhum commit, nenhum push, nenhum `git add`.
- **Repositório original do usuário (`D:\projetos\pi-benchmark`, pastas `pi-rust/`, `workspaces/`, etc.):** não modificado.

Índice de evidências: `evidence/` contém logs de cada comando (`baseline-*.log`, `rerun-*-count5.log`, `baseline-all.log`), `baseline-summary.txt`, `clock-resolution.txt`, `variant-lf-*.log`, `environment-attempt2.json`, `integrity-attempt2.json`, `go-env.txt`, `go-mod-download.log`.

---

## 8. Veredito

### **BLOQUEADO**

**Critérios do gate:**

| Critério | Situação |
|---|---|
| Commit correto | **Atendido.** HEAD = `0eaf98f0`, árvore limpa |
| Ambiente reproduzível | **Não atendido para a área da tarefa.** Os comandos são reproduzíveis (resultados repetidos 5/5), mas o ambiente não compila `internal/cmd` (onde o cache é montado) nem executa Redis, e dois pacotes de cache/gRPC falham por causa do host |
| Falhas do baseline classificadas | **Atendido em grande parte.** 10/10 falhas de build e 5/6 falhas de teste com causa ambiental (confirmada ou provável). Uma (`storage/auth/memory`) não classificada |

Por que BLOQUEADO e não APROVADO: se o gate exigisse só "reproduzível e classificado", seria APROVADO com ressalvas. Mas o objetivo do benchmark é comparar agentes em **um** ambiente. Nesse ambiente, `internal/cmd` (o wiring do cache, com o defeito de escopo) não compila, o Redis não roda, e `server/middleware/grpc` (o pacote-alvo dos testes de cache) falha de forma determinística. Um agente que implementasse corretamente poderia ser penalizado, ou um que quebrasse o wiring passaria despercebido.

**Condições para desbloquear (ordem sugerida):**

1. **Ambiente de execução:** rodar a baseline em Linux (ou WSL com Go instalado) com `gcc` e `CGO_ENABLED=1`, para compilar `internal/cmd` e os pacotes SQL. Isso também confirma ou refuta a hipótese do relógio.
2. **Docker:** iniciar o daemon do Docker Desktop (ou usar Docker em Linux) para os testes de Redis.
3. **Git:** clonar com `core.autocrlf=false` (ou `input`), para o working tree bater com o índice.
4. **Especificação:** preencher `tasks/task-02.md` (objetivo, entrada, critério de sucesso). Sem ela, não há como validar o `no-store`.
5. **Reexecutar** esta baseline no novo ambiente, registrar nova `environment-*.json` e novo `baseline-summary`, e reclassificar as falhas.

**Nenhum código foi implementado e nenhum agente foi executado.**
