# Avaliador — TASK 02 (`instance_flipt-io__flipt-e2bd19dafa7166c96b082fb2a59eb54b4be0d778`)

**Esta pasta é do avaliador. Os agentes não devem acessá-la.** Não está em `agents/`, e a regra é
registrada no `TASK.md` e no manifesto. Como ambos os agentes rodam com o mesmo usuário do Windows,
isso é uma regra de procedimento, não uma barreira técnica (ver manifesto, seção de isolamento).

## Conteúdo

| Arquivo | Conteúdo | Situação |
|---|---|---|
| `test-identifiers.json` | identificadores `fail_to_pass` (10) e `pass_to_pass` (0) da instância | **obtido** do dataset `ScaleAI/SWE-bench_Pro`, split `test` |
| `evaluate.py` | procedimento de avaliação único, usado para os dois agentes | pronto; testado |
| `private/test.patch` | patch de testes de referência, necessário para executar `fail_to_pass` | **AUSENTE** (não autorizado) |
| `results/<run>/<agente>/` | saídas da avaliação (JSON, go test -json, stderr) | gerado pela execução |
| `work/` | cópias de trabalho temporárias, removidas após cada avaliação | — |

## Por que `fail_to_pass` não pode ser executado ainda

Os 10 identificadores **não existem no código-base** (`0eaf98f0`). Verificado com busca por `func <nome>(`
nos arquivos `*_test.go` do clone: 0 ocorrências para cada um. Eles são criados pelo patch de testes
de referência, que não foi autorizado. Sem esse patch, a avaliação de `fail_to_pass` retorna `BLOCKED`
(código 3). Nenhum resultado é inferido.

`pass_to_pass` está vazio no dataset. Isso significa que o oráculo oficial não verifica regressões. Para
regressão, seria preciso uma decisão separada (ex.: executar os testes existentes dos pacotes afetados e
comparar com o baseline). Não foi incluído.

## Procedimento (idêntico para os dois agentes)

1. Confere que `test-identifiers.json` tem `base_commit = 0eaf98f0…`.
2. Confere que o clone do agente está em HEAD = `0eaf98f0…`. Lê o clone; não altera nada nele
   (`git --no-optional-locks`).
3. Copia a árvore final do clone, sem `.git`, para `work/<run>/<agente>/`.
4. Aplica `private/test.patch` com `git apply`. Se ausente: `BLOCKED`.
5. Executa `go test -json -count=1 -run '^(ids)$' ./...` com timeout de 1800 s.
6. Classifica cada identificador: `PASS` (passou e nenhum subteste falhou), `FAIL`, `NOT_RUN` (não apareceu) ou `SKIP`.
7. Grava `results/<run>/<agente>/result.json`, `go-test.jsonl` e `go-test.stderr`, e remove a cópia de trabalho.

Uso:

```bash
python evaluator/evaluate.py --agent pi-original --run-id R1 --clone agents/pi-original/flipt
python evaluator/evaluate.py --agent pi-rust     --run-id R1 --clone agents/pi-rust/flipt
```

`resolved = true` exige todos os `fail_to_pass` em `PASS`, nenhum timeout e todos os `pass_to_pass` em `PASS`.

## Verificação no Windows atual (modo de controle)

Modo `--control` roda identificadores **existentes** no código-base, sem patch, para checar o pipeline. Nunca
é resultado do benchmark.

Execução `control-1` (`results/control-1/control/result.json`), identificadores `TestNewCache`,
`TestCacheControlHeaderKey`, `TestSetHandleMarshalError`, `TestGetEvaluationRules`:

| Identificador | Resultado | Observação |
|---|---|---|
| TestNewCache | PASS | existe em `internal/cache/memory` e `redis` |
| TestCacheControlHeaderKey | NOT_RUN | não existe no base (esperado) |
| TestSetHandleMarshalError | PASS | `internal/storage/cache` |
| TestGetEvaluationRules | PASS | `internal/storage/cache` |

Pacotes que não compilam neste ambiente (sem cgo) aparecem em `build_failed_packages`. Isso afeta a
execução do `./...` no Windows, mas não invalida os identificadores acima. Duração: 49 s.

## Limites

- Sem o patch de testes, o benchmark não tem resultado final.
- O Windows atual não compila os pacotes com sqlite (ver manifesto, seção de problemas ambientais), e o relógio
  do host faz alguns testes falharem por motivos de ambiente. Isso deve ser registrado em qualquer resultado.
- O procedimento executa `./...`. Testes que falham no baseline por ambiente aparecem como `FAIL` se fizerem parte
  dos identificadores. Ao reportar, comparar com `BASELINE_REPORT.md`.
