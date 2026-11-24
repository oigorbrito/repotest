"""Testes de infraestrutura do benchmark TASK 02. Usam apenas processos Python artificiais.

Nenhuma chamada de modelo, nenhum Pi ou Pi-Rust é iniciado.
Executar: python -m unittest discover -s scripts/tests -v
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ra = _load("run_agent", "run-agent.py")
snap = _load("snapshot", "snapshot.py")
draw = _load("draw_order", "draw-order.py")

PY = sys.executable

ASSIST_OK = ('{"type":"message_end","message":{"role":"assistant","usage":{"input":10,"output":5,'
             '"cacheRead":2,"cacheWrite":0,"totalTokens":17,"cost":{"input":0.1,"output":0.2,'
             '"cacheRead":0,"cacheWrite":0,"total":%s,"totalFromProvider":false}}}}')


def fake(code):
    return [PY, "-u", "-c", code]


class RunAgentCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="infra-")
        self.out = os.path.join(self.tmp, "run")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_fake(self, code, timeout=30, cap=1.0, env=None):
        return ra.execute(fake(code), self.tmp, env or dict(os.environ), self.out, timeout, cap)

    def read(self, name, mode="rb"):
        with open(os.path.join(self.out, name), mode) as f:
            return f.read()


class T1NormalExit(RunAgentCase):
    def test_normal_exit_records_usage_tools_and_raw_stdout(self):
        code = (
            'import sys,time\n'
            'print(\'{"type":"agent_start"}\')\n'
            'print(\'{"type":"tool_execution_start","toolCallId":"c1","toolName":"bash","args":{}}\')\n'
            f'print(\'{ASSIST_OK % "0.3"}\')\n'
            'print(\'{"type":"agent_end","messages":[],"willRetry":false}\')\n'
            'print(\'{"type":"agent_settled","aborted":false}\')\n'
        )
        r = self.run_fake(code)
        self.assertEqual(r["status"], "completed")
        self.assertEqual(r["exit_code"], 0)
        self.assertEqual(r["usage"]["input"], 10)
        self.assertEqual(r["usage"]["cacheRead"], 2)
        self.assertEqual(r["usage"]["cacheWrite"], 0)  # presente como 0 no JSON -> é valor, não ausência
        self.assertAlmostEqual(r["usage"]["cost_total_usd"], 0.3)
        self.assertEqual(r["tool_calls"]["total"], 1)
        self.assertEqual(r["tool_calls"]["by_type"], {"bash": 1})
        self.assertTrue(r["agent_end_seen"])
        self.assertIs(r["agent_settled_aborted"], False)
        self.assertEqual(r["cost_control"], "enforced")
        self.assertIn("start_utc", r)
        self.assertTrue(r["end_utc"].endswith("+00:00"))
        # stdout bruto é a sequência exata de bytes emitida
        # print() no Windows grava CRLF; o wrapper preserva os bytes. Comparação sem o terminador.
        self.assertTrue(self.read("stdout.raw").startswith(b'{"type":"agent_start"}'))
        self.assertIn(b'"toolName":"bash"', self.read("stdout.raw"))


class T2Timeout(RunAgentCase):
    def test_timeout_kills_process_and_records_reason(self):
        t0 = time.monotonic()
        r = self.run_fake("import time; time.sleep(60)", timeout=2)
        elapsed = time.monotonic() - t0
        self.assertEqual(r["status"], "timeout")
        self.assertEqual(r["termination_reason"], "timeout")
        self.assertLess(elapsed, 30, "processo não foi encerrado no timeout")


class T3CostCap(RunAgentCase):
    def test_committed_cost_over_cap_stops_run(self):
        code = (
            f'import time\nprint(\'{ASSIST_OK % "0.6"}\', flush=True)\n'
            f'print(\'{ASSIST_OK % "0.6"}\', flush=True)\n'
            'time.sleep(60)\n'
            f'print(\'{ASSIST_OK % "0.6"}\', flush=True)\n'
        )
        t0 = time.monotonic()
        r = self.run_fake(code, cap=1.0)
        self.assertLess(time.monotonic() - t0, 30)
        self.assertEqual(r["status"], "cost_cap_stopped")
        self.assertEqual(r["termination_reason"], "cost_cap")
        self.assertAlmostEqual(r["usage"]["cost_total_usd"], 1.2)
        self.assertEqual(r["assistant_messages"], 2)  # a terceira nunca foi emitida

    def test_process_exiting_after_exceeding_cap_is_flagged(self):
        code = "print(" + repr(ASSIST_OK % "1.5") + ", flush=True)"
        r = self.run_fake(code, cap=1.0)
        self.assertEqual(r["status"], "completed")
        self.assertTrue(r["cost_cap_exceeded"])

    def test_inflight_cost_over_cap_stops_before_message_end(self):
        code = (
            'import time\n'
            'print(\'{"type":"message_update","usage":{"input":1,"output":1,"cacheRead":0,'
            '"cacheWrite":0,"totalTokens":2,"cost":{"total":1.5}},"assistantMessageEvent":'
            '{"type":"text_delta","contentIndex":0,"delta":"x"}}\', flush=True)\n'
            'time.sleep(60)\n'
        )
        t0 = time.monotonic()
        r = self.run_fake(code, cap=1.0)
        self.assertLess(time.monotonic() - t0, 30)
        self.assertEqual(r["status"], "cost_cap_stopped")
        self.assertEqual(r["assistant_messages"], 0)


class T4StdoutStderr(RunAgentCase):
    def test_raw_bytes_preserved_and_exit_code_recorded(self):
        code = (
            'import sys\n'
            'sys.stdout.buffer.write(b"\\xff\\xfe raw-no-json\\n")\n'
            'sys.stdout.buffer.flush()\n'
            'sys.stderr.buffer.write(b"err\\x00bytes\\n")\n'
            'sys.stderr.buffer.flush()\n'
            'sys.exit(3)\n'
        )
        r = self.run_fake(code)
        self.assertEqual(r["exit_code"], 3)
        self.assertEqual(r["status"], "process_error")
        self.assertEqual(self.read("stdout.raw"), b"\xff\xfe raw-no-json\n")
        self.assertEqual(self.read("stderr.raw"), b"err\x00bytes\n")
        self.assertEqual(r["non_json_stdout_lines"], 1)
        self.assertEqual(r["stderr_bytes"], len(b"err\x00bytes\n"))

    def test_refuses_to_overwrite_recorded_run(self):
        self.run_fake("print('x')")
        with self.assertRaises(FileExistsError):
            self.run_fake("print('y')")


class T5ProtectedFileChange(unittest.TestCase):
    """Snapshot detecta alteração fora do workspace autorizado e não restaura nada."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="iso-")
        self.home = tempfile.mkdtemp(prefix="home-")
        os.makedirs(os.path.join(self.root, "agents", "pi-original", "flipt"))
        os.makedirs(os.path.join(self.root, "agents", "pi-rust", "flipt"))
        self.protected = os.path.join(self.root, "agents", "pi-rust", "TASK.md")
        with open(self.protected, "w", encoding="utf-8") as f:
            f.write("tarefa original\n")
        self._old = snap.TASK_ROOT
        snap.TASK_ROOT = self.root

    def tearDown(self):
        snap.TASK_ROOT = self._old
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.home, ignore_errors=True)

    def test_change_outside_workspace_is_divergence_not_restored(self):
        before = snap.take(root=self.root, home_agent=self.home)
        # agente simula: escreve no próprio workspace e altera arquivo protegido
        with open(os.path.join(self.root, "agents", "pi-original", "flipt", "ok.txt"), "w") as f:
            f.write("permitido")
        with open(self.protected, "w", encoding="utf-8") as f:
            f.write("ALTERADO\n")
        after = snap.take(root=self.root, home_agent=self.home)
        diff = snap.compare(before, after, ["agents/pi-original/flipt/", "evidence/pi-original/"])
        self.assertFalse(diff["ok"])
        paths = [d["path"] for d in diff["divergences"]]
        self.assertIn("agents/pi-rust/TASK.md", paths)
        self.assertNotIn("agents/pi-original/flipt/ok.txt", paths)
        # nada foi restaurado
        with open(self.protected, encoding="utf-8") as f:
            self.assertEqual(f.read(), "ALTERADO\n")

    def test_external_shared_file_change_detected(self):
        with open(os.path.join(self.home, "settings.json"), "w") as f:
            f.write("{}")
        before = snap.take(root=self.root, home_agent=self.home)
        with open(os.path.join(self.home, "settings.json"), "w") as f:
            f.write('{"x":1}')
        after = snap.take(root=self.root, home_agent=self.home)
        diff = snap.compare(before, after, ["agents/pi-original/flipt/"])
        self.assertIn("ext:settings.json", [d["path"] for d in diff["divergences"]])

    def test_run_outputs_and_control_artifacts_excluded(self):
        os.makedirs(os.path.join(self.root, "evidence", "pi-original", "runs", "r1"))
        before = snap.take(root=self.root, home_agent=self.home)
        with open(os.path.join(self.root, "evidence", "pi-original", "runs", "r1", "stdout.raw"), "w") as f:
            f.write("x")
        os.makedirs(os.path.join(self.root, "evidence", "preparation"))
        with open(os.path.join(self.root, "evidence", "preparation", "snapshot-x.json"), "w") as f:
            f.write("{}")
        after = snap.take(root=self.root, home_agent=self.home)
        self.assertEqual(snap.compare(before, after, [])["changes"], [])


class T6SimulatedUsage(RunAgentCase):
    def test_missing_fields_are_unavailable_not_zero(self):
        code = (
            'print(\'{"type":"message_end","message":{"role":"assistant","usage":{"input":100,'
            '"output":20,"cacheRead":5,"totalTokens":120,"cost":{"total":0.01}}}}\', flush=True)\n'
            'print(\'{"type":"message_end","message":{"role":"assistant","content":[]}}\', flush=True)\n'
        )
        r = self.run_fake(code)
        self.assertEqual(r["assistant_messages"], 2)
        self.assertEqual(r["assistant_messages_missing_usage"], 1)
        self.assertEqual(r["usage"]["cacheWrite"], "unavailable")
        self.assertEqual(r["usage"]["cost_total_usd"], "unavailable")
        self.assertEqual(r["usage"]["cost_partial_sum_usd"], 0.01)
        self.assertEqual(r["cost_control"], "partial")
        self.assertEqual(r["usage"]["input"], {"partial_sum": 100, "messages_with_field": 1,
                                               "assistant_messages": 2})

    def test_no_usage_at_all_reports_cost_control_unavailable(self):
        code = 'print(\'{"type":"message_end","message":{"role":"assistant"}}\', flush=True)\n'
        r = self.run_fake(code, cap=1.0)
        self.assertEqual(r["cost_control"], "unavailable")
        self.assertEqual(r["usage"]["input"], "unavailable")

    def test_schema_fields_of_real_original_session_are_parsed(self):
        # Mensagem copiada da sessão real do incidente (somente campos de usage).
        real = ('{"role":"assistant","usage":{"input":4,"output":310,"cacheRead":2213,"cacheWrite":1116,'
                '"totalTokens":3643,"cost":{"input":4e-07,"output":0.000155,"cacheRead":2.213e-05,'
                '"cacheWrite":0.0001395,"total":0.00031703000000000005,"totalFromProvider":false},'
                '"reasoning":97}}')
        code = f"print('{{\"type\":\"message_end\",\"message\":{real}}}', flush=True)\n"
        r = self.run_fake(code)
        self.assertEqual(r["usage"]["cacheRead"], 2213)
        self.assertEqual(r["usage"]["cacheWrite"], 1116)
        self.assertAlmostEqual(r["usage"]["cost_total_usd"], 0.00031703, places=8)
        self.assertEqual(r["cost_from_provider_flags"] if "cost_from_provider_flags" in r else
                         r["usage"]["cost_from_provider_flags"]["false"], 1)


class T7Environment(RunAgentCase):
    def test_session_variables_removed_and_extra_added(self):
        os.environ["PI_MODEL"] = "x-model"
        try:
            env, removed = ra.build_env({"PI_MANAGED_INSTALL_ROOT": "C:\\managed"})
        finally:
            del os.environ["PI_MODEL"]
        self.assertIn("PI_MODEL", removed)
        self.assertNotIn("PI_MODEL", env)
        self.assertEqual(env["PI_MANAGED_INSTALL_ROOT"], "C:\\managed")
        r = ra.execute(fake("import os,sys; print(os.environ.get('PI_MODEL','ABSENT'))"),
                       self.tmp, env, self.out, 30, 1.0)
        self.assertEqual(self.read("stdout.raw").strip(), b"ABSENT")
        self.assertEqual(r["status"], "completed")


class T8Gate(unittest.TestCase):
    def test_unvalidated_schema_refused_without_flag(self):
        self.assertEqual(ra.main(["--agent", "pi-rust", "--run-id", "gate-test", "--dry-run"]), 4)

    def test_invalid_run_id_rejected(self):
        with self.assertRaises(SystemExit):
            ra.main(["--agent", "pi-original", "--run-id", "../bad", "--dry-run"])

    def test_dry_run_builds_same_flags_for_both_agents(self):
        run_dir = os.path.join(ra.TASK_ROOT, "evidence", "x", "runs", "y")
        a = ra.build_cmd("pi-original", run_dir)
        b = ra.build_cmd("pi-rust", run_dir)
        flags_a = a[a.index("--provider"):]
        flags_b = b[b.index("--provider"):]
        self.assertEqual(flags_a, flags_b)
        self.assertNotIn("--system-prompt", a + b)
        self.assertNotIn("--max-cost", a + b)  # limite externo aplicado pelo wrapper aos dois


class T9Draw(unittest.TestCase):
    def test_draw_is_reproducible_from_recorded_seed(self):
        tmp = tempfile.mkdtemp(prefix="draw-")
        try:
            out = os.path.join(tmp, "d.json")
            draw.draw(out, seed=12345)
            with open(out, encoding="utf-8") as f:
                rec = json.load(f)
            self.assertEqual(rec["seed"], 12345)
            self.assertFalse(rec["agents_started_by_this_script"])
            self.assertEqual(draw.verify(out), 0)
            self.assertEqual(sorted(rec["order"]), sorted(draw.AGENTS))
            # mesma semente -> mesma ordem, em outra chamada
            self.assertEqual(draw.shuffle(12345, draw.AGENTS), rec["order"])
            # adulteração do resultado gravado é detectada
            rec["order"] = list(reversed(rec["order"]))
            with open(out, "w", encoding="utf-8") as f:
                json.dump(rec, f)
            self.assertEqual(draw.verify(out), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class T10EvaluatorParser(unittest.TestCase):
    """Parser do avaliador. Entradas SINTÉTICAS (não são resultados de execução)."""

    @classmethod
    def setUpClass(cls):
        cls.ev = _load("evaluate", os.path.join("..", "evaluator", "evaluate.py"))

    def test_pass_fail_notrun_and_subtests(self):
        lines = [
            '{"Action":"run","Test":"TestA"}',
            '{"Action":"run","Test":"TestA/sub1"}',
            '{"Action":"pass","Test":"TestA/sub1"}',
            '{"Action":"pass","Test":"TestA"}',
            '{"Action":"run","Test":"TestB"}',
            '{"Action":"pass","Test":"TestB/x"}',
            '{"Action":"fail","Test":"TestB"}',
            'linha que não é json',
            '{"Action":"pass","Test":"TestOutro"}',
        ]
        r = self.ev.parse_go_json(lines, ["TestA", "TestB", "TestC"])
        self.assertEqual(r["per_identifier"], {"TestA": "PASS", "TestB": "FAIL", "TestC": "NOT_RUN"})
        self.assertEqual(r["non_json_lines"], 1)

    def test_build_failure_is_reported_not_as_pass(self):
        lines = ['{"Action":"fail","Package":"pkg/x"}']
        r = self.ev.parse_go_json(lines, ["TestA"])
        self.assertEqual(r["per_identifier"], {"TestA": "NOT_RUN"})
        self.assertEqual(r["build_failed_packages"], ["pkg/x"])

    def test_skip_only_is_skip_not_pass(self):
        r = self.ev.parse_go_json(['{"Action":"skip","Test":"TestS"}'], ["TestS"])
        self.assertEqual(r["per_identifier"], {"TestS": "SKIP"})

    def test_run_regex_rejects_unsafe_names(self):
        with self.assertRaises(SystemExit):
            self.ev.build_run_regex(["TestA;rm"])
        self.assertEqual(self.ev.build_run_regex(["TestA", "TestB"]), "^(TestA|TestB)$")

    def test_benchmark_mode_is_blocked_without_test_patch(self):
        self.assertFalse(os.path.exists(self.ev.PATCH_PATH),
                         "este teste assume que o patch de testes NÃO foi autorizado/entregue")
        self.assertEqual(self.ev.main(["--agent", "pi-original", "--run-id", "unit-blocked",
                                       "--clone", os.path.join("agents", "pi-original", "flipt")]), 3)


class T11OrderAndLock(unittest.TestCase):
    def test_expected_agent_follows_drawn_order(self):
        order = ["pi-rust", "pi-original"]
        self.assertEqual(ra.expected_agent(order, []), "pi-rust")
        self.assertEqual(ra.expected_agent(order, ["pi-rust"]), "pi-original")
        self.assertIsNone(ra.expected_agent(order, ["pi-rust", "pi-original"]))

    def test_out_of_order_run_refused(self):
        drawn = json.load(open(os.path.join(ra.TASK_ROOT, "evidence", "preparation", "draw-order.json"),
                               encoding="utf-8"))
        first = drawn["order"][0]
        second = drawn["order"][1]
        if completed_count(second) == 0 and completed_count(first) == 0:
            self.assertEqual(ra.main(["--agent", second, "--run-id", "order-gate-test", "--dry-run",
                                      "--allow-unvalidated-usage"]), 6)

    def test_lock_is_exclusive(self):
        lock = ra.LOCK_FILE
        if os.path.exists(lock):
            self.skipTest("lock de execução real presente; teste não deve interferir")
        self.assertTrue(ra.acquire_lock())
        try:
            self.assertFalse(ra.acquire_lock())
        finally:
            ra.release_lock()
        self.assertFalse(os.path.exists(lock))


def completed_count(agent):
    return len(ra.completed_runs(agent))


if __name__ == "__main__":
    unittest.main()
