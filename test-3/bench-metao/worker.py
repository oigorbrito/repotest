"""Teste 3 — worker de processo único para o benchmark do metaO.

Cada papel roda em um processo separado. A árvore do metaO é escolhida por --tree (src/ dela entra no sys.path),
então o mesmo worker testa a linha de base e a versão corrigida. Saída: uma linha JSON em --out.
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import inspect
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--tree", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--id", default="w")
    p.add_argument("--out", required=True)
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--m", type=int, default=10)
    p.add_argument("--token", type=int, default=None)
    p.add_argument("--exec-id", default=None)
    p.add_argument("--duration", type=float, default=0.5)
    p.add_argument("--barrier", default=None)
    p.add_argument("--release", default=None)
    p.add_argument("--ready", default=None)
    p.add_argument("--window", default=None)
    p.add_argument("--op", default=None)
    return p.parse_args()


ARGS = parse()
TREE = Path(ARGS.tree)
sys.path.insert(0, str(TREE / "src"))

from metao.core import ExecutionStatus  # noqa: E402
from metao.execution_handle import ActiveExecutionHandle  # noqa: E402
from metao.observability import MissionEventKind  # noqa: E402
from metao.sqlite_event_ledger import SQLiteEventLedger  # noqa: E402
from metao.sqlite_execution_handle import SQLiteExecutionHandleStore  # noqa: E402
from metao.sqlite_store import SQLiteMissionStore  # noqa: E402
import metao.mission_store as mission_store  # noqa: E402

FENCED = "fencing_token" in inspect.signature(SQLiteExecutionHandleStore.complete).parameters
OCC = hasattr(mission_store, "MissionRevisionConflict")
MID = "m-1"

_spec = importlib.util.spec_from_file_location("t1wu04", TREE / "tests" / "unit" / "test_roadmap_1_work_unit_04.py")
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)
make_record = _fixture.make_record


def kw(token):
    """Token keyword for the tree under test. The baseline has no token parameter, so nothing is passed there."""
    return {"fencing_token": token} if FENCED else {}


def with_objective(record, text):
    return dataclasses.replace(record, mission=dataclasses.replace(record.mission, objective=text))


def err(exc: Exception) -> str:
    return type(exc).__name__


def wait_for(path: str, timeout: float = 60.0) -> None:
    end = time.time() + timeout
    while not os.path.exists(path):
        if time.time() > end:
            raise TimeoutError(path)
        time.sleep(0.002)


def arm_crash(window: str) -> None:
    """Crash inside the write transaction, before the statement named by the window runs.

    The trace callback fires before each statement. Exiting there leaves the transaction open and uncommitted, so
    SQLite rolls it back on the next open. os._exit skips every cleanup path, as a power cut would.
    """
    markers = {
        "tx:append": "INSERT INTO mission_events",
        "tx:replace": "UPDATE mission_records",
        "tx:complete": "SET status='COMPLETED'",  # trace gives expanded SQL, so bound values appear
        "tx:activate": "INSERT INTO active_mission_executions",
        "tx:bind": "SET external_execution_id",
    }
    marker = markers[window]
    real = sqlite3.connect

    def connect(*a, **k):
        conn = real(*a, **k)
        conn.set_trace_callback(lambda sql: os._exit(137) if marker in sql else None)
        return conn

    sqlite3.connect = connect  # type: ignore[assignment]


def snapshot(db: str) -> dict:
    conn = real_connect_plain(db)
    try:
        mrow = conn.execute("SELECT revision, record_json FROM mission_records WHERE mission_id=?", (MID,)).fetchone()
        events = conn.execute("SELECT sequence, payload_json FROM mission_events WHERE mission_id=? ORDER BY sequence", (MID,)).fetchall() if _has_table(conn, "mission_events") else []
        cols = "execution_id, status, execution_status" + (", fencing_token" if _has_column(conn, "active_mission_executions", "fencing_token") else "")
        handle = conn.execute(f"SELECT {cols} FROM active_mission_executions WHERE mission_id=?", (MID,)).fetchall() if _has_table(conn, "active_mission_executions") else []
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        objective = json.loads(mrow[1])["mission"]["objective"] if mrow else None
        return {
            "revision": mrow[0] if mrow else None,
            "objective": objective,
            "events": [[s, json.loads(p).get("by") or json.loads(p).get("w")] for s, p in events],
            "handle": [list(h) for h in handle],
            "integrity": integrity,
        }
    finally:
        conn.close()


real_connect_plain = sqlite3.connect


def _has_column(conn, table, column):
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def main() -> None:
    result: dict = {"role": ARGS.role, "id": ARGS.id, "fenced_tree": FENCED, "occ_tree": OCC}
    db = ARGS.db
    if ARGS.window and ARGS.window.startswith("tx:"):
        arm_crash(ARGS.window)
    if ARGS.barrier and ARGS.role in {"occ", "append", "tx_op"}:
        wait_for(ARGS.barrier)  # start together, so the writes really overlap

    if ARGS.role == "setup":
        SQLiteMissionStore(db).create(make_record(MID, revision=1))
        SQLiteEventLedger(db)
        SQLiteExecutionHandleStore(db)
        if ARGS.exec_id:
            h = SQLiteExecutionHandleStore(db).activate(ActiveExecutionHandle(MID, ARGS.exec_id, "runtime-setup", 1, 0.0))
            result["token"] = getattr(h, "fencing_token", None)

    elif ARGS.role == "occ":
        store = SQLiteMissionStore(db)
        ok = conflicts = 0
        markers: list[str] = []
        for i in range(ARGS.n):
            marker = f"{ARGS.id}-{i}"
            while True:
                current = store.get(MID)
                try:
                    store.replace(with_objective(current, current.mission.objective + f";{marker}"))
                    ok += 1
                    markers.append(marker)
                    break
                except Exception as exc:  # noqa: BLE001
                    if err(exc) == "MissionRevisionConflict":
                        conflicts += 1
                        continue
                    raise
        result.update(successes=ok, conflicts=conflicts, markers=markers)

    elif ARGS.role == "append":
        ledger = SQLiteEventLedger(db)
        seqs, errors = [], []
        for i in range(ARGS.m):
            try:
                ev = ledger.append(MID, MissionEventKind.RUNTIME_STARTED, payload={"w": ARGS.id, "i": i}, **kw(ARGS.token))
                seqs.append(ev.sequence)
            except Exception as exc:  # noqa: BLE001
                errors.append(err(exc))
        result.update(sequences=seqs, errors=errors)

    elif ARGS.role == "activate":
        if ARGS.barrier:
            wait_for(ARGS.barrier)
        h = SQLiteExecutionHandleStore(db).activate(ActiveExecutionHandle(MID, ARGS.exec_id, f"runtime-{ARGS.id}", 2, time.time()))
        result.update(token=getattr(h, "fencing_token", None), exec_id=ARGS.exec_id)

    elif ARGS.role == "complete_loop":
        handles = SQLiteExecutionHandleStore(db)
        accepted, rejected, stale_violations, returned = [], 0, 0, []
        end = time.time() + ARGS.duration
        if ARGS.barrier:
            wait_for(ARGS.barrier)
        while time.time() < end:
            try:
                h = handles.complete(MID, ended_at_epoch=time.time(), execution_status=ExecutionStatus.SUCCEEDED, **kw(ARGS.token))
                accepted.append(h.execution_id)
                returned.append([h.execution_id, h.status.value, h.execution_status.value if h.execution_status else None])
                # A write from this worker landed on another execution: the row now reads COMPLETED/SUCCEEDED for a
                # different execution id. A post-commit read that merely shows another id is not counted.
                if h.execution_id != ARGS.exec_id and h.status.value == "COMPLETED" and h.execution_status is not None and h.execution_status.value == "SUCCEEDED":
                    stale_violations += 1
            except Exception as exc:  # noqa: BLE001
                rejected += 1
                result.setdefault("errors", {})
                result["errors"][err(exc)] = result["errors"].get(err(exc), 0) + 1
            time.sleep(0.001)
        result.update(accepted=len(accepted), rejected=rejected, stale_completions_of_other_execution=stale_violations, returned=returned)

    elif ARGS.role == "suspended_a":
        # Reads its own copy first, announces readiness, then stays suspended until released.
        missions = SQLiteMissionStore(db)
        handles = SQLiteExecutionHandleStore(db)
        ledger = SQLiteEventLedger(db)
        h = handles.activate(ActiveExecutionHandle(MID, ARGS.exec_id, "runtime-a", 1, time.time()))
        token = getattr(h, "fencing_token", None)
        stale_copy = missions.get(MID)
        open(ARGS.ready, "w").close()
        wait_for(ARGS.release)
        attempts = {}
        for name, call in {
            "append": lambda: ledger.append(MID, MissionEventKind.EVIDENCE_RECORDED, payload={"by": "A"}, **kw(token)),
            "replace": lambda: missions.replace(with_objective(stale_copy, "by A"), **kw(token)),
            "complete": lambda: handles.complete(MID, ended_at_epoch=time.time() + 1, execution_status=ExecutionStatus.FAILED, **kw(token)),
            "bind": lambda: handles.bind_external_execution(ARGS.exec_id, "ext-A", **kw(token)),
        }.items():
            try:
                call()
                attempts[name] = "ACCEPTED"
            except Exception as exc:  # noqa: BLE001
                attempts[name] = f"REJECTED:{err(exc)}"
        result.update(token=token, attempts=attempts)

    elif ARGS.role == "takeover_b":
        missions = SQLiteMissionStore(db)
        handles = SQLiteExecutionHandleStore(db)
        ledger = SQLiteEventLedger(db)
        h = handles.activate(ActiveExecutionHandle(MID, ARGS.exec_id, "runtime-b", 2, time.time()))
        token = getattr(h, "fencing_token", None)
        ledger.append(MID, MissionEventKind.RUNTIME_STARTED, payload={"by": "B"}, **kw(token))
        cur = missions.get(MID)
        missions.replace(with_objective(cur, "by B"), **kw(token))
        ledger.append(MID, MissionEventKind.EVIDENCE_RECORDED, payload={"by": "B"}, **kw(token))
        result.update(token=token)

    elif ARGS.role == "tx_op":
        # One guarded write, used for crash windows. Exceptions are recorded, not raised.
        op = ARGS.op
        try:
            if op == "append":
                SQLiteEventLedger(db).append(MID, MissionEventKind.RUNTIME_STARTED, payload={"by": ARGS.id}, **kw(ARGS.token))
            elif op == "replace":
                s = SQLiteMissionStore(db)
                s.replace(with_objective(s.get(MID), f"by {ARGS.id}"), **kw(ARGS.token))
            elif op == "complete":
                SQLiteExecutionHandleStore(db).complete(MID, ended_at_epoch=time.time() + 1, execution_status=ExecutionStatus.SUCCEEDED, **kw(ARGS.token))
            elif op == "activate":
                SQLiteExecutionHandleStore(db).activate(ActiveExecutionHandle(MID, ARGS.exec_id, "runtime-x", 3, 3.0))
            elif op == "bind":
                SQLiteExecutionHandleStore(db).bind_external_execution(ARGS.exec_id, "ext-x", **kw(ARGS.token))
            result["outcome"] = "ACCEPTED"
        except Exception as exc:  # noqa: BLE001
            result["outcome"] = f"REJECTED:{err(exc)}"

    elif ARGS.role == "snapshot":
        result["state"] = snapshot(db)

    else:
        raise SystemExit(f"unknown role {ARGS.role}")

    if ARGS.role not in {"snapshot"}:
        result["state"] = snapshot(db)
    Path(ARGS.out).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if ARGS.window and ARGS.window.startswith("after:"):
        os._exit(137)  # crash after the write has returned (and committed)


if __name__ == "__main__":
    main()
