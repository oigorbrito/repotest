// Teste 2 — FineCode runtime.memo(): cenários A–E com processos reais.
// Uso: node --conditions=source --experimental-strip-types memo-bench.ts            (orquestra tudo)
//      node ... memo-bench.ts child --role=... (usado internamente pelo orquestrador)
// Nada fora de test-2/ é escrito. O FineCode é lido via import por nome de pacote (node_modules é link para o original).
import { appendFileSync, copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { spawn, execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createModels } from "@earendil-works/pi-ai/models";
import { createRegistry, defineExtension, defineTask, Harness } from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";

const HERE = dirname(fileURLToPath(import.meta.url));
const TEST2 = resolve(HERE, "..");
const RAW = join(TEST2, "raw", "finecode");
const FINECODE = "D:/projetos/FineCode";
const CTX = BACKGROUND_CONTEXT;
const TO = 3; // unidades lógicas: unit_1..unit_3
const EXPECTED_KEYS = ["unit_1", "unit_2", "unit_3"];

// ----------------------------------------------------------------------------------------------
// Processo filho: executa uma etapa (setup | run) com a implementação real do FineCode.
// ----------------------------------------------------------------------------------------------
let traceFile = "";
let effectFile = "";
let runLabel = "";
let crashSpec = "";
let onStop: () => void = () => {};
let widenMs = 0;

function trace(event: Record<string, unknown>): void {
	appendFileSync(traceFile, `${JSON.stringify({ t: Date.now(), pid: process.pid, run: runLabel, ...event })}\n`);
}
function crashAt(point: string): void {
	if (crashSpec !== point) return;
	trace({ ev: "crash", point }); // gravado de forma síncrona antes da morte abrupta
	process.kill(process.pid, "SIGKILL");
}
function effect(key: string): void {
	// Efeito externo simulado: uma linha com identificador único por ocorrência.
	appendFileSync(effectFile, `${JSON.stringify({ key, occurrence: randomUUID(), pid: process.pid, run: runLabel, t: Date.now() })}\n`);
}
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

type UnitCfg = { pattern: "intent" | "effect"; stopAfter?: number };

// Padrão "intent" (o usado no Teste 1): memo("unit_n", true) ANTES do efeito; memo como guarda.
// Padrão "effect": efeito ANTES do memo; memo só é gravado depois que o efeito retornou.
function unitTask(cfg: UnitCfg) {
	return defineTask<{ to: number }, { phase: "unit"; n: number }, string>({
		name: "t2.memo.unit",
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
						const winner = await runtime.memo(key, true, ctx);
						trace({ ev: "memo_write", key, winner });
						crashAt(`after_memo:${n}`);
						if (widenMs > 0) await sleep(widenMs);
						effect(key);
						trace({ ev: "effect", key });
						crashAt(`after_effect:${n}`);
					} else {
						if (widenMs > 0) await sleep(widenMs);
						effect(key);
						trace({ ev: "effect", key });
						crashAt(`after_effect:${n}`);
						const winner = await runtime.memo(key, true, ctx);
						trace({ ev: "memo_write", key, winner });
						crashAt(`after_memo:${n}`);
					}
				}
				if (n >= task.input.to) {
					await runtime.commit(
						() => ({ status: "terminal", outcome: { status: "completed", result: `units=${n}` } }),
						ctx,
					);
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

// Chaves diferentes e mesma chave com valores diferentes, dentro de uma única tarefa que sobrevive a reinício.
const valuesTask = defineTask<Record<string, never>, { phase: "d1" | "d2" }, string>({
	name: "t2.memo.values",
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
	traceFile = join(dir, "trace.jsonl");
	effectFile = join(dir, "effects.log");
	runLabel = a.run ?? a.role;
	crashSpec = a.crash ?? "";
	widenMs = Number(a.widen ?? 0);
	const cfg: UnitCfg = { pattern: (a.pattern as "intent" | "effect") ?? "intent", stopAfter: a.stopAfter ? Number(a.stopAfter) : undefined };
	const def = a.task === "values" ? valuesTask : unitTask(cfg);
	const registry = createRegistry();
	registry.install(defineExtension({ name: "t2", tasks: [def as any] }));
	const storage = await openNodeSqliteStorage(join(dir, "db.sqlite"));
	const h = await Harness.open(
		storage,
		{
			models: createModels(),
			registry,
			onReport: (error: unknown, info: unknown) =>
				trace({ ev: "report", message: String((error as Error)?.message ?? error), stack: String((error as Error)?.stack ?? "").slice(0, 800), info }),
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
		result = {
			kind: (winner as any).kind,
			outcome: settled?.state?.outcome ?? null,
			status: settled?.state?.status ?? null,
		};
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

function spawnChild(args: string[], label: string, timeoutMs = 60000): Promise<Proc> {
	return new Promise((resolveProc) => {
		const child = spawn(process.execPath, ["--conditions=source", "--experimental-strip-types", "--no-warnings", fileURLToPath(import.meta.url), "child", ...args], {
			cwd: HERE,
			windowsHide: true,
		});
		let stdout = "";
		let stderr = "";
		child.stdout.on("data", (d) => (stdout += d));
		child.stderr.on("data", (d) => (stderr += d));
		const timer = setTimeout(() => child.kill(), timeoutMs);
		child.on("exit", (code, signal) => {
			clearTimeout(timer);
			resolveProc({ code, signal, stdout, stderr });
		});
		void label;
	});
}

function gitSnapshot(repo: string) {
	const head = execFileSync("git", ["-C", repo, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
	const status = execFileSync("git", ["-C", repo, "status", "--porcelain"], { encoding: "utf8" });
	return { head, status: status.trim().split("\n").filter(Boolean) };
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
	const recoveryRun = traces.filter((t) => t.run === "recover");
	return {
		effects_executed: effects.length,
		per_key: counts,
		effects_duplicated: duplicates,
		effects_lost: lost,
		phase_starts_recovery: recoveryRun.filter((t) => t.ev === "phase_start").length,
		memo_values_recovered: recoveryRun.filter((t) => t.ev === "memo_read" && t.seen !== null).map((t) => ({ key: t.key, seen: t.seen })),
		crash_events: traces.filter((t) => t.ev === "crash").map((t) => t.point),
	};
}

async function orchestrate(): Promise<void> {
	mkdirSync(RAW, { recursive: true });
	const repoBefore = gitSnapshot(FINECODE);
	const REPS = [1, 2, 3];
	const scenarios: Array<{ id: string; desc: string; mode: string; pattern?: string; crash?: string; widen?: number }> = [
		{ id: "A", desc: "memo intent gravado; efeito não executado; crash after_memo:2", mode: "crash", pattern: "intent", crash: "after_memo:2" },
		{ id: "B", desc: "efeito executado; memo não gravado; crash after_effect:2 (padrão effect-first)", mode: "crash", pattern: "effect", crash: "after_effect:2" },
		{ id: "B2", desc: "efeito executado após memo intent; crash after_effect:2 (controle extra)", mode: "crash", pattern: "intent", crash: "after_effect:2" },
		{ id: "C", desc: "memo, efeito e checkpoint confirmados; parada graciosa após unit_2; reinício", mode: "graceful", pattern: "intent" },
		{ id: "D", desc: "mesma chave com valores diferentes (intra-processo e após reinício)", mode: "values" },
		{ id: "E-intent", desc: "duas instâncias concorrentes, padrão intent, sem atraso", mode: "concurrent", pattern: "intent", widen: 0 },
		{ id: "E-intent-widened", desc: "duas instâncias concorrentes, padrão intent, atraso de 300 ms entre leitura e efeito", mode: "concurrent", pattern: "intent", widen: 300 },
		{ id: "E-effect", desc: "duas instâncias concorrentes, padrão effect-first, sem atraso", mode: "concurrent", pattern: "effect", widen: 0 },
	];
	const out: Record<string, unknown> = { generated_at: new Date().toISOString(), finecode_before: repoBefore, scenarios: {} };

	for (const s of scenarios) {
		const reps: unknown[] = [];
		for (const rep of REPS) {
			const dir = join(RAW, s.id, `rep${rep}`);
			rmSync(dir, { recursive: true, force: true });
			mkdirSync(dir, { recursive: true });
			const task = s.mode === "values" ? "values" : "unit";
			const pattern = s.pattern ?? "intent";
			const base = ["--dir", dir, "--task", task, "--pattern", pattern];
			const logs: Record<string, Proc> = {};
			logs.setup = await spawnChild([...base, "--role", "setup", "--run", "setup"], "setup");
			let note = "";
			if (s.mode === "crash") {
				logs.run1 = await spawnChild([...base, "--role", "run", "--run", "run1", "--crash", s.crash!], "run1");
				for (const suffix of ["", "-wal", "-shm"]) {
					if (existsSync(join(dir, `db.sqlite${suffix}`))) copyFileSync(join(dir, `db.sqlite${suffix}`), join(dir, `db-after-run1-crash.sqlite${suffix}`));
				}
				logs.recover = await spawnChild([...base, "--role", "run", "--run", "recover"], "recover");
			} else if (s.mode === "graceful") {
				logs.run1 = await spawnChild([...base, "--role", "run", "--run", "run1", "--stopAfter", "2"], "run1");
				logs.recover = await spawnChild([...base, "--role", "run", "--run", "recover"], "recover");
			} else if (s.mode === "values") {
				logs.run1 = await spawnChild([...base, "--role", "run", "--run", "run1"], "run1");
				logs.recover = await spawnChild([...base, "--role", "run", "--run", "recover"], "recover");
			} else if (s.mode === "concurrent") {
				const p1 = spawnChild([...base, "--role", "run", "--run", "instA", "--id", "A", "--barrier", "1", "--widen", String(s.widen ?? 0)], "A");
				const p2 = spawnChild([...base, "--role", "run", "--run", "instB", "--id", "B", "--barrier", "1", "--widen", String(s.widen ?? 0)], "B");
				// Espera ambos prontos antes de liberar; sem barreira, a janela de concorrência seria acidental.
				const end = Date.now() + 20000;
				while (!(existsSync(join(dir, "ready-A")) && existsSync(join(dir, "ready-B")))) {
					if (Date.now() > end) break;
					await sleep(5);
				}
				writeFileSync(join(dir, "go"), "");
				const [ra, rb] = await Promise.all([p1, p2]);
				logs.instA = ra;
				logs.instB = rb;
			}
			for (const [k, v] of Object.entries(logs)) {
				writeFileSync(join(dir, `${k}.stdout.txt`), v.stdout);
				writeFileSync(join(dir, `${k}.stderr.txt`), v.stderr);
			}
			const m = unitMetrics(dir);
			const traces = readTrace(dir);
			const resultFiles = readdirSync(dir).filter((f) => f.startsWith("result-"));
			const results = resultFiles.map((f) => JSON.parse(readFileSync(join(dir, f), "utf8")));
			const stateBefore = traces.filter((t) => t.run !== "recover" && t.run !== "setup");
			reps.push({
				rep,
				...m,
				run_exit: Object.fromEntries(Object.entries(logs).map(([k, v]) => [k, { code: v.code, signal: v.signal }])),
				results,
				memo_reads_run1: stateBefore.filter((t) => t.ev === "memo_read").length,
				notes: note,
			});
			void note;
		}
		(out.scenarios as Record<string, unknown>)[s.id] = { desc: s.desc, mode: s.mode, pattern: s.pattern ?? null, crash: s.crash ?? null, widen: s.widen ?? null, reps };
		console.log(`scenario ${s.id} done`);
	}
	out.finecode_after = gitSnapshot(FINECODE);
	out.finecode_unchanged = JSON.stringify(out.finecode_before) === JSON.stringify(out.finecode_after);
	writeFileSync(join(RAW, "finecode-results.json"), JSON.stringify(out, null, 2));
	console.log("written", join(RAW, "finecode-results.json"), "unchanged:", out.finecode_unchanged);
}

if (process.argv[2] === "child") {
	const args: Record<string, string> = {};
	const argv = process.argv.slice(3);
	for (let i = 0; i < argv.length; i += 2) args[argv[i].replace(/^--/, "")] = argv[i + 1];
	await runChild(args);
} else {
	await orchestrate();
}
