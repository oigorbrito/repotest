#!/usr/bin/env python3
"""Real-service manager for the fencing benchmark.

Starts Redis (2 pairs, AOF always), ZooKeeper 3.9.1, etcd 3.4.30 and PostgreSQL 16 from the
Ubuntu packages, each with its own configuration and data dir under work/. Every service runs in
its own process group so `kill` (SIGKILL of the whole group) simulates a hard crash of the coordinator.

Usage: svc.py init | start NAME... | kill NAME | stop-all | status
"""
import json, os, signal, socket, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
PIDS = WORK / "pids"
LOGS = WORK / "logs"
PG_BIN = "/usr/lib/postgresql/16/bin"
ZK_HOME = "/usr/share/zookeeper"
PG_DATA = WORK / "pg" / "data"
PG_PORT = 5433
PG2_DATA = WORK / "pg2" / "data"
PG2_PORT = 5434
ZK_PORT = 2181
ETCD_PORT = 2379

def _as_postgres(*cmd):
    # setpriv execs the target, so the recorded pid/pgid is the postgres process itself.
    return ["setpriv", "--reuid=postgres", "--regid=postgres", "--init-groups", *cmd]

def _pg_cmd(data, port, name):
    return _as_postgres(f"{PG_BIN}/postgres", "-D", str(data), "-p", str(port),
                        "-k", str(WORK / name / "sock"), "-c", "listen_addresses=127.0.0.1",
                        "-c", "max_connections=200", "-c", "fsync=on", "-c", "synchronous_commit=on")

def _redis(port, replicaof=None):
    d = WORK / f"redis-{port}"
    d.mkdir(parents=True, exist_ok=True)
    cmd = ["redis-server", "--port", str(port), "--bind", "127.0.0.1", "--dir", str(d),
           "--appendonly", "yes", "--appendfsync", "always", "--save", "", "--protected-mode", "no"]
    if replicaof:
        cmd += ["--replicaof", "127.0.0.1", str(replicaof)]
    return cmd

SERVICES = {
    # name: (command, port used for readiness)
    "redis-6400": (lambda: _redis(6400), 6400),              # group 1 master (StatePact Redis)
    "redis-6401": (lambda: _redis(6401, 6400), 6401),        # group 1 replica (failover test)
    "redis-6402": (lambda: _redis(6402), 6402),              # group 2 master (ZooKeeper + Redis Lua)
    "redis-6403": (lambda: _redis(6403, 6402), 6403),        # group 2 replica (failover test)
    "zk": (lambda: [f"{ZK_HOME}/bin/zkServer.sh", "start-foreground", str(WORK / "zk/conf/zoo.cfg")], ZK_PORT),
    "etcd": (lambda: ["etcd", "--name", "bench", "--data-dir", str(WORK / "etcd/data"),
                      "--listen-client-urls", f"http://127.0.0.1:{ETCD_PORT}",
                      "--advertise-client-urls", f"http://127.0.0.1:{ETCD_PORT}",
                      "--listen-peer-urls", "http://127.0.0.1:2380",
                      "--initial-advertise-peer-urls", "http://127.0.0.1:2380",
                      "--initial-cluster", "bench=http://127.0.0.1:2380",
                      "--initial-cluster-token", "bench", "--initial-cluster-state", "new"], ETCD_PORT),
    "pg": (lambda: _pg_cmd(PG_DATA, PG_PORT, "pg"), PG_PORT),        # StatePact PostgreSQL instance
    "pg2": (lambda: _pg_cmd(PG2_DATA, PG2_PORT, "pg2"), PG2_PORT),    # etcd + PostgreSQL instance
}

def _port_open(port, timeout=0.2):
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0

def wait_ready(name, timeout=60):
    port = SERVICES[name][1]
    end = time.time() + timeout
    while time.time() < end:
        if _port_open(port):
            if name.startswith("redis"):
                try:
                    out = subprocess.run(["redis-cli", "-p", str(port), "ping"], capture_output=True, text=True, timeout=2).stdout
                    if out.strip() == "PONG":
                        return True
                except subprocess.TimeoutExpired:
                    pass
            elif name == "etcd":
                if subprocess.run(["curl", "-sf", f"http://127.0.0.1:{ETCD_PORT}/health"], capture_output=True).returncode == 0:
                    return True
            else:
                return True
        time.sleep(0.1)
    raise RuntimeError(f"service {name} not ready after {timeout}s (see {LOGS / (name + '.log')})")

def start(name):
    PIDS.mkdir(parents=True, exist_ok=True); LOGS.mkdir(parents=True, exist_ok=True)
    pidfile = PIDS / f"{name}.json"
    if pidfile.exists() and _port_open(SERVICES[name][1]):
        return
    if name in ("pg", "pg2") and not _port_open(SERVICES[name][1]):
        data = PG_DATA if name == "pg" else PG2_DATA
        (data / "postmaster.pid").unlink(missing_ok=True)   # left by a SIGKILLed postmaster
        sock = WORK / ("pg" if name == "pg" else "pg2") / "sock"
        for stale in sock.glob(f".s.PGSQL.{SERVICES[name][1]}*"):
            stale.unlink(missing_ok=True)                    # socket + lock file of the dead postmaster
    cmd = SERVICES[name][0]()
    env = dict(os.environ)
    if name == "zk":
        env["ZOO_LOG_DIR"] = str(LOGS)
        env["ZOO_LOG4J_PROP"] = "INFO,ROLLINGFILE"
    log = open(LOGS / f"{name}.log", "ab")
    p = subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True, env=env, cwd=str(WORK))
    # start_new_session=True makes the child a session/group leader, so its pgid is its own pid.
    # (Reading os.getpgid(p.pid) here races with the child's setsid() and can return the PARENT's group,
    # which would make kill() take down unrelated services.)
    pidfile.write_text(json.dumps({"pid": p.pid, "pgid": p.pid, "cmd": cmd}))
    wait_ready(name)

def kill(name):
    """Hard crash: SIGKILL the whole process group (no graceful shutdown, no fsync on exit)."""
    pidfile = PIDS / f"{name}.json"
    if not pidfile.exists():
        return
    info = json.loads(pidfile.read_text())
    try:
        os.killpg(info["pgid"], signal.SIGKILL)
    except ProcessLookupError:
        pass
    deadline = time.time() + 10
    while time.time() < deadline and _port_open(SERVICES[name][1]):
        time.sleep(0.05)
    pidfile.unlink(missing_ok=True)

def restart(name):
    kill(name)
    start(name)

def _init_pg(name, data, port, dbs):
    root = WORK / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "sock").mkdir(parents=True, exist_ok=True)
    subprocess.run(["chown", "-R", "postgres:postgres", str(root)], check=True)
    if not (data / "PG_VERSION").exists():
        r = subprocess.run(_as_postgres(f"{PG_BIN}/initdb", "-D", str(data), "-U", "postgres",
                                        "--auth=trust", "-E", "UTF8"), capture_output=True, text=True)
        (LOGS).mkdir(parents=True, exist_ok=True)
        (LOGS / f"initdb-{name}.log").write_text(r.stdout + r.stderr)
        if r.returncode != 0:
            raise RuntimeError(f"initdb failed for {name}: see {LOGS / ('initdb-' + name + '.log')}")
    start(name)
    for db in dbs:
        exists = subprocess.run(["psql", f"postgresql://postgres@127.0.0.1:{port}/postgres", "-tAc",
                                 f"SELECT 1 FROM pg_database WHERE datname='{db}'"],
                                capture_output=True, text=True).stdout.strip()
        if exists != "1":
            subprocess.run(["psql", f"postgresql://postgres@127.0.0.1:{port}/postgres", "-c",
                            f"CREATE DATABASE {db}"], check=True, capture_output=True)

def init():
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "zk/conf").mkdir(parents=True, exist_ok=True)
    (WORK / "zk/conf/zoo.cfg").write_text(
        f"tickTime=500\ninitLimit=10\nsyncLimit=5\ndataDir={WORK}/zk/data\n"
        f"clientPort={ZK_PORT}\nadmin.enableServer=false\n")
    (WORK / "etcd").mkdir(parents=True, exist_ok=True)
    _init_pg("pg", PG_DATA, PG_PORT, ["statepg"])
    _init_pg("pg2", PG2_DATA, PG2_PORT, ["etcdpg"])

def stop_all():
    for name in list(SERVICES):
        kill(name)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "init":
        init(); print("init ok")
    elif cmd == "start":
        for n in sys.argv[2:]:
            start(n); print(f"{n} ready")
    elif cmd == "kill":
        kill(sys.argv[2]); print(f"{sys.argv[2]} killed")
    elif cmd == "restart":
        restart(sys.argv[2]); print(f"{sys.argv[2]} restarted")
    elif cmd == "stop-all":
        stop_all(); print("all stopped")
    elif cmd == "status":
        for n in SERVICES:
            print(f"{n:12s} port={SERVICES[n][1]} up={_port_open(SERVICES[n][1])}")
    else:
        sys.exit(__doc__)
