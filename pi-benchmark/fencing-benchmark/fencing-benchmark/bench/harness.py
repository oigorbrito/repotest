#!/usr/bin/env python3
"""Benchmark driver for one fencing candidate against the real services.

  harness.py --impl IMPL --phase scenarios|race|failover|perf --reps N --out DIR [--only D2,C4]

Each repetition uses a fresh resource name, so repetitions never share lease or fence state.
Writers A and B are separate OS processes (worker.py). "Suspended" means SIGSTOP on A while A holds
its lease; "resumed" means SIGCONT. Coordinator "crash" means SIGKILL of the whole service group.
Every JSON record written here is one repetition; analyze.py turns them into the metrics.
"""
import argparse, json, os, random, subprocess, sys, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import svc
from proc import Proc, TTL

EXPIRE = TTL + 0.8   # wait long enough for the lease to expire (TTL plus margin)

# commit_store: the service the commit path depends on (killed in FAIL).
# lease_store:  the service that issues tokens (restarted in REST).
TOPOLOGY = {
    "statepact-redis": {"commit_store": "redis-6400", "lease_store": "redis-6400", "failover": (6400, 6401)},
    "zk-redis-lua":    {"commit_store": "redis-6402", "lease_store": "zk",         "failover": (6402, 6403)},
    "statepact-pg":    {"commit_store": "pg",         "lease_store": "pg",         "failover": None},
    "etcd-pg":         {"commit_store": "pg2",        "lease_store": "etcd",       "failover": None},
    "etcd-pg-v1":      {"commit_store": "pg2",        "lease_store": "etcd",       "failover": None},  # ablation, race only
}
SERVICES_FOR = {
    "statepact-redis": ["redis-6400", "redis-6401"],
    "zk-redis-lua": ["redis-6402", "redis-6403", "zk"],
    "statepact-pg": ["pg"],
    "etcd-pg": ["etcd", "pg2"],
    "etcd-pg-v1": ["etcd", "pg2"],
}


def uniq(scen, rep):
    return f"{scen.lower()}-{rep}-{uuid.uuid4().hex[:8]}"


def call_retry(p, op, deadline=30, **kw):
    """Retry infrastructure errors (service down / connection reset). Semantic results are returned as-is."""
    end = time.time() + deadline
    retries = 0
    while True:
        r = p.call(op, **kw)
        if "error" not in r or time.time() > end:
            r["retries"] = retries
            return r
        retries += 1
        time.sleep(0.1)


def acquire_wait(p, res, owner, deadline=25):
    """Acquire, waiting while the lease is still held by someone else (until it expires)."""
    end = time.time() + deadline
    while True:
        r = p.call("acquire", res=res, owner=owner, ttl=TTL)
        if r.get("ok") or time.time() > end:
            return r
        time.sleep(0.1)


def setup(p, res):
    """Create the resource; retried and verified, because a silently failed setup corrupts the repetition."""
    r = call_retry(p, "setup", res=res)
    if "error" in r:
        raise RuntimeError(f"setup failed: {r['error']}")
    return r


def commit(p, res, owner, token, value, idem, fenced=True, key="v"):
    return call_retry(p, "commit", res=res, owner=owner, token=token, key=key, value=value,
                      idem=idem, fenced=fenced)


def read(p, res, key="v"):
    r = call_retry(p, "read", res=res, key=key)
    return r.get("value")


def cstatus(r):
    return r.get("status") if r.get("ok") else ("infra_error" if "error" in r else "no_lease")


def valid_acquire(r):
    return bool(r.get("ok")) and isinstance(r.get("token"), int)


class Ctx:
    def __init__(self, impl):
        self.impl = impl
        self.topo = TOPOLOGY[impl]
        self.A = Proc(impl, "A")
        self.B = Proc(impl, "B")

    def close(self):
        self.A.close(); self.B.close()


# ------------------------------------------------------------------ scenarios ----------------------
def scen_D2(c, rep, fenced_stale=True):
    """Suspended old writer: A holds the lease, is frozen, expires; B adopts and writes; A resumes and writes."""
    res = uniq("D2", rep)
    setup(c.A, res)
    ta = acquire_wait(c.A, res, "A")
    if not valid_acquire(ta):
        return {"invalid": True, "why": f"A could not acquire: {ta}"}
    c.A.suspend()
    time.sleep(EXPIRE)
    tb = acquire_wait(c.B, res, "B")
    if not valid_acquire(tb):
        c.A.resume(); return {"invalid": True, "why": f"B could not acquire: {tb}"}
    wb = commit(c.B, res, "B", tb["token"], "vB", f"{res}-B")
    c.A.resume()
    wa = commit(c.A, res, "A", ta["token"], "vA", f"{res}-A", fenced=fenced_stale)
    final = read(c.B, res)
    stale_accepted = cstatus(wa) == "ok"
    return {
        "stale_accepted": stale_accepted, "valid_rejected": cstatus(wb) != "ok",
        "monotonic_violation": tb["token"] <= ta["token"], "final_is_new_owner": final == "vB",
        "final_value": final, "tokens": [ta["token"], tb["token"]],
        "commit_A": cstatus(wa), "commit_B": cstatus(wb),
        "control_detected": stale_accepted and final == "vA",
    }


def scen_NEG(c, rep):
    """Control: the same sequence as D2 with fencing validation disabled for the stale writer."""
    r = scen_D2(c, rep, fenced_stale=False)
    if r.get("invalid"):
        return r
    return {**r, "passed_by_design": r["control_detected"]}


def scen_C4(c, rep):
    """Old process resumes after the new owner has adopted the work and released the lease."""
    res = uniq("C4", rep)
    setup(c.A, res)
    ta = acquire_wait(c.A, res, "A")
    if not valid_acquire(ta):
        return {"invalid": True, "why": f"A: {ta}"}
    c.A.suspend()
    time.sleep(EXPIRE)
    tb = acquire_wait(c.B, res, "B")
    if not valid_acquire(tb):
        c.A.resume(); return {"invalid": True, "why": f"B: {tb}"}
    w1 = commit(c.B, res, "B", tb["token"], "vB1", f"{res}-B1")
    w2 = commit(c.B, res, "B", tb["token"], "vB2", f"{res}-B2")
    rel = c.B.call("release", res=res, owner="B")
    c.A.resume()
    wa = commit(c.A, res, "A", ta["token"], "vA", f"{res}-A")
    final = read(c.B, res)
    return {
        "stale_accepted": cstatus(wa) == "ok", "valid_rejected": not (cstatus(w1) == "ok" and cstatus(w2) == "ok"),
        "monotonic_violation": tb["token"] <= ta["token"], "final_is_new_owner": final == "vB2",
        "final_value": final, "tokens": [ta["token"], tb["token"]], "commit_A": cstatus(wa),
        "release_ok": bool(rel.get("ok")),
    }


def scen_EXP_BEFORE(c, rep):
    """Old writer resumes after its lease expired, with NO successor having acquired it yet."""
    res = uniq("EXPB", rep)
    setup(c.A, res)
    ta = acquire_wait(c.A, res, "A")
    if not valid_acquire(ta):
        return {"invalid": True, "why": f"A: {ta}"}
    c.A.suspend()
    time.sleep(EXPIRE)
    c.A.resume()
    wa = commit(c.A, res, "A", ta["token"], "vA", f"{res}-A")
    return {"expired_write_accepted": cstatus(wa) == "ok", "commit_A": cstatus(wa),
            "final_value": read(c.A, res), "token": ta["token"]}


def scen_EXP_AFTER(c, rep):
    """Old writer resumes after expiry AND after a successor acquired and released the lease (no write)."""
    res = uniq("EXPA", rep)
    setup(c.A, res)
    ta = acquire_wait(c.A, res, "A")
    if not valid_acquire(ta):
        return {"invalid": True, "why": f"A: {ta}"}
    c.A.suspend()
    time.sleep(EXPIRE)
    tb = acquire_wait(c.B, res, "B")
    if not valid_acquire(tb):
        c.A.resume(); return {"invalid": True, "why": f"B: {tb}"}
    c.B.call("release", res=res, owner="B")
    c.A.resume()
    wa = commit(c.A, res, "A", ta["token"], "vA", f"{res}-A")
    return {"stale_accepted": cstatus(wa) == "ok", "monotonic_violation": tb["token"] <= ta["token"],
            "commit_A": cstatus(wa), "final_value": read(c.B, res), "tokens": [ta["token"], tb["token"]]}


def scen_CONC(c, rep):
    """Concurrent acquisition and commit: A (expired lease) commits while B acquires, in separate processes."""
    res = uniq("CONC", rep)
    setup(c.A, res)
    ta = acquire_wait(c.A, res, "A")
    if not valid_acquire(ta):
        return {"invalid": True, "why": f"A: {ta}"}
    c.A.suspend()
    time.sleep(EXPIRE)
    c.A.resume()
    c.A.send("commit", res=res, owner="A", token=ta["token"], key="v", value="vA", idem=f"{res}-A", fenced=True)
    time.sleep(random.uniform(0, 0.003))
    tb = acquire_wait(c.B, res, "B")
    wb = commit(c.B, res, "B", tb["token"], "vB", f"{res}-B") if valid_acquire(tb) else {"ok": False}
    wa = c.A.recv()
    final = read(c.B, res)
    return {"stale_final": final == "vA", "final_value": final, "commit_A": cstatus(wa),
            "b_acquired": valid_acquire(tb), "commit_B": cstatus(wb),
            "monotonic_violation": valid_acquire(tb) and tb["token"] <= ta["token"],
            "valid_rejected": valid_acquire(tb) and cstatus(wb) != "ok",
            "tokens": [ta["token"], tb.get("token")]}


def scen_REST(c, rep):
    """Restart the token/lease coordinator (and commit store) with crash semantics; tokens must stay monotonic."""
    res = uniq("REST", rep)
    setup(c.A, res)
    ta = acquire_wait(c.A, res, "A")
    if not valid_acquire(ta):
        return {"invalid": True, "why": f"A: {ta}"}
    w1 = commit(c.A, res, "A", ta["token"], "v1", f"{res}-A")
    c.A.call("release", res=res, owner="A")
    stores = [c.topo["lease_store"]] + ([c.topo["commit_store"]] if c.topo["commit_store"] != c.topo["lease_store"] else [])
    t_kill = time.time()
    for s in stores:
        svc.kill(s)
    for s in stores:
        svc.start(s)
    t_up = time.time()
    value_after = read(c.B, res)
    t_first_op = time.time()
    tb = acquire_wait(c.B, res, "B")
    w2 = commit(c.B, res, "B", tb["token"], "v2", f"{res}-B") if valid_acquire(tb) else {"ok": False}
    return {"monotonic_violation": (not valid_acquire(tb)) or tb["token"] <= ta["token"],
            "value_lost": value_after != "v1", "value_after_restart": value_after,
            "valid_rejected": cstatus(w2) != "ok", "commit_before": cstatus(w1), "commit_after": cstatus(w2),
            "tokens": [ta["token"], tb.get("token")], "restart_ms": round((t_up - t_kill) * 1000, 1),
            "first_read_after_restart_ms": round((t_first_op - t_kill) * 1000, 1)}


def scen_FAIL(c, rep):
    """Crash the commit store while A's commit is in flight; the client retries with the SAME idempotency key."""
    res = uniq("FAIL", rep)
    setup(c.A, res)
    ta = acquire_wait(c.A, res, "A")
    if not valid_acquire(ta):
        return {"invalid": True, "why": f"A: {ta}"}
    before = call_retry(c.A, "version", res=res).get("version")
    idem = f"{res}-A"
    c.A.send("commit", res=res, owner="A", token=ta["token"], key="v", value="vA", idem=idem, fenced=True)
    time.sleep(random.uniform(0, 0.004))
    t_kill = time.time()
    svc.kill(c.topo["commit_store"])
    first = c.A.recv()
    svc.start(c.topo["commit_store"])
    t_up = time.time()
    probe = call_retry(c.A, "read", res=res, key="v")
    downtime_ms = round((time.time() - t_kill) * 1000, 1)
    retry = commit(c.A, res, "A", ta["token"], "vA", idem, fenced=True)
    after = call_retry(c.A, "version", res=res).get("version")
    applied = (after - before) if isinstance(after, int) and isinstance(before, int) else None
    final = read(c.A, res)
    return {"duplicate_effect": applied is not None and applied > 1, "applied_effects": applied,
            "lost_write": final != "vA", "final_value": final, "first_attempt": cstatus(first),
            "retry_commit": cstatus(retry), "retry_replayed": bool(retry.get("replayed")),
            "downtime_ms": downtime_ms, "restart_ms": round((t_up - t_kill) * 1000, 1),
            "probe_ok": "value" in probe, "tokens": [ta["token"]]}


def _info(port, section="replication"):
    out = subprocess.run(["redis-cli", "-p", str(port), "info", section],
                         capture_output=True, text=True, timeout=5).stdout
    return dict(l.split(":", 1) for l in out.splitlines() if ":" in l and not l.startswith("#"))


def wait_replica_caught_up(master, replica, timeout=20):
    """Block until the replica's link is up and it has applied everything the master has sent so far.
    Without this, a just-restarted replica (full resync in progress) is promoted empty, which measures a
    harness artifact instead of asynchronous-replication loss."""
    end = time.time() + timeout
    while time.time() < end:
        m, r = _info(master), _info(replica)
        if (r.get("role") == "slave" and r.get("master_link_status") == "up"
                and int(r.get("slave_repl_offset", 0)) >= int(m.get("master_repl_offset", 0))):
            return True
        time.sleep(0.05)
    raise RuntimeError(f"replica {replica} did not catch up with master {master}")


def scen_FAILOVER(c, rep):
    """Redis-only: master crashes right after the lease is issued (async replication may lag); replica promoted."""
    master, replica = c.topo["failover"]
    wait_replica_caught_up(master, replica)              # replica fully synced before this repetition
    res = uniq("FOVR", rep)
    setup(c.A, res)
    wait_replica_caught_up(master, replica)              # resource metadata has reached the replica
    ta = acquire_wait(c.A, res, "A")                     # from here on, only the lease/fence writes can be lost
    if not valid_acquire(ta):
        return {"invalid": True, "why": f"A: {ta}"}
    c.A.suspend()
    svc.kill(f"redis-{master}")
    subprocess.run(["redis-cli", "-p", str(replica), "replicaof", "no", "one"], capture_output=True)
    c.B.call("switch", port=replica)
    time.sleep(EXPIRE)
    tb = acquire_wait(c.B, res, "B")
    wb = commit(c.B, res, "B", tb["token"], "vB", f"{res}-B") if valid_acquire(tb) else {"ok": False}
    c.A.resume()
    c.A.call("switch", port=replica)
    wa = commit(c.A, res, "A", ta["token"], "vA", f"{res}-A")
    final = read(c.B, res)
    result = {"token_regression": valid_acquire(tb) and tb["token"] <= ta["token"],
              "stale_accepted": cstatus(wa) == "ok", "valid_rejected": cstatus(wb) != "ok",
              "final_is_new_owner": final == "vB", "final_value": final, "tokens": [ta["token"], tb.get("token")],
              "commit_A": cstatus(wa), "commit_B": cstatus(wb)}
    # restore the original topology, then point both writers back at the master for the next repetition
    svc.kill(f"redis-{replica}")
    svc.start(f"redis-{master}")
    svc.start(f"redis-{replica}")
    c.A.call("switch", port=master)
    c.B.call("switch", port=master)
    return result


SCENARIOS = {"D2": scen_D2, "C4": scen_C4, "EXP_BEFORE": scen_EXP_BEFORE, "EXP_AFTER": scen_EXP_AFTER,
             "CONC": scen_CONC, "REST": scen_REST, "FAIL": scen_FAIL, "NEG": scen_NEG}


# ------------------------------------------------------------------ race (deterministic) ----------
def _pg_wait_blocked(dsn, needle, timeout=5):
    import psycopg
    end = time.time() + timeout
    with psycopg.connect(dsn, autocommit=True) as q:
        while time.time() < end:
            n = q.execute("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' "
                          "AND query LIKE %s", (f"%{needle}%",)).fetchone()[0]
            if n:
                return True
            time.sleep(0.02)
    return False


def _race_pg_statepact(c, rep, path):
    """A's commit is held inside _commit_locked (its value write blocks on a row lock). B then acquires.
    path='direct'  : backend.acquire_lease() called directly (what the protocol names)
    path='manager' : TransactionManager.lease() (public API, runs ensure_resource first)"""
    import psycopg
    dsn = "postgresql://postgres@127.0.0.1:5433/statepg"
    res = uniq("RACEPG", rep)
    setup(c.A, res)
    ta = acquire_wait(c.A, res, "A")
    commit(c.A, res, "A", ta["token"], "v0", f"{res}-0")
    time.sleep(EXPIRE)                                              # A's lease has expired
    h = psycopg.connect(dsn, autocommit=False)
    h.execute("SELECT 1 FROM statepact_values WHERE resource=%s AND key=%s FOR UPDATE", (res, "v"))
    c.A.send("commit", res=res, owner="A", token=ta["token"], key="v", value="vA", idem=f"{res}-A", fenced=True)
    blocked = _pg_wait_blocked(dsn, "statepact_values")
    c.B.send("lock1_direct" if path == "direct" else "acquire", res=res, owner="B", ttl=TTL)
    b_done_while_a_blocked = c.B.poll(timeout=2.0)                 # did B's grant finish while A is mid-commit?
    b_reply = c.B.recv() if b_done_while_a_blocked else None
    h.commit(); h.close()
    wa = c.A.recv()
    if b_reply is None:
        b_reply = c.B.recv()
    b_granted_first = b_done_while_a_blocked and bool(b_reply.get("ok"))
    return {"path": path, "a_blocked_in_commit": blocked, "b_grant_completed_while_a_in_commit": b_granted_first,
            "b_blocked_behind_a": not b_done_while_a_blocked,
            "stale_accepted_after_successor_granted": b_granted_first and cstatus(wa) == "ok",
            "commit_A": cstatus(wa), "tokens": [ta["token"], b_reply.get("token")]}


def race_statepact_pg_direct(c, rep):
    return _race_pg_statepact(c, rep, "direct")


def race_statepact_pg_manager(c, rep):
    return _race_pg_statepact(c, rep, "manager")


def race_etcd_pg(c, rep):
    """A's commit holds the fence row lock and is blocked on its value write. B's acquisition (etcd grant +
    fence registration, one transaction) must not complete until A's transaction ends."""
    import psycopg
    dsn = "postgresql://postgres@127.0.0.1:5434/etcdpg"
    res = uniq("RACEEP", rep)
    setup(c.A, res)
    ta = acquire_wait(c.A, res, "A")
    commit(c.A, res, "A", ta["token"], "v0", f"{res}-0")
    time.sleep(EXPIRE)
    h = psycopg.connect(dsn, autocommit=False)
    h.execute("SELECT 1 FROM fb_kv WHERE res=%s AND key=%s FOR UPDATE", (res, "v"))
    c.A.send("commit", res=res, owner="A", token=ta["token"], key="v", value="vA", idem=f"{res}-A", fenced=True)
    blocked = _pg_wait_blocked(dsn, "fb_kv")
    c.B.send("acquire", res=res, owner="B", ttl=TTL)
    b_done_while_a_blocked = c.B.poll(timeout=2.0)
    b_reply = c.B.recv() if b_done_while_a_blocked else None
    h.commit(); h.close()
    wa = c.A.recv()
    if b_reply is None:
        b_reply = c.B.recv()
    granted_first = b_done_while_a_blocked and bool(b_reply.get("ok"))
    return {"a_blocked_in_commit": blocked, "b_grant_completed_while_a_in_commit": granted_first,
            "b_blocked_behind_a": not b_done_while_a_blocked,
            "stale_accepted_after_successor_granted": granted_first and cstatus(wa) == "ok",
            "commit_A": cstatus(wa), "tokens": [ta["token"], b_reply.get("token")]}


def race_etcd_pg_v1(c, rep):
    """ABLATION (v1, grant outside the fence lock): B's etcd grant completes while A is still in its commit,
    so A is accepted after the successor's grant is committed in etcd."""
    import psycopg
    dsn = "postgresql://postgres@127.0.0.1:5434/etcdpg"
    res = uniq("RACEV1", rep)
    setup(c.A, res)
    ta = acquire_wait(c.A, res, "A")
    commit(c.A, res, "A", ta["token"], "v0", f"{res}-0")
    time.sleep(EXPIRE)
    h = psycopg.connect(dsn, autocommit=False)
    h.execute("SELECT 1 FROM fb_kv WHERE res=%s AND key=%s FOR UPDATE", (res, "v"))
    c.A.send("commit", res=res, owner="A", token=ta["token"], key="v", value="vA", idem=f"{res}-A", fenced=True)
    blocked = _pg_wait_blocked(dsn, "fb_kv")
    s1 = c.B.call("lock1", res=res, owner="B", ttl=TTL)
    granted_while_a = bool(s1.get("ok"))
    c.B.send("lock2", res=res, owner="B", token=s1.get("token", 0))
    time.sleep(0.5)
    h.commit(); h.close()
    wa = c.A.recv()
    s2 = c.B.recv()
    return {"a_blocked_in_commit": blocked, "b_granted_before_a_commit": granted_while_a,
            "stale_accepted_in_window": granted_while_a and cstatus(wa) == "ok",
            "b_register_ok": bool(s2.get("ok")), "commit_A": cstatus(wa), "tokens": [ta["token"], s1.get("token")]}


def race_window(c, rep):
    """zk-redis-lua: B's lock is granted in ZooKeeper but NOT yet registered in Redis when A commits.
    A is frozen until its ZooKeeper session expires (as in D2), so B can take the lock."""
    res = uniq("WIN", rep)
    setup(c.A, res)
    ta = acquire_wait(c.A, res, "A")
    commit(c.A, res, "A", ta["token"], "v0", f"{res}-0")
    c.A.suspend()
    time.sleep(EXPIRE)
    s1 = c.B.call("lock1", res=res, owner="B", ttl=TTL)             # ZooKeeper grant, Redis fence not yet raised
    c.A.resume()
    wa = commit(c.A, res, "A", ta["token"], "vA", f"{res}-A")
    s2 = c.B.call("lock2", res=res, owner="B", token=s1.get("token", 0)) if s1.get("ok") else {"ok": False}
    return {"b_granted_before_a_commit": bool(s1.get("ok")), "commit_A": cstatus(wa),
            "stale_accepted_in_window": bool(s1.get("ok")) and cstatus(wa) == "ok",
            "b_register_ok": bool(s2.get("ok")), "tokens": [ta["token"], s1.get("token")]}


def race_redis_atomic(c, rep):
    """Redis atomicity: the lease grant and the fence write happen in one EVAL, so no window can be staged.
    Recorded as a structural check; the empirical check is the CONC scenario."""
    return {"note": "single EVAL: no interleaving point between grant and fence registration", "structural": True}


# ------------------------------------------------------------------ perf ----------------------------
def perf(c, n):
    res = uniq("PERF", "x")
    setup(c.A, res)
    rows = []
    for i in range(n):
        t0 = time.perf_counter()
        a = acquire_wait(c.A, res, "P", deadline=10)
        t1 = time.perf_counter()
        if not valid_acquire(a):
            rows.append({"i": i, "error": a}); continue
        m = commit(c.A, res, "P", a["token"], i, f"{res}-{i}", fenced=True, key="k")
        t2 = time.perf_counter()
        c.A.call("release", res=res, owner="P")
        t3 = time.perf_counter()
        rows.append({"i": i, "acquire_ms": a.get("ms"), "commit_ms": m.get("ms"),
                     "rt_acquire_ms": (t1 - t0) * 1000, "rt_commit_ms": (t2 - t1) * 1000,
                     "rt_release_ms": (t3 - t2) * 1000, "commit_status": cstatus(m)})
    return rows


# ------------------------------------------------------------------ main ---------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True, choices=list(TOPOLOGY))
    ap.add_argument("--phase", required=True, choices=["scenarios", "race", "failover", "perf"])
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--perf-ops", type=int, default=1000)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    random.seed(1)
    out = os.path.join(args.out, args.impl)
    os.makedirs(out, exist_ok=True)
    c = Ctx(args.impl)
    try:
        if args.phase == "scenarios":
            names = [n for n in SCENARIOS if not args.only or n in args.only.split(",")]
            for name in names:
                path = os.path.join(out, f"{name}.jsonl")
                with open(path, "w") as f:
                    for rep in range(args.reps):
                        t0 = time.time()
                        try:
                            rec = SCENARIOS[name](c, rep)
                        except Exception as e:  # keep going: an aborted repetition is recorded, not hidden
                            rec = {"invalid": True, "why": f"exception {type(e).__name__}: {e}"}
                        rec.update({"scenario": name, "rep": rep, "elapsed_s": round(time.time() - t0, 2)})
                        f.write(json.dumps(rec) + "\n"); f.flush()
                        if rec.get("invalid"):
                            print(f"[{args.impl}] {name} rep {rep} INVALID: {rec.get('why')}", flush=True)
                        # re-create worker processes after an aborted repetition so state cannot leak forward
                        if rec.get("invalid") and "exception" in rec.get("why", ""):
                            c.close(); c = Ctx(args.impl)
                print(f"[{args.impl}] {name} done", flush=True)
        elif args.phase == "race":
            if args.impl == "statepact-redis":
                fn_list = [("ATOMIC", race_redis_atomic)]
            elif args.impl == "etcd-pg":
                fn_list = [("PG_LOCK", race_etcd_pg)]
            elif args.impl == "etcd-pg-v1":
                fn_list = [("PG_LOCK_V1_ABLATION", race_etcd_pg_v1)]
            elif args.impl == "statepact-pg":
                fn_list = [("DIRECT", race_statepact_pg_direct), ("MANAGER", race_statepact_pg_manager)]
            else:
                fn_list = [("WINDOW", race_window)]
            for label, f_ in fn_list:
                with open(os.path.join(out, f"race-{label}.jsonl"), "w") as fh:
                    for rep in range(args.reps):
                        try:
                            rec = f_(c, rep)
                        except Exception as e:
                            rec = {"invalid": True, "why": f"exception {type(e).__name__}: {e}"}
                            c.close(); c = Ctx(args.impl)
                        rec.update({"scenario": f"RACE-{label}", "rep": rep})
                        fh.write(json.dumps(rec) + "\n")
                print(f"[{args.impl}] race {label} done", flush=True)
        elif args.phase == "failover":
            if not c.topo["failover"]:
                print(f"[{args.impl}] no failover topology: NOT TESTED", flush=True); return
            with open(os.path.join(out, "FAILOVER.jsonl"), "w") as f:
                for rep in range(args.reps):
                    try:
                        rec = scen_FAILOVER(c, rep)
                    except Exception as e:
                        rec = {"invalid": True, "why": f"exception {type(e).__name__}: {e}"}
                        c.close(); c = Ctx(args.impl)
                    rec.update({"scenario": "FAILOVER", "rep": rep})
                    f.write(json.dumps(rec) + "\n"); f.flush()
            print(f"[{args.impl}] failover done", flush=True)
        elif args.phase == "perf":
            rows = perf(c, args.perf_ops)
            with open(os.path.join(out, "perf.json"), "w") as f:
                json.dump(rows, f)
            print(f"[{args.impl}] perf done ({len(rows)} cycles)", flush=True)
    finally:
        c.close()


if __name__ == "__main__":
    main()
