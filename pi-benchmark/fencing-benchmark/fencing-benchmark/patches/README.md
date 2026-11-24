# patches/

**Nenhum patch foi necessário para rodar os candidatos.** Os dois backends do StatePact (`statepact==0.1.2`, PyPI)
rodam do wheel instalado, sem modificação. O harness só chama a API pública (`TransactionManager`, `session`, `lease`,
`backend.acquire_lease` no teste de corrida pelo caminho direto, `release_lease`).

Duas leituras de atributos privados são feitas, somente leitura, para obter a sequência global de commits, usada na
detecção de duplicação (não existe accessor público):

- `RedisBackend._redis` / `_prefix` → `GET <prefix>:seq` (chave documentada em `statepact/storage/redis.py`).
- `PostgresBackend._pool` → `SELECT seq FROM statepact_meta WHERE id = 1`.

Nada escreve nesses internos. Se uma versão futura do StatePact mudar esses nomes, o único ponto a atualizar é
`StatePactBackend.version` em `bench/backends.py`.
