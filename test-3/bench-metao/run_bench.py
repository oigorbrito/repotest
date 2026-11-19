"""Teste 3 — orquestrador do benchmark do metaO (processos reais, SQLite real).

Executa os mesmos cenários contra a linha de base (metao-baseline) e contra a versão corrigida (metao).
Uso: python run_bench.py <reps>
Saída: test-3/raw/metao-<árvore>/bench.json e logs de cada processo.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEST3 = HERE.parent
WORK = TEST3 / "work"
RAW = TEST3 / "raw"
WORKER = HERE / "worker.py"
TREES = {"baseline": WORK / "metao-baseline", "fixed": WORK / "metao"}
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def run(tree: Path, out_dir: Path, role: str, wid: str, *extra: str, background: bool = False, **kw):
    out = out_dir / f"{role}-{wid}.json"
    cmd = [sys.executable, str(WORKER), "--tree", str(tree), "--db", str(out_dir / "db.sqlite"), "--role", role,
           "--id", wid, "--out", str(out), *extra]
    log = open(out_dir / f"{role}-{wid}.log", "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=ENV)
    if background:
        return proc, out
    code = proc.wait(timeout=180)
    log.close()
    return code, out


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def fresh(out_dir: Path) -> Path:
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    return out_dir / "db.sqlite"


def barrier(out_dir: Path, name: str) -> str:
    return str(out_dir / f"barrier-{name}")


def go(path: str) -> None:
    Path(path).write_text("go", encoding="utf-8")


# --------------------------------------------------------------------------------------------------
def scenario_occ(tree_name: str, tree: Path, reps: int) -> list[dict]:
    rows = []
    for rep in range(1, reps + 1):
        d = RAW / f"metao-{tree_name}" / "occ" / f"rep{rep}"
        fresh(d)
        run(tree, d, "setup", "s")[0] == 0 or sys.exit("setup failed")
        go(barrier(d, "b"))
        procs = [run(tree, d, "occ", f"W{i}", "--n", "15", "--barrier", barrier(d, "b"), background=True)[0] for i in range(4)]
        for p in procs:
            p.wait(timeout=300)
        results = [load(d / f"occ-W{i}.json") for i in range(4)]
        final = snapshot_state(tree, d)
        markers_final = [m for m in final["objective"].split(";")[1:]]
        successes = sum(r["successes"] for r in results if r)
        rows.append({
            "rep": rep,
            "successes": successes,
            "conflicts_retried": sum(r["conflicts"] for r in results if r),
            "final_revision": final["revision"],
            "expected_revision": 1 + successes,
            "markers_in_final": len(markers_final),
            "lost_updates": successes - len(markers_final),
            "integrity": final["integrity"],
        })
    return rows


def snapshot_state(tree: Path, d: Path) -> dict:
    out = d / f"snapshot-{time.time_ns()}.json"
    code, _ = run(tree, d, "snapshot", "snap", "--out", str(out))
    assert code == 0, "snapshot failed"
    return json.loads(out.read_text(encoding="utf-8"))["state"]


def scenario_append(tree_name: str, tree: Path, reps: int) -> list[dict]:
    rows = []
    for rep in range(1, reps + 1):
        d = RAW / f"metao-{tree_name}" / "append" / f"rep{rep}"
        fresh(d)
        run(tree, d, "setup", "s", "--exec-id", "e1")
        token = load(d / "setup-s.json").get("token")
        go(barrier(d, "b"))
        procs = [run(tree, d, "append", f"W{i}", "--m", "25", "--token", str(token) if token else "",
                     "--barrier", barrier(d, "b"), background=True)[0] for i in range(4)] if token else []
        if not token:  # baseline: no token parameter exists
            procs = [subprocess.Popen([sys.executable, str(WORKER), "--tree", str(tree), "--db", str(d / "db.sqlite"),
                                       "--role", "append", "--id", f"W{i}", "--m", "25", "--barrier", barrier(d, "b"),
                                       "--out", str(d / f"append-W{i}.json")], env=ENV) for i in range(4)]
        for p in procs:
            p.wait(timeout=300)
        seqs, errors = [], []
        for i in range(4):
            r = load(d / f"append-W{i}.json")
            seqs += r["sequences"]
            errors += r["errors"]
        st = snapshot_state(tree, d)
        rows.append({
            "rep": rep,
            "appended_ok": len(seqs),
            "errors": errors,
            "unique_sequences": len(set(seqs)),
            "stored_events": len(st["events"]),
            "sequences_contiguous": sorted(s for s, _ in st["events"]) == list(range(1, len(st["events"]) + 1)),
            "integrity": st["integrity"],
        })
    return rows


def scenario_complete_race(tree_name: str, tree: Path, reps: int) -> list[dict]:
    rows = []
    for rep in range(1, reps + 1):
        d = RAW / f"metao-{tree_name}" / "complete_race" / f"rep{rep}"
        fresh(d)
        run(tree, d, "setup", "s", "--exec-id", "e1")
        token = load(d / "setup-s.json").get("token")
        tok_args = ["--token", str(token)] if token else []
        go(barrier(d, "b"))
        b_procs = [run(tree, d, "complete_loop", f"B{i}", "--exec-id", "e1", "--duration", "0.4", "--barrier",
                       barrier(d, "b"), *tok_args, background=True)[0] for i in range(3)]
        c = run(tree, d, "activate", "C", "--exec-id", "e2", "--barrier", barrier(d, "b"), background=True)[0]
        for p in b_procs + [c]:
            p.wait(timeout=300)
        b_results = [load(d / f"complete_loop-B{i}.json") for i in range(3)]
        stale = sum(r["stale_completions_of_other_execution"] for r in b_results)
        st = snapshot_state(tree, d)
        final_handle = st["handle"][0] if st["handle"] else None
        rows.append({
            "rep": rep,
            "b_accepted": sum(r["accepted"] for r in b_results),
            "b_rejected": sum(r["rejected"] for r in b_results),
            "stale_completions_of_newer_execution": stale,
            "final_execution_id": final_handle[0] if final_handle else None,
            "final_status": final_handle[1] if final_handle else None,
            "integrity": st["integrity"],
        })
    return rows


def scenario_suspended(tree_name: str, tree: Path, reps: int) -> list[dict]:
    rows = []
    for rep in range(1, reps + 1):
        d = RAW / f"metao-{tree_name}" / "suspended_worker" / f"rep{rep}"
        fresh(d)
        run(tree, d, "setup", "s")
        ready, release = str(d / "ready"), str(d / "release")
        a_proc, a_out = run(tree, d, "suspended_a", "A", "--exec-id", "eA", "--ready", ready, "--release", release,
                            background=True)
        end = time.time() + 60
        while not os.path.exists(ready):
            if time.time() > end:
                raise TimeoutError("A never became ready")
            time.sleep(0.01)
        b_code, _ = run(tree, d, "takeover_b", "B", "--exec-id", "eB")
        assert b_code == 0, "B failed"
        Path(release).write_text("go", encoding="utf-8")
        a_proc.wait(timeout=120)
        a = load(a_out) or {}
        st = snapshot_state(tree, d)
        attempts = a.get("attempts", {})
        accepted = [k for k, v in attempts.items() if v == "ACCEPTED"]
        rows.append({
            "rep": rep,
            "A_attempts": attempts,
            "A_accepted_count": len(accepted),
            "objective_final": st["objective"],
            "events_final_by": [p for _, p in st["events"]],
            "handle_final": st["handle"],
            "stale_write_visible": (st["objective"] == "by A") or ("A" in [p for _, p in st["events"]]),
            "integrity": st["integrity"],
        })
    return rows


def scenario_crash_windows(tree_name: str, tree: Path, reps: int) -> list[dict]:
    windows = [
        ("tx:append", "append"),
        ("tx:replace", "replace"),
        ("tx:complete", "complete"),
        ("tx:activate", "activate"),
        ("after:append", "append"),
        ("after:replace", "replace"),
    ]
    rows = []
    for win, op in windows:
        for rep in range(1, reps + 1):
            d = RAW / f"metao-{tree_name}" / "crash_windows" / f"{win.replace(':', '_')}" / f"rep{rep}"
            fresh(d)
            run(tree, d, "setup", "s", "--exec-id", "e1")
            token = load(d / "setup-s.json").get("token")
            tok = ["--token", str(token)] if token else []
            before = snapshot_state(tree, d)
            crash_out = d / "crash-op.json"
            code, _ = run(tree, d, "tx_op", "X", "--op", op, "--exec-id", "e2" if op == "activate" else "e1",
                          "--window", win, "--out", str(crash_out), *tok)
            after_crash = snapshot_state(tree, d)
            committed_before_crash = win.startswith("after:")
            # Restart: the legitimate owner (same token) retries the same operation once.
            retry_code, retry_out = run(tree, d, "tx_op", "R", "--op", op,
                                        "--exec-id", "e2" if op == "activate" else "e1", *tok)
            final = snapshot_state(tree, d)
            retry = load(retry_out) or {}
            rows.append({
                "window": win,
                "op": op,
                "rep": rep,
                "crash_exit_code": code,
                "crashed_before_commit_state_unchanged": (not committed_before_crash) and after_crash == before,
                "after_commit_state_persisted": committed_before_crash and after_crash != before,
                "retry_outcome": retry.get("outcome"),
                "events_before": len(before["events"]),
                "events_after_crash": len(after_crash["events"]),
                "events_final": len(final["events"]),
                "integrity_after_crash": after_crash["integrity"],
                "integrity_final": final["integrity"],
            })
    return rows


def main() -> None:
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    only = os.environ.get("METAO_BENCH_ONLY")
    all_results = {}
    scenarios = {
        "occ": (scenario_occ, reps),
        "append": (scenario_append, reps),
        "complete_race": (scenario_complete_race, max(reps, 20)),
        "suspended_worker": (scenario_suspended, reps),
        "crash_windows": (scenario_crash_windows, 5),
    }
    for tree_name, tree in TREES.items():
        all_results[tree_name] = {"tree": str(tree)}
        for name, (fn, n) in scenarios.items():
            if only and name not in only.split(","):
                continue
            t0 = time.time()
            rows = fn(tree_name, tree, n)
            all_results[tree_name][name] = rows
            print(f"{tree_name}:{name} done ({n} reps, {time.time() - t0:.1f}s)", flush=True)
        out = RAW / f"metao-{tree_name}" / "bench.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        merged = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        merged.update(all_results[tree_name])  # a subset run updates only its scenarios
        out.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    (RAW / "metao-bench-summary.json").write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    print("written")


if __name__ == "__main__":
    main()
