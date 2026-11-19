"""Consolida os brutos do Teste 3 em test-3/results.json. Não reexecuta experimentos."""
import json, collections, subprocess
from pathlib import Path
T3 = Path(__file__).resolve().parent
RAW = T3 / "raw"

def fc_summary(tree):
    r = json.loads((RAW / tree / "bench-results.json").read_text(encoding="utf-8"))
    out = {}
    for sid, s in r["scenarios"].items():
        reps = s["reps"]
        out[sid] = {
            "reps": len(reps),
            "effects_executed": sorted(collections.Counter(x["effects_executed"] for x in reps).items()),
            "effects_duplicated_per_rep": [x["effects_duplicated"] for x in reps],
            "effects_lost_per_rep": [len(x["effects_lost"]) for x in reps],
            "instance_superseded_reports": sum(1 for x in reps for m in x["reports"] if "superseded" in m),
            "task_results": [[q.get("kind") for q in x["results"]] for x in reps],
        }
    return {"description_source": "raw/" + tree + "/bench-results.json", "scenarios": out}

fc_base = fc_summary("finecode-baseline")
fc_fix = fc_summary("finecode-fixed")

mo = {t: json.loads((RAW / f"metao-{t}" / "bench.json").read_text(encoding="utf-8")) for t in ("baseline", "fixed")}
def occ(t):
    rows = mo[t]["occ"]
    return {"reps": len(rows), "lost_updates_per_rep": [r["lost_updates"] for r in rows],
            "conflicts_retried_total": sum(r["conflicts_retried"] for r in rows),
            "final_revision_matches_successes": all(r["final_revision"] == r["expected_revision"] for r in rows),
            "integrity": sorted({r["integrity"] for r in rows})}
def append(t):
    rows = mo[t]["append"]
    return {"reps": len(rows), "appended_per_rep": [r["appended_ok"] for r in rows],
            "errors_total": sum(len(r["errors"]) for r in rows),
            "unique_and_contiguous": all(r["unique_sequences"] == r["appended_ok"] and r["sequences_contiguous"] for r in rows)}
def complete_race(t):
    rows = mo[t]["complete_race"]
    return {"reps": len(rows), "stale_writes_landed_on_newer_execution_per_rep": [r["stale_completions_of_newer_execution"] for r in rows],
            "reps_with_stale_write": sum(1 for r in rows if r["stale_completions_of_newer_execution"] > 0),
            "final_state": dict(collections.Counter(f"{r['final_execution_id']}/{r['final_status']}" for r in rows))}
def suspended(t):
    rows = mo[t]["suspended_worker"]
    return {"reps": len(rows), "stale_accepted_per_rep": [r["A_accepted_count"] for r in rows],
            "attempt_outcomes": dict(collections.Counter(json.dumps(r["A_attempts"], sort_keys=True) for r in rows)),
            "objective_final": dict(collections.Counter(r["objective_final"] for r in rows))}
def crash(t):
    rows = mo[t]["crash_windows"]
    grp = collections.defaultdict(list)
    for r in rows: grp[r["window"]].append(r)
    return {w: {"reps": len(v), "crash_exit_codes": sorted({x["crash_exit_code"] for x in v}),
                "state_unchanged_if_crashed_before_commit": all(x["crashed_before_commit_state_unchanged"] for x in v) if not w.startswith("after:") else None,
                "state_persisted_if_crashed_after_commit": all(x["after_commit_state_persisted"] for x in v) if w.startswith("after:") else None,
                "retry_outcomes": dict(collections.Counter(x["retry_outcome"] for x in v)),
                "events_before_crash_final": [v[0]["events_before"], v[0]["events_after_crash"], v[0]["events_final"]],
                "integrity_final": sorted({x["integrity_final"] for x in v})} for w, v in grp.items()}

cost = [json.loads(l) for l in (RAW / "metao-cost.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

tests = {
    "finecode_durable_full_suite": {
        "note": "copies received the 739 git-ignored data files of the original (provider model catalogs) before this run",
        "baseline": "1249 passed, 1 failed (provider-session-cache-e2e: needs a live Codex provider, external service, not run), 5 skipped",
        "fixed": "1252 passed (+3 new owner-fence tests), same 1 external-service failure, 5 skipped",
        "logs": ["raw/durable-full-finecode-baseline.log", "raw/durable-full-finecode.log"],
    },
    "metao_pytest_unit_integration": {
        "baseline": "812 passed, 1 failed (test_operator_initialization_e2e: subprocess cannot load test plugin 'bootstrap_e2e_runtime:create_plugin'), 12 collection errors (crewai/langgraph not installed)",
        "fixed": "831 passed (+19 new), same failure set",
        "logs": ["raw/metao-fixed-final-pytest.log", "raw/baseline/metao-pytest.log"],
    },
    "intermittent_under_load": "harness-ownership 'tracks ownership chains deeper than the call stack' timed out (60 s) in one full run of each tree and passed in isolation 8/8 per tree; not counted as a regression",
}

results = {
    "test": "Teste Comparativo 3 — correção e validação das garantias de durabilidade",
    "generated_by": "test-3/consolidate.py a partir de raw/ (sem reexecução)",
    "origins": {
        "finecode": {"head": subprocess.run(["git", "-C", "D:/projetos/FineCode", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
                     "status_porcelain_after": subprocess.run(["git", "-C", "D:/projetos/FineCode", "status", "--porcelain"], capture_output=True, text=True).stdout.split("\n")},
        "metao": {"head": subprocess.run(["git", "-C", "D:/projetos/metaO", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
                  "status_porcelain_after": subprocess.run(["git", "-C", "D:/projetos/metaO", "status", "--porcelain"], capture_output=True, text=True).stdout.split("\n")},
    },
    "mechanisms": {
        "finecode.runtime.memo (storage owner fence)": {
            "verdict": "APROVADO COM LIMITAÇÕES",
            "patch": "patches/finecode-owner-fence.patch",
            "baseline": fc_base, "fixed": fc_fix,
        },
        "metao.SQLiteMissionStore.replace (OCC)": {
            "verdict": "APROVADO COM LIMITAÇÕES",
            "patch": "patches/metao-occ-revision.patch",
            "baseline": occ("baseline"), "fixed": occ("fixed"),
        },
        "metao.fencing token (append/replace/complete/bind)": {
            "verdict": "REPROVADO como garantia de sistema; APROVADO COM LIMITAÇÕES nos caminhos que apresentam token",
            "patch": "patches/metao-fencing.patch",
            "append": {"baseline": append("baseline"), "fixed": append("fixed")},
            "complete_race": {"baseline": complete_race("baseline"), "fixed": complete_race("fixed")},
            "suspended_worker": {"baseline": suspended("baseline"), "fixed": suspended("fixed")},
            "crash_windows": {"baseline": crash("baseline"), "fixed": crash("fixed")},
        },
    },
    "cost_metao_us_per_op_median": cost,
    "test_suites": tests,
}
(T3 / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print("written test-3/results.json")
