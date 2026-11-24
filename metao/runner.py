"""Adapter for metaO durability primitives (copied tree: <copies>/metaO/src).

Native persistence used:
  - SQLiteEventLedger.append/list   (append-only, UNIQUE(mission_id, sequence), BEGIN IMMEDIATE)
  - SQLiteMissionStore.create/get/replace (mission record, revision column, _validated())
  - SQLiteExecutionHandleStore.activate/get/complete (active execution handle per mission)
  - supervise_project (project-level supervision; pure function over ports)

Workload mapping: one "unit" = one external effect (append line to effects log) followed by a
durable ledger event {"work_unit": n} (the native per-unit durable record). The resume position
is derived by the adapter from ledger.list() (native read API).

Modes (argv[1] = JSON):
  ledger   db, effects, invocations, out, mission, total, stopAfter?, crash?{unit,point}, handles?:bool
  append   db, mission, tag, count, out                    (concurrent appenders, D1)
  record   db, mission, out                                 (stale MissionRecord replace, D2)
  handle   db, mission, out                                 (execution-handle takeover, D3)
  inspect  db, mission, out                                 (read everything through native APIs)
  seed     db, mission, out                                 (one DB with record + 3 events + closed handle)
  supervise effects, invocations, out, crashAfterUnit?      (supervise_project with fake ports)
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

COPY_SRC = Path(os.environ.get("METAO_SRC", r"D:\projetos\durability-benchmark\copies\metaO\src"))
sys.path.insert(0, str(COPY_SRC))
sys.path.insert(0, str(COPY_SRC.parent / "tests" / "unit"))  # for make_record fixture (test adapter)

import metao  # noqa: E402
from metao.observability import MissionEventKind  # noqa: E402
from metao.sqlite_event_ledger import SQLiteEventLedger  # noqa: E402
from metao.sqlite_store import SQLiteMissionStore  # noqa: E402
from metao.sqlite_execution_handle import SQLiteExecutionHandleStore  # noqa: E402
from metao.execution_handle import ActiveExecutionHandle  # noqa: E402
from metao.core import ExecutionStatus  # noqa: E402

T0 = time.perf_counter()


def _emit(out_path: str, data: dict) -> None:
    data.setdefault("module_file", metao.__file__)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _kill() -> None:
    # Abrupt process death: no atexit, no finally, no buffered flush.
    os._exit(137)


def _effect(args: dict, n: int) -> None:
    with open(args["invocations"], "a", encoding="utf-8") as f:
        f.write(json.dumps({"unit": n, "pid": os.getpid()}) + "\n")
    with open(args["effects"], "a", encoding="utf-8") as f:
        f.write(f"unit={n} pid={os.getpid()}\n")
        f.flush()
        os.fsync(f.fileno())


def mode_ledger(args: dict) -> dict:
    ledger = SQLiteEventLedger(args["db"])
    handles = SQLiteExecutionHandleStore(args["db"]) if args.get("handles") else None
    mission = args["mission"]
    t_init = time.perf_counter()
    recovered_events = ledger.list(mission)
    done = max((e.payload.get("work_unit", 0) for e in recovered_events), default=0)
    out = {
        "units_recovered": done,
        "events_before": len(recovered_events),
        "init_ms": round((t_init - T0) * 1000),
    }
    t_work = time.perf_counter()
    completed = []
    crash = args.get("crash")
    for n in range(done + 1, args["total"] + 1):
        if args.get("stopAfter") is not None and n > args["stopAfter"]:
            break
        if handles is not None:
            handles.activate(
                ActiveExecutionHandle(
                    mission_id=mission,
                    execution_id=f"{mission}-exec-{n}",
                    orchestrator_id="worker-1",
                    attempt_number=n,
                    started_at_epoch=float(n),
                )
            )
        _effect(args, n)
        if crash and crash["unit"] == n and crash["point"] == "after_effect":
            _kill()
        ledger.append(mission, MissionEventKind.EVIDENCE_RECORDED, payload={"work_unit": n}, occurred_at_epoch=float(n))
        if handles is not None:
            handles.complete(mission, ended_at_epoch=float(n), execution_status=ExecutionStatus.SUCCEEDED)
        if crash and crash["unit"] == n and crash["point"] == "after_commit":
            _kill()
        completed.append(n)
    out["units_completed_this_run"] = completed
    out["work_ms"] = round((time.perf_counter() - t_work) * 1000)
    out["closed_normally"] = True
    out["events_after"] = len(ledger.list(mission))
    return out


def mode_append(args: dict) -> dict:
    ledger = SQLiteEventLedger(args["db"])
    seqs = []
    for i in range(args["count"]):
        ev = ledger.append(args["mission"], MissionEventKind.EVIDENCE_RECORDED, payload={"tag": args["tag"], "i": i})
        seqs.append(ev.sequence)
    return {"tag": args["tag"], "appended": len(seqs), "sequences": seqs}


def mode_record(args: dict) -> dict:
    store = SQLiteMissionStore(args["db"])
    mission = args["mission"]
    from test_roadmap_1_work_unit_04 import make_record  # type: ignore

    base = make_record(mission)
    store.create(base)
    worker_a = store.get(mission)  # revision 1
    worker_b = store.get(mission)  # revision 1
    # Worker B commits first (legitimate update, expects revision 1 -> 2).
    b_update = replace(worker_b, outcome=replace(worker_b.outcome, orchestrator_id="worker-B"))
    after_b = store.replace(b_update)
    # Worker A is stale (still based on revision 1). Does replace() reject it?
    a_update = replace(worker_a, outcome=replace(worker_a.outcome, orchestrator_id="worker-A-STALE"))
    try:
        after_a = store.replace(a_update)
        stale = {"stale_write": "accepted", "revision_after_b": after_b.revision, "revision_after_a": after_a.revision}
    except Exception as exc:  # noqa: BLE001
        stale = {"stale_write": "rejected", "error": f"{type(exc).__name__}: {exc}"}
    final = store.get(mission)
    stale["final_orchestrator_id"] = final.outcome.orchestrator_id
    stale["final_revision"] = final.revision
    return stale


def mode_handle(args: dict) -> dict:
    store = SQLiteExecutionHandleStore(args["db"])
    mission = args["mission"]
    h1 = store.activate(ActiveExecutionHandle(mission, f"{mission}-exec-1", "worker-1", 1, 1.0))
    # Worker 2 takes over the mission's active execution (no ownership/lease check in activate()).
    try:
        h2 = store.activate(ActiveExecutionHandle(mission, f"{mission}-exec-2", "worker-2", 2, 2.0))
        takeover = "accepted"
    except Exception as exc:  # noqa: BLE001
        takeover = f"rejected: {type(exc).__name__}: {exc}"
        h2 = None
    # Stale worker 1 finishes its attempt after the takeover.
    try:
        stale_complete = store.complete(mission, ended_at_epoch=3.0, execution_status=ExecutionStatus.SUCCEEDED)
        stale = "accepted"
    except Exception as exc:  # noqa: BLE001
        stale = f"rejected: {type(exc).__name__}: {exc}"
        stale_complete = None
    final = store.get(mission)
    return {
        "takeover_by_worker2": takeover,
        "stale_complete_by_worker1": stale,
        "final_execution_id": final.execution_id,
        "final_orchestrator_id": final.orchestrator_id,
        "final_status": final.status.value,
    }


def mode_seed(args: dict) -> dict:
    """Create one database holding every native table: mission record, 3 ledger events, one closed handle."""
    from test_roadmap_1_work_unit_04 import make_record  # type: ignore

    mission = args["mission"]
    store = SQLiteMissionStore(args["db"])
    ledger = SQLiteEventLedger(args["db"])
    handles = SQLiteExecutionHandleStore(args["db"])
    store.create(make_record(mission))
    for n in range(1, 4):
        ledger.append(mission, MissionEventKind.EVIDENCE_RECORDED, payload={"work_unit": n}, occurred_at_epoch=float(n))
    handles.activate(ActiveExecutionHandle(mission, f"{mission}-exec-3", "worker-1", 3, 3.0))
    handles.complete(mission, ended_at_epoch=3.0, execution_status=ExecutionStatus.SUCCEEDED)
    return {"seeded": True, "events": 3}


def mode_inspect(args: dict) -> dict:
    out: dict = {}
    try:
        events = SQLiteEventLedger(args["db"]).list(args["mission"])
        out["events"] = [e.payload.get("work_unit") for e in events]
        out["ledger_ok"] = True
    except Exception as exc:  # noqa: BLE001
        out["ledger_ok"] = False
        out["ledger_error"] = f"{type(exc).__name__}: {exc}"
    try:
        rec = SQLiteMissionStore(args["db"]).get(args["mission"])
        out["record_ok"] = True
        out["record_revision"] = rec.revision
        out["record_orchestrator_id"] = rec.outcome.orchestrator_id
    except Exception as exc:  # noqa: BLE001
        out["record_ok"] = False
        out["record_error"] = f"{type(exc).__name__}: {exc}"
    try:
        h = SQLiteExecutionHandleStore(args["db"]).get(args["mission"])
        out["handle_ok"] = True
        out["handle_status"] = h.status.value
        out["handle_execution_id"] = h.execution_id
    except Exception as exc:  # noqa: BLE001
        out["handle_ok"] = False
        out["handle_error"] = f"{type(exc).__name__}: {exc}"
    return out


def mode_supervise(args: dict) -> dict:
    from metao.project_supervision import (  # noqa: WPS433
        ExecutorTarget,
        ProjectObjective,
        RepositoryCheckpoint,
        WorkExecutionResult,
        WorkExecutionStatus,
        WorkGraph,
        WorkUnit,
        WorkVerificationResult,
        supervise_project,
    )

    units = tuple(
        WorkUnit(f"wu-{i}", f"unit {i}", dependencies=((f"wu-{i-1}",) if i > 1 else ()))
        for i in range(1, args["total"] + 1)
    )
    target = ExecutorTarget("exec-1", "prov-1")
    invocations = {"n": 0}
    crash_after = args.get("crashAfterUnit")  # kill during this unit's effect (after previous units accepted in memory)

    class Planner:
        def plan(self, objective):
            return WorkGraph("metao", units)

        def corrective_work(self, objective, failed_unit, verification, graph):
            return None

    class Scheduler:
        def select(self, unit, *, excluded_executor_ids):
            return target

    class Runner:
        def run(self, objective, unit, tgt, checkpoint):
            n = int(unit.work_unit_id.split("-")[1])
            _effect(args, n)
            if crash_after is not None and n == crash_after:
                _kill()
            return WorkExecutionResult(
                unit.work_unit_id, tgt.executor_id, tgt.provider_id, WorkExecutionStatus.SUCCEEDED,
                f"state-{n}", artifact_ref=f"art-{n}", evidence_ref=f"ev-{n}",
            )

    class Repo:
        def initial(self, objective):
            return RepositoryCheckpoint("cp-0", "repo", "state-0", "art-0")

        def capture(self, objective, unit, execution):
            n = unit.work_unit_id.split("-")[1]
            return RepositoryCheckpoint(f"cp-{n}", "repo", f"state-{n}", f"art-{n}")

        def handoff(self, checkpoint, *, from_executor_id, to_executor_id):
            return checkpoint

    class Verifier:
        def verify(self, objective, unit, execution, checkpoint):
            return WorkVerificationResult(True, "verifier-1", f"ev-{unit.work_unit_id}", "test-ok")

    obj = ProjectObjective("proj-1", "req-1", "durability sub-check")
    t = time.perf_counter()
    result = supervise_project(
        objective=obj, planner=Planner(), scheduler=Scheduler(), runner=Runner(),
        repository=Repo(), verifier=Verifier(),
    )
    return {
        "verdict": result.verdict.value,
        "graph_units": sorted(u.work_unit_id for u in result.graph.units),
        "reason": result.reason,
        "trace_len": len(result.trace),
        "supervise_ms": round((time.perf_counter() - t) * 1000),
    }


def main() -> None:
    args = json.loads(sys.argv[1])
    mode = args["mode"]
    try:
        if mode == "ledger":
            out = mode_ledger(args)
        elif mode == "append":
            out = mode_append(args)
        elif mode == "record":
            out = mode_record(args)
        elif mode == "handle":
            out = mode_handle(args)
        elif mode == "inspect":
            out = mode_inspect(args)
        elif mode == "seed":
            out = mode_seed(args)
        elif mode == "supervise":
            out = mode_supervise(args)
        else:
            raise SystemExit(f"unknown mode {mode}")
        out["mode"] = mode
        out["pid"] = os.getpid()
        out["total_ms"] = round((time.perf_counter() - T0) * 1000)
        _emit(args["out"], out)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _emit(args["out"], {"mode": mode, "error": f"{type(exc).__name__}: {exc}", "total_ms": round((time.perf_counter() - T0) * 1000)})
        raise SystemExit(2)


if __name__ == "__main__":
    main()
