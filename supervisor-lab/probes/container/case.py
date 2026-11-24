import json, os, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer

# Container probe. Runs the real orcacode binary against a scripted local model.
# Approvals: every approval_request is answered "allow" so we measure what the
# shell/process tools can DO once approved, which is the boundary in question.

CASE = os.environ["CASE"]
PORT = 8099
DONE = "done"

CASES = {
    # Contained? Writes inside /work; writes to container root; host mount visibility.
    "contain": {
        "tools": "shell",
        "script": [
            {"call": ["shell", {"command": "printf x > /work/inside.txt; printf y > /root_probe.txt; echo WRITE_ROOT_OK; test -e /mnt/c && echo HOST_MNT_VISIBLE || echo HOST_MNT_HIDDEN; ls / | tr '\\n' ' '"}]},
            {"text": DONE},
        ],
    },
    # Network: shell tries an outbound TCP connect to a public address.
    "network": {
        "tools": "shell",
        "script": [
            {"call": ["shell", {"command": "timeout 5 bash -c 'echo > /dev/tcp/1.1.1.1/53' && echo NET_OK || echo NET_BLOCKED"}]},
            {"text": DONE},
        ],
    },
    # Descendants: a background grandchild appends to a workspace file for ~60s.
    # The host stops the container mid-run; we check whether growth stops.
    "descendants": {
        "tools": "shell",
        "script": [
            {"call": ["shell", {"command": "(for i in $(seq 1 300); do printf x >> /work/grand.txt; sleep 0.2; done) & wait"}]},
            {"text": DONE},
        ],
    },
}

CASES["profile"] = {
    # Recommended profile: no process tool, shell+write_file gated, network off (run with --network none).
    "tools": "shell,write_file,edit_file",
    "script": [
        {"call": ["process", {"action": "spawn", "command": "printf x > /work/proc.txt"}]},
        {"call": ["shell", {"command": "printf ok > /work/allowed.txt; timeout 5 bash -c 'echo > /dev/tcp/1.1.1.1/53' && echo NET_OK || echo NET_BLOCKED"}]},
        {"text": DONE},
    ],
}

cfg = CASES[CASE]
lock = threading.Lock()
calls = {"n": 0}


def sse(reply, step):
    if "call" in reply:
        name, args = reply["call"]
        chunks = [
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_%d" % step, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
        ]
    else:
        chunks = [
            {"choices": [{"index": 0, "delta": {"content": reply["text"]}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
    return "".join("data: %s\n\n" % json.dumps(c) for c in chunks) + "data: [DONE]\n\n"


class Model(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", "0"))
        self.rfile.read(n)
        with lock:
            step = calls["n"]
            calls["n"] += 1
        reply = cfg["script"][min(step, len(cfg["script"]) - 1)]
        payload = sse(reply, step).encode()
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(payload)))
        self.send_header("connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


def main():
    srv = HTTPServer(("127.0.0.1", PORT), Model)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs("/tmp/home", exist_ok=True)
    with open("/tmp/p.txt", "w") as f:
        f.write("probe")
    env = {"PATH": os.environ["PATH"], "HOME": "/tmp/home", "ORCA_CONFIG_DIR": "/tmp/home/config"}
    args = ["/probe/bin/orcacode", "--base-url", "http://127.0.0.1:%d/v1" % PORT, "--model", "fake",
            "--no-prompt-cache", "--prompt-file", "/tmp/p.txt", "--json", "--no-session",
            "--approvals", "stdio", "--tools", cfg["tools"]]
    p = subprocess.Popen(args, cwd="/work", stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=env, text=True)
    t0 = time.time()
    approvals = 0
    for line in p.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "approval_request":
            approvals += 1
            p.stdin.write(json.dumps({"type": "approval", "id": ev["id"], "decision": "allow"}) + "\n")
            p.stdin.flush()
        if ev.get("type") == "tool_result":
            print("TOOL_RESULT %s" % json.dumps(ev.get("output"))[:700], flush=True)
        if ev.get("type") == "summary":
            print("SUMMARY status=%s" % ev.get("status"), flush=True)
    p.stdin.close()
    rc = p.wait()
    err = p.stderr.read()
    print("CASE %s approvals=%d rc=%s secs=%.1f" % (CASE, approvals, rc, time.time() - t0), flush=True)
    if err.strip():
        print("STDERR %s" % err.strip()[:400], flush=True)


if __name__ == "__main__":
    main()
