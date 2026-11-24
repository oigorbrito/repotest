# Benchmark Pi TypeScript (`original`) vs Pi-Rust (`rust`)

Estrutura de comparação reproduzível. Este documento descreve o ambiente; **o benchmark ainda não foi executado**.

## 1. Três elementos distintos

| Elemento | `original` (Pi TypeScript 1.5.2) | `rust` (Pi-Rust) |
|---|---|---|
| Código-fonte do agente | Fora deste diretório: `C:\Users\igorb\.pi\agent\install\releases\1.5.2\node_modules\@earendil-works\pi-coding-agent` | `pi-rust/` nesta pasta (clone git de `yannelli/pi-rust`, commit `e9dd2b54`, árvore limpa) |
| Executável a usar | `C:\Users\igorb\.pi\agent\bin\pi` (shell wrapper → `pi-launcher.js` → 1.5.2). Verificado: `--version` = `1.5.2` | Binário a ser compilado a partir de `pi-rust/` (ainda não existe em `pi-rust/target/release/`) |
| Workspace de teste | `workspaces/original/` | `workspaces/rust/` |
| Resultados | `results/<timestamp>/original/` | `results/<timestamp>/rust/` |

O código-fonte dos agentes **não deve ser modificado** e **não deve ser usado como workspace**.

## 2. Estrutura

```text
pi-benchmark/
├── benchmark-pi-vs-pirs.ps1    # Original preservado (raiz, ver seção 4)
├── README-BENCHMARK.md
├── pi-rust/                    # Código-fonte do Pi-Rust (não editar durante o benchmark)
├── scripts/                    # Vazio: run-comparison.ps1 ainda não existe
├── workspaces/
│   ├── original/               # Pi TypeScript (vazio)
│   └── rust/                   # Pi-Rust (vazio)
├── tasks/
│   ├── task-01.md              # Esqueletos, status PENDENTE
│   ├── task-02.md
│   └── task-03.md
├── results/
│   ├── original/               # Legado, vazio (ver seção 5)
│   ├── rust/                   # Legado, vazio (ver seção 5)
│   └── <timestamp>/            # Criado por execução: original/ e rust/
├── reports/                    # raw/, summary/, comparison/ (vazios)
├── fixtures/                   # Vazio
└── archive/
    ├── raw/                    # Movido de results/raw (vazio)
    ├── detailed/               # Movido de reports/detailed (vazio)
    └── tests/                  # Movido de tests/ (subpastas vazias)
```

## 3. Isolamento

- `original` e `rust` devem começar como **cópias independentes do mesmo projeto open source, no mesmo commit**. O projeto ainda **não foi escolhido** (pendência).
- Nenhum agente pode ler ou escrever no workspace do outro.
- `tasks/` e `fixtures/` são compartilhados e somente leitura durante a execução.
- Logs, métricas e artefatos ficam separados por agente dentro de cada `results/<timestamp>/`.

## 4. Script de benchmark

`benchmark-pi-vs-pirs.ps1` foi **preservado sem alterações** (SHA-256 `38481eeb...f061e13`) e permanece na raiz porque o `OutputRoot` padrão é `$PSScriptRoot\results`. Movê-lo para `scripts/` faria os resultados irem para `scripts/results/`.

Limitações atuais do script (não corrigidas):

- Grava em `results/<timestamp>/` com `home-pi` e `home-pirs`, **sem** as subpastas `original/` e `rust/`.
- Usa os rótulos `PI` e `PI_RS`, não `original` e `rust`.
- O default `-RustExe pirs` não existe: o binário do Pi-Rust se chama `pi` (crate `crates/pi-coding-agent`) e ainda não foi compilado. Precisa ser passado com caminho completo.
- O `pi` do PATH é ambíguo. Verificado com `--version`:
  - `~\.pi\agent\bin\pi` → `1.5.2` (**este é o `original`**).
  - `%APPDATA%\npm\pi.cmd` → `1.3.0` (não usar).
  - `%LOCALAPPDATA%\Programs\pi\pi.exe` → `0.12.16` (build Pi-Rust fora desta pasta; não usar como `rust`, pois o benchmark usa `pi-rust/`).
  Por isso o script deve receber `-PiExe` com caminho completo.
- Os testes são CLI/startup/erro; não medem tarefas de código nem autenticação real.

## 5. Pendências

1. **`pi-rust/` fora da árvore proposta**: a nova estrutura não o lista. Mantido na raiz, sem mover, até confirmação.
2. **`scripts/run-comparison.ps1`**: não existe. Não foi criado para evitar script fictício. Precisa ser escrito e testado.
3. **`tasks/task-01..03.md`**: são esqueletos com status PENDENTE. O conteúdo precisa ser definido.
4. **`results/original/` e `results/rust/`**: vazios e sem correspondência na nova árvore. Não removidos; decidir se ficam ou se são descartados.
5. **`reports/` e `fixtures/`**: não aparecem na nova árvore, mas foram mantidos porque estavam na estrutura anterior. Confirmar.
6. Escolher o projeto open source de teste e o commit fixo; clonar nos dois workspaces.
7. Compilar o Pi-Rust a partir de `pi-rust/` (`pi-rust/target/release/pi.exe` ainda não existe) e passá-lo como `-RustExe` com caminho completo. O `original` já está confirmado: `~\.pi\agent\bin\pi` = 1.5.2.
8. Adaptar o script para gravar `original/` e `rust/` dentro de `results/<timestamp>/`.
