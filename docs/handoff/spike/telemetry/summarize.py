#!/usr/bin/env python3
"""Print a per-block summary table from runs.jsonl (markdown)."""
import collections, json, sys

path = sys.argv[1] if len(sys.argv) > 1 else "runs.jsonl"
rows = [json.loads(l) for l in open(path, encoding="utf-8")]
by = collections.OrderedDict()
for r in rows:
    by.setdefault(r["block"], []).append(r)

print("| block | runs | legit | tamper | harness_stop | stopped_itself | timeout | tool_calls | tool_errors | rescued | api_errors | input_tok | output_tok | ctx_peak | oom_runs |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for b, xs in by.items():
    o = collections.Counter(x["outcome"] for x in xs)
    t = lambda k: sum(x["totals"][k] or 0 for x in xs)
    tok = [x["totals"]["tokens"] for x in xs if x["totals"]["tokens"]]
    inp = sum(k["input"] for k in tok) if tok else "n/a"
    out = sum(k["output"] for k in tok) if tok else "n/a"
    ctx = [x["totals"]["ctx_peak_tokens"] for x in xs if x["totals"]["ctx_peak_tokens"]]
    print(f"| {b} | {len(xs)} | {o['legit_pass']} | {o['pass_tampered']} | {o['harness_stop']} | "
          f"{o['stopped_itself']} | {o['timeout']} | {t('tool_calls')} | {t('tool_errors')} | "
          f"{t('rescued_from_text')} | {t('api_errors')} | {inp} | {out} | {max(ctx) if ctx else 'n/a'} | "
          f"{sum(1 for x in xs if x['oom_overlap'])} |")
