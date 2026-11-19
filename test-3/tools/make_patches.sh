#!/usr/bin/env bash
# Gera os patches do Teste 3 a partir dos blobs LF do HEAD original (sem eol do autocrlf) e dos arquivos editados.
# Não escreve nos repositórios originais: só lê com `git show` e `git ls-tree`.
set -euo pipefail
T3="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$T3/patches"; mkdir -p "$OUT"

make_base() { # $1 = repo original, $2 = destino, $3.. = caminhos
  local orig="$1" dst="$2"; shift 2
  rm -rf "$dst"; mkdir -p "$dst"
  for p in "$@"; do mkdir -p "$dst/$(dirname "$p")"; git -C "$orig" show "HEAD:$p" > "$dst/$p"; done
  git -C "$dst" init -q; git -C "$dst" config core.autocrlf false
  git -C "$dst" add -A; git -C "$dst" -c user.email=t3@local -c user.name=t3 commit -qm base
}
edited() { # $1 = árvore editada, $2 = destino, $3.. = caminhos
  local src="$1" dst="$2"; shift 2
  for p in "$@"; do mkdir -p "$dst/$(dirname "$p")"; cp "$src/$p" "$dst/$p"; sed -i 's/\r$//' "$dst/$p"; done
}

# --- FineCode: owner fence (storage)
FC_FILES=(packages/durable/src/storage/sqlite/index.ts packages/durable/src/storage/sqlite/migrations.ts \
          packages/durable/src/storage/sqlite/storage.ts packages/durable/test/sqlite-cloudflare.test.ts \
          packages/durable/test/sqlite-migrations.test.ts packages/durable/test/sqlite-owner-fence.test.ts)
make_base /d/projetos/FineCode "$T3/work/_pg-finecode" $(printf '%s ' "${FC_FILES[@]:0:5}")
edited "$T3/work/finecode" "$T3/work/_pg-finecode-edit" "${FC_FILES[@]}"
rm -rf "$T3/work/_pg-finecode-edit/.git"
# o diff é gerado comparando base (repo) com a edição: copiar a edição por cima da base
cp -r "$T3/work/_pg-finecode-edit/." "$T3/work/_pg-finecode/"
git -C "$T3/work/_pg-finecode" add -A
git -C "$T3/work/_pg-finecode" -c core.autocrlf=false diff --cached -- packages/durable > "$OUT/finecode-owner-fence.patch"

# --- metaO: OCC (mission_store.py, sqlite_store.py)
MO_OCC=(src/metao/mission_store.py src/metao/sqlite_store.py)
MO_FENCE=(src/metao/fencing.py src/metao/execution_handle.py src/metao/sqlite_execution_handle.py src/metao/sqlite_event_ledger.py src/metao/operator.py tests/unit/test_issue_396_external_execution_correlation.py tests/unit/test_roadmap_1_work_unit_10.py tests/unit/test_t3_fencing_and_occ.py)
ALL_MO=("${MO_OCC[@]}" "${MO_FENCE[@]}")
# base = blobs do HEAD para os arquivos que existem no HEAD; novos arquivos entram como vazio
rm -rf "$T3/work/_pg-metao"; mkdir -p "$T3/work/_pg-metao"
for p in "${ALL_MO[@]}"; do
  mkdir -p "$T3/work/_pg-metao/$(dirname "$p")"
  if git -C /d/projetos/metaO cat-file -e "HEAD:$p" 2>/dev/null; then git -C /d/projetos/metaO show "HEAD:$p" > "$T3/work/_pg-metao/$p"; fi
done
# arquivos base de src/tests que não serão alterados ficam fora; o patch só compara os caminhos da lista
git -C "$T3/work/_pg-metao" init -q; git -C "$T3/work/_pg-metao" config core.autocrlf false
git -C "$T3/work/_pg-metao" add -A; git -C "$T3/work/_pg-metao" -c user.email=t3@local -c user.name=t3 commit -qm base --allow-empty
for p in "${ALL_MO[@]}"; do if [ -f "$T3/work/_pg-metao/$p" ]; then :; fi; done
edited "$T3/work/metao" "$T3/work/_pg-metao-edit" "${ALL_MO[@]}"
# OCC: arquivos da lista OCC (sem a parte de fencing em sqlite_store já incluída)
cp -r "$T3/work/_pg-metao-edit/." "$T3/work/_pg-metao/"
git -C "$T3/work/_pg-metao" add -A
git -C "$T3/work/_pg-metao" -c core.autocrlf=false diff --cached -- "${MO_OCC[@]}" > "$OUT/metao-occ-revision.patch"
git -C "$T3/work/_pg-metao" -c core.autocrlf=false diff --cached -- "${MO_FENCE[@]}" > "$OUT/metao-fencing.patch"
echo "patches regenerated in $OUT"
wc -l "$OUT"/*.patch
