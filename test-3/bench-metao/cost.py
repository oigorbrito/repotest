"""Custo por escrita (processo único, SQLite local): linha de base vs corrigida. Saída JSON em stdout."""
import dataclasses, importlib.util, inspect, json, statistics, sys, tempfile, time
from pathlib import Path
tree = Path(sys.argv[1]); N = int(sys.argv[2]) if len(sys.argv) > 2 else 500
sys.dont_write_bytecode = True
sys.path.insert(0, str(tree / "src"))
from metao.observability import MissionEventKind
from metao.execution_handle import ActiveExecutionHandle
from metao.sqlite_event_ledger import SQLiteEventLedger
from metao.sqlite_execution_handle import SQLiteExecutionHandleStore
from metao.sqlite_store import SQLiteMissionStore
spec = importlib.util.spec_from_file_location("f", tree / "tests/unit/test_roadmap_1_work_unit_04.py")
fx = importlib.util.module_from_spec(spec); spec.loader.exec_module(fx)
fenced = "fencing_token" in inspect.signature(SQLiteEventLedger.append).parameters
res = {"tree": tree.name, "fenced_api": fenced, "n": N}
times = {"append": [], "replace": []}
for rep in range(5):
    d = Path(tempfile.mkdtemp()); db = d / "m.db"
    ms = SQLiteMissionStore(db); ms.create(fx.make_record("m-1", revision=1))
    ledger = SQLiteEventLedger(db); h = SQLiteExecutionHandleStore(db)
    tok = {}
    if fenced:
        tok = {"fencing_token": h.activate(ActiveExecutionHandle("m-1", "e1", "r", 1, 0.0)).fencing_token}
    t0 = time.perf_counter()
    for i in range(N):
        ledger.append("m-1", MissionEventKind.RUNTIME_STARTED, payload={"i": i}, **tok)
    times["append"].append((time.perf_counter() - t0) / N * 1e6)
    t0 = time.perf_counter()
    for i in range(N):
        cur = ms.get("m-1")
        ms.replace(dataclasses.replace(cur, mission=dataclasses.replace(cur.mission, objective=f"o{i}")), **tok)
    times["replace"].append((time.perf_counter() - t0) / N * 1e6)
for k, v in times.items():
    res[f"{k}_us_per_op_median"] = round(statistics.median(v), 1)
    res[f"{k}_us_per_op_all"] = [round(x, 1) for x in v]
print(json.dumps(res))
