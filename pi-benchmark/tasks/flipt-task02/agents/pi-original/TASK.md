# TASK — flipt-io/flipt (instância `instance_flipt-io__flipt-e2bd19dafa7166c96b082fb2a59eb54b4be0d778`)

**Repositório:** `flipt-io/flipt` (Go)
**Commit base:** `0eaf98f050d86247bfe9bd7e41178865cb585060`
**Origem da descrição:** descrição pública da instância no dataset SWE-bench Pro (campos `problem_statement`, `requirements` e `interface`), copiada sem alteração de conteúdo. Única exceção: os três itens de requisitos que citavam caminhos de arquivo tiveram apenas o caminho removido (ver "Nota de edição" no final).

Trabalhe apenas no repositório do diretório atual. Investigue o código livremente. Não faça commit, push ou merge.

---

## Descrição do problema

# Title
Flag lookups are cached only in the gRPC interceptor and clients cannot opt out of cached values

## Description
Flipt caches flag and evaluation responses inside a single gRPC unary interceptor. Because a flag is cached only at the request layer, the flag reads the storage layer performs while evaluating a flag never find a cached value, so enabling the cache does not reduce database load on those paths. Clients also have no way to opt out of the cache: a request that carries a `Cache-Control: no-store` header is served like any other request and what it fetches is still written to the cache, so a caller that needs the current state of a flag right after a change keeps reading the stale entry until it expires.

---

## Requisitos

- The shared cache package that defines the `Cacher` interface must provide `WithDoNotStore`, which returns a context carrying a do-not-store mark, and `IsDoNotStore`, which reports `true` for a context carrying the mark and `false` for any other context.

- The gRPC middleware package must define the unexported package-level constants `cacheControlHeaderKey` and `cacheControlNoStore`. `cacheControlHeaderKey` must equal the incoming metadata key under which grpc-gateway forwards the HTTP `Cache-Control` header, that is the grpc-gateway metadata prefix (`runtime.MetadataPrefix`) followed by `cache-control`, and `cacheControlNoStore` must equal `"no-store"`.

- `CacheControlUnaryInterceptor` must exist in the gRPC middleware package as a function callable directly as a `grpc.UnaryServerInterceptor` (context, request, server info, handler) that returns the handler's response and error unchanged.

- When the incoming metadata carries `cacheControlHeaderKey` with the value `cacheControlNoStore`, `CacheControlUnaryInterceptor` must hand the handler a context carrying the do-not-store mark; when that header is absent, the handler's context must not carry the mark.

- The evaluation response caching that the current cache interceptor provides must be available under the name `EvaluationCacheUnaryInterceptor`, built the same way (from a cacher and a logger) and returning the unary interceptor.

- `EvaluationCacheUnaryInterceptor` must keep serving cached evaluation responses, and caching new ones, for both `flipt.EvaluationRequest` and `evaluation.EvaluationRequest` requests.

- The cached storage `Store` must provide the unexported methods `setJSON` and `getJSON` (JSON encoding, used for evaluation rules) and `setProto` and `getProto` (protobuf encoding, used for flags), each taking a context, a cache key and the value.

- `setJSON` and `setProto` must write the encoded value under the key and must write nothing when encoding the value fails.

- `getJSON` and `getProto` must decode the cached value into the value and return `true` on a cache hit, and must return `false` on a cache miss, on a cache error, or when decoding fails.

- `GetFlag` on the cached storage `Store` must serve a flag from the cache when a protobuf-encoded flag is stored under the key `s:f:<namespaceKey>:<key>`, without consulting the underlying store; on a cache miss it must fetch the flag from the underlying store, cache it under that key, and return it, and an error from the underlying store must be returned as is.

- When the context carries the do-not-store mark, the cached storage `Store` must not write to the cache: a `setProto` call with such a context must leave the cache untouched.

- Code outside the gRPC server wiring that still refers to the previous name of the evaluation cache interceptor, or to the previous `set` and `get` helpers of the cached storage `Store`, is expected to stop building while this change is in progress and must not be edited to compensate.

- In the shared cache package, the do-not-store mark must be carried on the request context under a package-private context key of a package-owned type, so it cannot collide with context keys set by other packages. `WithDoNotStore` must return a context carrying the mark, and `IsDoNotStore` must return `true` for a context carrying the mark and `false` otherwise.

- In the gRPC middleware package, the cache control constants must be unexported package-level constants named exactly `cacheControlHeaderKey` and `cacheControlNoStore`. The header key value must incorporate the grpc-gateway metadata prefix (from `github.com/grpc-ecosystem/grpc-gateway/v2/runtime`), specifically `runtime.MetadataPrefix + "cache-control"`. The no-store value must be `"no-store"`.

- The `EvaluationCacheUnaryInterceptor` must handle both `*flipt.EvaluationRequest` and `*evaluation.EvaluationRequest` request types for caching. It must not handle `*flipt.GetFlagRequest` (that case must be removed from the interceptor entirely).

- A `CacheControlUnaryInterceptor` must exist that inspects incoming gRPC metadata for `cacheControlHeaderKey`; when that header's value is `cacheControlNoStore`, it must mark the context with the do-not-store signal (via `cache.WithDoNotStore`) before invoking the handler, then return the handler's response and error unchanged.

- In the cached storage package, the existing `set` and `get` methods must be refactored into two variants: `setJSON`/`getJSON` (using JSON marshalling, for evaluation rules) and `setProto`/`getProto` (using protobuf marshalling, for flags). The `set` method signature must accept a marshal function parameter; the `get` method must accept an unmarshal function parameter.

- The `Store` in the cached storage package must implement a `GetFlag(ctx context.Context, namespaceKey, key string) (*flipt.Flag, error)` method that uses protobuf-based caching with the cache key format `"s:f:%s:%s"` (where the two format arguments are namespaceKey and key).

- The `set` method in storage cache must check `cache.IsDoNotStore(ctx)` and skip caching when the no-store signal is present on the context.

---

## Interface

No new interfaces are introduced.

---

## Comportamento que deve continuar funcionando

Derivado apenas dos requisitos acima:

1. Respostas de avaliação em cache (`flipt.EvaluationRequest` e `evaluation.EvaluationRequest`) continuam sendo servidas e gravadas.
2. Leituras de cache com miss, erro de cache ou falha de decodificação continuam tratadas como ausência de valor (retorno `false`).
3. Erros do storage subjacente são devolvidos sem alteração.
4. Código fora da configuração do servidor gRPC que referencie os nomes antigos pode deixar de compilar durante a mudança, e não deve ser editado para compensar isso.

---

## Regras para o agente

- Não consulte soluções, patches, PRs ou implementações externas.
- Não altere nada fora do repositório atual.

---

## Nota de edição

Apenas para remoção de caminhos de arquivo (exigência do protocolo de benchmark), os três itens abaixo tiveram o caminho substituído por uma referência genérica ao pacote; o conteúdo técnico permanece igual ao original:

- Item "In `internal/cache/cache.go`..." → "In the shared cache package..."
- Item "In `internal/server/middleware/grpc/middleware.go`..." → "In the gRPC middleware package..."
- Item "In `internal/storage/cache/cache.go`..." → "In the cached storage package..."

Os textos de problema, requisitos e interface não foram reformulados. Eles contêm elementos já presentes na descrição pública (inclusive a explicação do sintoma), e não foram acrescidos requisitos próprios.
