#!/usr/bin/env bash
# Usage: run_r4.sh HARNESS MODEL REPS OUTDIR   (AGENT_CTX honored for mingbird)
set -u
H="$1"; MODEL="$2"; REPS="${3:-2}"; OUT="$4"
TASKS=/home/user/spike/tasks
MB=/home/user/mingbird/mingbird-agent; MBPY=/home/user/mingbird/venv/bin/python
LC=/home/user/itayinbarr/little-coder/bin/little-coder.mjs
mkdir -p "$OUT"; CSV="$OUT/results.csv"
[ -s "$CSV" ] || echo "harness,model,task,rep,exit,pass,legit,seconds,src_changed,tests_modified,tools" > "$CSV"
if ! curl -fsS -m 10 http://127.0.0.1:11434/api/tags | grep -q "${MODEL%%:*}"; then echo "PREFLIGHT FAILED: $MODEL"; exit 2; fi
declare -A P
P[t1_bugfix]="Tests in test_stats.py fail. Fix the bug in src/stats.py so all tests pass. Do not change the tests."
P[t2_feature]="Implement slugify in src/textutil.py so that test_textutil.py passes. Lowercase, strip accents, replace runs of non-alphanumerics with a single hyphen, trim hyphens. Do not change the tests."
P[t3_rename]="Rename function compute_total to calculate_total everywhere in this project (definition and all callers), so test_rename.py passes."
P[t4_data]="Read sales.json and write summary.csv with columns region,total: total per region (float), rows sorted by region name ascending. Make test_summary.py pass."
P[t5_spec]="Read SPEC.md and update dates.py so test_dates.py passes, following the spec exactly."
P[t6_refactor]="calc.py has three copies of the same validation and formula. Refactor calc.py to remove the duplication without changing behavior, so test_calc.py passes."
for t in t1_bugfix t2_feature t3_rename t4_data t5_spec t6_refactor; do
  printf '%s\n' "${P[$t]}" > "$OUT/prompt_$t.txt"
  for r in $(seq 1 "$REPS"); do
    if grep -q "^$H,$MODEL,$t,$r," "$CSV" 2>/dev/null; then continue; fi
    W=$(mktemp -d /home/user/spike/work/r4_${H}_${t}_${r}_XXXX); cp -r "$TASKS/$t/." "$W/"
    LOG="$OUT/${t}_${r}.log"; start=$(date +%s)
    if [ "$H" = mingbird ]; then
      ( cd "$W" && AGENT_UNATTENDED=1 timeout 300 "$MBPY" "$MB/ollama_agent.py" "$MODEL" "$OUT/prompt_$t.txt" "$W" --new < /dev/null ) > "$LOG" 2>&1
    else
      ( cd "$W" && LITTLE_CODER_NO_UPDATE_CHECK=1 OLLAMA_API_KEY=noop timeout 300 node "$LC" --model "ollama/$MODEL" --thinking off -p "${P[$t]}" < /dev/null ) > "$LOG" 2>&1
    fi
    rc=$?; end=$(date +%s)
    if ( cd "$W" && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider > "$OUT/${t}_${r}.pytest" 2>&1 ); then pass=1; else pass=0; fi
    diff -rq --exclude='.*' --exclude='__pycache__' --exclude='*.pyc' --exclude='todo.json' "$TASKS/$t" "$W" > "$OUT/${t}_${r}.changes" 2>&1
    src=$(grep -v "test_" "$OUT/${t}_${r}.changes" | grep -c "differ\|Only in" || true)
    tmod=$(grep "^Files .* differ" "$OUT/${t}_${r}.changes" | grep -c "test_" || true)
    legit=$([ "$pass" = 1 ] && [ "$tmod" = 0 ] && echo 1 || echo 0)
    if [ "$H" = mingbird ]; then tools=$(grep -c "^\[[0-9]*|+[0-9]*s\] ⚙" "$LOG" || true)
    else tools=$(python3 - "$W" <<'PY'
import sys,json,glob
w=sys.argv[1].rstrip('/').split('/')[-1]; n=0
for f in glob.glob("/root/.pi/agent/sessions/*/*.jsonl"):
    if w not in f: continue
    for ln in open(f,encoding="utf-8"):
        try: o=json.loads(ln)
        except Exception: continue
        m=o.get("message") or {}
        for p in (m.get("content") or []) if isinstance(m.get("content"),list) else []:
            if isinstance(p,dict) and p.get("type") in ("toolCall","tool_use"): n+=1
print(n)
PY
); fi
    echo "$H,$MODEL,$t,$r,$rc,$pass,$legit,$((end-start)),$src,$tmod,$tools" >> "$CSV"
    echo "$H $MODEL $t r$r exit=$rc pass=$pass legit=$legit tests_mod=$tmod src=$src tools=$tools $((end-start))s"
  done
done
