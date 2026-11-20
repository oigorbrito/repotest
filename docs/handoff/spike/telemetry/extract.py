#!/usr/bin/env python3
"""Consolidate per-run telemetry for the Mingbird / little-coder spike.

For every run in a results.csv block directory this writes one JSON object
with: outcome (judge + exit + legitimacy), file changes, OOM overlap, and an
ordered list of events (tool calls, results, errors, rescues, text-only turns),
plus token totals when the harness records them.

Sources:
  * <block>/results.csv             runner output (one row per run)
  * <block>/<task>_<rep>.log         harness stdout/stderr
  * <block>/<task>_<rep>.pytest      judge output
  * <block>/<task>_<rep>.changes     `diff -rq` against the pristine task
  * little-coder session JSONL       ~/.pi/agent/sessions (tokens, tool calls)
  * oom_events_utc.txt               llama-server OOM timestamps (optional)

Usage:
  python3 extract.py --spike /home/user/spike --sessions /root/.pi/agent/sessions \
      --out docs/handoff/spike/telemetry/runs.jsonl
"""
import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
from collections import defaultdict

TEXT_CUT = 200


def cut(s, n=TEXT_CUT):
    s = (s or "").replace("\n", "\\n")
    return s if len(s) <= n else s[:n] + "…"


def parse_changes(path):
    """Return (modified_src, modified_tests, new_files)."""
    mod_src, mod_tests, new = [], [], []
    if not os.path.exists(path):
        return mod_src, mod_tests, new
    for ln in open(path, errors="replace"):
        if ln.startswith("Files "):
            name = os.path.basename(ln.split(" and ")[0].split()[-1])
            (mod_tests if name.startswith("test_") else mod_src).append(name)
        elif ln.startswith("Only in "):
            name = ln.rsplit(": ", 1)[-1].strip()
            if name != "todo.json":
                new.append(name)
    return mod_src, mod_tests, new


def mingbird_events(log_path):
    """Parse the Mingbird console log into ordered events and a context trace."""
    events, ctx_trace, pending_rescue = [], [], None
    api_errors = 0
    for ln in open(log_path, encoding="utf-8", errors="replace"):
        ln = ln.rstrip("\n")
        m = re.match(r"^\[ctx: (\d+)/(\d+) = (\d+)%\]", ln)
        if m:
            ctx_trace.append(int(m.group(1)))
            continue
        m = re.match(r"^\[(?:\d+)\] ⚡ 抢救到文本工具调用: (\S+)", ln)
        if m:
            pending_rescue = m.group(1)
            continue
        m = re.match(r"^\[(\d+)\|\+(\d+)s\] ⚙ (\S+)\s?(.*)$", ln)
        if m:
            idx, t, name, rest = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
            args, _, result = rest.partition(" -> ")
            is_error = ("tool error" in result) or ("[exit 1]" in result) or result.startswith("[error")
            events.append({"i": idx, "t_s": t, "type": "tool_call", "tool": name,
                           "args": cut(args), "result": cut(result),
                           "is_error": is_error, "rescued_from_text": pending_rescue == name})
            pending_rescue = None
            continue
        m = re.match(r"^\[(\d+)\|\+(\d+)s\] ✍", ln)
        if m:
            events.append({"i": int(m.group(1)), "t_s": int(m.group(2)), "type": "text_turn_without_tool"})
            continue
        if "API 4xx" in ln or "API error" in ln or "HTTP Error" in ln:
            api_errors += 1
            events.append({"type": "api_error", "text": cut(ln)})
    return events, ctx_trace, api_errors


def session_last_epoch(path):
    """Epoch seconds of the last timestamped record in a session file."""
    last = None
    for ln in open(path, encoding="utf-8", errors="replace"):
        try:
            o = json.loads(ln)
        except Exception:
            continue
        ts = o.get("timestamp") or (o.get("message") or {}).get("timestamp")
        if ts:
            last = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if isinstance(ts, str) else ts / 1000.0
    return last


def session_for(sessions_root, harness_tag, task, rep, model, run_end_epoch):
    """Each (model, task, rep) is exactly one run, so the workdir-name pattern plus the
    model recorded in the session identify it. If several sessions still match (for
    example a re-run), take the one whose last record is closest to the log end."""
    cands = []
    pat = f"{harness_tag}_{task}_{rep}_"
    for d in glob.glob(os.path.join(sessions_root, "*")):
        if pat not in os.path.basename(d):
            continue
        for f in glob.glob(os.path.join(d, "*.jsonl")):
            if model not in open(f, encoding="utf-8", errors="replace").read(20000):
                continue
            cands.append((abs((session_last_epoch(f) or 0) - run_end_epoch), f))
    return min(cands)[1] if cands else None


def littlecoder_events(session_path):
    events, totals = [], dict(input=0, output=0, cache_read=0, cache_write=0, turns=0)
    if not session_path:
        return events, totals, None
    t0 = None
    for ln in open(session_path, encoding="utf-8"):
        try:
            o = json.loads(ln)
        except Exception:
            continue
        if o.get("type") != "message":
            continue
        msg = o.get("message") or {}
        ts = msg.get("timestamp")
        if ts and t0 is None:
            t0 = ts
        rel = round((ts - t0) / 1000, 1) if (ts and t0) else None
        role = msg.get("role")
        if role == "assistant":
            u = msg.get("usage") or {}
            totals["turns"] += 1
            totals["input"] += u.get("input", 0)
            totals["output"] += u.get("output", 0)
            totals["cache_read"] += u.get("cacheRead", 0)
            totals["cache_write"] += u.get("cacheWrite", 0)
            calls = [p for p in (msg.get("content") or []) if isinstance(p, dict) and p.get("type") == "toolCall"]
            for c in calls:
                events.append({"t_s": rel, "type": "tool_call", "tool": c.get("name"),
                               "args": cut(json.dumps(c.get("arguments"), ensure_ascii=False))})
            if not calls:
                events.append({"t_s": rel, "type": "text_turn_without_tool",
                               "stop": msg.get("stopReason")})
        elif role == "toolResult":
            text = " ".join(p.get("text", "") for p in (msg.get("content") or [])
                            if isinstance(p, dict) and p.get("type") == "text")
            events.append({"t_s": rel, "type": "tool_result", "tool": msg.get("toolName"),
                           "is_error": bool(msg.get("isError")), "result": cut(text)})
    model = None
    for ln in open(session_path, encoding="utf-8"):
        if '"model_change"' in ln:
            model = json.loads(ln).get("modelId") or model
    return events, totals, session_path


def load_oom(path):
    if not path or not os.path.exists(path):
        return []
    return [dt.datetime.strptime(x.strip(), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
            for x in open(path) if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spike", required=True)
    ap.add_argument("--sessions", default="/root/.pi/agent/sessions")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    oom = load_oom(os.path.join(args.spike, "r4", "oom_events_utc.txt"))
    out_rows = []
    for csvf in sorted(glob.glob(os.path.join(args.spike, "r4", "*", "results.csv"))):
        block_dir = os.path.dirname(csvf)
        block = os.path.basename(block_dir)
        harness = "mingbird" if block.startswith("mb_") else "littlecoder"
        harness_tag = "r4_littlecoder" if harness == "littlecoder" else "r4_mingbird"
        for r in csv.DictReader(open(csvf)):
            task, rep, model = r["task"], r["rep"], r["model"]
            base = os.path.join(block_dir, f"{task}_{rep}")
            log_mtime = os.path.getmtime(base + ".log")
            end = dt.datetime.fromtimestamp(log_mtime, dt.timezone.utc)
            start = end - dt.timedelta(seconds=int(r["seconds"]))
            oom_overlap = any(start <= o <= end for o in oom)
            src, tests_mod, new = parse_changes(base + ".changes")
            judge_last = ""
            if os.path.exists(base + ".pytest"):
                lines = open(base + ".pytest", errors="replace").read().strip().splitlines()
                judge_last = lines[-1] if lines else ""
            if harness == "mingbird":
                events, ctx_trace, api_errors = mingbird_events(base + ".log")
                tokens = None
                session = None
                ctx_peak = max(ctx_trace) if ctx_trace else None
            else:
                session = session_for(args.sessions, harness_tag, task, rep, model, log_mtime)
                events, tokens, session = littlecoder_events(session)
                api_errors = sum(1 for e in events if e.get("type") == "api_error")
                ctx_trace, ctx_peak = [], None
            tool_calls = [e for e in events if e.get("type") == "tool_call"]
            rec = {
                "block": block, "harness": harness, "model": model, "task": task, "rep": int(rep),
                "exit": int(r["exit"]), "pass": int(r["pass"]), "legit": int(r["legit"]),
                "seconds": int(r["seconds"]),
                "outcome": ("legit_pass" if r["legit"] == "1" else
                            "pass_tampered" if r["pass"] == "1" else
                            "harness_stop" if r["exit"] == "1" else
                            "stopped_itself" if r["exit"] == "0" else "timeout"),
                "judge_last_line": judge_last,
                "changes": {"src_modified": src, "tests_modified": tests_mod, "new_files": new},
                "oom_overlap": oom_overlap,
                "totals": {"tool_calls": len(tool_calls),
                           "tool_errors": sum(1 for e in events if e.get("is_error")),
                           "rescued_from_text": sum(1 for e in events if e.get("rescued_from_text")),
                           "text_turns_without_tool": sum(1 for e in events if e.get("type") == "text_turn_without_tool"),
                           "api_errors": api_errors,
                           "ctx_peak_tokens": ctx_peak,
                           "tokens": tokens},
                "session_file": os.path.basename(session) if session else None,
                "events": events,
            }
            out_rows.append(rec)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for rec in out_rows:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {len(out_rows)} runs to {args.out}")


if __name__ == "__main__":
    main()
