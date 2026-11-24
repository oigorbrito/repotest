# Integração técnica — Pi Original × Pi-Rust (resty-3)

## Veredito: PARCIALMENTE VALIDADO

A integração corrige todos os defeitos identificados em `review-comparative/REVIEW.md` que são verificáveis sem `-race`. Duas pendências impedem aprovação plena: (1) `-race` não pôde ser executado, porque este host não tem cgo; (2) a remoção da sincronização de leitura em `Clone()` não é detectada pelos testes sem o detector de corrida.

## 1. Caminho da terceira cópia

`D:\projetos\pi-benchmark\review-comparative\integrated\resty-3\`

Base: `resty-3.zip`, extraído para essa pasta. Sem Git. As duas árvores originais (`resty-3or`, `resty-3rust`) e o ZIP foram conferidos por SHA-256 após a integração e continuam idênticos aos hashes da revisão.

## 2. Arquivos modificados e adicionados (em relação ao ZIP)

| Arquivo | Situação | Conteúdo |
|---|---|---|
| `client.go` | modificado | hooks com snapshot sob `RLock`; `Clone()` corrigido; notas de deadlock removidas |
| `circuit_breaker.go` | modificado | `RunOnTriggerHooks` e `RunOnStateChangeHooks` com snapshot sob `RLock` |
| `BUILD.bazel` | modificado | registra `circuit_breaker_test.go`, `client_clone_test.go` e `hooks_concurrency_test.go` |
| `client_clone_test.go` | **adicionado** | 9 testes de regressão de `Clone()` |
| `hooks_concurrency_test.go` | **adicionado** | testes de hooks do Pi original, sem o teste de Clone dependente de capacidade, mais o teste de concorrência adaptado do Rust (C3) |

Diff completo: `integrated/INTEGRATION.patch` (752 linhas).

## 3. Correções do `Clone()`

Estado no ZIP e na revisão, e o que foi feito:

1. **`beforeRequest`, `afterResponse`, `retryConditions` compartilhavam o array do pai.** Agora cada um é `slices.Clone`. Confirmado por sonda antes da correção (`sameBackingArray=true`, middleware do pai sobrescrito).
2. **`retryHooks` e as cinco listas de hook** eram copiadas sem isolamento. Agora são `slices.Clone` (correção dos dois agentes, mantida).
3. **`contentDecompresserKeys`** usava `copy(cc.x, c.x)`, que copia o slice sobre si mesmo e mantém o array compartilhado. Agora é `slices.Clone`.
4. **`cookies`** só era recriado quando `len > 0`. Um slice vazio com capacidade continuava compartilhado. Agora é sempre alocado. Defeito que nenhum dos agentes tratou.
5. **Leitura do pai sem sincronização.** `*cc = *c` agora ocorre sob `c.lock.RLock()`. Confirmado que nenhum chamador interno de `Client.Clone` segura o lock, então não há deadlock. Hooks também não o seguram durante a execução (passo 1), então `Clone()` chamado de dentro de um hook funciona (testado).
6. **Mapas e demais campos.** `maps.Clone` e `cloneURLValues` já isolavam os mapas; `header`, `pathParams`, `credentials`, `proxyURL` e o mutex (recriado) estavam corretos.

**Decisão deliberada (não alterada):** ponteiros para objetos com estado (`httpClient`, `loadBalancer`, `circuitBreaker`, `hedging`, `rateLimiter`, `log`) continuam **compartilhados** entre pai e clone. Não são listas ou slices mutáveis, e compartilhá-los é o comportamento pretendido pela API (um pool de conexões ou um circuit breaker é um recurso, não uma configuração). Registrado como decisão, não como omissão.

## 4. Resultados reais por conjunto de testes

Todos executados em `integrated/resty-3` com `-mod=readonly`.

| Conjunto | Comando | Resultado |
|---|---|---|
| Compilação e análise | `gofmt -l .`, `go vet`, `go test -run '^$'` | limpos (exit 0) |
| Hooks, Clone, reentrância | `go test -count=1 -v -run 'TestClientHook\|TestClientClose\|TestClientCloneHook\|TestCircuitBreakerHook\|TestClone\|TestCircuitBreakerOn'` | **21 de nível superior PASS, 0 FAIL** (24 subtestes PASS) |
| Circuit breaker (todos) | `go test -count=1 -v -run 'CircuitBreaker'` | **25 PASS, 0 FAIL** |
| Concorrência | `TestClientHookConcurrentRegistrationAndDispatch` (5 subtestes repetíveis) e `TestCloneConcurrentWithRegistration` | **PASS** (incluídos no conjunto acima) |
| Repetição | mesmo conjunto focado com `-count=5` | **110 PASS, 0 FAIL** |
| Cruzado A | testes do Rust (renomeados) sobre o código integrado | **5 PASS, 0 FAIL** |
| Cruzado B | testes integrados sobre o código do Rust | 17 PASS, **5 FAIL** (os 5 testes de aliasing de Clone) |
| Cruzado C | testes integrados sobre o código do Pi original | 17 PASS, **5 FAIL** (os mesmos 5) |
| Suíte completa | `go test -count=1 -v .` | 1292 linhas PASS, 2 linhas FAIL (ver §5) |

Os cruzados B e C confirmam, de forma independente, o defeito identificado na revisão: os dois agentes deixaram aliasing em `afterResponse`, `beforeRequest`, `retryConditions`, `contentDecompresserKeys` e `cookies`.

## 5. Comparação com os resultados anteriores

Métrica comparável (contagem de linhas `--- PASS` e `--- FAIL` em qualquer nível, mesmo critério para todas):

| Árvore | PASS | FAIL | Falhas (nomes) |
|---|---|---|---|
| Base (ZIP) | 1261 | 3 | `TestTraceInfo`, `TestRequestDataRace`, `TestPostRedirectWithBody` |
| Pi original | 1277 | 4 | `TestTraceInfo`, `TestPostRedirectWithBody`, `TestRequestDataRace` |
| Pi-Rust | 1285 | 3 | `TestTraceInfo`, `TestPostRedirectWithBody` |
| **Integrada** | **1292** | **2** | `TestTraceInfo` (apenas) |

**Nenhuma falha nova** em relação à base. A integrada não tem falha que não exista na base.

Falhas pré-existentes, **não atribuídas à integração**:
- `TestTraceInfo/enable_trace_on_invalid_request,_issue_#1016`: idêntica nas quatro árvores (`Expected true, got [false]`).
- `TestPostRedirectWithBody` e `TestRequestDataRace`: testes de carga (4.000 requisições concorrentes) com `connection refused` no Windows. Variam de uma execução para outra. Medidas: `TestRequestDataRace` falhou 6/6 na base, 6/6 no original, 5/6 no Rust e 1/6 na integrada; `TestPostRedirectWithBody` falhou 9/10 na base, 10/10 no original, 10/10 no Rust e 3/6 na integrada. **A variação não é evidência de melhoria**, porque o teste é instável e o defeito ambiental está fora do código alterado.

Lista de testes: 14 testes novos em relação à base (9 de Clone, 4 de hooks do original, 1 de concorrência do Rust), nenhuma duplicata.

## 6. Mutação: os testes detectam os defeitos?

Cada mutante reverte uma única correção da integração (`integrated-mut/`, logs em `mut-logs/`). Mesmo conjunto de testes (`TestClone|TestClientHook|TestClientClose|TestCircuitBreakerHook|TestCircuitBreakerOn`).

| Mutante | Correção revertida | Resultado | Testes que falham |
|---|---|---|---|
| mA | clone dos seis slices de hook | **detectado** | `TestCloneHookRegistrationIsolated` |
| mB | clone de middlewares e retry conditions | **detectado** | `TestCloneDoesNotShareResponseMiddlewares`, `…RequestMiddlewares`, `…RetryConditions` |
| mC | `contentDecompresserKeys` como no ZIP | **detectado** | `TestCloneDoesNotShareContentDecompresserKeys` |
| mD | `cookies` como no ZIP | **detectado** | `TestCloneDoesNotShareEmptyCookieSlice` |
| mE | circuit breaker do ZIP | **detectado** | `TestCircuitBreakerHookReentrantRegistration` |
| mF | despacho de hooks segurando o lock (como no ZIP) | **detectado** | `TestClientHookGetterWhileWriterWaits`, `TestClientCloseReentrantFromOnCloseHook`, `TestClientHookOrderAndRegistration` |
| mG | `RLock` removido de `Clone()` | **NÃO detectado** | nenhum (ver §7) |
| mH | código do ZIP inteiro com os testes integrados | 10 falhas de regressão | todos os testes de defeito acima |

A mutante **H** mostra também o que os testes de concorrência *não* detectam sem `-race`: no código-base, `TestClientHookConcurrentRegistrationAndDispatch` e `TestCloneConcurrentWithRegistration` passam. Essa cobertura de corrida depende do detector.

Os testes de guarda `TestCloneFromInsideHookDoesNotDeadlock` e `TestCloneCopiesStateAndResetsInstanceState` passam também na base. São guardas de regressão contra uma correção futura, não detectores do defeito atual.

## 7. Pendências

1. **`-race` não executado.** Exige cgo; este host não tem compilador C (`go: -race requires cgo`). Consequências:
   - a mutante G (`RLock` removido de `Clone()`) não é detectada;
   - os testes de concorrência só verificam ausência de deadlock e de perda de registro, não ausência de corrida;
   - as afirmações de "race-free" continuam sem verificação dinâmica. Os comentários dos testes dizem isso explicitamente.
   **Ação necessária:** executar `CGO_ENABLED=1 go test -race -count=5 -run 'TestClone|TestClientHook|TestCircuitBreaker' .` em ambiente com gcc.
2. **Testes de carga instáveis** (§5). Pré-existentes.
3. **Lacuna de `BUILD.bazel` pré-existente, fora do escopo.** O ZIP omite cinco arquivos de teste que não exercitam o código alterado: `debug_test.go`, `query_test.go`, `rate_limiter_test.go`, `redirect_test.go`, `stream_test.go`. Não foram adicionados, para não ampliar o escopo.
4. **Testes cruzados A não cobrem o Clone do Rust.** O conjunto do Rust não tem teste de Clone; isso é esperado, pois a integração é o ponto de referência.
5. **Os testes de concorrência não são um teste de corrida.** Documentado no próprio arquivo.

## 8. Alterações de código de integração (registro do processo)

Durante a validação, encontrei e corrigi problemas de minha própria autoria, que não chegaram à entrega:
- arquivos gravados com `\r\n` por escrita em modo texto no Windows (`gofmt` acusou o arquivo inteiro); normalizados para LF;
- um teste usava `parent.QueryParam` inexistente; trocado por `queryParams`;
- um teste assumia inserção no fim para `AddRequestMiddleware`, que insere antes do último elemento; reescrito para comparar a sequência completa;
- um teste de Clone tinha uma linha inútil (`assertNil(t, nil)`); removida.

Scripts de integração e mutação: `integrate_prod.py`, `mutate.py`, `snippets/`.
