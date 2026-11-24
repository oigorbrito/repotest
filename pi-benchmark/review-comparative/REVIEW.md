# Revisão técnica comparativa — Pi Original × Pi-Rust (resty-3)

Somente leitura. Nenhum código foi editado; nenhum commit, push ou merge; nenhum ZIP ou diretório de trabalho foi modificado.
SHA-256 do ZIP de referência: `67e2d67ebd362221f7f80dceff856f2fbaa216769adb99fbef9096725e237b80` (conferido antes e depois).

## 0. Estrutura e método

- Referência: `resty-3.zip`, raiz interna `resty-3/` (58 arquivos, sem `.git`, sem `__MACOSX`).
- Original: `resty-3or/resty-3/` (59 arquivos). Rust: `resty-3rust/resty-3/` (59 arquivos). Raiz `resty-3/` confirmada nas duas.
- Comparação por caminho relativo e SHA-256 (`hash_compare.py`, `hashes.json`). Não há diferença de quebra de linha: ZIP e as duas cópias usam LF.

| Caminho | Original × ZIP | Rust × ZIP |
|---|---|---|
| `client.go` | modificado (+26/-22) | modificado (+26/-21) |
| `circuit_breaker.go` | modificado (+6/-4) | modificado (+8/-4) |
| `BUILD.bazel` | — | modificado (+1) |
| `hooks_concurrency_test.go` | **adicionado** (294 linhas) | — |
| `client_hooks_concurrency_test.go` | — | **adicionado** (259 linhas) |
| Removidos | nenhum | nenhum |

Nenhum outro arquivo difere. Os dois arquivos adicionados foram lidos integralmente (cópias de trabalho em `work/or/` e `work/rust/`).

## 1. Diff completo — Pi original (`diff-or.patch`)

```diff
--- a/circuit_breaker.go
+++ b/circuit_breaker.go
@@ -392,8 +392,9 @@
 // RunOnTriggerHooks method executes all registered trigger hooks with the given request and error.
 func (cb *circuitBreakerBase) RunOnTriggerHooks(req *Request, err error) {
 	cb.lock.RLock()
-	defer cb.lock.RUnlock()
-	for _, h := range cb.triggerHooks {
+	hooks := cb.triggerHooks
+	cb.lock.RUnlock()
+	for _, h := range hooks {
 		h(req, err)
 	}
 }
@@ -410,8 +411,9 @@
 // RunOnStateChangeHooks method executes all registered state change hooks with the given old and new states.
 func (cb *circuitBreakerBase) RunOnStateChangeHooks(oldState, newState CircuitBreakerState) {
 	cb.lock.RLock()
-	defer cb.lock.RUnlock()
-	for _, h := range cb.stateChangeHooks {
+	hooks := cb.stateChangeHooks
+	cb.lock.RUnlock()
+	for _, h := range hooks {
 		h(oldState, newState)
 	}
 }
--- a/client.go
+++ b/client.go
@@ -931,9 +931,6 @@
 //
 // Out of the [Client.OnSuccess], [Client.OnError], [Client.OnInvalid], [Client.OnPanic]
 // callbacks, exactly one set will be invoked for each call to [Request.Execute] that completes.
-//
-// NOTE:
-//   - Do not use [Client] setter methods within OnError hooks; deadlock will happen.
 func (c *Client) OnError(hooks ...ErrorHook) *Client {
 	c.lock.Lock()
 	defer c.lock.Unlock()
@@ -946,9 +943,6 @@
 //
 // Out of the [Client.OnSuccess], [Client.OnError], [Client.OnInvalid], [Client.OnPanic]
 // callbacks, exactly one set will be invoked for each call to [Request.Execute] that completes.
-//
-// NOTE:
-//   - Do not use [Client] setter methods within OnSuccess hooks; deadlock will happen.
 func (c *Client) OnSuccess(hooks ...SuccessHook) *Client {
 	c.lock.Lock()
 	defer c.lock.Unlock()
@@ -961,9 +955,6 @@
 //
 // Out of the [Client.OnSuccess], [Client.OnError], [Client.OnInvalid], [Client.OnPanic]
 // callbacks, exactly one set will be invoked for each call to [Request.Execute] that completes.
-//
-// NOTE:
-//   - Do not use [Client] setter methods within OnInvalid hooks; deadlock will happen.
 func (c *Client) OnInvalid(hooks ...ErrorHook) *Client {
 	c.lock.Lock()
 	defer c.lock.Unlock()
@@ -979,9 +970,6 @@
 //
 // If an [Client.OnSuccess], [Client.OnError], or [Client.OnInvalid] callback panics,
 // then exactly one rule can be violated.
-//
-// NOTE:
-//   - Do not use [Client] setter methods within OnPanic hooks; deadlock will happen.
 func (c *Client) OnPanic(hooks ...ErrorHook) *Client {
 	c.lock.Lock()
 	defer c.lock.Unlock()
@@ -2432,6 +2420,15 @@
 	cc.header = c.header.Clone()
 	cc.pathParams = maps.Clone(c.pathParams)
 
+	// hook lists are appended under the clone's own lock, so they must not share
+	// backing arrays with the parent
+	cc.errorHooks = slices.Clone(c.errorHooks)
+	cc.invalidHooks = slices.Clone(c.invalidHooks)
+	cc.panicHooks = slices.Clone(c.panicHooks)
+	cc.successHooks = slices.Clone(c.successHooks)
+	cc.closeHooks = slices.Clone(c.closeHooks)
+	cc.retryHooks = slices.Clone(c.retryHooks)
+
 	if c.credentials != nil {
 		cc.credentials = c.credentials.Clone()
 	}
@@ -2669,17 +2666,21 @@
 // It wraps the error in a [ResponseError] if the resp is not nil
 // so hooks can access it.
 func (c *Client) onErrorHooks(req *Request, res *Response, err error) {
-	c.lock.RLock()
-	defer c.lock.RUnlock()
 	if err != nil {
 		if res != nil { // wrap with ResponseError
 			err = &ResponseError{Response: res, Err: err}
 		}
-		for _, h := range c.errorHooks {
+		c.lock.RLock()
+		hooks := c.errorHooks
+		c.lock.RUnlock()
+		for _, h := range hooks {
 			h(req, err)
 		}
 	} else {
-		for _, h := range c.successHooks {
+		c.lock.RLock()
+		hooks := c.successHooks
+		c.lock.RUnlock()
+		for _, h := range hooks {
 			h(c, res)
 		}
 	}
@@ -2688,8 +2689,9 @@
 // Helper to run panicHooks hooks.
 func (c *Client) onPanicHooks(req *Request, err error) {
 	c.lock.RLock()
-	defer c.lock.RUnlock()
-	for _, h := range c.panicHooks {
+	hooks := c.panicHooks
+	c.lock.RUnlock()
+	for _, h := range hooks {
 		h(req, err)
 	}
 }
@@ -2697,8 +2699,9 @@
 // Helper to run invalidHooks hooks.
 func (c *Client) onInvalidHooks(req *Request, err error) {
 	c.lock.RLock()
-	defer c.lock.RUnlock()
-	for _, h := range c.invalidHooks {
+	hooks := c.invalidHooks
+	c.lock.RUnlock()
+	for _, h := range hooks {
 		h(req, err)
 	}
 }
@@ -2706,8 +2709,9 @@
 // Helper to run closeHooks hooks.
 func (c *Client) onCloseHooks() {
 	c.lock.RLock()
-	defer c.lock.RUnlock()
-	for _, h := range c.closeHooks {
+	hooks := c.closeHooks
+	c.lock.RUnlock()
+	for _, h := range hooks {
 		h()
 	}
 }
```

Arquivo adicionado `hooks_concurrency_test.go` (294 linhas, 5 funções): `TestClientHookGetterWhileWriterWaits`, `TestClientCloseReentrantFromOnCloseHook`, `TestClientHookOrderAndRegistration`, `TestClientCloneHookRegistrationIsolated`, `TestCircuitBreakerHookReentrantRegistration`.

## 2. Diff completo — Pi-Rust (`diff-rust.patch`)

```diff
--- a/BUILD.bazel
+++ b/BUILD.bazel
@@ -39,6 +39,7 @@
     srcs = [
         "benchmark_test.go",
         "cert_watcher_test.go",
+        "client_hooks_concurrency_test.go",
         "client_test.go",
         "context_test.go",
         "curl_test.go",
--- a/circuit_breaker.go
+++ b/circuit_breaker.go
@@ -391,9 +391,11 @@
 
 // RunOnTriggerHooks method executes all registered trigger hooks with the given request and error.
 func (cb *circuitBreakerBase) RunOnTriggerHooks(req *Request, err error) {
+	// hooks run without holding cb.lock, so they may register further hooks
 	cb.lock.RLock()
-	defer cb.lock.RUnlock()
-	for _, h := range cb.triggerHooks {
+	hooks := cb.triggerHooks
+	cb.lock.RUnlock()
+	for _, h := range hooks {
 		h(req, err)
 	}
 }
@@ -409,9 +411,11 @@
 
 // RunOnStateChangeHooks method executes all registered state change hooks with the given old and new states.
 func (cb *circuitBreakerBase) RunOnStateChangeHooks(oldState, newState CircuitBreakerState) {
+	// hooks run without holding cb.lock, so they may register further hooks
 	cb.lock.RLock()
-	defer cb.lock.RUnlock()
-	for _, h := range cb.stateChangeHooks {
+	hooks := cb.stateChangeHooks
+	cb.lock.RUnlock()
+	for _, h := range hooks {
 		h(oldState, newState)
 	}
 }
--- a/client.go
+++ b/client.go
@@ -931,9 +931,6 @@
 //
 // Out of the [Client.OnSuccess], [Client.OnError], [Client.OnInvalid], [Client.OnPanic]
 // callbacks, exactly one set will be invoked for each call to [Request.Execute] that completes.
-//
-// NOTE:
-//   - Do not use [Client] setter methods within OnError hooks; deadlock will happen.
 func (c *Client) OnError(hooks ...ErrorHook) *Client {
 	c.lock.Lock()
 	defer c.lock.Unlock()
@@ -946,9 +943,6 @@
 //
 // Out of the [Client.OnSuccess], [Client.OnError], [Client.OnInvalid], [Client.OnPanic]
 // callbacks, exactly one set will be invoked for each call to [Request.Execute] that completes.
-//
-// NOTE:
-//   - Do not use [Client] setter methods within OnSuccess hooks; deadlock will happen.
 func (c *Client) OnSuccess(hooks ...SuccessHook) *Client {
 	c.lock.Lock()
 	defer c.lock.Unlock()
@@ -961,9 +955,6 @@
 //
 // Out of the [Client.OnSuccess], [Client.OnError], [Client.OnInvalid], [Client.OnPanic]
 // callbacks, exactly one set will be invoked for each call to [Request.Execute] that completes.
-//
-// NOTE:
-//   - Do not use [Client] setter methods within OnInvalid hooks; deadlock will happen.
 func (c *Client) OnInvalid(hooks ...ErrorHook) *Client {
 	c.lock.Lock()
 	defer c.lock.Unlock()
@@ -979,9 +970,6 @@
 //
 // If an [Client.OnSuccess], [Client.OnError], or [Client.OnInvalid] callback panics,
 // then exactly one rule can be violated.
-//
-// NOTE:
-//   - Do not use [Client] setter methods within OnPanic hooks; deadlock will happen.
 func (c *Client) OnPanic(hooks ...ErrorHook) *Client {
 	c.lock.Lock()
 	defer c.lock.Unlock()
@@ -2432,6 +2420,15 @@
 	cc.header = c.header.Clone()
 	cc.pathParams = maps.Clone(c.pathParams)
 
+	// hook lists are appended to under each client's own lock; they must not
+	// share a backing array with the parent
+	cc.errorHooks = slices.Clone(c.errorHooks)
+	cc.invalidHooks = slices.Clone(c.invalidHooks)
+	cc.panicHooks = slices.Clone(c.panicHooks)
+	cc.successHooks = slices.Clone(c.successHooks)
+	cc.closeHooks = slices.Clone(c.closeHooks)
+	cc.retryHooks = slices.Clone(c.retryHooks)
+
 	if c.credentials != nil {
 		cc.credentials = c.credentials.Clone()
 	}
@@ -2668,18 +2665,23 @@
 // Helper to run errorHooks hooks.
 // It wraps the error in a [ResponseError] if the resp is not nil
 // so hooks can access it.
+//
+// Hooks run without holding c.lock, so they may call Client getters and setters.
+// Hook slices are only ever appended to, and elements below the snapshot length
+// are never rewritten, so reading the snapshot after unlocking is race-free.
 func (c *Client) onErrorHooks(req *Request, res *Response, err error) {
 	c.lock.RLock()
-	defer c.lock.RUnlock()
+	errorHooks, successHooks := c.errorHooks, c.successHooks
+	c.lock.RUnlock()
 	if err != nil {
 		if res != nil { // wrap with ResponseError
 			err = &ResponseError{Response: res, Err: err}
 		}
-		for _, h := range c.errorHooks {
+		for _, h := range errorHooks {
 			h(req, err)
 		}
 	} else {
-		for _, h := range c.successHooks {
+		for _, h := range successHooks {
 			h(c, res)
 		}
 	}
@@ -2688,8 +2690,9 @@
 // Helper to run panicHooks hooks.
 func (c *Client) onPanicHooks(req *Request, err error) {
 	c.lock.RLock()
-	defer c.lock.RUnlock()
-	for _, h := range c.panicHooks {
+	hooks := c.panicHooks
+	c.lock.RUnlock()
+	for _, h := range hooks {
 		h(req, err)
 	}
 }
@@ -2697,8 +2700,9 @@
 // Helper to run invalidHooks hooks.
 func (c *Client) onInvalidHooks(req *Request, err error) {
 	c.lock.RLock()
-	defer c.lock.RUnlock()
-	for _, h := range c.invalidHooks {
+	hooks := c.invalidHooks
+	c.lock.RUnlock()
+	for _, h := range hooks {
 		h(req, err)
 	}
 }
@@ -2706,8 +2710,9 @@
 // Helper to run closeHooks hooks.
 func (c *Client) onCloseHooks() {
 	c.lock.RLock()
-	defer c.lock.RUnlock()
-	for _, h := range c.closeHooks {
+	hooks := c.closeHooks
+	c.lock.RUnlock()
+	for _, h := range hooks {
 		h()
 	}
 }
```

Arquivo adicionado `client_hooks_concurrency_test.go` (259 linhas, 5 funções): `TestClientHookGetterWhileWriterWaits`, `TestClientCloseReentrantFromOnClose`, `TestClientHookExecutionOrder`, `TestClientHookRegistrationDuringDispatch`, `TestClientHookConcurrentRegistrationAndDispatch`.

## 3. Verificação de corretude (estática)

### A. Locks e callbacks
- **Mesmo mecanismo nos dois:** o lock é segurado só para copiar o slice de hooks; os hooks rodam depois, sem lock. No original, `defer RUnlock()` mantinha o `RLock` durante toda a execução dos hooks.
- **Deadlock de setter dentro de hook eliminado** nos dois. `Close()` libera o lock antes de `onCloseHooks()` (`client.go`); `execute()` libera o lock antes de `RunOnTriggerHooks` (`client.go:2518`). Não há caminho de hook executado com `c.lock` ou `cb.lock` segurado, exceto o reentrante que os testes cobrem.
- **Invariante de corrida:** todas as escritas nas listas são `X = append(X, hooks...)` (6 em `client.go`, 2 em `circuit_breaker.go`), sob `Lock`. Não há truncamento nem reescrita de índice; por isso um snapshot lido sob `RLock` não muda depois. **Válido nos dois.** O Rust documenta essa invariante em `onErrorHooks`; o original não.
- **Remoção das notas "Do not use [Client] setter methods within … hooks; deadlock will happen":** correta nos dois, porque o defeito foi corrigido. É mudança de comportamento documentado e deve ser mantida.
- **Diferença de forma:** o Rust lê `errorHooks` e `successHooks` numa única seção crítica; o original lê uma lista por ramo. Efeito equivalente, custo desprezível.

### B. Clone()
- **Mesma correção nos dois:** `slices.Clone` das seis listas de hook (`errorHooks`, `invalidHooks`, `panicHooks`, `successHooks`, `closeHooks`, `retryHooks`). O `retryHooks` faltava no ZIP.
- **Defeitos residuais nos dois (nenhum foi corrigido):**
  1. **Aliasing reproduzido fora dos hooks.** Sonda descartável (`work/probe-ref`, `work/probe-rust`): após `Clone()`, pai e clone escrevem no mesmo slot de `afterResponse` (`sameBackingArray=true`); o middleware do pai é substituído pelo do clone (`ALIASING ... ran [C]`). Campos afetados: `beforeRequest` (`client.go:824`, `:850`), `afterResponse` (`:882`, `:910`) e `retryConditions` (`:1519`). Nenhum deles é copiado em `Clone()`.
  2. **`contentDecompresserKeys` continua compartilhado:** `Clone()` faz `copy(cc.contentDecompresserKeys, c.contentDecompresserKeys)`, que copia o slice sobre si mesmo, sem alocar.
  3. **Leitura sem lock:** `*cc = *c` lê todos os campos do pai sem `c.lock`. Há corrida se o pai for modificado em paralelo ao `Clone()`.
- Os dois recriam `cc.lock = &sync.RWMutex{}` corretamente (o mutex não é copiado por valor).

### C. Testes
| Aspecto | Original | Rust |
|---|---|---|
| Getter enquanto escritor aguarda (5 tipos de hook) | sim | sim |
| Close reentrante em OnClose | sim | sim |
| Ordem de execução | sim (`TestClientHookOrderAndRegistration`) | sim (C1) |
| Registro durante dispatch; efeito no próximo dispatch | sim | sim (C2) |
| Registro e dispatch concorrentes | não | sim (C3; sem asserção de resultado; só detecta corrida com `-race`) |
| **Clone isola listas de hook** | **sim** (`TestClientCloneHookRegistrationIsolated`) | **não** |
| **Circuit breaker: hook registra hook** | **sim** (`TestCircuitBreakerHookReentrantRegistration`) | **não** |
| Detecta a remoção da correção de Clone (mutação M3/M2) | **sim** (M3) | **não** (M2) |
| Detecta a remoção da correção do circuit breaker (mutação M1) | não aplicável (ver T8) | **não** (M1) |

Defeitos específicos dos testes:
- **Original:** `TestClientCloneHookRegistrationIsolated` depende de a capacidade do slice ser 4 após 3 `append`s. É detalhe de implementação do runtime Go; pode quebrar ou passar por acaso.
- **Rust:** C3 não verifica resultado; só detecta corrida com `-race`, que não foi executado (seção 6).
- **Ambos:** `TestClientHookGetterWhileWriterWaits` tem o mesmo nome nos dois arquivos, e os arquivos **não coexistem** no mesmo pacote (`TestClientHookGetterWhileWriterWaits redeclared in this block`, `run-or_rust-test.log`).
- **Ambos:** nenhum teste cobre o aliasing de `afterResponse`/`beforeRequest` (sonda da seção B).

### D. Alterações extras
- **Rust `BUILD.bazel`:** adiciona `client_hooks_concurrency_test.go` às `srcs` do `go_test`. Correto e necessário: o original não registrou seu arquivo de teste, então o alvo Bazel o ignora.
- **Rust:** comentários novos em `circuit_breaker.go` e `onErrorHooks`, que explicam o invariante. Manter.
- **Nenhum código desnecessário, nenhuma regressão e nenhuma mudança fora do escopo** em nenhum dos dois. Os diffs de produção são do mesmo tamanho e tocam os mesmos pontos.

### E. Eficiência
- **Agente (tokens, custo, tempo): N/D.** Não existe registro de execução do `resty-3` no benchmark: `results/`, `reports/`, `workspaces/` e `archive/` estão vazios para este caso, e não há `result.json` de execução. O único registro existente é o do incidente do Flipt, que é outra tarefa. Nada foi inventado.
- **Implementação (métricas objetivas do código):**
  - Produção: original +32/-26 linhas (`client.go`, `circuit_breaker.go`); Rust +34/-25 (mais +1 em `BUILD.bazel`).
  - Testes: original 294 linhas / 5 funções; Rust 259 linhas / 5 funções.
  - Duração da seleção de hooks: `ok` em 0,17 s (original) e 0,24 s (Rust). Sem diferença relevante.
  - Retenção do lock: nos dois, reduzida de "duração de todos os hooks" para "cópia do slice". Efeito comparável.

## 4. Execução de testes (separada da revisão estática)

Rodados em cópias (`work/`) com `-mod=readonly`; diretórios de trabalho não foram tocados. **`-race` não foi executado:** exige cgo, e não há compilador C neste host (`go: -race requires cgo`).

| # | Comando (no diretório indicado) | Resultado |
|---|---|---|
| T1 | `go test -count=1 -run '^$' .` em `ref`, `or`, `rust`, `ref+or-test`, `ref+rust-test` | compila nas cinco (exit 0) |
| T2 | `go test -count=1 -v -run 'TestClientHook\|TestClientClose\|TestClientCloneHook\|TestCircuitBreakerHook' .` | ref+or-test: 3 PASS / 16 FAIL; ref+rust-test: 13 PASS / 13 FAIL; **or: 19 PASS, 0 FAIL; rust: 26 PASS, 0 FAIL** |
| T3 | mesmos testes cruzados (funções renomeadas na cópia para evitar colisão) | **or+rust-test: 48 PASS, 0 FAIL; rust+or-test: 48 PASS, 0 FAIL** |
| T4 | `-count=5` com os testes de hook em `or` e `rust` | **sem falhas** nos dois |
| T5 | `go test -count=1 -timeout 1500s -v .` (suíte completa) em `ref`, `or`, `rust` | ref: 1261 PASS / 3 linhas FAIL; or: 1277 / 4; rust: 1285 / 3 |
| T6 | `-count=10 -run '^TestPostRedirectWithBody$'` | ref 9/10 FAIL; or 10/10 FAIL; rust 10/10 FAIL |
| T7 | `-count=6 -run '^TestRequestDataRace$'` | ref 6/6 FAIL; or 6/6 FAIL; rust 5/6 FAIL |
| T8 | **M1:** rust com `circuit_breaker.go` do ZIP; testes CB do rust (`-run CircuitBreaker`) | **exit 0: defeito não detectado** |
| T9 | **M2:** rust com as 6 linhas de clone removidas; testes `Clone\|TestClient` do rust | **exit 0: não detectado** |
| T10 | **M3:** original com as 6 linhas de clone removidas; testes do original | **exit 1: `TestClientCloneHookRegistrationIsolated` detecta** (`Expected [1], got [0]`) |
| T11 | Sonda de aliasing em `afterResponse`, em `ref` e `rust` | **ambos: aliasing reproduzido** (`ALIASING … ran [C]`) |
| T12 | Cobertura de linha (`-coverprofile`) da suíte completa | 100% nas funções alteradas em ref, or e rust. **Não discrimina a correção** (a base já era coberta; ver T8–T10) |

**Falhas da suíte completa, classificadas:**

| Teste | Base | Original | Rust | Causa |
|---|---|---|---|---|
| `TestTraceInfo/enable_trace_on_invalid_request,_issue_#1016` | FAIL | FAIL | FAIL | pré-existente, idêntico nas três árvores (`Expected true, got [false]`); sem relação com hooks |
| `TestPostRedirectWithBody` | ok na suíte completa; 9/10 FAIL isolado | FAIL | FAIL | 4.000 requisições concorrentes; `connectex: … recusou ativamente` (Windows); instabilidade de ambiente |
| `TestRequestDataRace` | FAIL | FAIL | ok (5/6 FAIL isolado) | 4.000 requisições concorrentes, mesma causa; a passagem única do rust **não é evidência** de correção |

**Conclusão de regressão:** nenhuma falha da suíte completa é introduzida pelos agentes. Todas as diferenças são instabilidade de carga, e as falhas pré-existem na base.

## 5. Consolidação

### Melhor solução por critério
| Critério | Melhor | Motivo |
|---|---|---|
| Locks e callbacks | **empate** (Rust com vantagem de documentação) | mesma lógica; Rust documenta o invariante de append-only |
| Clone() | **empate** | mesma correção; mesmos defeitos residuais |
| Testes de regressão | **Original** | cobre Clone e circuit breaker; Rust não detecta a remoção de nenhuma das duas correções (T8, T9) |
| Testes de concorrência | **Rust** | C3: registro e dispatch concorrentes (sem asserção; só com `-race`) |
| Build (Bazel) | **Rust** | registra o arquivo de teste; o original não |
| Escopo | **Rust** (comentários explicativos) | sem alteração fora do escopo; o original também não tem alteração fora do escopo |

### Preservar
- Snapshot sob `RLock` nos hooks (`client.go` e `circuit_breaker.go`), idêntico nos dois.
- `slices.Clone` das seis listas de hook em `Clone()`, incluindo `retryHooks`.
- Remoção das notas de deadlock na documentação dos setters.
- Comentários de invariante do Rust (`onErrorHooks`).
- `client_hooks_concurrency_test.go` (Rust): C1, C2 e C3 com `hookKinds` reutilizável. Renomear para não colidir com o do original.
- `TestClientCloneHookRegistrationIsolated` e `TestCircuitBreakerHookReentrantRegistration` (original): testes de regressão que detectam os defeitos. Trocar a asserção de capacidade por um cenário independente de capacidade.
- Entrada de `client_hooks_concurrency_test.go` em `BUILD.bazel` (Rust). Adicionar também a entrada do arquivo do original.

### Descartar
- Nada funcional. Descartar ou reescrever o comentário "race-free (see -race)" de C3, que afirma uma garantia que não foi verificada.
- A asserção de capacidade do slice em `TestClientCloneHookRegistrationIsolated`.

### Correções necessárias (valem para qualquer das duas)
1. Copiar `beforeRequest`, `afterResponse` e `retryConditions`, e alocar `contentDecompresserKeys`, em `Clone()`. Teste de aliasing (sonda T11).
2. Ler o pai sob `c.lock` em `Clone()`, ou documentar que `Clone()` não pode ser concorrente com modificações do pai.
3. Acrescentar ao conjunto do Rust um teste de regressão do circuit breaker e um de Clone (ausentes; T8, T9).
4. Executar `go test -race` em ambiente com cgo (não disponível aqui). Sem isso, C3 e os testes de corrida não são verificados.
5. Resolver a colisão de nomes antes de juntar os dois conjuntos de testes.

## 6. Limitações desta revisão
- `-race` não executado (sem cgo). Afirmações sobre corrida vêm de leitura de código e de mutação, não de detector.
- Testes de carga (`TestPostRedirectWithBody`, `TestRequestDataRace`) instáveis neste host; não foram usados como evidência.
- Não há registro de execução de agente para este trabalho (seção E).
- A pasta `diff-review/` na raiz do benchmark (criada entre 20:38 e 20:51, antes desta revisão) contém relatórios de uma revisão anterior. **Não foram usados como evidência** e não foram alterados.

## 7. Recomendação final

**Não escolher um lado inteiro. Combinar:**
- **Produção:** a mesma lógica dos dois (equivalentes); manter os comentários do Rust.
- **Testes:** conjunto do **original** (regressão de Clone e circuit breaker), mais o C3 de concorrência do **Rust**, renomeados para coexistir e sem asserção dependente de capacidade.
- **Build:** entrada no `BUILD.bazel` para os dois arquivos de teste.
- **Correções residuais:** itens 1–5 da seção 5 antes de aceitar a implementação.

Sem essas correções, a implementação de qualquer dos dois ainda deixa um defeito de aliasing reproduzível no `Clone()`, que nenhum teste existente detecta.
