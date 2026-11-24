#!/usr/bin/env python3
"""Wrapper externo de execução para o benchmark TASK 02 (Pi original x Pi-Rust).

Responsabilidades:
  - executar UM agente por vez, no clone de seu workspace;
  - timeout de parede (padrão 3600 s), com encerramento da árvore de processos;
  - teto de custo acumulado (padrão US$ 1), monitorado pelo stream JSON em tempo real,
    incluindo o custo parcial da mensagem em andamento (message_update);
  - preservar stdout e stderr brutos (bytes exatos);
  - registrar UTC de início/término, tokens, cache, custo, ferramentas, código de saída,
    interrupções e erros, com "unavailable" (nunca zero) quando um campo não existe;
  - snapshot antes/depois e registro de divergências de isolamento (sem restaurar nada).

Não altera nada fora de evidence/<agente>/runs/<run-id>/ (além da execução do próprio agente
dentro do seu workspace).

Uso:
  python scripts/run-agent.py --agent pi-original --run-id R1 [--timeout 3600] [--cost-cap 1.0]
  python scripts/run-agent.py --agent pi-rust --run-id R1 --allow-unvalidated-usage
  python scripts/run-agent.py --agent pi-original --run-id R1 --dry-run

Schema de usage: ver scripts/AGENT_SCHEMAS.md. O Pi-Rust ainda NÃO teve o formato de saída
validado em execução real; por isso exige --allow-unvalidated-usage.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import snapshot as snap  # noqa: E402

TASK_ROOT = snap.TASK_ROOT
BASE_SHA = "0eaf98f050d86247bfe9bd7e41178865cb585060"
NODE = r"C:\Program Files\nodejs\node.exe"
PI_ORIG_CLI = (r"C:\Users\igorb\.pi\agent\install\releases\1.5.2\node_modules"
               r"\@earendil-works\pi-coding-agent\dist\bundle\cli.js")
PI_ORIG_ENV = {"PI_MANAGED_INSTALL_ROOT": r"C:\Users\igorb\.pi\agent\install"}
PI_RUST_EXE = os.path.join(TASK_ROOT, "evidence", "preparation", "pi-rust-build", "release", "pi.exe")

# Flags idênticas nas duas CLIs. Nenhum prompt de sistema é sobrescrito (prompts nativos).
COMMON_FLAGS = [
    "--provider", "anthropic", "--model", "claude-haiku-5-5", "--thinking", "medium",
    "--mode", "json", "--no-extensions", "--no-mcp", "--no-skills", "--no-prompt-templates",
    "--no-themes", "--no-context-files", "--no-approve",
]
USER_MESSAGE = "Leia o TASK.md anexado e implemente a tarefa descrita nele, neste repositório."
TASK_ARG = "@../TASK.md"  # relativo ao cwd agents/<agente>/flipt -> agents/<agente>/TASK.md

AGENTS = {
    "pi-original": {
        "cmd_prefix": [NODE, PI_ORIG_CLI],
        "env_extra": PI_ORIG_ENV,
        "workspace": os.path.join("agents", "pi-original", "flipt"),
        "version": "1.5.2",
        "schema": "documented",   # docs/json.md + docs/message-types.md + sessão real (incidente)
        "runtime_validated": True,
    },
    "pi-rust": {
        "cmd_prefix": [PI_RUST_EXE],
        "env_extra": {},
        "workspace": os.path.join("agents", "pi-rust", "flipt"),
        "version": "0.12.16",
        "schema": "source-inspected",  # código pi-rust/crates/pi-coding-agent e pi-ai (não executado)
        "runtime_validated": False,
    },
}
SANITIZE_ENV = ["PI_CODING_AGENT", "PI_REASONING_LEVEL", "PI_SESSION_FILE", "PI_SESSION_ID",
                "PI_PROVIDER", "PI_MODEL"]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def build_cmd(agent, run_dir):
    a = AGENTS[agent]
    session_dir = os.path.join(run_dir, "sessions")
    return a["cmd_prefix"] + COMMON_FLAGS + ["--session-dir", session_dir, "-p", TASK_ARG, USER_MESSAGE]


def build_env(extra):
    env = dict(os.environ)
    removed = []
    for k in SANITIZE_ENV:
        if k in env:
            del env[k]
            removed.append(k)
    env.update(extra or {})
    return env, removed


def kill_tree(proc):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=60)
        else:
            proc.kill()
    except Exception as e:  # registrado pelo chamador
        return str(e)
    return None


class Monitor:
    """Acumula usage e ferramentas a partir de linhas JSON de stdout."""

    def __init__(self, cost_cap):
        self.cost_cap = cost_cap
        self.lock = threading.Lock()
        self.cap_reached = False
        self.committed_cost = 0.0
        self.inflight_cost = 0.0
        self.assistant_messages = 0
        self.messages_missing_usage = 0
        self.messages_missing_cost = 0
        self.usage_sum = {k: 0 for k in ("input", "output", "cacheRead", "cacheWrite", "totalTokens")}
        self.usage_seen = {k: 0 for k in self.usage_sum}
        self.cost_from_provider = {"true": 0, "false": 0, "absent": 0}
        self.tool_total = 0
        self.tool_by_type = {}
        self.agent_end_seen = False
        self.agent_settled_seen = False
        self.agent_settled_aborted = None
        self.non_json_lines = 0
        self.json_lines = 0
        self.stdout_bytes = 0
        self.stderr_bytes = 0
        self.errors = []

    def _check_cap(self):
        if self.cost_cap is None:
            return
        if self.committed_cost + self.inflight_cost >= self.cost_cap:
            self.cap_reached = True

    def feed(self, line):
        try:
            ev = json.loads(line)
        except ValueError:
            with self.lock:
                self.non_json_lines += 1
            return
        if not isinstance(ev, dict):
            with self.lock:
                self.non_json_lines += 1
            return
        with self.lock:
            self.json_lines += 1
            t = ev.get("type")
            if t == "tool_execution_start":
                name = str(ev.get("toolName", "unknown"))
                self.tool_total += 1
                self.tool_by_type[name] = self.tool_by_type.get(name, 0) + 1
            elif t == "message_update":
                u = ev.get("usage")
                c = (u or {}).get("cost", {}).get("total") if isinstance(u, dict) else None
                if isinstance(c, (int, float)):
                    self.inflight_cost = float(c)
                    self._check_cap()
            elif t == "message_end":
                msg = ev.get("message") or {}
                if msg.get("role") != "assistant":
                    return
                self.assistant_messages += 1
                self.inflight_cost = 0.0
                u = msg.get("usage")
                if not isinstance(u, dict):
                    self.messages_missing_usage += 1
                    self.messages_missing_cost += 1
                    self._check_cap()
                    return
                for k in self.usage_sum:
                    v = u.get(k)
                    if isinstance(v, (int, float)):
                        self.usage_sum[k] += v
                        self.usage_seen[k] += 1
                cost = u.get("cost") if isinstance(u.get("cost"), dict) else {}
                c = cost.get("total")
                if isinstance(c, (int, float)):
                    self.committed_cost += float(c)
                else:
                    self.messages_missing_cost += 1
                tfp = cost.get("totalFromProvider", None)
                self.cost_from_provider["absent" if tfp is None else ("true" if tfp else "false")] += 1
                self._check_cap()
            elif t == "agent_end":
                self.agent_end_seen = True
            elif t == "agent_settled":
                self.agent_settled_seen = True
                self.agent_settled_aborted = ev.get("aborted")

    def usage_report(self):
        """Soma completa só quando todas as mensagens do assistente trouxeram o campo.
        Campo ausente em todas -> 'unavailable'. Presente em parte -> soma parcial explícita."""
        n = self.assistant_messages
        out = {}
        for k in self.usage_sum:
            seen = self.usage_seen[k]
            if seen == 0:
                out[k] = "unavailable"
            elif seen == n:
                out[k] = self.usage_sum[k]
            else:
                out[k] = {"partial_sum": self.usage_sum[k], "messages_with_field": seen, "assistant_messages": n}
        complete = n > 0 and self.messages_missing_cost == 0
        out["cost_total_usd"] = round(self.committed_cost, 8) if complete else "unavailable"
        out["cost_partial_sum_usd"] = round(self.committed_cost, 8) if n > 0 else "unavailable"
        out["cost_from_provider_flags"] = self.cost_from_provider
        return out


def _reader_stdout(stream, raw_path, monitor):
    with open(raw_path, "wb") as raw:
        for line in iter(stream.readline, b""):
            raw.write(line)
            raw.flush()
            with monitor.lock:
                monitor.stdout_bytes += len(line)
            monitor.feed(line.decode("utf-8", errors="replace").rstrip("\r\n"))


def _reader_stderr(stream, raw_path, monitor):
    with open(raw_path, "wb") as raw:
        for chunk in iter(lambda: stream.read(4096), b""):
            raw.write(chunk)
            raw.flush()
            with monitor.lock:
                monitor.stderr_bytes += len(chunk)


def execute(cmd, cwd, env, out_dir, timeout_s, cost_cap, extra_meta=None):
    """Executa cmd, monitora e grava artefatos em out_dir (que não pode existir)."""
    if os.path.exists(os.path.join(out_dir, "result.json")):
        raise FileExistsError(f"execução já registrada (não sobrescrever): {out_dir}")
    os.makedirs(out_dir, exist_ok=True)
    monitor = Monitor(cost_cap)
    result = {"cmd": cmd, "cwd": cwd, "timeout_seconds": timeout_s, "cost_cap_usd": cost_cap,
              "start_utc": utc_now(), "status": None, "termination_reason": None,
              "exit_code": None, "errors": []}
    if extra_meta:
        result.update(extra_meta)
    t0 = time.monotonic()
    creation = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=creation)
    except OSError as e:
        result.update({"status": "start_error", "termination_reason": "start_error",
                       "errors": [str(e)], "end_utc": utc_now(), "duration_seconds": 0.0})
        _write_result(out_dir, result, monitor)
        return result
    result["pid"] = proc.pid
    th_out = threading.Thread(target=_reader_stdout,
                              args=(proc.stdout, os.path.join(out_dir, "stdout.raw"), monitor), daemon=True)
    th_err = threading.Thread(target=_reader_stderr,
                              args=(proc.stderr, os.path.join(out_dir, "stderr.raw"), monitor), daemon=True)
    th_out.start()
    th_err.start()
    reason = None
    try:
        while True:
            if proc.poll() is not None:
                break
            if monitor.cap_reached:
                reason = "cost_cap"
                err = kill_tree(proc)
                if err:
                    result["errors"].append(f"kill: {err}")
                break
            if time.monotonic() - t0 > timeout_s:
                reason = "timeout"
                err = kill_tree(proc)
                if err:
                    result["errors"].append(f"kill: {err}")
                break
            time.sleep(0.2)
        rc = proc.wait(timeout=60)
    except KeyboardInterrupt:
        reason = "interrupted"
        kill_tree(proc)
        rc = proc.wait(timeout=60)
    except Exception as e:
        reason = "monitor_error"
        result["errors"].append(f"monitor: {e!r}")
        kill_tree(proc)
        rc = proc.wait(timeout=60)
    th_out.join(timeout=60)
    th_err.join(timeout=60)
    for stream in (proc.stdout, proc.stderr):
        try:
            stream.close()
        except Exception:
            pass
    duration = time.monotonic() - t0
    result["exit_code"] = rc
    # teto ultrapassado sem que o processo fosse interrompido (ex.: saiu logo após a mensagem cara)
    result["cost_cap_exceeded"] = bool(monitor.cap_reached)
    result["termination_reason"] = reason or "process_exit"
    if reason == "cost_cap":
        result["status"] = "cost_cap_stopped"
    elif reason == "timeout":
        result["status"] = "timeout"
    elif reason == "interrupted":
        result["status"] = "interrupted"
    elif reason == "monitor_error":
        result["status"] = "monitor_error"
    else:
        result["status"] = "completed" if rc == 0 else "process_error"
    result["end_utc"] = utc_now()
    result["duration_seconds"] = round(duration, 3)
    _write_result(out_dir, result, monitor)
    return result


def _write_result(out_dir, result, monitor):
    cost_control = "enforced"
    if monitor.messages_missing_cost:
        cost_control = "partial" if monitor.assistant_messages > monitor.messages_missing_cost else "unavailable"
    result.update({
        "usage": monitor.usage_report(),
        "cost_control": cost_control,
        "assistant_messages": monitor.assistant_messages,
        "assistant_messages_missing_usage": monitor.messages_missing_usage,
        "assistant_messages_missing_cost": monitor.messages_missing_cost,
        "tool_calls": {"total": monitor.tool_total, "by_type": monitor.tool_by_type},
        "agent_end_seen": monitor.agent_end_seen,
        "agent_settled_seen": monitor.agent_settled_seen,
        "agent_settled_aborted": monitor.agent_settled_aborted,
        "json_lines": monitor.json_lines,
        "non_json_stdout_lines": monitor.non_json_lines,
        "stdout_bytes": monitor.stdout_bytes,
        "stderr_bytes": monitor.stderr_bytes,
    })
    with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)


ORDER_FILE = os.path.join(TASK_ROOT, "evidence", "preparation", "draw-order.json")
LOCK_FILE = os.path.join(TASK_ROOT, "evidence", "infra-tests", "run.lock")  # excluído do snapshot


def expected_agent(order, completed_agents):
    """Próximo agente da ordem sorteada, ou None se todos já têm uma execução registrada."""
    for name in order:
        if name not in completed_agents:
            return name
    return None


def completed_runs(agent):
    base = os.path.join(TASK_ROOT, "evidence", agent, "runs")
    if not os.path.isdir(base):
        return []
    return [r for r in os.listdir(base) if os.path.exists(os.path.join(base, r, "result.json"))]


def acquire_lock():
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as f:
        f.write(utc_now() + " pid=" + str(os.getpid()) + "\n")
    return True


def release_lock():
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent", required=True, choices=sorted(AGENTS))
    p.add_argument("--run-id", required=True)
    p.add_argument("--timeout", type=float, default=3600)
    p.add_argument("--cost-cap", type=float, default=1.0)
    p.add_argument("--allow-unvalidated-usage", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", args.run_id):
        p.error("run-id inválido")
    a = AGENTS[args.agent]
    if not a["runtime_validated"] and not args.allow_unvalidated_usage:
        print(f"RECUSADO: schema de {args.agent} não validado em execução real "
              f"({a['schema']}). Use --allow-unvalidated-usage após o piloto.", file=sys.stderr)
        return 4
    if not os.path.exists(ORDER_FILE):
        print("RECUSADO: draw-order.json ausente (rodar scripts/draw-order.py antes)", file=sys.stderr)
        return 4
    with open(ORDER_FILE, encoding="utf-8") as f:
        drawn = json.load(f)
    done = [a for a in drawn["input"] if completed_runs(a)]
    nxt = expected_agent(drawn["order"], done)
    if nxt != args.agent:
        print(f"RECUSADO: ordem sorteada {drawn['order']}; próximo esperado = {nxt}, pedido = {args.agent}",
              file=sys.stderr)
        return 6
    run_dir = os.path.join(TASK_ROOT, "evidence", args.agent, "runs", args.run_id)
    if os.path.exists(run_dir):
        print(f"RECUSADO: run-id já existe: {run_dir}", file=sys.stderr)
        return 4
    cwd = os.path.join(TASK_ROOT, a["workspace"])
    cmd = build_cmd(args.agent, run_dir)
    env, removed = build_env(a["env_extra"])
    print("cmd:", " ".join(cmd[:4]), "...")
    if args.dry_run:
        print("dry-run: nenhum processo iniciado")
        return 0
    # pré-condições: clone no SHA-base e árvore limpa
    head = subprocess.run(["git", "-C", cwd, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", cwd, "status", "--porcelain", "--untracked-files=all"],
                           capture_output=True, text=True).stdout.strip()
    if head != BASE_SHA or dirty:
        print(f"RECUSADO: workspace fora do estado inicial (HEAD={head}, sujo={bool(dirty)})", file=sys.stderr)
        return 4
    if not acquire_lock():
        print("RECUSADO: outra execução em andamento (evidence/infra-tests/run.lock)", file=sys.stderr)
        return 7
    try:
        return _run_locked(args, a, cmd, cwd, env, removed, run_dir)
    finally:
        release_lock()


def _run_locked(args, a, cmd, cwd, env, removed, run_dir):
    # snapshot pré-execução
    os.makedirs(run_dir)
    pre = snap.take()
    with open(os.path.join(run_dir, "snapshot-pre.json"), "w", encoding="utf-8") as f:
        json.dump(pre, f, ensure_ascii=False, indent=1)
    baseline_path = os.path.join(TASK_ROOT, "evidence", "preparation", "snapshot-baseline.json")
    if not os.path.exists(baseline_path):
        print("RECUSADO: snapshot-baseline.json ausente (rodar snapshot.py take antes)", file=sys.stderr)
        return 4
    with open(baseline_path, encoding="utf-8") as f:
        base = json.load(f)
    pre_cmp = snap.compare(base, pre, [])
    pre_divergence = len(pre_cmp["divergences"])
    if pre_divergence:
        print(f"RECUSADO: {pre_divergence} alteração(ões) antes do início (ver pre-divergences.json)", file=sys.stderr)
        with open(os.path.join(run_dir, "pre-divergences.json"), "w", encoding="utf-8") as f:
            json.dump(pre_cmp, f, ensure_ascii=False, indent=1)
        return 5
    # execução e snapshot pós (run_dir já existe e contém apenas snapshot-pre.json)
    result = execute(cmd, cwd, env, run_dir, args.timeout, args.cost_cap,
                     extra_meta={"agent": args.agent, "agent_version": a["version"],
                                 "run_id": args.run_id, "env_removed": removed,
                                 "schema": a["schema"], "pre_divergences_vs_baseline": pre_divergence})
    post = snap.take()
    with open(os.path.join(run_dir, "snapshot-post.json"), "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=1)
    allow = [os.path.join("agents", args.agent, "flipt").replace("\\", "/") + "/",
             os.path.join("evidence", args.agent).replace("\\", "/") + "/"]
    diff = snap.compare(pre, post, allow)
    with open(os.path.join(run_dir, "isolation-diff.json"), "w", encoding="utf-8") as f:
        json.dump(diff, f, ensure_ascii=False, indent=1)
    result["isolation_divergences"] = len(diff["divergences"])
    result["isolation_ok"] = diff["ok"]
    with open(os.path.join(run_dir, "result.json"), encoding="utf-8") as f:
        final = json.load(f)
    final["isolation_divergences"] = len(diff["divergences"])
    final["isolation_ok"] = diff["ok"]
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=1)
    print(f"status={final['status']} exit={final['exit_code']} duration={final['duration_seconds']}s "
          f"cost={final['usage']['cost_total_usd']} tools={final['tool_calls']['total']} "
          f"isolation_ok={diff['ok']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
