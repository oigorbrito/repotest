"""Orchestrator for the durability benchmark (run1).

Every step is a separate OS process. Interruptions are real process deaths
(SIGKILL / abort / os._exit) triggered at deterministic points inside the adapter.
Nothing here is an LLM, API or paid service. Outcomes are classified by the rules in
RULES below, which are fixed before any run and are not adjusted after observing results.

Output:
  runs/<RUN_ID>/...   per-repetition artifacts (databases, effects logs, adapter JSON outputs)
  raw/<RUN_ID>/...    per-step stdout/stderr and the exit code of every spawned process
  results.json        consolidated machine-readable results (written by this script)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:\projetos\durability-benchmark")
RUN_ID = os.environ.get("BENCH_RUN_ID", "run1")
RUNS = ROOT / "runs" / RUN_ID
RAW = ROOT / "raw" / RUN_ID
COPIES = ROOT / "copies"
REPS = [1, 2, 3]
TOTAL = 5  # units per workload, identical for every project
STEP_TIMEOUT = 120
FC_DIR = COPIES / "FineCode" / "packages" / "durable"
EV_BIN = ROOT / "evbench" / "target" / "debug" / "evbench.exe"
MO_RUNNER = ROOT / "metao" / "runner.py"
FC_RUNNER_SRC = ROOT / "finecode" / "runner.ts"

STEP_LOG: list[dict] = []


def jdump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def jload(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def run_step(name: str, cmd: list[str], cwd: Path, timeout: int = STEP_TIMEOUT) -> dict:
    """Run one child process to completion, keep its raw stdio, return its exit info."""
    RAW.mkdir(parents=True, exist_ok=True)
    t = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    wall = round((time.perf_counter() - t) * 1000)
    (RAW / f"{name}.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (RAW / f"{name}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    info = {"step": name, "exit_code": proc.returncode, "wall_ms": wall, "cmd": cmd}
    STEP_LOG.append(info)
    return info


def spawn_step(name: str, cmd: list[str], cwd: Path) -> tuple[subprocess.Popen, object, object]:
    RAW.mkdir(parents=True, exist_ok=True)
    fo = open(RAW / f"{name}.stdout.txt", "w", encoding="utf-8", errors="replace")
    fe = open(RAW / f"{name}.stderr.txt", "w", encoding="utf-8", errors="replace")
    p = subprocess.Popen(cmd, cwd=str(cwd), stdout=fo, stderr=fe)
    return p, fo, fe


def finish_spawn(name: str, p: subprocess.Popen, fo, fe, timeout: int) -> int:
    rc = p.wait(timeout=timeout)
    fo.close()
    fe.close()
    STEP_LOG.append({"step": name, "exit_code": rc, "wall_ms": None, "cmd": "(spawned)"})
    return rc


def wait_for(path: Path, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists():
            return True
        time.sleep(0.02)
    return False


def count_units(path: Path, pattern: str = r"unit=(\d+)") -> Counter:
    c: Counter = Counter()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.search(pattern, line)
            if m:
                c[int(m.group(1))] += 1
    return c


def jsonl_units(path: Path) -> Counter:
    c: Counter = Counter()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c[json.loads(line)["unit"]] += 1
    return c


def metrics_from(effects: Counter, invocations: Counter, total: int, recovered: int) -> dict:
    units = range(1, total + 1)
    return {
        "units_recovered": recovered,
        "units_before_interruption": recovered,
        "re_executed": sum(max(0, invocations.get(u, 0) - 1) for u in units),
        "effects_duplicated": sum(max(0, effects.get(u, 0) - 1) for u in units),
        "effects_lost": sum(1 for u in units if effects.get(u, 0) == 0),
        "effect_counts": {str(u): effects.get(u, 0) for u in units},
        "invocation_counts": {str(u): invocations.get(u, 0) for u in units},
    }


def empty_metrics() -> dict:
    return {
        "units_recovered": None, "units_before_interruption": None, "re_executed": None,
        "effects_duplicated": None, "effects_lost": None, "stale_rejected": None,
        "state_integrity": None, "recovery_ms": None, "init_ms": None, "work_ms": None,
        "wall_ms": None, "manual_interventions": 0,
    }


# ---------------------------------------------------------------- FineCode

def fc_prepare_runner() -> None:
    shutil.copyfile(FC_RUNNER_SRC, FC_DIR / "bench-runner.ts")


def fc_args(d: Path, step: str, variant: str, **kw) -> dict:
    base = {
        "mode": "run",
        "db": str(d / "state.sqlite"),
        "idFile": str(d / "id.txt"),
        "effects": str(d / "effects.log"),
        "invocations": str(d / "inv.log"),
        "outFile": str(d / f"out-{step}.json"),
        "total": TOTAL,
        "variant": variant,
    }
    base.update(kw)
    return base


def fc_cmd(args: dict) -> list[str]:
    import json as _j
    return ["node", "--conditions=source", "--experimental-strip-types", "bench-runner.ts", _j.dumps(args)]


def fc_step(name: str, d: Path, step: str, variant: str, **kw) -> dict:
    args = fc_args(d, step, variant, **kw)
    info = run_step(f"{name}", fc_cmd(args), FC_DIR)
    info["out"] = jload(Path(args["outFile"]))
    return info


def fc_effects(d: Path) -> tuple[Counter, Counter]:
    return count_units(d / "effects.log", r"unit=(\d+)"), jsonl_units(d / "inv.log")


# ---------------------------------------------------------------- EvCore

def ev_cmd(mode: str, d: Path, step: str, **kw) -> list[str]:
    cmd = [str(EV_BIN), mode, "--dir", str(d / "sess"), "--out", str(d / f"out-{step}.json")]
    for k, v in kw.items():
        cmd += [f"--{k}", str(v)]
    return cmd


def ev_effects(d: Path) -> tuple[Counter, Counter]:
    eff = count_units(d / "effects.log", r"unit=(\d+)")
    return eff, eff  # EvCore's effect tool is the only invocation path; every call writes one line


# ---------------------------------------------------------------- metaO

def mo_cmd(args: dict) -> list[str]:
    import json as _j
    return [sys.executable, str(MO_RUNNER), _j.dumps(args)]


def mo_args(d: Path, step: str, mode: str, **kw) -> dict:
    base = {
        "mode": mode,
        "db": str(d / "store.db"),
        "mission": "m-bench",
        "effects": str(d / "effects.log"),
        "invocations": str(d / "inv.log"),
        "out": str(d / f"out-{step}.json"),
        "total": TOTAL,
    }
    base.update(kw)
    return base


def mo_effects(d: Path) -> tuple[Counter, Counter]:
    eff = count_units(d / "effects.log", r"unit=(\d+)")
    return eff, jsonl_units(d / "inv.log")


# ---------------------------------------------------------------- scenario helpers

def rep_dir(project: str, scen: str, variant: str, rep: int) -> Path:
    d = RUNS / project / scen / variant / f"rep{rep}"
    if d.exists():
        raise SystemExit(f"refusing to overwrite existing evidence directory: {d}")
    d.mkdir(parents=True)
    return d


def record(results: dict, project: str, scen: str, variant: str, rep: int, status: str, metrics: dict, evidence: dict, note: str) -> None:
    results.setdefault(project, {}).setdefault("scenarios", {}).setdefault(scen, {}).setdefault(variant, []).append({
        "rep": rep,
        "status": status,
        "metrics": metrics,
        "evidence": evidence,
        "note": note,
    })
    print(f"[{project} {scen}/{variant} rep{rep}] {status} :: {note}", flush=True)


# ---------------------------------------------------------------- FineCode scenarios

def fc_scenario(results: dict, scen: str, rep: int) -> None:
    proj = "FineCode"
    if scen == "A":
        d = rep_dir(proj, scen, "plain", rep)
        r1 = fc_step(f"FineCode-A-rep{rep}-run1-stop3", d, "run1", "plain", stopAfter=3)
        r2 = fc_step(f"FineCode-A-rep{rep}-run2-recover", d, "run2", "plain")
        eff, inv = fc_effects(d)
        m = metrics_from(eff, inv, TOTAL, (r2["out"] or {}).get("units_recovered", -1))
        m.update(init_ms=(r2["out"] or {}).get("open_ms"), recovery_ms=(r2["out"] or {}).get("recover_ms"),
                 work_ms=(r1["out"] or {}).get("work_ms"), wall_ms=r2["wall_ms"])
        ok = (r1["exit_code"] == 0 and r2["exit_code"] == 0 and m["units_recovered"] == 3
              and (r2["out"] or {}).get("outcome") == {"status": "completed", "result": TOTAL}
              and m["effects_duplicated"] == 0 and m["effects_lost"] == 0 and m["re_executed"] == 0)
        m["state_integrity"] = "completed_consistent" if ok else "inconsistent"
        note = f"run1 closed normally (exit {r1['exit_code']}), run2 recovered {m['units_recovered']}, outcome={(r2['out'] or {}).get('outcome')}"
        record(results, proj, scen, "plain", rep, "PASS" if ok else "FAIL", m, {"dir": str(d)}, note)

    elif scen == "B":
        d = rep_dir(proj, scen, "plain", rep)
        r1 = fc_step(f"FineCode-B-rep{rep}-run1-sigkill", d, "run1", "plain", crash={"unit": 2, "point": "after_commit"})
        r2 = fc_step(f"FineCode-B-rep{rep}-run2-recover", d, "run2", "plain")
        eff, inv = fc_effects(d)
        m = metrics_from(eff, inv, TOTAL, (r2["out"] or {}).get("units_recovered", -1))
        m.update(init_ms=(r2["out"] or {}).get("open_ms"), recovery_ms=(r2["out"] or {}).get("recover_ms"), wall_ms=r2["wall_ms"])
        killed = r1["exit_code"] != 0
        ok = (killed and r2["exit_code"] == 0 and m["units_recovered"] == 2 and m["effects_duplicated"] == 0
              and m["effects_lost"] == 0 and m["re_executed"] == 0
              and (r2["out"] or {}).get("outcome") == {"status": "completed", "result": TOTAL})
        m["state_integrity"] = "completed_consistent" if ok else "inconsistent"
        note = f"run1 terminated abruptly (exit {r1['exit_code']}); run2 recovered {m['units_recovered']} units"
        record(results, proj, scen, "plain", rep, "PASS" if ok else "FAIL", m, {"dir": str(d)}, note)

    elif scen == "C":
        for variant in ["plain", "memo", "idem"]:
            d = rep_dir(proj, scen, variant, rep)
            r1 = fc_step(f"FineCode-C-{variant}-rep{rep}-run1-kill-after-effect", d, "run1", variant,
                         crash={"unit": 3, "point": "after_effect"})
            r2 = fc_step(f"FineCode-C-{variant}-rep{rep}-run2-recover", d, "run2", variant)
            eff, inv = fc_effects(d)
            m = metrics_from(eff, inv, TOTAL, (r2["out"] or {}).get("units_recovered", -1))
            m.update(init_ms=(r2["out"] or {}).get("open_ms"), recovery_ms=(r2["out"] or {}).get("recover_ms"), wall_ms=r2["wall_ms"])
            completed = (r2["out"] or {}).get("outcome") == {"status": "completed", "result": TOTAL}
            safe = m["effects_duplicated"] == 0 and m["effects_lost"] == 0 and completed and r2["exit_code"] == 0
            m["state_integrity"] = "completed_consistent" if completed else "inconsistent"
            note = (f"killed after effect of unit 3 (exit {r1['exit_code']}); recovered {m['units_recovered']}; "
                    f"invocations(3)={m['invocation_counts']['3']}, effect records(3)={m['effect_counts']['3']}")
            record(results, proj, scen, variant, rep, "PASS" if safe else "FAIL", m, {"dir": str(d)}, note)

    elif scen == "D":
        d = rep_dir(proj, scen, "plain", rep)
        ready, release, stale_log = d / "stale.ready", d / "stale.release", d / "stale-commit.json"
        p1, fo, fe = spawn_step(f"FineCode-D-rep{rep}-worker1-stale", fc_cmd(fc_args(
            d, "stale", "plain", mode="stale", staleUnit=3, readyFile=str(ready), releaseFile=str(release),
            staleLog=str(stale_log), timeoutMs=60000, outFile=str(d / "out-stale.json"))), FC_DIR)
        ready_ok = wait_for(ready, 60)
        r2 = fc_step(f"FineCode-D-rep{rep}-worker2-takeover", d, "takeover", "plain")
        release.write_text("go", encoding="utf-8")
        rc1 = finish_spawn(f"FineCode-D-rep{rep}-worker1-stale", p1, fo, fe, 90)
        sc = jload(stale_log) or {"commit": "no_result"}
        eff, inv = fc_effects(d)
        m = metrics_from(eff, inv, TOTAL, (r2["out"] or {}).get("units_recovered", -1))
        m.update(stale_rejected=(sc.get("commit") == "rejected"), wall_ms=r2["wall_ms"])
        final = (r2["out"] or {}).get("outcome")
        ok = ready_ok and sc.get("commit") == "rejected"
        m["state_integrity"] = f"final_outcome={final}; stale_commit={sc.get('commit')}"
        note = (f"worker1 held unit 3 after effect; worker2 reopened (reconciled) and completed; "
                f"worker1 late commit -> {sc.get('commit')} {sc.get('error', '')}")
        record(results, proj, scen, "plain", rep, "PASS" if ok else "FAIL", m, {"dir": str(d), "stale_commit": sc, "worker1_exit": rc1}, note)

    elif scen == "E":
        # Build a valid completed-to-3 state, then damage the file.
        base = rep_dir(proj, scen, "seed", rep)
        fc_step(f"FineCode-E-rep{rep}-seed", base, "seed", "plain", stopAfter=3)
        valid_bytes = (base / "state.sqlite").read_bytes()
        for kind in ["truncate", "overwrite"]:
            d = rep_dir(proj, scen, kind, rep)
            data = bytearray(valid_bytes)
            if kind == "truncate":
                data = data[: len(data) // 2]
            else:
                data[4096:6144] = b"\xff" * 2048
            (d / "state.sqlite").write_bytes(bytes(data))
            shutil.copy(base / "id.txt", d / "id.txt")
            ins = fc_step(f"FineCode-E-{kind}-rep{rep}-inspect", d, "inspect", "plain", mode="inspect")
            out = ins["out"] or {}
            rejected = "error" in out
            status = "PASS" if rejected else "FAIL"
            if not rejected:
                st = (out.get("inspect") or {})
                status = "PASS" if (st and st.get("checkpoint", {}).get("done") == 3) else "FAIL"
            m = empty_metrics()
            m.update(state_integrity="rejected" if rejected else "accepted", units_recovered=None)
            note = f"{kind}: {'rejected: ' + out['error'][:160] if rejected else 'accepted; state=' + json.dumps(out.get('inspect'))[:160]}"
            record(results, proj, "E", kind, rep, status, m, {"dir": str(d)}, note)


# ---------------------------------------------------------------- EvCore scenarios

def ev_scenario(results: dict, scen: str, rep: int) -> None:
    proj = "EvCore"
    if scen == "A":
        d = rep_dir(proj, scen, "plain", rep)
        r1 = run_step(f"EvCore-A-rep{rep}-run1-stop3", ev_cmd("run", d, "run1", total=TOTAL,
                      effects=d / "effects.log", **{"stop-after": 3}), ROOT)
        r2 = run_step(f"EvCore-A-rep{rep}-run2-recover", ev_cmd("run", d, "run2", total=TOTAL, effects=d / "effects.log"), ROOT)
        o1, o2 = jload(d / "out-run1.json") or {}, jload(d / "out-run2.json") or {}
        eff, inv = ev_effects(d)
        m = metrics_from(eff, inv, TOTAL, o2.get("units_recovered", -1))
        m.update(init_ms=o2.get("open_ms"), recovery_ms=o2.get("open_ms"), work_ms=o2.get("work_ms"), wall_ms=r2["wall_ms"],
                 state_integrity="verified_jsonl" if not o2.get("warnings") else "warnings")
        ok = (r1["exit_code"] == 0 and r2["exit_code"] == 0 and m["units_recovered"] == 3
              and o2.get("units_completed_this_run") == [4, 5] and m["effects_duplicated"] == 0 and m["effects_lost"] == 0)
        note = f"run1 units {o1.get('units_completed_this_run')}; run2 recovered {m['units_recovered']} and completed {o2.get('units_completed_this_run')}"
        record(results, proj, scen, "plain", rep, "PASS" if ok else "FAIL", m, {"dir": str(d)}, note)

    elif scen == "B":
        d = rep_dir(proj, scen, "plain", rep)
        r1 = run_step(f"EvCore-B-rep{rep}-run1-abort", ev_cmd("run", d, "run1", total=TOTAL, effects=d / "effects.log",
                      **{"crash-unit": 2, "crash-point": "after_sync"}), ROOT)
        r2 = run_step(f"EvCore-B-rep{rep}-run2-recover", ev_cmd("run", d, "run2", total=TOTAL, effects=d / "effects.log"), ROOT)
        o2 = jload(d / "out-run2.json") or {}
        eff, inv = ev_effects(d)
        m = metrics_from(eff, inv, TOTAL, o2.get("units_recovered", -1))
        m.update(init_ms=o2.get("open_ms"), recovery_ms=o2.get("open_ms"), work_ms=o2.get("work_ms"), wall_ms=r2["wall_ms"],
                 state_integrity="warnings:" + json.dumps(o2.get("warnings")) if o2.get("warnings") else "verified_jsonl")
        ok = (r1["exit_code"] != 0 and r2["exit_code"] == 0 and m["units_recovered"] == 2 and m["effects_duplicated"] == 0
              and m["effects_lost"] == 0 and m["re_executed"] == 0)
        note = f"run1 aborted (exit {r1['exit_code']}); run2 recovered {m['units_recovered']}; warnings={o2.get('warnings')}"
        record(results, proj, scen, "plain", rep, "PASS" if ok else "FAIL", m, {"dir": str(d)}, note)

    elif scen == "C":
        d = rep_dir(proj, scen, "plain", rep)
        r1 = run_step(f"EvCore-C-rep{rep}-run1-abort-after-effect", ev_cmd("run", d, "run1", total=TOTAL,
                      effects=d / "effects.log", **{"crash-unit": 3, "crash-point": "after_effect"}), ROOT)
        r2 = run_step(f"EvCore-C-rep{rep}-run2-recover", ev_cmd("run", d, "run2", total=TOTAL, effects=d / "effects.log"), ROOT)
        o2 = jload(d / "out-run2.json") or {}
        eff, inv = ev_effects(d)
        m = metrics_from(eff, inv, TOTAL, o2.get("units_recovered", -1))
        m.update(init_ms=o2.get("open_ms"), recovery_ms=o2.get("open_ms"), wall_ms=r2["wall_ms"],
                 state_integrity="verified_jsonl" if not o2.get("warnings") else "warnings")
        safe = m["effects_duplicated"] == 0 and m["effects_lost"] == 0 and r2["exit_code"] == 0
        note = (f"aborted inside tool of unit 3 after its effect (exit {r1['exit_code']}); recovered {m['units_recovered']}; "
                f"effect lines(3)={m['effect_counts']['3']}")
        record(results, proj, scen, "plain", rep, "PASS" if safe else "FAIL", m, {"dir": str(d)}, note)

    elif scen == "D":
        d = rep_dir(proj, scen, "plain", rep)
        run_step(f"EvCore-D-rep{rep}-seed", ev_cmd("run", d, "seed", total=3, effects=d / "effects.log"), ROOT)
        r = run_step(f"EvCore-D-rep{rep}-stale-takeover", ev_cmd("stale", d, "stale", effects=d / "effects.log"), ROOT)
        o = jload(d / "out-stale.json") or {}
        eff, inv = ev_effects(d)
        msgs = o.get("user_messages") or []
        rejected = "rejected" in str(o.get("stale_run_result", ""))
        m = metrics_from(eff, inv, 4, o.get("units_recovered", -1))
        m.update(stale_rejected=rejected, state_integrity="stale_message_persisted" if any("stale" in x for x in msgs) else "clean",
                 wall_ms=r["wall_ms"])
        status = "PASS" if rejected else "FAIL"
        note = f"second handle on same file; stale append -> {o.get('stale_run_result')}; user messages={msgs}"
        record(results, proj, scen, "plain", rep, status, m, {"dir": str(d)}, note)

    elif scen == "E":
        base = rep_dir(proj, scen, "seed", rep)
        run_step(f"EvCore-E-rep{rep}-seed", ev_cmd("run", base, "seed", total=TOTAL, effects=base / "effects.log",
                 **{"stop-after": 3}), ROOT)
        src = next((base / "sess").glob("*.jsonl"))
        raw = src.read_bytes()
        for kind in ["truncate", "overwrite"]:
            d = rep_dir(proj, scen, kind, rep)
            (d / "sess").mkdir()
            dst = d / "sess" / src.name
            if kind == "truncate":
                dst.write_bytes(raw[: len(raw) // 2])  # cut mid-file: crash-style unterminated last line
            else:
                lines = raw.split(b"\n")
                idx = max(2, len(lines) // 2)
                lines[idx] = b'{"corrupted": ' + lines[idx][:10]
                dst.write_bytes(b"\n".join(lines))
            ins = run_step(f"EvCore-E-{kind}-rep{rep}-inspect", ev_cmd("inspect", d, "inspect"), ROOT)
            o = jload(d / "out-inspect.json") or {}
            if o.get("ok") is False:
                status, state = "PASS", "rejected"
            elif o.get("ok") and o.get("warnings"):
                status, state = "PASS", "recovered_with_warning"
            else:
                status, state = "FAIL", "accepted_silently"
            m = empty_metrics()
            m.update(state_integrity=state, units_recovered=len(o.get("user_messages") or []) if o.get("ok") else None)
            note = f"{kind}: ok={o.get('ok')} error={o.get('error')} warnings={o.get('warnings')} user_msgs={o.get('user_messages')}"
            record(results, proj, "E", kind, rep, status, m, {"dir": str(d)}, note)


# ---------------------------------------------------------------- metaO scenarios

def mo_scenario(results: dict, scen: str, rep: int) -> None:
    proj = "metaO"
    if scen == "A":
        d = rep_dir(proj, scen, "plain", rep)
        r1 = run_step(f"metaO-A-rep{rep}-run1-stop3", mo_cmd(mo_args(d, "run1", "ledger", stopAfter=3)), ROOT)
        r2 = run_step(f"metaO-A-rep{rep}-run2-recover", mo_cmd(mo_args(d, "run2", "ledger")), ROOT)
        o2 = jload(d / "out-run2.json") or {}
        eff, inv = mo_effects(d)
        m = metrics_from(eff, inv, TOTAL, o2.get("units_recovered", -1))
        m.update(init_ms=o2.get("init_ms"), recovery_ms=o2.get("init_ms"), work_ms=o2.get("work_ms"), wall_ms=r2["wall_ms"],
                 state_integrity="ledger_events_" + str(o2.get("events_after")))
        ok = (r1["exit_code"] == 0 and r2["exit_code"] == 0 and m["units_recovered"] == 3
              and o2.get("units_completed_this_run") == [4, 5] and o2.get("events_after") == 5
              and m["effects_duplicated"] == 0 and m["effects_lost"] == 0)
        note = f"ledger events persisted {o2.get('events_before')}; run2 completed {o2.get('units_completed_this_run')}"
        record(results, proj, scen, "plain", rep, "PASS" if ok else "FAIL", m, {"dir": str(d)}, note)
        # Sub-check A-sup: project-level supervise_project under abrupt death (no persistence in the function).
        d2 = rep_dir(proj, "A-sup", "plain", rep)
        s1 = run_step(f"metaO-Asup-rep{rep}-run1-kill-unit3", mo_cmd(mo_args(d2, "sup1", "supervise", crashAfterUnit=3)), ROOT)
        s2 = run_step(f"metaO-Asup-rep{rep}-run2-restart", mo_cmd(mo_args(d2, "sup2", "supervise")), ROOT)
        so2 = jload(d2 / "out-sup2.json") or {}
        eff2, inv2 = mo_effects(d2)
        m2 = metrics_from(eff2, inv2, TOTAL, 0)  # nothing is recovered: no supervision state exists
        m2.update(wall_ms=s2["wall_ms"], state_integrity="no_persisted_supervision_state")
        note = (f"supervise_project killed in unit 3 (exit {s1['exit_code']}); restart verdict={so2.get('verdict')}; "
                f"re-executed={m2['re_executed']} effects_duplicated={m2['effects_duplicated']}")
        record(results, proj, "A-sup", "plain", rep, "NOT_SUPPORTED", m2, {"dir": str(d2)},
               "supervise_project keeps progress only in local variables; " + note)

    elif scen == "B":
        d = rep_dir(proj, scen, "plain", rep)
        r1 = run_step(f"metaO-B-rep{rep}-run1-os_exit", mo_cmd(mo_args(d, "run1", "ledger",
                      crash={"unit": 2, "point": "after_commit"})), ROOT)
        r2 = run_step(f"metaO-B-rep{rep}-run2-recover", mo_cmd(mo_args(d, "run2", "ledger")), ROOT)
        o2 = jload(d / "out-run2.json") or {}
        eff, inv = mo_effects(d)
        m = metrics_from(eff, inv, TOTAL, o2.get("units_recovered", -1))
        m.update(init_ms=o2.get("init_ms"), recovery_ms=o2.get("init_ms"), work_ms=o2.get("work_ms"), wall_ms=r2["wall_ms"],
                 state_integrity="ledger_events_" + str(o2.get("events_after")))
        ok = (r1["exit_code"] != 0 and r2["exit_code"] == 0 and m["units_recovered"] == 2 and m["effects_duplicated"] == 0
              and m["effects_lost"] == 0 and m["re_executed"] == 0 and o2.get("events_after") == 5)
        note = f"run1 os._exit (exit {r1['exit_code']}); run2 recovered {m['units_recovered']}"
        record(results, proj, scen, "plain", rep, "PASS" if ok else "FAIL", m, {"dir": str(d)}, note)

    elif scen == "C":
        d = rep_dir(proj, scen, "plain", rep)
        r1 = run_step(f"metaO-C-rep{rep}-run1-exit-after-effect", mo_cmd(mo_args(d, "run1", "ledger",
                      crash={"unit": 3, "point": "after_effect"}, handles=True)), ROOT)
        insp = run_step(f"metaO-C-rep{rep}-inspect-after-crash", mo_cmd(mo_args(d, "insp1", "inspect")), ROOT)
        oi = jload(d / "out-insp1.json") or {}
        r2 = run_step(f"metaO-C-rep{rep}-run2-recover", mo_cmd(mo_args(d, "run2", "ledger", handles=True)), ROOT)
        o2 = jload(d / "out-run2.json") or {}
        eff, inv = mo_effects(d)
        m = metrics_from(eff, inv, TOTAL, o2.get("units_recovered", -1))
        m.update(init_ms=o2.get("init_ms"), recovery_ms=o2.get("init_ms"), work_ms=o2.get("work_ms"), wall_ms=r2["wall_ms"],
                 state_integrity=f"orphan_handle_status={oi.get('handle_status')}")
        safe = m["effects_duplicated"] == 0 and m["effects_lost"] == 0 and r2["exit_code"] == 0
        note = (f"exit-after-effect of unit 3 (exit {r1['exit_code']}); handle after crash={oi.get('handle_status')} "
                f"{oi.get('handle_execution_id')}; recovered {m['units_recovered']}; effect lines(3)={m['effect_counts']['3']}")
        record(results, proj, scen, "plain", rep, "PASS" if safe else "FAIL", m, {"dir": str(d)}, note)

    elif scen == "D":
        # D1: concurrent ledger appenders (sequence assigned inside BEGIN IMMEDIATE).
        d1 = rep_dir(proj, "D1-ledger", "plain", rep)
        procs = []
        for tag in ["A", "B"]:
            procs.append(spawn_step(f"metaO-D1-rep{rep}-appender-{tag}", mo_cmd(
                {"mode": "append", "db": str(d1 / "store.db"), "mission": "m-conc", "tag": tag, "count": 20,
                 "out": str(d1 / f"out-{tag}.json")}), ROOT) + (tag,))
        for p, fo, fe, tag in procs:
            finish_spawn(f"metaO-D1-rep{rep}-appender-{tag}", p, fo, fe, 120)
        seqs = []
        for tag in ["A", "B"]:
            seqs += (jload(d1 / f"out-{tag}.json") or {}).get("sequences", [])
        d1ok = sorted(seqs) == list(range(1, 41))
        m1 = empty_metrics()
        m1.update(state_integrity="unique_contiguous_40" if d1ok else "conflict", effects_duplicated=0 if d1ok else None)
        record(results, proj, "D1-ledger", "plain", rep, "PASS" if d1ok else "FAIL", m1, {"dir": str(d1)},
               f"two processes x20 appends; sequences unique and contiguous: {d1ok}")
        # D2: stale MissionRecord replace() after another worker's replace()
        d2 = rep_dir(proj, "D2-record", "plain", rep)
        r = run_step(f"metaO-D2-rep{rep}-stale-record", mo_cmd({"mode": "record", "db": str(d2 / "store.db"), "mission": "m-rec",
                     "out": str(d2 / "out.json")}), ROOT)
        o = jload(d2 / "out.json") or {}
        m2 = empty_metrics()
        m2.update(stale_rejected=o.get("stale_write") == "rejected", state_integrity=f"final_orch={o.get('final_orchestrator_id')} rev={o.get('final_revision')}")
        record(results, proj, "D2-record", "plain", rep, "PASS" if o.get("stale_write") == "rejected" else "FAIL", m2,
               {"dir": str(d2)}, f"stale replace -> {o.get('stale_write')}; final orchestrator={o.get('final_orchestrator_id')}")
        # D3: execution-handle takeover then stale complete()
        d3 = rep_dir(proj, "D3-handle", "plain", rep)
        r = run_step(f"metaO-D3-rep{rep}-stale-handle", mo_cmd({"mode": "handle", "db": str(d3 / "store.db"), "mission": "m-h",
                     "out": str(d3 / "out.json")}), ROOT)
        o = jload(d3 / "out.json") or {}
        ok = str(o.get("stale_complete_by_worker1", "")).startswith("rejected")
        m3 = empty_metrics()
        m3.update(stale_rejected=o.get("stale_complete_by_worker1", "").startswith("rejected"),
                  state_integrity=f"final_exec={o.get('final_execution_id')} status={o.get('final_status')}")
        record(results, proj, "D3-handle", "plain", rep, "PASS" if ok else "FAIL", m3, {"dir": str(d3)},
               f"takeover={o.get('takeover_by_worker2')}; stale complete={o.get('stale_complete_by_worker1')}; final={o.get('final_execution_id')}")

    elif scen == "E":
        base = rep_dir(proj, scen, "seed", rep)
        run_step(f"metaO-E-rep{rep}-seed", mo_cmd({"mode": "seed", "db": str(base / "store.db"), "mission": "m-s",
                 "out": str(base / "out-seed.json")}), ROOT)
        valid = (base / "store.db").read_bytes()
        import sqlite3
        cases = {}
        cases["truncate"] = valid[: len(valid) // 2]
        cases["overwrite"] = valid[:4096] + b"\xff" * 2048 + valid[6144:]
        for kind, data in cases.items():
            d = rep_dir(proj, scen, kind, rep)
            (d / "store.db").write_bytes(data)
            ins = run_step(f"metaO-E-{kind}-rep{rep}-inspect", mo_cmd(mo_args(d, "inspect", "inspect", mission="m-s")), ROOT)
            o = jload(d / "out-inspect.json") or {}
            # PASS = no table is silently wrong (each readable table is either rejected or matches the seed).
            silent = (o.get("ledger_ok") and o.get("events") != [1, 2, 3]) or (o.get("record_ok") and o.get("record_revision") != 1)
            rejected_all = not o.get("ledger_ok") and not o.get("record_ok")
            status = "FAIL" if silent else "PASS"
            m = empty_metrics()
            m.update(state_integrity="rejected" if rejected_all else f"partial:{json.dumps({k: v for k, v in o.items() if k.endswith('_ok')})}")
            record(results, proj, "E", kind, rep, status, m, {"dir": str(d)},
                   f"{kind}: ledger_ok={o.get('ledger_ok')} record_ok={o.get('record_ok')} handle_ok={o.get('handle_ok')} "
                   f"err={o.get('ledger_error') or o.get('record_error') or o.get('handle_error')}")
        # E3: logical column tamper (revision column != snapshot), only the record table.
        d = rep_dir(proj, scen, "column-tamper", rep)
        shutil.copy(base / "store.db", d / "store.db")
        con = sqlite3.connect(str(d / "store.db"))
        con.execute("UPDATE mission_records SET revision = 99 WHERE mission_id = 'm-s'")
        con.commit()
        con.close()
        ins = run_step(f"metaO-E-column-tamper-rep{rep}-inspect", mo_cmd(mo_args(d, "inspect", "inspect", mission="m-s")), ROOT)
        o = jload(d / "out-inspect.json") or {}
        ok = (o.get("record_ok") is False) and "does not match snapshot" in str(o.get("record_error"))
        m = empty_metrics()
        m.update(state_integrity="record_rejected" if o.get("record_ok") is False else "accepted")
        record(results, proj, "E", "column-tamper", rep, "PASS" if ok else "FAIL", m, {"dir": str(d)},
               f"record_ok={o.get('record_ok')} err={o.get('record_error')}; ledger_ok={o.get('ledger_ok')}")


# ---------------------------------------------------------------- main

def main() -> None:
    if RUNS.exists():
        raise SystemExit(f"{RUNS} already exists; choose a new BENCH_RUN_ID")
    RUNS.mkdir(parents=True)
    RAW.mkdir(parents=True, exist_ok=True)
    fc_prepare_runner()
    results: dict = {"run_id": RUN_ID, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "total_units": TOTAL, "reps": REPS}
    scen_filter = os.environ.get("BENCH_ONLY")
    for rep in REPS:
        for scen in ["A", "B", "C", "D", "E"]:
            if scen_filter and scen not in scen_filter.split(","):
                continue
            fc_scenario(results, scen, rep)
            ev_scenario(results, scen, rep)
            mo_scenario(results, scen, rep)
    results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    results["steps"] = STEP_LOG
    jdump(ROOT / f"results-{RUN_ID}.json", results)
    print("WROTE", ROOT / f"results-{RUN_ID}.json")


if __name__ == "__main__":
    main()
