"""Client process (role A or B). One JSON request per stdin line, one JSON reply per stdout line.

Running A and B as separate OS processes lets the harness SIGSTOP a writer while it holds a lease
(the suspended-writer scenario) and race two real processes against the coordinator.
"""
import asyncio, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import backends

# Keep the protocol channel clean: library prints go to stderr (the worker log).
_proto = os.fdopen(os.dup(1), "w", buffering=1)
os.dup2(2, 1)


async def dispatch(be, op, a):
    if op == "setup":
        await be.setup(a["res"]); return {}
    if op == "acquire":
        return {"token": await be.acquire(a["res"], a["owner"], a["ttl"])}
    if op == "lock1":
        return {"token": await be.lock1(a["res"], a["owner"], a["ttl"])}
    if op == "lock1_direct":
        return {"token": await be.lock1_direct(a["res"], a["owner"], a["ttl"])}
    if op == "lock2":
        await be.lock2(a["res"], a["owner"], a["token"]); return {}
    if op == "release":
        await be.release(a["res"], a["owner"]); return {}
    if op == "commit":
        return await be.commit(a["res"], a["owner"], a["token"], a["key"], a["value"],
                               a.get("idem"), a.get("fenced", True))
    if op == "read":
        return {"value": await be.read(a["res"], a["key"])}
    if op == "version":
        return {"version": await be.version(a["res"])}
    if op == "switch":
        await be.switch(a["port"]); return {}
    raise ValueError(f"unknown op {op}")


async def main():
    impl, ttl = sys.argv[1], float(sys.argv[2])
    be = backends.make(impl)
    await be.open(ttl)
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        req = json.loads(line)
        op = req.pop("op")
        t0 = time.perf_counter()
        try:
            res = await dispatch(be, op, req)
            out = {"ok": True, **res}
        except backends.Held:
            out = {"ok": False, "held": True}
        except Exception as e:  # infrastructure failure: the driver decides whether to retry
            out = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
        out["ms"] = round((time.perf_counter() - t0) * 1000, 3)
        _proto.write(json.dumps(out) + "\n")
    await be.close()


if __name__ == "__main__":
    asyncio.run(main())
