"""Consolida os brutos do Teste 2 em test-2/results.json (sem reexecutar experimentos)."""
import json
from pathlib import Path

T2 = Path(__file__).resolve().parent
fc = json.loads((T2 / "raw/finecode/finecode-results.json").read_text(encoding="utf-8"))
mo = json.loads((T2 / "raw/metao/metao-results.json").read_text(encoding="utf-8"))


def fc_scenario(key: str, na_effects: bool = False) -> dict:
    s = fc["scenarios"][key]
    reps = []
    for r in s["reps"]:
        reps.append({
            "rep": r["rep"],
            "effects_executed": r["effects_executed"],
            "effects_duplicated": r["effects_duplicated"],
            "effects_lost": "N/A" if na_effects else r["effects_lost"],
            "memo_values_recovered": r["memo_values_recovered"],
            "phase_starts_after_restart": r["phase_starts_recovery"],
            "crash_points_reached": r["crash_events"],
            "exit_codes": {k: v["code"] for k, v in r["run_exit"].items()},
            "task_results": [{"kind": x["kind"], "outcome": x.get("outcome"), "error": x.get("error")} for x in r["results"]],
        })
    return {"description": s["desc"], "mode": s["mode"], "pattern": s["pattern"], "crash": s["crash"],
            "widen_ms": s["widen"], "reps": reps}


def ok(rows, key):
    return [row[key] for row in rows]


occ = mo["occ"]
fen = mo["fencing"]

results = {
    "test": "Teste Comparativo 2 — idempotência e fencing real",
    "generated_by": "test-2/consolidate.py (a partir de raw/)",
    "origins": {
        "finecode": {"path": "D:/projetos/FineCode", "commit_before": fc["finecode_before"]["head"],
                     "commit_after": fc["finecode_after"]["head"], "unchanged": fc["finecode_unchanged"],
                     "git_status_before": fc["finecode_before"]["status"], "git_status_after": fc["finecode_after"]["status"]},
        "metao": {"path": "D:/projetos/metaO", "commit_before": mo["metao_before"]["head"],
                  "commit_after": mo["metao_after"]["head"], "unchanged": mo["metao_unchanged"],
                  "git_status_before": mo["metao_before"]["status"], "git_status_after": mo["metao_after"]["status"]},
    },
    "mechanisms": {
        "finecode.runtime.memo": {
            "classification": "PARCIAL",
            "files": ["packages/durable/src/harness/scheduler.ts (memo 2014–2029, #gated 2188, open 352–390)",
                      "packages/durable/src/storage/sqlite/storage.ts (commit 187, task upsert 818–830, task read 427)",
                      "packages/chord/src/sqlite/node.ts (transaction BEGIN IMMEDIATE 139–158, WAL 189)"],
            "guarantee_obtained": {
                "intra_process_first_writer_wins": "COMPROVADO (D)",
                "persistence_before_restart": "COMPROVADO (A, B2, C, D)",
                "exactly_once_effect": "NÃO OBTIDO",
                "at_most_once": "obtida com padrão intent (A: efeito perdido 3/3)",
                "at_least_once": "obtida com padrão effect-first (B: duplicado 3/3)",
                "cross_instance_uniqueness": "FALHOU (E-intent, E-intent-widened, E-effect: duplicados 3/3 em cada)",
            },
            "scenarios": {
                "A": fc_scenario("A"), "B": fc_scenario("B"), "B2": fc_scenario("B2"), "C": fc_scenario("C"),
                "D": fc_scenario("D", na_effects=True),
                "E-intent": fc_scenario("E-intent"), "E-intent-widened": fc_scenario("E-intent-widened"),
                "E-effect": fc_scenario("E-effect"),
            },
            "snapshots": "raw/finecode/db-snapshots-after-crash.txt",
        },
        "metao.SQLiteMissionStore.replace (OCC)": {
            "classification": "FALHOU",
            "files": ["src/metao/sqlite_store.py:507–524 (replace)", "src/metao/mission_store.py:118 (InMemoryMissionStore.replace, mesma semântica)"],
            "reps": [{"rep": o["rep"], "stale_base_revision": o["stale_base_revision"],
                      "stale_replace_accepted": o["stale_replace"]["accepted"],
                      "db_final": o["db_final"], "verdict": o["verdict"]} for o in occ],
            "strict_prototype_isolated": mo["occ_prototype_strict"],
        },
        "metao.ledger fencing (SQLiteEventLedger.append + SQLiteExecutionHandleStore)": {
            "classification": "FALHOU",
            "files": ["src/metao/sqlite_event_ledger.py:84–125 (append, sem token/worker), :44 (UNIQUE(mission_id, sequence))",
                      "src/metao/sqlite_execution_handle.py:112–157 (activate, ON CONFLICT sobrescreve), :210–230 (complete, sem execution_id)",
                      "src/metao/runtime.py:26–75 (FencingToken, Lease, reject_stale_worker — sem chamadas em src/)"],
            "reps": [{
                "rep": f["rep"],
                "B_takeover_accepted": f["b_takeover"]["accepted"],
                "active_execution_after_takeover": f["active_execution_after_takeover"],
                "A_publish_stale_token_accepted": f["A_publish_event_with_stale_token"]["accepted"],
                "A_publish_sequence": f["seq_max_before_A_publish"] + 1,
                "A_publish_used_unused_sequence": f["A_publish_used_unused_sequence"],
                "A_replace_stale_copy_accepted": f["A_replace_mission_stale_copy"]["accepted"],
                "A_complete_handle_accepted": f["A_complete_handle"]["accepted"],
                "A_bind_external_error": f["A_bind_external_by_stale_execution_id"].get("error"),
                "helper_reject_stale_worker_raises": f["helper_reject_stale_worker_raises"],
                "final_mission": f["final_mission"],
                "final_handle_status": f["final_handle_status"],
                "final_events": [(e["seq"], e["payload"].get("worker")) for e in f["final_events"]],
            } for f in fen],
            "fenced_prototype_isolated": mo["fencing_prototype"],
        },
    },
    "answers": {
        "1_memo_reusable": "Sim, somente como registro durável de decisão/intenção por tarefa dentro de UMA instância Harness; garantia depende do padrão (at-most-once com intent-first; at-least-once com effect-first); exige chave idempotente no destino para exactly-once; não usar com duas instâncias sobre o mesmo DB.",
        "2_metao_occ_replace": "Não. replace() aceita cópia obsoleta silenciosamente (3/3).",
        "3_metao_blocks_stale_workers": "Não. Worker A obsoleto publicou evento (seq 4), substituiu missão e concluiu a execução de B (3/3).",
        "4_ready_or_adapt": "memo: adaptar (contrato de chave/padrão e lock de instância). OCC replace: adaptar (cláusula de revisão). Fencing: adaptar (token persistido validado na mesma transação de append/replace/complete).",
    },
}

(T2 / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print("written results.json")
