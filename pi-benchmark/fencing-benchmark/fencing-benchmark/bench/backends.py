"""Fencing candidates behind one async interface. Each runs inside a worker process (see worker.py).

  statepact-redis : StatePact 0.1.2 RedisBackend — the real PyPI code, unmodified.
  statepact-pg    : StatePact 0.1.2 PostgresBackend — the real PyPI code, unmodified.
  zk-redis-lua    : ZooKeeper 3.9.1 sequential-ephemeral lock (token = sequence number) and a Redis Lua
                    script that validates the token and writes in ONE atomic EVAL. REIMPLEMENTED from the
                    benchmark specification: no reference code exists in the accessible repositories.
  etcd-pg         : etcd 3.4.30 lease (lock key, token = create revision) and PostgreSQL 16 fence row; the
                    token is validated and the write applied in ONE transaction that takes the same row lock
                    as the lease registration. REIMPLEMENTED from the benchmark specification.

Every backend exposes: lock1/lock2 (acquire, split in two steps so races can be staged), release, commit,
read, version, switch (failover reconnect, Redis only) and close.
"""
import asyncio, base64, json, time, urllib.request
import redis as redis_sync
import psycopg
from kazoo.client import KazooClient
from kazoo.exceptions import NoNodeError

ZK_HOSTS = "127.0.0.1:2181"
ETCD_URL = "http://127.0.0.1:2379"
PG_DSN = {"statepg": "postgresql://postgres@127.0.0.1:5433/statepg",   # instance "pg"
          "etcdpg": "postgresql://postgres@127.0.0.1:5434/etcdpg"}      # instance "pg2"


class Held(Exception):
    """The lease is currently held by someone else (a normal outcome, not an error)."""


class Backend:
    name = "?"

    async def open(self, ttl):
        raise NotImplementedError

    async def setup(self, res):
        raise NotImplementedError

    async def lock1(self, res, owner, ttl):
        raise NotImplementedError

    async def lock2(self, res, owner, token):
        return None

    async def unlock_partial(self, res, owner):
        return None

    async def acquire(self, res, owner, ttl):
        tok = await self.lock1(res, owner, ttl)
        try:
            await self.lock2(res, owner, tok)
        except Exception:
            await self.unlock_partial(res, owner)
            raise
        return tok

    async def release(self, res, owner):
        raise NotImplementedError

    async def commit(self, res, owner, token, key, value, idem, fenced):
        raise NotImplementedError

    async def read(self, res, key):
        raise NotImplementedError

    async def version(self, res):
        raise NotImplementedError

    async def switch(self, port):
        raise NotImplementedError(f"{self.name} has no failover path")

    async def close(self):
        return None


# ---------------------------------------------------------------- StatePact (real code) ----------
class StatePactBackend(Backend):
    def __init__(self, kind, redis_port=6400):
        self.kind = kind
        self.redis_port = redis_port
        self.name = "statepact-redis" if kind == "redis" else "statepact-pg"

    async def _connect(self):
        from statepact import TransactionManager
        from statepact.storage.redis import RedisBackend
        from statepact.storage.postgres import PostgresBackend
        if self.kind == "redis":
            self.be = await RedisBackend.connect(f"redis://127.0.0.1:{self.redis_port}/0", prefix="fb-sp")
        else:
            self.be = await PostgresBackend.connect(PG_DSN["statepg"], min_size=1, max_size=4)
        self.mgr = TransactionManager(backend=self.be)
        self.leases = {}
        self.objs = {}

    async def open(self, ttl):
        await self._connect()

    def _obj(self, res):
        if res not in self.objs:
            self.objs[res] = self.mgr.resource(res, {"v": None})
        return self.objs[res]

    async def setup(self, res):
        await self._obj(res).ensure(self.mgr)

    async def lock1(self, res, owner, ttl):
        from statepact import LeaseNotAvailableError
        try:
            lease = await self.mgr.lease(res, owner=owner, ttl_seconds=ttl)
        except LeaseNotAvailableError:
            raise Held()
        self.leases[(res, owner)] = lease
        return lease.token

    async def lock1_direct(self, res, owner, ttl):
        """backend.acquire_lease() called directly: skips TransactionManager.lease()'s ensure_resource(),
        which is the only step that takes the commit advisory lock."""
        from statepact import LeaseNotAvailableError
        try:
            lease = await self.be.acquire_lease(res, owner, ttl)
        except LeaseNotAvailableError:
            raise Held()
        self.leases[(res, owner)] = lease
        return lease.token

    async def release(self, res, owner):
        lease = self.leases.pop((res, owner), None)
        if lease is not None:
            await self.be.release_lease(lease)

    async def commit(self, res, owner, token, key, value, idem, fenced):
        from statepact import LeaseLostError
        from statepact.core.exceptions import ConflictError
        try:
            async with self.mgr.session(agent_id=owner, resources=[self._obj(res)],
                                        fence=(token if fenced else None),
                                        idempotency_key=idem) as s:
                await s.write(key, value)
                cr = await s.commit()
            return {"status": "ok", "version": cr.commit_version, "replayed": bool(cr.replayed)}
        except LeaseLostError:
            return {"status": "rejected"}
        except ConflictError as e:
            return {"status": "conflict", "detail": type(e).__name__}

    async def read(self, res, key):
        return await self._obj(res).read(key)

    async def version(self, res):
        if self.kind == "redis":
            return int(await self.be._redis.get(f"{self.be._prefix}:seq") or 0)
        return int(await self.be._pool.fetchval("SELECT seq FROM statepact_meta WHERE id=1"))

    async def switch(self, port):
        assert self.kind == "redis"
        await self.close()
        self.redis_port = port
        await self._connect()

    async def close(self):
        try:
            await self.mgr.close()
        except Exception:
            pass


# ---------------------------------------------------------------- ZooKeeper + Redis Lua ----------
RAISE_LUA = """
local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
local tok = tonumber(ARGV[1])
if tok > cur then redis.call('SET', KEYS[1], tok) end
return tok
"""

# One atomic EVAL: idempotency replay, token validation against the stored high-water mark, and the write.
COMMIT_LUA = """
local has_idem = ARGV[5] ~= ''
if has_idem then
  local prev = redis.call('GET', KEYS[3])
  if prev then
    local d = cjson.decode(prev)
    d.replayed = true
    return cjson.encode(d)
  end
end
if ARGV[2] == '1' then
  local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
  local tok = tonumber(ARGV[1])
  if tok < cur then return cjson.encode({status = 'rejected', current = cur}) end
  if tok > cur then redis.call('SET', KEYS[1], tok) end
end
local seq = redis.call('INCR', KEYS[2])
redis.call('HSET', KEYS[4], ARGV[3], ARGV[4])
local out = cjson.encode({status = 'ok', version = seq, replayed = false})
if has_idem then redis.call('SET', KEYS[3], out) end
return out
"""


class ZkRedisBackend(Backend):
    name = "zk-redis-lua"

    def __init__(self, redis_port=6402, zk_hosts=ZK_HOSTS):
        self.redis_port = redis_port
        self.zk_hosts = zk_hosts

    async def open(self, ttl):
        # ZooKeeper session timeout == lease TTL: a suspended process loses its ephemeral lock node.
        self.ttl = ttl
        self.zk = KazooClient(hosts=self.zk_hosts, timeout=ttl)
        self.zk.start(timeout=20)
        self._connect_redis(self.redis_port)
        self.nodes = {}

    def _connect_redis(self, port):
        self.redis_port = port
        self.r = redis_sync.Redis(host="127.0.0.1", port=port, decode_responses=True,
                                  socket_timeout=3, socket_connect_timeout=3)
        self.raise_s = self.r.register_script(RAISE_LUA)
        self.commit_s = self.r.register_script(COMMIT_LUA)

    def _k(self, res, part):
        return f"fb-zkr:{res}:{part}"

    def _zk_ready(self):
        """A suspended worker can wake with an expired session; kazoo then loops on it. Start a fresh session."""
        from kazoo.protocol.states import KazooState
        if self.zk.state != KazooState.CONNECTED:
            try:
                self.zk.stop(); self.zk.close()
            except Exception:
                pass
            self.zk = KazooClient(hosts=self.zk_hosts, timeout=self.ttl)
            self.zk.start(timeout=20)
        return self.zk

    async def setup(self, res):
        self._zk_ready().ensure_path(f"/bench/zkr/{res}")

    async def lock1(self, res, owner, ttl):
        base = f"/bench/zkr/{res}"
        self._zk_ready().ensure_path(base)
        node = self.zk.create(f"{base}/lock-", value=owner.encode(), ephemeral=True, sequence=True)
        name = node.rsplit("/", 1)[1]
        kids = sorted(self.zk.get_children(base))
        if kids[0] != name:                       # not the lowest sequence: someone else holds the lock
            self.zk.delete(node)
            raise Held()
        self.nodes[(res, owner)] = node
        return int(name.rsplit("lock-", 1)[1]) + 1  # ZK sequence (monotonic); +1 so tokens start at 1 like StatePact

    async def lock2(self, res, owner, token):
        self.raise_s(keys=[self._k(res, "fence")], args=[token])   # register the new high-water mark

    async def unlock_partial(self, res, owner):
        node = self.nodes.pop((res, owner), None)
        if node:
            try:
                self.zk.delete(node)
            except NoNodeError:
                pass

    async def release(self, res, owner):
        await self.unlock_partial(res, owner)

    async def commit(self, res, owner, token, key, value, idem, fenced):
        raw = self.commit_s(keys=[self._k(res, "fence"), self._k(res, "seq"),
                                  self._k(res, f"idem:{idem}" if idem else "idem-none"),
                                  self._k(res, "data")],
                            args=[token, "1" if fenced else "0", key, json.dumps(value), idem or ""])
        return json.loads(raw)

    async def read(self, res, key):
        raw = self.r.hget(self._k(res, "data"), key)
        return None if raw is None else json.loads(raw)

    async def version(self, res):
        return int(self.r.get(self._k(res, "seq")) or 0)

    async def switch(self, port):
        self._connect_redis(port)

    async def close(self):
        try:
            self.zk.stop(); self.zk.close()
        except Exception:
            pass


# ---------------------------------------------------------------- etcd + PostgreSQL --------------
def _etcd(path, body):
    req = urllib.request.Request(ETCD_URL + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _b64(s):
    return base64.b64encode(s.encode()).decode()


class EtcdPgBackend(Backend):
    """variant 'v2' (the candidate): the etcd grant happens INSIDE the transaction that holds the fence row
    lock, the same lock commit() takes, so a grant and a concurrent commit are serialized.
    variant 'v1' (ablation, kept as evidence): the grant happens before the lock is taken, leaving a window."""

    def __init__(self, variant="v2"):
        self.variant = variant
        self.name = "etcd-pg" if variant == "v2" else "etcd-pg-v1"
        self.conn = None
        self.lease_ids = {}
        self._txn = False

    async def open(self, ttl):
        self.ttl = int(ttl)            # etcd lease TTLs are whole seconds
        self._pg()

    def _pg(self):
        if self.conn is None or self.conn.closed:
            self.conn = psycopg.connect(PG_DSN["etcdpg"], autocommit=True, connect_timeout=5)
            self._txn = False
        return self.conn

    def _lock_key(self, res):
        return f"/bench/etcd-lock/{res}"

    async def setup(self, res):
        c = self._pg()
        with c.transaction():
            c.execute("""CREATE TABLE IF NOT EXISTS fb_fence (res text PRIMARY KEY, fence bigint NOT NULL DEFAULT 0,
                         seq bigint NOT NULL DEFAULT 0)""")
            c.execute("""CREATE TABLE IF NOT EXISTS fb_kv (res text NOT NULL, key text NOT NULL, value text,
                         version bigint NOT NULL, PRIMARY KEY (res, key))""")
            c.execute("""CREATE TABLE IF NOT EXISTS fb_idem (id text PRIMARY KEY, result text NOT NULL)""")
            c.execute("INSERT INTO fb_fence (res) VALUES (%s) ON CONFLICT DO NOTHING", (res,))

    def _etcd_grant(self, res, owner):
        lease = _etcd("/v3/lease/grant", {"TTL": str(self.ttl), "ID": "0"})
        lid = lease["ID"]
        key = self._lock_key(res)
        txn = _etcd("/v3/kv/txn", {
            "compare": [{"key": _b64(key), "target": "CREATE", "result": "EQUAL", "create_revision": "0"}],
            "success": [{"request_put": {"key": _b64(key), "value": _b64(owner), "lease": lid}}],
            "failure": [{"request_range": {"key": _b64(key)}}]})
        if not txn.get("succeeded"):
            _etcd("/v3/lease/revoke", {"ID": lid})
            raise Held()
        self.lease_ids[(res, owner)] = lid
        return int(txn["header"]["revision"])     # etcd revision: strictly increasing across the cluster

    async def lock1(self, res, owner, ttl):
        c = self._pg()
        if self.variant == "v1":
            return self._etcd_grant(res, owner)
        try:
            c.execute("BEGIN")
            self._txn = True
            c.execute("INSERT INTO fb_fence (res) VALUES (%s) ON CONFLICT DO NOTHING", (res,))
            c.execute("SELECT fence FROM fb_fence WHERE res=%s FOR UPDATE", (res,)).fetchone()
            return self._etcd_grant(res, owner)
        except Held:
            c.execute("ROLLBACK"); self._txn = False
            raise
        except Exception:
            self.conn = None
            raise

    async def lock2(self, res, owner, token):
        c = self._pg()
        if self.variant == "v1":
            try:
                with c.transaction():
                    c.execute("INSERT INTO fb_fence (res) VALUES (%s) ON CONFLICT DO NOTHING", (res,))
                    fence = c.execute("SELECT fence FROM fb_fence WHERE res=%s FOR UPDATE", (res,)).fetchone()[0]
                    if token > fence:
                        c.execute("UPDATE fb_fence SET fence=%s WHERE res=%s", (token, res))
            except Exception:
                self.conn = None
                raise
            return
        try:
            c.execute("UPDATE fb_fence SET fence=GREATEST(fence, %s) WHERE res=%s", (token, res))
            c.execute("COMMIT"); self._txn = False
        except Exception:
            self.conn = None
            raise

    async def unlock_partial(self, res, owner):
        if self.variant == "v2" and self._txn and self.conn is not None and not self.conn.closed:
            self.conn.execute("ROLLBACK"); self._txn = False
        lid = self.lease_ids.pop((res, owner), None)
        if lid:
            _etcd("/v3/lease/revoke", {"ID": lid})

    async def release(self, res, owner):
        lid = self.lease_ids.pop((res, owner), None)
        if lid:
            _etcd("/v3/lease/revoke", {"ID": lid})

    async def commit(self, res, owner, token, key, value, idem, fenced):
        c = self._pg()
        try:
            with c.transaction():
                fence, seq = c.execute("SELECT fence, seq FROM fb_fence WHERE res=%s FOR UPDATE",
                                       (res,)).fetchone()
                if idem:
                    row = c.execute("SELECT result FROM fb_idem WHERE id=%s", (idem,)).fetchone()
                    if row:
                        d = json.loads(row[0]); d["replayed"] = True
                        return d
                if fenced and token < fence:
                    raise _Reject(fence)
                if fenced and token > fence:
                    c.execute("UPDATE fb_fence SET fence=%s WHERE res=%s", (token, res))
                seq += 1
                c.execute("UPDATE fb_fence SET seq=%s WHERE res=%s", (seq, res))
                c.execute("""INSERT INTO fb_kv (res, key, value, version) VALUES (%s,%s,%s,%s)
                             ON CONFLICT (res, key) DO UPDATE SET value=EXCLUDED.value, version=EXCLUDED.version""",
                          (res, key, json.dumps(value), seq))
                out = {"status": "ok", "version": seq, "replayed": False}
                if idem:
                    c.execute("INSERT INTO fb_idem (id, result) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                              (idem, json.dumps(out)))
            return out
        except _Reject as r:
            return {"status": "rejected", "current": r.fence}
        except Exception:
            self.conn = None
            raise

    async def read(self, res, key):
        row = self._pg().execute("SELECT value FROM fb_kv WHERE res=%s AND key=%s", (res, key)).fetchone()
        return None if row is None else json.loads(row[0])

    async def version(self, res):
        return int(self._pg().execute("SELECT seq FROM fb_fence WHERE res=%s", (res,)).fetchone()[0])

    async def close(self):
        if self.conn is not None:
            self.conn.close()


class _Reject(Exception):
    def __init__(self, fence):
        self.fence = fence


def make(impl):
    if impl == "statepact-redis":
        return StatePactBackend("redis")
    if impl == "statepact-pg":
        return StatePactBackend("pg")
    if impl == "zk-redis-lua":
        return ZkRedisBackend()
    if impl == "etcd-pg":
        return EtcdPgBackend("v2")
    if impl == "etcd-pg-v1":
        return EtcdPgBackend("v1")
    raise ValueError(impl)
