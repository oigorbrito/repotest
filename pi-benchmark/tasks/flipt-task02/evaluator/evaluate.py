#!/usr/bin/env python3
"""Avaliador do benchmark TASK 02. Procedimento único, idêntico para os dois agentes.

Fora de agents/: o agente nunca tem acesso a esta pasta durante a execução.

Procedimento (mesmo código para pi-original e pi-rust):
  1. Confere que o identificador de base do avaliador é o commit-base obrigatório.
  2. Confere que o clone do agente está em HEAD = commit-base (leitura; sem alterar o clone).
  3. Copia a árvore de trabalho final do clone (sem .git) para evaluator/work/<run>/<agente>/.
  4. Aplica o patch de testes de referência (evaluator/private/test.patch). Se ausente: BLOCKED.
  5. Executa `go test -json -count=1 -run '^(id1|id2|...)$' ./...` com timeout.
  6. Classifica cada identificador de fail_to_pass e pass_to_pass como PASS, FAIL ou NOT_RUN.
  7. Grava evaluator/results/<run>/<agente>/{result.json, go-test.jsonl, go-test.stderr}.

Modo de controle (--control): executa identificadores existentes no código-base, sem patch,
para verificar o pipeline. Resultado marcado como CONTROL e nunca usado como resultado do benchmark.

Uso:
  python evaluator/evaluate.py --agent pi-original --run-id R1 --clone agents/pi-original/flipt
  python evaluator/evaluate.py --control --run-id C1 --clone source --ids TestNewCache,TestSet
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
TASK_ROOT = os.path.dirname(HERE)
BASE_SHA = "0eaf98f050d86247bfe9bd7e41178865cb585060"
IDS_PATH = os.path.join(HERE, "test-identifiers.json")
PATCH_PATH = os.path.join(HERE, "private", "test.patch")
MODULE_PKG_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def utc():
    return datetime.now(timezone.utc).isoformat()


def load_ids():
    with open(IDS_PATH, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("base_commit") != BASE_SHA:
        raise SystemExit("identifiers base_commit diferente do commit-base obrigatório")
    return d


def build_run_regex(names):
    for n in names:
        if not MODULE_PKG_PATTERN.match(n):
            raise SystemExit(f"identificador inválido para -run: {n!r}")
    return "^(" + "|".join(names) + ")$"


def parse_go_json(lines, identifiers):
    """Classifica identificadores a partir de linhas de `go test -json`.

    Um identificador é PASS se ele próprio e todos os subtestes emitiram pass e nenhum fail;
    FAIL se algum emitiu fail; NOT_RUN se nunca apareceu. Entrada não-JSON é contada e ignorada.
    """
    final = {}
    non_json = 0
    build_failed = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except ValueError:
            non_json += 1
            continue
        action = ev.get("Action")
        test = ev.get("Test")
        if action == "build-fail" or (action == "fail" and not test and ev.get("Package")):
            build_failed.append(ev.get("Package"))
        if not test or action not in ("pass", "fail", "skip"):
            continue
        top = test.split("/")[0]
        if top not in identifiers:
            continue
        rec = final.setdefault(top, {"pass": 0, "fail": 0, "skip": 0, "subtests": set()})
        rec[action] += 1
        if "/" in test:
            rec["subtests"].add(test)
    results = {}
    for name in identifiers:
        rec = final.get(name)
        if rec is None:
            results[name] = "NOT_RUN"
        elif rec["fail"]:
            results[name] = "FAIL"
        elif rec["pass"]:
            results[name] = "PASS"
        else:
            results[name] = "SKIP"
    return {"per_identifier": results, "non_json_lines": non_json,
            "build_failed_packages": sorted(set(p for p in build_failed if p))}


def copy_worktree(src, dst):
    def ignore(d, names):
        return [n for n in names if n == ".git"]
    shutil.copytree(src, dst, ignore=ignore)


def git_out(args, cwd):
    r = subprocess.run(["git", "--no-optional-locks", *args], cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent")
    p.add_argument("--run-id", required=True)
    p.add_argument("--clone")
    p.add_argument("--control", action="store_true")
    p.add_argument("--ids", help="(controle) lista separada por vírgulas")
    p.add_argument("--timeout", type=float, default=1800)
    args = p.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", args.run_id):
        p.error("run-id inválido")

    if args.control:
        agent_label = "control"
        if not args.ids or not args.clone:
            p.error("--control exige --ids e --clone")
        identifiers = {"fail_to_pass": [], "pass_to_pass": [], "base_commit": BASE_SHA}
        names = [s for s in args.ids.split(",") if s]
        ids_for_run = names
        clone = os.path.abspath(args.clone)
    else:
        if not args.agent or not args.clone:
            p.error("--agent e --clone são obrigatórios")
        agent_label = args.agent
        identifiers = load_ids()
        ids_for_run = identifiers["fail_to_pass"] + identifiers["pass_to_pass"]
        clone = os.path.abspath(os.path.join(TASK_ROOT, args.clone) if not os.path.isabs(args.clone) else args.clone)

    out_dir = os.path.join(HERE, "results", args.run_id, agent_label)
    os.makedirs(out_dir, exist_ok=True)
    result = {"run_id": args.run_id, "agent": agent_label, "control": args.control,
              "base_commit": BASE_SHA, "started_utc": utc(), "status": None, "reason": None}

    def finish(status, reason=None):
        result.update({"status": status, "reason": reason, "finished_utc": utc()})
        with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(f"status={status} reason={reason} -> {out_dir}")
        return {"BLOCKED": 3, "EVALUATED": 0, "ERROR": 1}.get(status, 1)

    if not args.control and not os.path.exists(PATCH_PATH):
        return finish("BLOCKED", "test_patch_missing: evaluator/private/test.patch não disponível (não autorizado)")

    head, rc = git_out(["rev-parse", "HEAD"], clone)
    if rc != 0 or head != BASE_SHA:
        return finish("ERROR", f"clone fora do commit-base (HEAD={head})")
    status_out, _ = git_out(["status", "--porcelain", "--untracked-files=all"], clone)
    result["agent_clone_status_lines"] = len([x for x in status_out.splitlines() if x])
    diffstat, _ = git_out(["diff", "--stat", "HEAD"], clone)
    result["agent_diff_stat"] = diffstat.splitlines()[-1] if diffstat else ""

    work = os.path.join(HERE, "work", args.run_id, agent_label)
    if os.path.exists(work):
        return finish("ERROR", "diretório de trabalho já existe")
    os.makedirs(os.path.dirname(work), exist_ok=True)
    copy_worktree(clone, work)
    if not args.control:
        ap = subprocess.run(["git", "apply", "--whitespace=nowarn", PATCH_PATH], cwd=work,
                            capture_output=True, text=True)
        result["test_patch_apply_rc"] = ap.returncode
        if ap.returncode != 0:
            return finish("ERROR", "test patch não aplicou: " + ap.stderr.strip()[:500])

    run_names = ids_for_run
    if not run_names:
        return finish("ERROR", "nenhum identificador a executar")
    cmd = ["go", "test", "-json", "-count=1", "-run", build_run_regex(run_names), "./..."]
    result["go_cmd"] = cmd
    try:
        proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=args.timeout)
        rc_go = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
        result["timed_out"] = False
    except subprocess.TimeoutExpired as e:
        rc_go = None
        stdout = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        result["timed_out"] = True
    with open(os.path.join(out_dir, "go-test.jsonl"), "w", encoding="utf-8") as f:
        f.write(stdout)
    with open(os.path.join(out_dir, "go-test.stderr"), "w", encoding="utf-8") as f:
        f.write(stderr)
    parsed = parse_go_json(stdout.splitlines(), run_names)
    result["go_exit_code"] = rc_go
    result["per_identifier"] = parsed["per_identifier"]
    result["build_failed_packages"] = parsed["build_failed_packages"]
    result["non_json_lines"] = parsed["non_json_lines"]
    result["fail_to_pass_total"] = len(identifiers["fail_to_pass"])
    result["fail_to_pass_pass"] = sum(1 for n in identifiers["fail_to_pass"] if parsed["per_identifier"].get(n) == "PASS")
    result["pass_to_pass_total"] = len(identifiers["pass_to_pass"])
    result["pass_to_pass_pass"] = sum(1 for n in identifiers["pass_to_pass"] if parsed["per_identifier"].get(n) == "PASS")
    resolved = (not result["timed_out"] and result["fail_to_pass_pass"] == result["fail_to_pass_total"]
                and result["pass_to_pass_pass"] == result["pass_to_pass_total"])
    # Em controle não há fail_to_pass oficial: 'resolved' não se aplica (null).
    result["resolved"] = None if args.control else resolved
    shutil.rmtree(work, ignore_errors=True)
    try:
        os.rmdir(os.path.dirname(work))  # remove evaluator/work/<run> se ficou vazio
    except OSError:
        pass
    result["work_dir_removed"] = True
    return finish("EVALUATED", "control" if args.control else "benchmark")


if __name__ == "__main__":
    sys.exit(main())
