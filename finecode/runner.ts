// Adapter for the FineCode durable runtime (packages/durable, source import).
// Copied into <copies>/FineCode/packages/durable/bench-runner.ts at run time so that
// bare-specifier imports resolve through the copy's own node_modules.
//
// Workload ("unit" = one task phase invocation that performs one external effect
// and then commits a checkpoint). One task, `total` units.
//
// argv[2] = JSON args:
//   mode: "run" | "stale" | "inspect"
//   db, idFile, effects, invocations, outFile : paths
//   total: number of units
//   variant: "plain" (no memo, non-idempotent service) | "memo" (durable memo intent before effect, non-idempotent service)
//            | "idem" (no memo, service ignores repeated request key)
//   stopAfter?: number            (run: block unit stopAfter+1, then close the Harness normally)
//   crash?: {unit, point: "after_effect" | "after_commit"}   (process SIGKILLs itself)
//   staleUnit?, releaseFile?, readyFile?  (stale: hold the invocation after unit staleUnit's effect)
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createModels } from "@earendil-works/pi-ai/models";
import { createRegistry, defineExtension, defineTask, Harness, type TaskId } from "./src/index.ts";
import { openNodeSqliteStorage } from "./src/storage/sqlite/node.ts";

const ctx = BACKGROUND_CONTEXT;
const args = JSON.parse(process.argv[2]!) as {
	mode: "run" | "stale" | "inspect";
	db: string;
	idFile: string;
	effects: string;
	invocations: string;
	outFile: string;
	total: number;
	variant: "plain" | "memo" | "idem";
	stopAfter?: number;
	crash?: { unit: number; point: "after_effect" | "after_commit" };
	staleUnit?: number;
	releaseFile?: string;
	readyFile?: string;
	staleLog?: string;
	timeoutMs?: number;
};

const T0 = performance.now();
const out: Record<string, unknown> = { mode: args.mode, variant: args.variant, pid: process.pid, module: import.meta.url };
mkdirSync(dirname(args.outFile), { recursive: true });
const flush = () => writeFileSync(args.outFile, JSON.stringify(out, null, 2));
const stages: string[] = [];
const stage = (name: string) => { stages.push(`${Math.round(performance.now() - T0)}ms ${name}`); out.stages = stages; flush(); };
process.on("exit", (code) => { if (!out.finished) { out.finished = false; out.exit_code = code; out.stages = stages; flush(); } });

type State = { phase: "unit"; done: number };
type Input = { total: number; variant: string };

function kill(): never {
	// Abrupt termination: no finally blocks, no harness close, no storage flush.
	process.kill(process.pid, "SIGKILL");
	throw new Error("unreachable");
}

function invoke(n: number) {
	appendFileSync(args.invocations, `${JSON.stringify({ unit: n, pid: process.pid, ms: Date.now() })}\n`);
}

// External effect. In "idem" mode the external service ignores a repeated request key,
// as in the FineCode durable example (payment service). In "plain" and "memo" it does not.
function effect(n: number) {
	invoke(n);
	const key = `unit-${n}`;
	if (args.variant === "idem" && existsSync(args.effects)) {
		const seen = readFileSync(args.effects, "utf8").split("\n").some((l) => l.includes(`key=${key} `));
		if (seen) return;
	}
	appendFileSync(args.effects, `unit=${n} key=${key} pid=${process.pid}\n`);
}

function waitForFile(path: string, timeoutMs: number): Promise<boolean> {
	const start = Date.now();
	return new Promise((resolve) => {
		const tick = () => {
			if (existsSync(path)) return resolve(true);
			if (Date.now() - start > timeoutMs) return resolve(false);
			setTimeout(tick, 20);
		};
		tick();
	});
}

const Units = defineTask<Input, State, number>({
	name: "bench.units",
	version: 1,
	initial: () => ({ phase: "unit", done: 0 }),
	phases: {
		unit: async (task, runtime, c) => {
			const n = task.state.checkpoint.done + 1;
			const total = task.input.total;
			if (n > total) {
				await runtime.commit(() => ({ status: "terminal", outcome: { status: "completed", result: total } }), c);
				return;
			}
			if (args.stopAfter !== undefined && n > args.stopAfter) {
				// Hold here (no effect) until the host closes the Harness.
				await new Promise<void>((resolve) => runtime.signal.addEventListener("abort", () => resolve(), { once: true }));
				return;
			}
			if (task.input.variant === "memo") await runtime.memo(`intent-${n}`, true, c);
			effect(n);
			if (args.crash?.unit === n && args.crash.point === "after_effect") kill();
			if (args.mode === "stale" && args.staleUnit === n) {
				writeFileSync(args.readyFile!, String(process.pid));
				const released = await waitForFile(args.releaseFile!, args.timeoutMs ?? 30000);
				let result: Record<string, unknown>;
				try {
					await runtime.commit(
						() => ({ status: "running", checkpoint: { phase: "unit", done: n } }),
						c,
					);
					result = { released, commit: "accepted" };
				} catch (error) {
					result = { released, commit: "rejected", error: String(error instanceof Error ? error.message : error) };
				}
				writeFileSync(args.staleLog!, JSON.stringify(result, null, 2));
				process.exit(0);
			}
			await runtime.commit(
				() =>
					n === total
						? { status: "terminal", outcome: { status: "completed", result: total } }
						: { status: "running", checkpoint: { phase: "unit", done: n } },
				c,
			);
			if (args.crash?.unit === n && args.crash.point === "after_commit") kill();
		},
	},
	abort: async (_task, runtime, c) => {
		await runtime.commit(() => ({ status: "terminal", outcome: { status: "aborted" } }), c);
	},
});

async function main() {
	stage("begin");
	const storage = await openNodeSqliteStorage(args.db);
	stage("storage_opened");
	const registry = createRegistry();
	registry.install(defineExtension({ name: "bench", tasks: [Units] }));
	const tOpen = performance.now();
	const harness = await Harness.open(storage, { models: createModels(), registry }, ctx);
	out.open_ms = Math.round(performance.now() - tOpen);
	stage("harness_opened");
	out.harness_module = import.meta.url;

	let id: TaskId<number>;
	if (existsSync(args.idFile)) {
		id = Number(readFileSync(args.idFile, "utf8").trim()) as TaskId<number>;
	} else {
		const root = await harness.root(ctx);
		id = await root.commit(
			(tx) => tx.createTask(Units, { total: args.total, variant: args.variant }, { ownership: { kind: "conversation" } }),
			ctx,
		);
		writeFileSync(args.idFile, String(id));
	}
	out.task_id = id;

	stage("task_id_ready");
	const before = await harness.getTask(id, ctx);
	stage("before_read");
	out.before = before === undefined ? null : { status: before.state.status, checkpoint: (before.state as { checkpoint?: unknown }).checkpoint ?? null, outcome: (before.state as { outcome?: unknown }).outcome ?? null };
	out.units_recovered = (before?.state as { checkpoint?: State } | undefined)?.checkpoint?.done ?? 0;

	if (args.mode === "inspect") {
		const after = await harness.getTask(id, ctx);
		out.inspect = after === undefined ? null : after.state;
		await harness.close(ctx);
		out.total_ms = Math.round(performance.now() - T0);
		flush();
		return;
	}

	const tRecover = performance.now();
	harness.resume();
	if (args.stopAfter !== undefined) {
		// Poll the durable checkpoint, then close normally while unit stopAfter+1 is held.
		const deadline = Date.now() + (args.timeoutMs ?? 30000);
		for (;;) {
			const rec = await harness.getTask(id, ctx);
			const done = (rec?.state as { checkpoint?: State } | undefined)?.checkpoint?.done ?? 0;
			if (done >= args.stopAfter) break;
			if (Date.now() > deadline) throw new Error("timeout waiting for stopAfter checkpoint");
			await new Promise((r) => setTimeout(r, 10));
		}
		out.closed_normally = true;
		await harness.close(ctx);
		out.work_ms = Math.round(performance.now() - tRecover);
		out.total_ms = Math.round(performance.now() - T0);
		flush();
		return;
	}
	stage("resumed_waiting");
	const settled = await harness.waitForTask(id, ctx);
	stage("settled");
	out.outcome = settled.state.outcome;
	out.recover_ms = Math.round(performance.now() - tRecover);
	out.total_ms = Math.round(performance.now() - T0);
	out.finished = true;
	await harness.close(ctx);
	flush();
}

main().catch((error) => {
	out.error = String(error instanceof Error ? `${error.name}: ${error.message}` : error);
	out.total_ms = Math.round(performance.now() - T0);
	flush();
	process.exitCode = 2;
});
