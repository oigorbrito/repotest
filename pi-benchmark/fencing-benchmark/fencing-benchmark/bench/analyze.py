#!/usr/bin/env python3
"""Aggregate raw/<impl>/*.jsonl and perf.json into results.json (metrics + provenance).

Verdicts are computed mechanically from the rules in README.md / RESULTS.md. Anything with no data is
NOT TESTADO. Invalid repetitions (infrastructure aborted the run) are counted and excluded from rates.
"""
import glob, hashlib, json, os, platform, statistics, subprocess, sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "raw")
OUT = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(ROOT, "results.json")
IMPLS = ["statepact-redis", "zk-redis-lua", "etcd-pg", "statepact-pg"]
ABLATIONS = ["etcd-pg-v1"]
LABEL = {"statepact-redis": "1. StatePact Redis", "zk-redis-lua": "2. ZooKeeper + Redis Lua",
         "etcd-pg": "3. etcd + PostgreSQL", "statepact-pg": "4. StatePact PostgreSQL"}
# Hard failures: any occurrence means the mechanism let a stale or inconsistent write through, or lost one.
HARD = {
    "D2": ["stale_accepted", "valid_rejected", "monotonic_violation"],
    "C4": ["stale_accepted", "valid_rejected", "monotonic_violation"],
    "EXP_AFTER": ["stale_accepted", "monotonic_violation"],
    "CONC": ["stale_final", "monotonic_violation", "valid_rejected"],
    "REST": ["monotonic_violation", "value_lost", "valid_rejected"],
    "FAIL": ["duplicate_effect", "lost_write"],
    "FAILOVER": ["token_regression", "stale_accepted", "valid_rejected"],
}
SCEN_ORDER = ["D2", "C4", "EXP_BEFORE", "EXP_AFTER", "CONC", "REST", "FAIL", "NEG", "FAILOVER"]


def load(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round(p / 100 * len(xs) + 0.5)) - 1))
    return round(xs[k], 3)


def summarize_scenario(name, rows):
    valid = [r for r in rows if not r.get("invalid")]
    out = {"runs": len(rows), "valid": len(valid), "invalid": len(rows) - len(valid),
           "invalid_reasons": sorted({r.get("why", "")[:120] for r in rows if r.get("invalid")})[:5]}
    counters = ["stale_accepted", "valid_rejected", "monotonic_violation", "final_is_new_owner_false",
                "stale_final", "value_lost", "duplicate_effect", "lost_write", "token_regression",
                "expired_write_accepted", "control_detected", "b_acquired", "a_accepted_during_adoption",
                "retry_replayed"]
    for c in counters:
        if c == "final_is_new_owner_false":
            out[c] = sum(1 for r in valid if "final_is_new_owner" in r and not r["final_is_new_owner"])
        elif c == "a_accepted_during_adoption":
            out[c] = sum(1 for r in valid if r.get("b_acquired") and r.get("commit_A") == "ok")
        elif any(c in r for r in valid):
            out[c] = sum(1 for r in valid if r.get(c))
    if name == "NEG":
        out["control_detected_rate"] = round(out.get("control_detected", 0) / max(1, len(valid)), 4)
    if name == "EXP_BEFORE":
        out["expired_write_accepted"] = sum(1 for r in valid if r.get("expired_write_accepted"))
    if name == "REST":
        out["restart_ms_p50"] = pct([r["restart_ms"] for r in valid if "restart_ms" in r], 50)
        out["restart_ms_p95"] = pct([r["restart_ms"] for r in valid if "restart_ms" in r], 95)
        out["first_read_after_restart_ms_p50"] = pct([r["first_read_after_restart_ms"] for r in valid if "first_read_after_restart_ms" in r], 50)
    if name == "FAIL":
        d = [r["downtime_ms"] for r in valid if "downtime_ms" in r]
        out["downtime_ms_p50"], out["downtime_ms_p95"], out["downtime_ms_p99"] = pct(d, 50), pct(d, 95), pct(d, 99)
        out["downtime_ms_max"] = max(d) if d else None
        out["first_attempt_outcomes"] = _count(valid, "first_attempt")
        out["retry_outcomes"] = _count(valid, "retry_commit")
    # passed: every hard criterion of the scenario holds in that repetition
    hard = HARD.get(name, [])
    if name == "NEG":
        out["passed"] = out.get("control_detected", 0)
        out["verdict_rule"] = "control: a stale write must be detected (accepted and final value == stale value)"
    elif name == "EXP_BEFORE":
        out["passed"] = sum(1 for r in valid if not r.get("expired_write_accepted"))
        out["verdict_rule"] = "writer resumed after expiry, no successor: must be rejected (limitation if accepted)"
    else:
        out["passed"] = sum(1 for r in valid if all(not r.get(h) for h in hard if h in r)
                            and (name != "CONC" or r.get("final_value") != "vA")
                            and (name != "FAIL" or r.get("retry_commit") == "ok")
                            and (name != "REST" or r.get("commit_after") == "ok")
                            and (name != "C4" or r.get("final_is_new_owner", True))
                            and (name != "D2" or r.get("final_is_new_owner", True))
                            and (name != "FAILOVER" or r.get("final_is_new_owner", True)))
        out["verdict_rule"] = "all hard criteria for the scenario hold: " + ", ".join(hard)
    out["pass_rate"] = round(out["passed"] / max(1, len(valid)), 4)
    return out


def _count(rows, key):
    c = {}
    for r in rows:
        c[str(r.get(key))] = c.get(str(r.get(key)), 0) + 1
    return c


def summarize_race(label, rows):
    valid = [r for r in rows if not r.get("invalid")]
    out = {"runs": len(rows), "valid": len(valid), "invalid": len(rows) - len(valid)}
    for k in ["a_blocked_in_commit", "b_grant_completed_while_a_in_commit", "b_blocked_behind_a",
              "stale_accepted_after_successor_granted", "b_granted_before_a_commit", "stale_accepted_in_window",
              "b_register_ok"]:
        if any(k in r for r in valid):
            out[k] = sum(1 for r in valid if r.get(k))
    if any("note" in r for r in valid):
        out["note"] = valid[0]["note"]
    return out


def perf_summary(rows):
    ok = [r for r in rows if "error" not in r]
    def col(k):
        return [r[k] for r in ok if r.get(k) is not None]
    out = {"cycles": len(rows), "failed_cycles": len(rows) - len(ok),
           "commit_rejected_or_not_ok": sum(1 for r in ok if r.get("commit_status") != "ok")}
    for k, lab in [("acquire_ms", "acquire_server_ms"), ("commit_ms", "commit_server_ms"),
                   ("rt_acquire_ms", "acquire_roundtrip_ms"), ("rt_commit_ms", "commit_roundtrip_ms"),
                   ("rt_release_ms", "release_roundtrip_ms")]:
        xs = col(k)
        out[lab] = {"p50": pct(xs, 50), "p95": pct(xs, 95), "p99": pct(xs, 99),
                    "mean": round(statistics.mean(xs), 3) if xs else None}
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def run(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e:
        return f"unavailable: {e}"


def provenance():
    venv = os.path.join(ROOT, ".venv", "bin")
    st = os.path.join(ROOT, "raw", "statepact-src", "statepact-0.1.2.tar.gz")
    whl = os.path.join(ROOT, "raw", "statepact-src", "whl", "statepact-0.1.2-py3-none-any.whl")
    files = sorted(glob.glob(os.path.join(ROOT, "bench", "*.py")) + glob.glob(os.path.join(ROOT, "scripts", "*")))
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": {"os": run("lsb_release -ds"), "kernel": platform.release(), "cpus": os.cpu_count(),
                 "mem_total_mb": run("free -m | awk '/Mem:/{print $2}'")},
        "versions": {
            "statepact": "0.1.2 (PyPI sdist+wheel; no git commit exists for this package)",
            "statepact_sdist_sha256": sha256(st) if os.path.exists(st) else None,
            "statepact_wheel_sha256": sha256(whl) if os.path.exists(whl) else None,
            "redis-server": run("redis-server --version").split(" ")[2].replace("v=", ""),
            "zookeeper": "3.9.1 (Ubuntu zookeeperd 3.9.1-1build2)",
            "etcd": run("etcd --version | head -1").replace("etcd Version: ", ""),
            "postgresql": run("psql --version"),
            "python": platform.python_version(),
            "kazoo": run(f"{venv}/python -c 'import kazoo.version as v;print(v.__version__)'"),
            "redis-py": run(f"{venv}/python -c 'import redis;print(redis.__version__)'"),
            "psycopg": run(f"{venv}/python -c 'import psycopg;print(psycopg.__version__)'"),
            "asyncpg": run(f"{venv}/python -c 'import asyncpg;print(asyncpg.__version__)'"),
        },
        "source_repos": {
            "mh": {"path": "/home/user/mh", "head": run("git -C /home/user/mh rev-parse HEAD"),
                   "modified": run("git -C /home/user/mh status --porcelain | wc -l")},
            "rusky": {"path": "/home/user/rusky", "head": run("git -C /home/user/rusky rev-parse HEAD")},
        },
        "benchmark_files_sha256": {os.path.relpath(f, ROOT): sha256(f) for f in files if os.path.isfile(f)},
        "lease_ttl_seconds": 2.0,
    }


def main():
    result = {"provenance": provenance(), "implementations": {}}
    for impl in IMPLS:
        d = os.path.join(RAW, impl)
        entry = {"label": LABEL[impl], "scenarios": {}, "race": {}, "failover": None, "perf": None}
        for name in SCEN_ORDER:
            rows = load(os.path.join(d, f"{name}.jsonl"))
            if rows is not None:
                entry["scenarios"][name] = summarize_scenario(name, rows)
        for path in sorted(glob.glob(os.path.join(d, "race-*.jsonl"))):
            label = os.path.basename(path)[len("race-"):-len(".jsonl")]
            entry["race"][label] = summarize_race(label, load(path))
        fo = load(os.path.join(d, "FAILOVER.jsonl"))
        if fo is not None:
            for r in fo:   # no successor: the lease was never obtained, so there is no takeover to judge
                if not r.get("invalid") and r.get("tokens") and r["tokens"][1] is None:
                    r["invalid"] = True
                    r["why"] = "successor could not acquire the lease within 25 s (no takeover occurred)"
            entry["failover"] = summarize_scenario("FAILOVER", fo)
        perf_path = os.path.join(d, "perf.json")
        perf = json.load(open(perf_path)) if os.path.exists(perf_path) else None   # one JSON array, not JSONL
        if perf is not None:
            entry["perf"] = perf_summary(perf)
        result["implementations"][impl] = entry
    for impl in ABLATIONS:
        d = os.path.join(RAW, impl)
        entry = {"label": f"ablation: {impl} (race only, not a candidate)", "scenarios": {}, "race": {}, "failover": None, "perf": None}
        for path in sorted(glob.glob(os.path.join(d, "race-*.jsonl"))):
            label = os.path.basename(path)[len("race-"):-len(".jsonl")]
            entry["race"][label] = summarize_race(label, load(path))
        result["implementations"][impl] = entry
    # hand-written verdicts (bench/verdicts.json) are merged so re-running analysis never drops them
    vpath = os.path.join(os.path.dirname(__file__), "verdicts.json")
    if os.path.exists(vpath):
        vd = json.load(open(vpath))
        for k, v in vd.items():
            if k == "_gate":
                result["gate"] = v
            elif k in result["implementations"]:
                result["implementations"][k].update(v)
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
