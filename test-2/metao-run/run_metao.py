"""Teste 2 — metaO: OCC em SQLiteMissionStore.replace() e fencing do ledger.

Usa as classes reais do metaO (importadas de D:/projetos/metaO/src, sem gravar bytecode no repositório).
Todos os bancos SQLite ficam em test-2/raw/metao/. Nada do repositório original é escrito.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import inspect
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

sys.dont_write_bytecode = True  # evita __pycache__ dentro de D:/projetos/metaO
METAO = Path("D:/projetos/metaO")
sys.path.insert(0, str(METAO / "src"))

from metao.core import ExecutionStatus  # noqa: E402
from metao.execution_handle import ActiveExecutionHandle, ExecutionHandleStatus  # noqa: E402
from metao.observability import MissionEventKind, thaw_event_value  # noqa: E402
from metao.runtime import FencingToken, StaleWorkerError, reject_stale_worker  # noqa: E402
from metao.sqlite_event_ledger import SQLiteEventLedger  # noqa: E402
from metao.sqlite_execution_handle import SQLiteExecutionHandleStore  # noqa: E402
from metao.sqlite_store import SQLiteMissionStore, _SCHEMA_VERSION, _record_to_json  # noqa: E402
from metao.mission_store import MissionRecord  # noqa: E402

# Fixture real do projeto (mesmo construtor usado pelos testes unitários do metaO).
_spec = importlib.util.spec_from_file_location(
    "t1wu04", METAO / "tests" / "unit" / "test_roadmap_1_work_unit_04.py"
)
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)
make_record = _fixture.make_record

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "raw" / "metao"
MID = "m-fence"


def git_snapshot() -> dict:
    head = subprocess.run(["git", "-C", str(METAO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(METAO), "status", "--porcelain"], capture_output=True, text=True).stdout
    return {"head": head, "status": sorted(line for line in status.splitlines() if line)}


def attempt(fn):
    """Executa uma operação e registra se foi aceita ou rejeitada (com a exceção)."""
    try:
        value = fn()
        return {"accepted": True, "value": repr(value)[:300]}
    except Exception as exc:  # noqa: BLE001 - registrar a classe exata da rejeição
        return {"accepted": False, "error": type(exc).__name__, "message": str(exc)[:300]}


def read_mission_row(db: Path) -> dict:
    with closing(sqlite3.connect(db)) as c:
        rev, raw = c.execute("SELECT revision, record_json FROM mission_records WHERE mission_id=?", (MID,)).fetchone()
    return {"revision": rev, "objective": json.loads(raw)["mission"]["objective"]}


def set_objective(record: MissionRecord, text: str) -> MissionRecord:
    return dataclasses.replace(record, mission=dataclasses.replace(record.mission, objective=text))


# ------------------------------------------------------------------------------------------------
# Teste OCC: replace() com cópia obsoleta
# ------------------------------------------------------------------------------------------------
def occ_rep(rep: int) -> dict:
    d = RAW / f"occ_rep{rep}"
    d.mkdir(parents=True, exist_ok=True)
    db = d / "metao.db"
    db.unlink(missing_ok=True)
    store = SQLiteMissionStore(db)
    store.create(make_record(MID, revision=1))                    # 1. missão na revisão 1
    copy_1 = store.get(MID)                                        # 2. duas cópias da revisão 1
    copy_2 = store.get(MID)
    first = store.replace(set_objective(copy_1, "rev2 by writer 1"))  # 3. atualização da cópia 1 -> rev 2
    after_first = read_mission_row(db)
    stale = attempt(lambda: store.replace(set_objective(copy_2, "stale writer 2")))  # 4. cópia obsoleta (base rev 1)
    final = read_mission_row(db)                                   # 5. o banco aceitou?
    stale_lost_update = final["objective"] == "stale writer 2"
    return {
        "rep": rep,
        "first_update_revision": first.revision,
        "db_after_first": after_first,
        "stale_base_revision": copy_2.revision,
        "stale_replace": stale,
        "db_final": final,
        "stale_overwrote_newer_content": stale_lost_update,
        "verdict": "FAILED_SILENT_OVERWRITE" if stale_lost_update else "REJECTED_OR_NO_OVERWRITE",
        "db_path": str(db.relative_to(HERE.parent.parent)),
    }


def strict_occ_prototype(rep: int) -> dict:
    """Valida, em banco isolado de teste, o SQL proposto: UPDATE condicionado à revisão lida, rowcount==1."""
    d = RAW / f"occ_prototype_rep{rep}"
    d.mkdir(parents=True, exist_ok=True)
    db = d / "proto.db"
    db.unlink(missing_ok=True)
    store = SQLiteMissionStore(db)
    store.create(make_record(MID, revision=1))
    c1, c2 = store.get(MID), store.get(MID)

    def strict_replace(record: MissionRecord, expected_revision: int) -> bool:
        # SQL proposto: UPDATE condicionado à revisão lida pelo chamador; sucesso somente com rowcount == 1.
        raw = _record_to_json(dataclasses.replace(record, revision=expected_revision + 1))
        with closing(sqlite3.connect(db, timeout=5.0)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "UPDATE mission_records SET status=?, revision=?, schema_version=?, record_json=? "
                "WHERE mission_id=? AND revision=?",
                (record.status.value, expected_revision + 1, _SCHEMA_VERSION, raw, MID, expected_revision),
            )
            return cur.rowcount == 1

    ok1 = strict_replace(set_objective(c1, "rev2 proto"), expected_revision=1)
    ok2 = strict_replace(set_objective(c2, "stale proto"), expected_revision=1)
    return {"rep": rep, "fresh_update_accepted": ok1, "stale_update_accepted": ok2, "db_final": read_mission_row(db)}


# ------------------------------------------------------------------------------------------------
# Teste de fencing: worker A (obsoleto) vs worker B (assume e avança), no mesmo banco metaO
# ------------------------------------------------------------------------------------------------
def plain(value):
    return json.loads(json.dumps(thaw_event_value(value), default=str))


def events_view(ledger: SQLiteEventLedger) -> list[dict]:
    return [{"seq": e.sequence, "kind": e.kind.value, "payload": plain(e.payload)} for e in ledger.list(MID)]


def fencing_rep(rep: int) -> dict:
    d = RAW / f"fencing_rep{rep}"
    d.mkdir(parents=True, exist_ok=True)
    db = d / "metao.db"
    db.unlink(missing_ok=True)
    missions = SQLiteMissionStore(db)
    ledger = SQLiteEventLedger(db)
    handles = SQLiteExecutionHandleStore(db)
    missions.create(make_record(MID, revision=1))

    # 1. Worker A adquire a propriedade (ativação da execução) — geração/token 1.
    handles.activate(ActiveExecutionHandle(MID, f"{MID}-exec-A", "runtime-a", 1, 0.0))
    ledger.append(MID, MissionEventKind.RUNTIME_STARTED, payload={"worker": "A", "execution_id": f"{MID}-exec-A", "generation": 1})
    a_copy = missions.get(MID)  # A lê o estado antes de suspender

    # 2. Worker A fica suspenso (nenhuma chamada).

    # 3. Worker B assume a propriedade (ativação da mesma missão) — geração/token 2.
    b_activate = attempt(lambda: handles.activate(ActiveExecutionHandle(MID, f"{MID}-exec-B", "runtime-b", 2, 1.0)))
    active_after_takeover = handles.get(MID).execution_id

    # 4. Worker B avança o estado: evento, revisão, conclusão da execução.
    ledger.append(MID, MissionEventKind.RUNTIME_STARTED, payload={"worker": "B", "execution_id": f"{MID}-exec-B", "generation": 2})
    b_copy = missions.get(MID)
    missions.replace(set_objective(b_copy, "advanced by B"))
    ledger.append(MID, MissionEventKind.EVIDENCE_RECORDED, payload={"worker": "B", "execution_id": f"{MID}-exec-B", "generation": 2})
    handles.complete(MID, ended_at_epoch=2.0, execution_status=ExecutionStatus.SUCCEEDED)
    seq_before_A = max((e.sequence for e in ledger.list(MID)), default=0)
    mission_before_A = read_mission_row(db)

    # 5. Worker A retorna e tenta publicar um evento com o token obsoleto (geração 1).
    a_publish = attempt(lambda: ledger.append(MID, MissionEventKind.EVIDENCE_RECORDED,
                                              payload={"worker": "A", "execution_id": f"{MID}-exec-A", "generation": 1}))
    # 5b. A tenta também gravar a missão a partir da cópia obsoleta.
    a_replace = attempt(lambda: missions.replace(set_objective(a_copy, "stale write by A")))
    # 5c. A tenta concluir/mexer na execução pelo mission_id (complete não recebe execution_id).
    a_complete = attempt(lambda: handles.complete(MID, ended_at_epoch=3.0, execution_status=ExecutionStatus.FAILED))
    # 5d. A tenta vincular execução externa por execution_id antigo.
    a_bind = attempt(lambda: handles.bind_external_execution(f"{MID}-exec-A", "ext-A"))

    # Helper de fencing existente no código (não usado pelos stores):
    helper = attempt(lambda: reject_stale_worker(FencingToken(2, "runtime-b"), FencingToken(1, "runtime-a")))

    final_events = events_view(ledger)
    a_seq = a_publish.get("value")
    return {
        "rep": rep,
        "b_takeover": b_activate,
        "active_execution_after_takeover": active_after_takeover,
        "seq_max_before_A_publish": seq_before_A,
        "mission_before_A": mission_before_A,
        "A_publish_event_with_stale_token": a_publish,
        "A_publish_used_unused_sequence": a_publish.get("accepted") is True and any(
            e["seq"] == seq_before_A + 1 and e["payload"].get("worker") == "A" for e in final_events
        ),
        "A_replace_mission_stale_copy": a_replace,
        "A_complete_handle": a_complete,
        "A_bind_external_by_stale_execution_id": a_bind,
        "helper_reject_stale_worker_direct_call": helper,
        "helper_reject_stale_worker_raises": helper.get("error") == StaleWorkerError.__name__,
        "final_mission": read_mission_row(db),
        "final_handle_status": handles.get(MID).status.value if handles.get(MID).status else None,
        "final_events": final_events,
        "sql_unique_mission_sequence": "UNIQUE(mission_id, sequence)" in inspect.getsource(SQLiteEventLedger._initialize),
        "append_signature": str(inspect.signature(SQLiteEventLedger.append)),
        "store_fenced": a_publish.get("accepted") is False,
        "db_path": str(db.relative_to(HERE.parent.parent)),
    }


def fenced_append_prototype(rep: int) -> dict:
    """Valida em banco isolado a verificação proposta: INSERT só se execution_id ativo == token apresentado."""
    d = RAW / f"fencing_prototype_rep{rep}"
    d.mkdir(parents=True, exist_ok=True)
    db = d / "proto.db"
    db.unlink(missing_ok=True)
    SQLiteMissionStore(db).create(make_record(MID, revision=1))
    handles = SQLiteExecutionHandleStore(db)
    ledger = SQLiteEventLedger(db)
    handles.activate(ActiveExecutionHandle(MID, f"{MID}-exec-A", "runtime-a", 1, 0.0))
    handles.activate(ActiveExecutionHandle(MID, f"{MID}-exec-B", "runtime-b", 2, 1.0))

    def fenced_append(expected_execution_id: str, payload: dict) -> bool:
        with closing(sqlite3.connect(db, timeout=5.0)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "INSERT INTO mission_events(event_id,mission_id,sequence,kind,occurred_at_epoch,payload_json) "
                "SELECT ?||':event:'||(COALESCE((SELECT MAX(sequence) FROM mission_events WHERE mission_id=?),0)+1), "
                "?, COALESCE((SELECT MAX(sequence) FROM mission_events WHERE mission_id=?),0)+1, ?, 0.0, ? "
                "WHERE EXISTS (SELECT 1 FROM active_mission_executions WHERE mission_id=? AND execution_id=? AND status=?)",
                (MID, MID, MID, MID, MissionEventKind.EVIDENCE_RECORDED.value,
                 json.dumps(payload), MID, expected_execution_id, ExecutionHandleStatus.ACTIVE.value),
            )
            return cur.rowcount == 1

    a_ok = fenced_append(f"{MID}-exec-A", {"worker": "A"})
    b_ok = fenced_append(f"{MID}-exec-B", {"worker": "B"})
    return {"rep": rep, "stale_A_accepted": a_ok, "current_B_accepted": b_ok,
            "events": [plain(e.payload) for e in ledger.list(MID)]}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    before = git_snapshot()
    out = {
        "metao_before": before,
        "occ": [occ_rep(r) for r in (1, 2, 3)],
        "occ_prototype_strict": [strict_occ_prototype(r) for r in (1, 2, 3)],
        "fencing": [fencing_rep(r) for r in (1, 2, 3)],
        "fencing_prototype": [fenced_append_prototype(r) for r in (1, 2, 3)],
    }
    out["metao_after"] = git_snapshot()
    out["metao_unchanged"] = before == out["metao_after"]
    (RAW / "metao-results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"occ": [r["verdict"] for r in out["occ"]],
                      "fencing_store_fenced": [r["store_fenced"] for r in out["fencing"]],
                      "metao_unchanged": out["metao_unchanged"]}, indent=2))


if __name__ == "__main__":
    main()
