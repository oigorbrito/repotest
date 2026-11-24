#!/usr/bin/env bash
# Verifica o estado das duas cópias do benchmark. Somente leitura.
# Uso: bash scripts/check-isolation.sh [saida.txt]
set -u
cd "$(dirname "$0")/.." || exit 1
SHA=0eaf98f050d86247bfe9bd7e41178865cb585060
E2BD=e2bd19dafa7166c96b082fb2a59eb54b4be0d778
OUT="${1:-/dev/stdout}"
fail=0
say(){ echo "$*" >> "$OUT"; }
: > "$OUT" 2>/dev/null || true
say "check-isolation $(date -Is)"

for agent in pi-original pi-rust; do
  d="agents/$agent/flipt"
  say "== $agent ($d)"
  head=$(git -C "$d" rev-parse HEAD 2>/dev/null)
  [ "$head" = "$SHA" ] && say "  HEAD OK ($head)" || { say "  HEAD DIVERGENTE: $head"; fail=1; }
  st=$(git -C "$d" status --porcelain --untracked-files=all 2>/dev/null | wc -l)
  [ "$st" = "0" ] && say "  arvore limpa" || { say "  arvore NAO limpa ($st linhas)"; git -C "$d" status --porcelain --untracked-files=all | sed 's/^/    /' >> "$OUT"; fail=1; }
  git -C "$d" cat-file -e $E2BD 2>/dev/null && { say "  ERRO: commit $E2BD presente no clone"; fail=1; } || say "  commit associado ausente (esperado)"
  [ -f "$d/.git/objects/info/alternates" ] && { say "  ERRO: alternates presente"; fail=1; } || say "  sem alternates"
  n=$(git -C "$d" remote | wc -l); [ "$n" = "0" ] && say "  sem remotes" || { say "  ERRO: remotes presentes"; fail=1; }
  # hashes dos arquivos rastreados contra o snapshot de preparação
  snap="evidence/preparation/sha256-$agent.txt"
  if (cd "$d" && git ls-files -z | xargs -0 sha256sum) | sort -k2 | cmp -s - <(sort -k2 "$snap"); then
    say "  sha256 dos arquivos rastreados = snapshot de preparação"
  else
    say "  ERRO: sha256 difere do snapshot de preparação"; fail=1
  fi
  # arquivos fora da árvore rastreada (ignorados ou não rastreados)
  extra=$(git -C "$d" status --porcelain --ignored | grep -c '^!!' || true)
  say "  arquivos ignorados: $extra"
done

say "== origem (source)"
[ "$(git -C source rev-parse HEAD)" = "$SHA" ] && say "  HEAD OK" || { say "  ERRO HEAD"; fail=1; }
[ "$(git -C source status --porcelain | wc -l)" = "0" ] && say "  arvore limpa" || { say "  ERRO: source sujo"; fail=1; }

say "== independência dos .git"
a=$(stat -c %i agents/pi-original/flipt/.git 2>/dev/null); b=$(stat -c %i agents/pi-rust/flipt/.git 2>/dev/null); c=$(stat -c %i source/.git 2>/dev/null)
if [ -n "$a" ] && [ "$a" != "$b" ] && [ "$a" != "$c" ] && [ "$b" != "$c" ]; then say "  .git distintos (inodes $a / $b / $c)"; else say "  ERRO: .git não distintos"; fail=1; fi

say "== snapshot completo (tasks/flipt-task02 + ~/.pi/agent) contra o baseline"
base="evidence/preparation/snapshot-baseline.json"
if [ ! -f "$base" ]; then
  say "  ERRO: $base ausente"; fail=1
else
  tmp=$(mktemp)
  if python scripts/snapshot.py take "$tmp" > /dev/null && python scripts/snapshot.py compare "$base" "$tmp" --out evidence/infra-tests/isolation-diff-latest.json > "$tmp.txt"; then
    say "  sem divergencias fora do baseline"
  else
    say "  DIVERGENCIAS (registradas, nada restaurado):"; sed 's/^/  /' "$tmp.txt" >> "$OUT"; fail=1
  fi
  rm -f "$tmp" "$tmp.txt"
fi

say "RESULTADO: $([ $fail = 0 ] && echo OK || echo FALHA)"
exit $fail
