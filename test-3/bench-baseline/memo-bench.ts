// Teste 3 — FineCode runtime.memo(): benchmark com processos reais.
// Idêntico em lógica ao Teste 2, acrescido de pausas controladas (takeover por outra instância).
// Este arquivo é copiado para bench-baseline/ e bench-fixed/; a árvore testada é a do node_modules local.
// Uso: BENCH_LABEL=<rótulo> node --conditions=source --experimental-strip-types --no-warnings memo-bench.ts [reps]
import { appendFileSync, copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createModels } from "@earendil-works/pi-ai/models";
import { createRegistry, defineExtension, defineTask, Harness } from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";

const HERE = dirname(fileURLToPath(import.meta.url));
const TEST3 = resolve(HERE, "..");
const LABEL = process.env.BENCH_LABEL ?? "unlabeled";
const RAW = join(TEST3, "raw", LABEL);
const FINECODE_ROOT = import.meta.resolve("@earendil-works/pi-durable");
const CTX = BACKGROUND_CONTEXT;
const TO = 3;
const EXPECTED_KEYS = ["unit_1", "unit_2", "unit_3"];

let traceFile = "";
let effectFile = "";
let runLabel = "";
let crashSpec = "";
let pauseSpec = "";
let dirGlobal = "";
let onStop: () => void = () => {};
let widenMs = 0;

function trace(event: Record<string, unknown>): void {
	appendFileSync(traceFile, `${JSON.stringify({ t: Date.now(), pid: process.pid, run: runLabel, ...event })}\n`);
}
function crashAt(point: string): void {
	if (crashSpec !== point) return;
	trace({ ev: "crash", point });
	process.kill(process.pid, "SIGKILL");
}
async function pauseAt(point: string): Promise<void> {
	if (pauseSpec !== point) return;
	trace({ ev: "pause", point });
	writeFileSync(join(dirGlobal, `paused-${point.replace(":", "_")}`), "");
	await waitForFile(join(dirGlobal, `release_${point.replace(":", "_")}`), 60000);
	trace({ ev: "resumed_from_pause", point });
}
function effect(key: string): void {
	appendFileSync(effectFile, `${JSON.stringify({ key, occurrence: randomUUID(), pid: process.pid, run: runLabel, t: Date.now() })}\n`);
}
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

type UnitCfg = { pattern: "intent" | "effect"; stopAfter?: number };

function unitTask(cfg: UnitCfg) {
	return defineTask<{ to: number }, { phase: "unit"; n: number }, string>({
		name: "t3.memo.unit",
		version: 1,
		initial: () => ({ phase: "unit", n: 1 }),
		phases: {
			unit: async (task: any, runtime: any, ctx: any) => {
				const n = task.state.checkpoint.n as number;
				const key = `unit_${n}`;
				trace({ ev: "phase_start", n });
				const seen = await runtime.memo(key, ctx);
				trace({ ev: "memo_read", key, seen: seen === undefined ? null : seen });
				if (seen === undefined) {
					if (cfg.pattern === "intent") {
						await pauseAt(`read:${key}`);
						const winner = await runtime.memo(key, true, ctx);
						trace({ ev: "memo_write", key, winner });
						crashAt(`after_memo:${n}`);
						await pauseAt(`memo:${key}`);
						if (widenMs > 0) await sleep(widenMs);
						effect(key);
						trace({ ev: "effect", key });
						crashAt(`after_effect:${n}`);
					} else {
						await pauseAt(`read:${key}`);
						if (widenMs > 0) await sleep(widenMs);
						effect(key);
						trace({ ev: "effect", key });
						crashAt(`after_effect:${n}`);
						await pauseAt(`effect:${key}`);
						const winner = await runtime.memo(key, true, ctx);
						trace({ ev: "memo_write", key, winner });
						crashAt(`after_memo:${n}`);
					}
				}
				if (n >= task.input.to) {
					await runtime.commit(() => ({ status: "terminal", outcome: { status: "completed", result: `units=${n}` } }), ctx);
					return;
				}
				const delay = cfg.stopAfter === n ? 1500 : 10;
				await runtime.sleepUntil(runtime.now() + delay, { phase: "unit", n: n + 1 }, ctx);
				trace({ ev: "checkpoint_committed", next: n + 1 });
				if (cfg.stopAfter === n) onStop();
			},
		},
		abort: async (_task: any, runtime: any, ctx: any) => {
			await runtime.commit(() => ({ status: "terminal", outcome: { status: "aborted" } }), ctx);
		},
	});
}

const valuesTask = defineTask<Record<string, never>, { phase: "d1" | "d2" }, string>({
	name: "t3.memo.values",
	version: 1,
	initial: () => ({ phase: "d1" }),
	phases: {
		d1: async (_task: any, runtime: any, ctx: any) => {
			const w1 = await runtime.memo("k", "v1", ctx);
			const w2 = await runtime.memo("k", "v2", ctx);
			const burst = await Promise.all(Array.from({ length: 8 }, (_, i) => runtime.memo("burst", `b${i}`, ctx)));
			const read = await runtime.memo("k", ctx);
			trace({ ev: "values_d1", w1, w2, read, burst });
			await runtime.sleepUntil(runtime.now() + 1500, { phase: "d2" }, ctx);
			onStop();
		},
		d2: async (_task: any, runtime: any, ctx: any) => {
			const read = await runtime.memo("k", ctx);
			const w3 = await runtime.memo("k", "v3", ctx);
			const burstRead = await runtime.memo("burst", ctx);
			trace({ ev: "values_d2", read, w3, burstRead });
			await runtime.commit(
				() => ({ status: "terminal", outcome: { status: "completed", result: JSON.stringify({ read, w3, burstRead }) } }),
				ctx,
			);
		},
	},
	abort: async (_task: any, runtime: any, ctx: any) => {
		await runtime.commit(() => ({ status: "terminal", outcome: { status: "aborted" } }), ctx);
	},
});

async function waitForFile(path: string, timeoutMs: number): Promise<void> {
	const end = Date.now() + timeoutMs;
	while (!existsSync(path)) {
		if (Date.now() > end) throw new Error(`barrier timeout: ${path}`);
		await sleep(5);
	}
}

async function runChild(a: Record<string, string>): Promise<void> {
	const dir = a.dir;
	dirGlobal = dir;
	traceFile = join(dir, "trace.jsonl");
	effectFile = join(dir, "effects.log");
	runLabel = a.run ?? a.role;
	crashSpec = a.crash ?? "";
	pauseSpec = a.pause ?? "";
	widenMs = Number(a.widen ?? 0);
	const cfg: UnitCfg = { pattern: (a.pattern as "intent" | "effect") ?? "intent", stopAfter: a.stopAfter ? Number(a.stopAfter) : undefined };
	const def = a.task === "values" ? valuesTask : unitTask(cfg);
	const registry = createRegistry();
	registry.install(defineExtension({ name: "t3", tasks: [def as any] }));
	const storage = await openNodeSqliteStorage(join(dir, "db.sqlite"));
	const h = await Harness.open(
		storage,
		{
			models: createModels(),
			registry,
			onReport: (error: unknown, info: unknown) =>
				trace({ ev: "report", message: String((error as Error)?.message ?? error), info }),
		},
		CTX,
	);

	if (a.role === "setup") {
		const root = await h.root(CTX);
		const input = a.task === "values" ? {} : { to: TO };
		const id = await root.commit((tx: any) => tx.createTask(def, input, { ownership: { kind: "conversation" } }), CTX);
		writeFileSync(join(dir, "task-id.json"), JSON.stringify(id));
		await h.close(CTX);
		return;
	}

	const stopped = new Promise<"stopped">((resolveStop) => {
		onStop = () => {
			trace({ ev: "stop_committed" });
			resolveStop("stopped");
		};
	});
	if (a.barrier === "1") {
		writeFileSync(join(dir, `ready-${a.id}`), "");
		await waitForFile(join(dir, "go"), 20000);
	}
	const taskId = JSON.parse(readFileSync(join(dir, "task-id.json"), "utf8"));
	trace({ ev: "resume" });
	h.resume();
	let result: Record<string, unknown>;
	try {
		const winner = await Promise.race([
			stopped.then((kind) => ({ kind })),
			h.waitForTask(taskId, CTX).then((settled: any) => ({ kind: "settled", settled })),
			sleep(Number(a.timeout ?? 20000)).then(() => ({ kind: "timeout" })),
		]);
		const settled = (winner as any).settled;
		result = { kind: (winner as any).kind, outcome: settled?.state?.outcome ?? null, status: settled?.state?.status ?? null };
	} catch (error) {
		result = { kind: "error", error: String((error as Error)?.message ?? error) };
	}
	writeFileSync(join(dir, `result-${a.run ?? a.role}-${process.pid}.json`), JSON.stringify(result, null, 2));
	await h.close(CTX).catch(() => {});
	process.exit(0);
}

// ----------------------------------------------------------------------------------------------
// Orquestrador
// ----------------------------------------------------------------------------------------------
type Proc = { code: number | null; signal: string | null; stdout: string; stderr: string };

function spawnChild(args: string[], timeoutMs = 90000): Promise<Proc> {
	return new Promise((resolveProc) => {
		const child = spawn(
			process.execPath,
			["--conditions=source", "--experimental-strip-types", "--no-warnings", fileURLToPath(import.meta.url), "child", ...args],
			{ cwd: HERE, windowsHide: true },
		);
		let stdout = "";
		let stderr = "";
		child.stdout.on("data", (d) => (stdout += d));
		child.stderr.on("data", (d) => (stderr += d));
		const timer = setTimeout(() => child.kill(), timeoutMs);
		child.on("exit", (code, signal) => {
			clearTimeout(timer);
			resolveProc({ code, signal, stdout, stderr });
		});
	});
}

function readTrace(dir: string): any[] {
	const p = join(dir, "trace.jsonl");
	if (!existsSync(p)) return [];
	return readFileSync(p, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
}
function readEffects(dir: string): any[] {
	const p = join(dir, "effects.log");
	if (!existsSync(p)) return [];
	return readFileSync(p, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
}

function unitMetrics(dir: string) {
	const effects = readEffects(dir);
	const counts: Record<string, number> = {};
	for (const e of effects) counts[e.key] = (counts[e.key] ?? 0) + 1;
	const duplicates = Object.values(counts).reduce((s, c) => s + Math.max(0, c - 1), 0);
	const lost = EXPECTED_KEYS.filter((k) => !counts[k]);
	const traces = readTrace(dir);
	return {
		effects_executed: effects.length,
		per_key: counts,
		effects_duplicated: duplicates,
		effects_lost: lost,
		crash_events: traces.filter((t) => t.ev === "crash").map((t) => t.point),
		reports: traces.filter((t) => t.ev === "report").map((t) => t.message),
		memo_writes_by_run: traces.filter((t) => t.ev === "memo_write").map((t) => `${t.run}:${t.key}:${t.winner}`),
	};
}

async function orchestrate(reps: number): Promise<void> {
	mkdirSync(RAW, { recursive: true });
	const REPS = Array.from({ length: reps }, (_, i) => i + 1);
	const scenarios: Array<{ id: string; desc: string; mode: string; pattern?: string; crash?: string; widen?: number }> = [
		{ id: "A", desc: "crash após memo(unit_2) gravado, antes do efeito (intent)", mode: "crash", pattern: "intent", crash: "after_memo:2" },
		{ id: "B", desc: "crash após efeito de unit_2, antes do memo (effect-first)", mode: "crash", pattern: "effect", crash: "after_effect:2" },
		{ id: "B2", desc: "crash após efeito de unit_2 com memo já gravado (intent)", mode: "crash", pattern: "intent", crash: "after_effect:2" },
		{ id: "C", desc: "parada graciosa após unit_2 e reinício", mode: "graceful", pattern: "intent" },
		{ id: "D", desc: "mesma chave com valores diferentes", mode: "values" },
		{ id: "E-intent", desc: "duas instâncias concorrentes, intent, sem atraso", mode: "concurrent", pattern: "intent", widen: 0 },
		{ id: "E-intent-widened", desc: "duas instâncias concorrentes, intent, 300 ms entre leitura e efeito", mode: "concurrent", pattern: "intent", widen: 300 },
		{ id: "E-effect", desc: "duas instâncias concorrentes, effect-first", mode: "concurrent", pattern: "effect", widen: 0 },
		{ id: "F", desc: "takeover com B vivo: A pausado após leitura do memo de unit_1 (intent); B pausado em read:unit_2; A liberado enquanto B está vivo", mode: "takeover", pattern: "intent", crash: "read:unit_1" },
		{ id: "F2", desc: "takeover com B vivo: A pausado após memo(unit_1) antes do efeito (intent); B pausado em read:unit_2", mode: "takeover", pattern: "intent", crash: "memo:unit_1" },
		{ id: "G", desc: "takeover com B vivo: A pausado após efeito de unit_1 antes do memo (effect-first); B pausado em read:unit_2", mode: "takeover", pattern: "effect", crash: "effect:unit_1" },
	];
	const out: Record<string, unknown> = { generated_at: new Date().toISOString(), label: LABEL, finecode_package: FINECODE_ROOT, reps: reps, scenarios: {} };
	const selected = process.env.BENCH_ONLY ? process.env.BENCH_ONLY.split(",") : null;

	for (const s of scenarios) {
		if (selected && !selected.includes(s.id)) continue;
		const reps2: unknown[] = [];
		for (const rep of REPS) {
			const dir = join(RAW, s.id, `rep${rep}`);
			rmSync(dir, { recursive: true, force: true });
			mkdirSync(dir, { recursive: true });
			const task = s.mode === "values" ? "values" : "unit";
			const pattern = s.pattern ?? "intent";
			const base = ["--dir", dir, "--task", task, "--pattern", pattern];
			const logs: Record<string, Proc> = {};
			logs.setup = await spawnChild([...base, "--role", "setup", "--run", "setup"]);
			if (s.mode === "crash") {
				logs.run1 = await spawnChild([...base, "--role", "run", "--run", "run1", "--crash", s.crash!]);
				copySnapshot(dir, "db-after-run1-crash");
				logs.recover = await spawnChild([...base, "--role", "run", "--run", "recover"]);
			} else if (s.mode === "graceful") {
				logs.run1 = await spawnChild([...base, "--role", "run", "--run", "run1", "--stopAfter", "2"]);
				logs.recover = await spawnChild([...base, "--role", "run", "--run", "recover"]);
			} else if (s.mode === "values") {
				logs.run1 = await spawnChild([...base, "--role", "run", "--run", "run1"]);
				logs.recover = await spawnChild([...base, "--role", "run", "--run", "recover"]);
			} else if (s.mode === "concurrent") {
				const p1 = spawnChild([...base, "--role", "run", "--run", "instA", "--id", "A", "--barrier", "1", "--widen", String(s.widen ?? 0)]);
				const p2 = spawnChild([...base, "--role", "run", "--run", "instB", "--id", "B", "--barrier", "1", "--widen", String(s.widen ?? 0)]);
				const end = Date.now() + 20000;
				while (!(existsSync(join(dir, "ready-A")) && existsSync(join(dir, "ready-B")))) {
					if (Date.now() > end) break;
					await sleep(5);
				}
				writeFileSync(join(dir, "go"), "");
				const [ra, rb] = await Promise.all([p1, p2]);
				logs.instA = ra;
				logs.instB = rb;
			} else if (s.mode === "takeover") {
				// A roda até a pausa; B assume e conclui a tarefa; depois A é liberado e tenta continuar.
				const bPause = "read:unit_2";
				const pA = spawnChild([...base, "--role", "run", "--run", "instA", "--id", "A", "--pause", s.crash!], 120000);
				await waitForFile(join(dir, `paused-${s.crash!.replace(":", "_")}`), 30000);
				const pB = spawnChild([...base, "--role", "run", "--run", "instB", "--id", "B", "--pause", bPause], 120000);
				await waitForFile(join(dir, `paused-${bPause.replace(":", "_")}`), 30000);
				// A volta enquanto B ainda está vivo e com a tarefa em execução.
				writeFileSync(join(dir, `release_${s.crash!.replace(":", "_")}`), "");
				const endA = Date.now() + 8000;
				while (Date.now() < endA && !existsSync(join(dir, "result-instA-x"))) {
					const tA = readTrace(dir).filter((t) => t.run === "instA");
					if (tA.some((t) => t.ev === "report" || t.ev === "effect" || t.ev === "memo_write")) break;
					await sleep(20);
				}
				await sleep(300);
				writeFileSync(join(dir, `release_${bPause.replace(":", "_")}`), "");
				logs.instB = await pB;
				logs.instA = await pA;
			}
			for (const [k, v] of Object.entries(logs)) {
				writeFileSync(join(dir, `${k}.stdout.txt`), v.stdout);
				writeFileSync(join(dir, `${k}.stderr.txt`), v.stderr);
			}
			const m = unitMetrics(dir);
			const results = readdirSync(dir).filter((f) => f.startsWith("result-")).map((f) => ({ file: f, ...JSON.parse(readFileSync(join(dir, f), "utf8")) }));
			reps2.push({
				rep,
				...m,
				run_exit: Object.fromEntries(Object.entries(logs).map(([k, v]) => [k, { code: v.code, signal: v.signal }])),
				results,
			});
		}
		(out.scenarios as Record<string, unknown>)[s.id] = { desc: s.desc, mode: s.mode, pattern: s.pattern ?? null, crash: s.crash ?? null, widen: s.widen ?? null, reps: reps2 };
		console.log(`scenario ${s.id} done (${reps} reps)`);
	}
	writeFileSync(join(RAW, "bench-results.json"), JSON.stringify(out, null, 2));
	console.log("written", join(RAW, "bench-results.json"));
}

function copySnapshot(dir: string, name: string): void {
	for (const suffix of ["", "-wal", "-shm"]) {
		const src = join(dir, `db.sqlite${suffix}`);
		if (existsSync(src)) copyFileSync(src, join(dir, `${name}.sqlite${suffix}`));
	}
}

if (process.argv[2] === "child") {
	const args: Record<string, string> = {};
	const argv = process.argv.slice(3);
	for (let i = 0; i < argv.length; i += 2) args[argv[i].replace(/^--/, "")] = argv[i + 1];
	await runChild(args);
} else {
	await orchestrate(Number(process.argv[2] ?? 3));
}
