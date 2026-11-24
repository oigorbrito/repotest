"""Integração do fluxo de run-agent.main com clone REAL do commit-base e agente ARTIFICIAL.

Nenhum modelo é chamado. Todos os caminhos globais são redirecionados para um diretório temporário.
Executar: python -m unittest discover -s scripts/tests -v
"""
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
TASK_ROOT = os.path.dirname(SCRIPTS)
FAKE_AGENT = os.path.join(HERE, "fake_agent.py")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ra = _load("run_agent_int", "run-agent.py")
snap = _load("snapshot_int", "snapshot.py")


class MainIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = os.path.join(TASK_ROOT, "source")
        if not os.path.isdir(os.path.join(cls.src, ".git")):
            raise unittest.SkipTest("source/ ausente")

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="int-")
        self.home = tempfile.mkdtemp(prefix="homei-")
        clone = os.path.join(self.root, "agents", "pi-original", "flipt")
        os.makedirs(os.path.dirname(clone))
        src_url = "file:///" + self.src.replace("\\", "/")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--no-hardlinks", "--no-checkout",
                        src_url, clone], check=True)
        subprocess.run(["git", "-C", clone, "config", "core.autocrlf", "false"], check=True)
        subprocess.run(["git", "-C", clone, "checkout", "-q", "--detach", ra.BASE_SHA], check=True)
        subprocess.run(["git", "-C", clone, "remote", "remove", "origin"], check=False)
        os.makedirs(os.path.join(self.root, "agents", "pi-rust", "flipt"))
        for agent in ("pi-original", "pi-rust"):
            with open(os.path.join(self.root, "agents", agent, "TASK.md"), "w", encoding="utf-8") as f:
                f.write("original\n")
        prep = os.path.join(self.root, "evidence", "preparation")
        os.makedirs(prep)
        self.order_path = os.path.join(prep, "draw-order.json")
        with open(self.order_path, "w", encoding="utf-8") as f:
            json.dump({"input": ["pi-original", "pi-rust"], "order": ["pi-original", "pi-rust"]}, f)
        os.makedirs(os.path.join(self.root, "evidence", "infra-tests"))
        self._patches = [
            mock.patch.object(ra, "TASK_ROOT", self.root),
            mock.patch.object(ra, "ORDER_FILE", self.order_path),
            mock.patch.object(ra, "LOCK_FILE", os.path.join(self.root, "evidence", "infra-tests", "run.lock")),
            mock.patch.object(ra, "build_cmd",
                              side_effect=lambda agent, run_dir: [ra.sys.executable, "-u", FAKE_AGENT]),
            # run-agent importa seu próprio módulo snapshot: o patch precisa atingir ra.snap
            mock.patch.object(ra.snap, "TASK_ROOT", self.root),
            mock.patch.object(ra.snap, "HOME_AGENT", self.home),
        ]
        for p in self._patches:
            p.start()
        with open(os.path.join(prep, "snapshot-baseline.json"), "w", encoding="utf-8") as f:
            json.dump(snap.take(root=self.root, home_agent=self.home), f)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.home, ignore_errors=True)
        os.environ.pop("FAKE_TOUCH_TASK", None)

    def _result(self, run_id, agent="pi-original"):
        path = os.path.join(self.root, "evidence", agent, "runs", run_id, "result.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _ws(self, agent="pi-original"):
        return os.path.join(self.root, "agents", agent, "flipt")

    def test_happy_path_writes_only_inside_workspace(self):
        rc = ra.main(["--agent", "pi-original", "--run-id", "it-ok"])
        self.assertEqual(rc, 0)
        r = self._result("it-ok")
        self.assertEqual(r["status"], "completed")
        self.assertTrue(r["isolation_ok"])
        self.assertAlmostEqual(r["usage"]["cost_total_usd"], 0.2)
        self.assertTrue(os.path.exists(os.path.join(self._ws(), "ok.txt")))
        run = os.path.join(self.root, "evidence", "pi-original", "runs", "it-ok")
        for name in ("snapshot-pre.json", "snapshot-post.json", "isolation-diff.json", "stdout.raw"):
            self.assertTrue(os.path.exists(os.path.join(run, name)), name)
        self.assertFalse(os.path.exists(ra.LOCK_FILE), "lock não foi liberado")

    def test_divergence_after_run_is_recorded_not_restored(self):
        os.environ["FAKE_TOUCH_TASK"] = "1"  # agente altera ../TASK.md (fora do workspace)
        rc = ra.main(["--agent", "pi-original", "--run-id", "it-div"])
        self.assertEqual(rc, 0)
        r = self._result("it-div")
        self.assertFalse(r["isolation_ok"])
        run = os.path.join(self.root, "evidence", "pi-original", "runs", "it-div")
        with open(os.path.join(run, "isolation-diff.json"), encoding="utf-8") as f:
            diff = json.load(f)
        self.assertIn("agents/pi-original/TASK.md", [d["path"] for d in diff["divergences"]])
        with open(os.path.join(self.root, "agents", "pi-original", "TASK.md"), encoding="utf-8") as f:
            self.assertIn("alterado pelo agente artificial", f.read(), "divergência não deve ser restaurada")

    def test_pre_run_divergence_refuses_start(self):
        with open(os.path.join(self.root, "agents", "pi-rust", "TASK.md"), "a", encoding="utf-8") as f:
            f.write("alterado antes do início\n")
        self.assertEqual(ra.main(["--agent", "pi-original", "--run-id", "it-pre"]), 5)
        self.assertFalse(os.path.exists(os.path.join(self._ws(), "ok.txt")), "agente não deveria ter iniciado")

    def test_dirty_workspace_refused(self):
        with open(os.path.join(self._ws(), "sujo.txt"), "w") as f:
            f.write("x")
        self.assertEqual(ra.main(["--agent", "pi-original", "--run-id", "it-dirty"]), 4)

    def test_out_of_order_after_first_completed(self):
        self.assertEqual(ra.main(["--agent", "pi-original", "--run-id", "it-first"]), 0)
        self.assertEqual(ra.main(["--agent", "pi-original", "--run-id", "it-second"]), 6)

    def test_lock_held_refuses(self):
        self.assertTrue(ra.acquire_lock())
        try:
            self.assertEqual(ra.main(["--agent", "pi-original", "--run-id", "it-lock"]), 7)
        finally:
            ra.release_lock()


if __name__ == "__main__":
    unittest.main()
