"""Driver-side handle for one worker process."""
import json, os, select, signal, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "..", ".venv", "bin", "python")
TTL = 2.0


class Proc:
    def __init__(self, impl, role, ttl=TTL, log_dir=None):
        log_dir = log_dir or os.path.join(HERE, "..", "work", "logs")
        os.makedirs(log_dir, exist_ok=True)
        self.role = role
        self.log = open(os.path.join(log_dir, f"worker-{impl}-{role}.log"), "ab")
        self.p = subprocess.Popen([PY, os.path.join(HERE, "worker.py"), impl, str(ttl)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                                  text=True, bufsize=1)

    def send(self, op, **kw):
        self.p.stdin.write(json.dumps({"op": op, **kw}) + "\n")
        self.p.stdin.flush()

    def recv(self, timeout=60):
        r, _, _ = select.select([self.p.stdout], [], [], timeout)
        if not r:
            raise TimeoutError(f"worker {self.role} silent for {timeout}s")
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError(f"worker {self.role} exited")
        return json.loads(line)

    def poll(self, timeout=0.0):
        """True if a reply is ready (non-blocking check, used to see whether a racing call finished)."""
        r, _, _ = select.select([self.p.stdout], [], [], timeout)
        return bool(r)

    def call(self, op, **kw):
        self.send(op, **kw)
        return self.recv()

    def suspend(self):
        os.kill(self.p.pid, signal.SIGSTOP)

    def resume(self):
        os.kill(self.p.pid, signal.SIGCONT)

    def close(self):
        try:
            self.p.stdin.close(); self.p.wait(timeout=10)
        except Exception:
            self.p.kill()
        self.log.close()
