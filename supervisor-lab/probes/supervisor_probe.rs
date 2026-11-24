//! PROBE (supervisor-lab, Q1): stdio approval behaviour on any OS.
//! Not part of upstream. Records what happens; asserts only the safety
//! property we need (a denied/unanswered write must not land).

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::{json, Value};

static NEXT: AtomicU64 = AtomicU64::new(1);

enum Reply {
    Text(&'static str),
    Call(&'static str, Value),
}

impl Reply {
    fn json(&self, step: usize) -> String {
        let (message, finish) = match self {
            Reply::Text(text) => (json!({"role": "assistant", "content": text}), "stop"),
            Reply::Call(name, args) => (
                json!({"role": "assistant", "content": null, "tool_calls": [{"id": format!("call_{step}"), "type": "function", "function": {"name": name, "arguments": args.to_string()}}]}),
                "tool_calls",
            ),
        };
        json!({"choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}).to_string()
    }

    fn sse(&self, step: usize) -> String {
        let chunks = match self {
            Reply::Text(text) => vec![
                json!({"choices": [{"index": 0, "delta": {"content": text}}]}),
                json!({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
            ],
            Reply::Call(name, args) => vec![
                json!({"choices": [{"index": 0, "delta": {"tool_calls": [{
                    "index": 0, "id": format!("call_{step}"), "type": "function",
                    "function": {"name": name, "arguments": args.to_string()},
                }]}}]}),
                json!({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}),
            ],
        };
        let mut body: String = chunks.iter().map(|c| format!("data: {c}\n\n")).collect();
        body.push_str("data: [DONE]\n\n");
        body
    }
}

struct FakeModel {
    url: String,
    calls: Arc<Mutex<usize>>,
}

impl FakeModel {
    fn start(script: Vec<Reply>) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}/v1", listener.local_addr().unwrap());
        let calls = Arc::new(Mutex::new(0usize));
        let counter = calls.clone();
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(mut stream) = stream else { continue };
                let Some(body) = read_request(&mut stream) else { continue };
                let streaming = body["stream"].as_bool().unwrap_or(false);
                let step = {
                    let mut n = counter.lock().unwrap();
                    *n += 1;
                    *n - 1
                };
                let (ctype, reply) = if streaming { ("text/event-stream", script[step.min(script.len() - 1)].sse(step)) } else { ("application/json", script[step.min(script.len() - 1)].json(step)) };
                let head = format!(
                    "HTTP/1.1 200 OK\r\ncontent-type: {ctype}\r\ncontent-length: {}\r\nconnection: close\r\n\r\n",
                    reply.len()
                );
                let _ = stream.write_all(head.as_bytes());
                let _ = stream.write_all(reply.as_bytes());
            }
        });
        Self { url, calls }
    }
}

fn read_request(stream: &mut std::net::TcpStream) -> Option<Value> {
    let mut raw = Vec::new();
    let mut buf = [0u8; 8192];
    loop {
        let n = stream.read(&mut buf).ok()?;
        if n == 0 {
            return None;
        }
        raw.extend_from_slice(&buf[..n]);
        let Some(split) = raw.windows(4).position(|w| w == b"\r\n\r\n") else {
            continue;
        };
        let head = String::from_utf8_lossy(&raw[..split]).to_lowercase();
        let length: usize = head
            .lines()
            .find_map(|l| l.strip_prefix("content-length:"))
            .map(|v| v.trim().parse().unwrap())
            .unwrap_or(0);
        if raw.len() >= split + 4 + length {
            return serde_json::from_slice(&raw[split + 4..split + 4 + length]).ok();
        }
    }
}

struct Fixture {
    root: PathBuf,
    workspace: PathBuf,
}

impl Fixture {
    fn new(label: &str) -> Self {
        let root = std::env::temp_dir().join(format!(
            "probe-q1-{label}-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = std::fs::remove_dir_all(&root);
        let workspace = root.join("ws");
        std::fs::create_dir_all(&workspace).unwrap();
        let prompt = root.join("prompt.txt");
        std::fs::write(&prompt, "do it").unwrap();
        Self { root, workspace }
    }

    fn spawn(&self, model: &FakeModel) -> Child {
        self.spawn_with(model, None)
    }

    fn spawn_with(&self, model: &FakeModel, tools: Option<&str>) -> Child {
        self.spawn_flags(model, tools, &[])
    }

    fn spawn_flags(&self, model: &FakeModel, tools: Option<&str>, flags: &[&str]) -> Child {
        let mut extra: Vec<String> = flags.iter().map(|f| f.to_string()).collect();
        if let Some(t) = tools {
            extra.push("--tools".into());
            extra.push(t.into());
        }
        Command::new(env!("CARGO_BIN_EXE_orcacode"))
            .args(["--base-url", &model.url, "--model", "fake", "--no-prompt-cache"])
            .args([
                "--prompt-file",
                self.root.join("prompt.txt").to_str().unwrap(),
                "--json",
                "--no-session",
                "--approvals",
                "stdio",
            ])
            .args(&extra)
            .current_dir(&self.workspace)
            .env("ORCA_CONFIG_DIR", self.root.join("config"))
            .env("HOME", &self.root)
            .env_remove("ORCA_MODEL")
            .env_remove("ORCA_BASE_URL")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.root);
    }
}

/// Outcome record for one probe, printed so the run is reviewable.
#[derive(Debug)]
struct Record {
    probe: &'static str,
    approval_requests: usize,
    file_written: bool,
    exit: Option<i32>,
    exited_after_eof_ms: Option<u128>,
    summary_status: Option<String>,
    stderr_tail: String,
}

fn drive(
    probe: &'static str,
    file: &str,
    script: Vec<Reply>,
    on_request: impl FnMut(&Value, &mut std::process::ChildStdin) -> bool,
) -> Record {
    drive_t(probe, file, script, None, on_request)
}

fn drive_t(
    probe: &'static str,
    file: &str,
    script: Vec<Reply>,
    tools: Option<&str>,
    mut on_request: impl FnMut(&Value, &mut std::process::ChildStdin) -> bool,
) -> Record {
    let fixture = Fixture::new(probe);
    let model = FakeModel::start(script);
    let mut child = fixture.spawn_with(&model, tools);
    let mut stdin = child.stdin.take();
    let stdout = child.stdout.take().unwrap();
    let mut stderr = child.stderr.take().unwrap();

    let (tx, rx) = mpsc::channel::<String>();
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            let _ = tx.send(line);
        }
    });
    let err_handle = std::thread::spawn(move || {
        let mut s = String::new();
        let _ = stderr.read_to_string(&mut s);
        s
    });

    let mut approval_requests = 0usize;
    let mut summary_status = None;
    let mut eof_at: Option<Instant> = None;
    let mut keep_open = true;
    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        match rx.recv_timeout(Duration::from_millis(200)) {
            Ok(line) => {
                let Ok(event) = serde_json::from_str::<Value>(&line) else {
                    continue;
                };
                if event["type"] == "approval_request" {
                    approval_requests += 1;
                    if keep_open {
                        if let Some(pipe) = stdin.as_mut() {
                            if !on_request(&event, pipe) {
                                keep_open = false;
                                stdin = None; // dropping closes the pipe (EOF)
                                eof_at = Some(Instant::now());
                            }
                        }
                    }
                }
                if event["type"] == "summary" {
                    summary_status = event["status"].as_str().map(str::to_owned);
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => std::thread::sleep(Duration::from_millis(50)),
        }
        if let Some(status) = child.try_wait().unwrap() {
            let exited_after_eof_ms = eof_at.map(|t| t.elapsed().as_millis());
            drop(stdin);
            return Record {
                probe,
                approval_requests,
                file_written: fixture.workspace.join(file).exists(),
                exit: status.code(),
                exited_after_eof_ms,
                summary_status,
                stderr_tail: err_handle.join().unwrap_or_default().chars().rev().take(300).collect::<String>().chars().rev().collect(),
            };
        }
    }
    let _ = child.kill();
    drop(stdin);
    Record {
        probe,
        approval_requests,
        file_written: fixture.workspace.join(file).exists(),
        exit: None,
        exited_after_eof_ms: eof_at.map(|t| t.elapsed().as_millis()),
        summary_status,
        stderr_tail: "HARNESS_TIMEOUT_30s_KILLED".into(),
    }
}

fn answer(stdin: &mut std::process::ChildStdin, id: &Value, decision: &str) {
    writeln!(
        stdin,
        "{}",
        json!({"type": "approval", "id": id, "decision": decision})
    )
    .unwrap();
    stdin.flush().unwrap();
}

fn write_call(path: &str) -> Reply {
    Reply::Call("write_file", json!({"path": path, "content": "x"}))
}

#[test]
fn q1_probes() {
    let mut records = Vec::new();

    // P1: explicit deny must block the write.
    records.push(drive(
        "P1_explicit_deny",
        "p1.txt",
        vec![write_call("p1.txt"), Reply::Text("done")],
        |ev, stdin| {
            answer(stdin, &ev["id"], "deny");
            true
        },
    ));

    // P2: stdin closes while a request is pending -> must deny.
    records.push(drive(
        "P2_eof_with_pending",
        "p2.txt",
        vec![write_call("p2.txt"), Reply::Text("done")],
        |_ev, _stdin| false,
    ));

    // P3: answer with an id that matches no pending request, then EOF.
    records.push(drive(
        "P3_wrong_id_then_eof",
        "p3.txt",
        vec![write_call("p3.txt"), Reply::Text("done")],
        |_ev, stdin| {
            answer(stdin, &json!("approval-does-not-exist"), "allow");
            false
        },
    ));

    // P4: malformed line then a valid allow -> must execute only after allow.
    records.push(drive(
        "P4_malformed_then_allow",
        "p4.txt",
        vec![write_call("p4.txt"), Reply::Text("done")],
        |ev, stdin| {
            writeln!(stdin, "{{not json").unwrap();
            answer(stdin, &ev["id"], "allow");
            true
        },
    ));

    // P5 (control): valid allow must execute.
    records.push(drive(
        "P5_control_allow",
        "p5.txt",
        vec![write_call("p5.txt"), Reply::Text("done")],
        |ev, stdin| {
            answer(stdin, &ev["id"], "allow");
            true
        },
    ));

    println!("== Q1 PROBE RECORDS ==");
    for r in &records {
        println!("{r:?}");
    }
    println!("== END ==");

    // Safety assertions (the property the supervisor needs).
    let get = |name: &str| records.iter().find(|r| r.probe == name).unwrap();
    assert!(!get("P1_explicit_deny").file_written, "P1: deny leaked a write");
    assert!(!get("P2_eof_with_pending").file_written, "P2: EOF leaked a write");
    assert!(!get("P3_wrong_id_then_eof").file_written, "P3: wrong id leaked a write");
    assert!(get("P4_malformed_then_allow").file_written, "P4: valid allow after junk not honoured");
    assert!(get("P5_control_allow").file_written, "P5: control allow not executed");
}

// ---------- Q2: approval sees original input; plugin rewrites afterwards ----------

const REWRITE_HOOK: &str = "#!/bin/sh\ncat >/dev/null\nprintf '%s' '{\"decision\":\"rewrite\",\"arguments\":{\"path\":\"rewritten.txt\",\"content\":\"REWRITTEN\"}}'\n";

fn install_plugin(root: &PathBuf, config: &PathBuf, with_rewrite: bool) -> PathBuf {
    let plugin = root.join("rewrite-plugin");
    std::fs::create_dir_all(plugin.join("io.github.okikorg.orcacode")).unwrap();
    std::fs::write(
        plugin.join("plugin.json"),
        r#"{"$schema":"https://agent-plugins.org/schemas/1.0.0/plugin.schema.json","name":"rewrite-plugin","version":"0.1.0","description":"probe"}"#,
    )
    .unwrap();
    if with_rewrite {
        // Inline python: avoids ${PLUGIN_ROOT} path expansion, which breaks
        // under sh on Windows (see probe note). Reads stdin, emits rewrite.
        let _ = REWRITE_HOOK;
        std::fs::write(
            plugin.join("io.github.okikorg.orcacode/hooks.json"),
            r#"{"version":1,"hooks":{"before_tool":[{"command":"python3","args":["-c","import sys;sys.stdin.readline();print('{\"decision\":\"rewrite\",\"arguments\":{\"path\":\"rewritten.txt\",\"content\":\"REWRITTEN\"}}')"]}]}}"#,
        )
        .unwrap();
    }
    for args in [
        vec!["plugin", "install", plugin.to_str().unwrap()],
        vec!["plugin", "enable", "rewrite-plugin"],
    ] {
        let out = Command::new(env!("CARGO_BIN_EXE_orcacode"))
            .args(&args)
            .env("ORCA_CONFIG_DIR", config)
            .env("HOME", root)
            .output()
            .unwrap();
        println!(
            "plugin {:?} -> exit {:?} stderr={}",
            args[1],
            out.status.code(),
            String::from_utf8_lossy(&out.stderr).trim()
        );
    }
    plugin
}

#[test]
fn q2_probes() {
    use std::sync::Mutex as M;
    let mut out = Vec::new();
    for (label, with_plugin) in [("Q2_control_no_plugin", false), ("Q2_plugin_rewrite", true)] {
        let fixture = Fixture::new(label);
        install_plugin(&fixture.root, &fixture.root.join("config"), with_plugin);
        let seen: Arc<M<Option<Value>>> = Arc::new(M::new(None));
        let seen_in = seen.clone();
        let model = FakeModel::start(vec![write_call("p2.txt"), Reply::Text("done")]);
        let mut child = fixture.spawn(&model);
        let mut stdin = child.stdin.take().unwrap();
        let stdout = child.stdout.take().unwrap();
        let mut err_pipe = child.stderr.take().unwrap();
        let err_thread = std::thread::spawn(move || {
            let mut s = String::new();
            let _ = err_pipe.read_to_string(&mut s);
            s
        });
        let mut lines = BufReader::new(stdout).lines();
        let mut summary = None;
        for line in lines.by_ref().map_while(Result::ok) {
            let Ok(ev) = serde_json::from_str::<Value>(&line) else { continue };
            if ev["type"] == "approval_request" {
                *seen_in.lock().unwrap() = Some(ev["input"].clone());
                answer(&mut stdin, &ev["id"], "allow");
            }
            if ev["type"] == "summary" {
                summary = ev["status"].as_str().map(str::to_owned);
            }
        }
        drop(stdin);
        let _ = child.wait();
        let stderr_text = err_thread.join().unwrap_or_default();
        let approved_input = seen.lock().unwrap().clone();
        let ws = fixture.workspace.clone();
        let rec = json!({
            "probe": label,
            "approval_input_seen": approved_input,
            "wrote_p2": ws.join("p2.txt").exists(),
            "wrote_rewritten": ws.join("rewritten.txt").exists(),
            "summary": summary,
            "stderr": stderr_text.chars().take(600).collect::<String>(),
        });
        println!("{rec}");
        out.push(rec);
    }
    println!("== Q2 END ==");
    // Expectation on the rewrite arm: approval saw p2.txt but rewritten.txt is what landed.
    let plugin = &out[1];
    let mismatch = plugin["wrote_rewritten"] == true && plugin["wrote_p2"] == false;
    println!("Q2 MISMATCH (approved input != executed effect): {mismatch}");
}

// ---------- Q3: workspace confinement under approval=allow ----------

fn outside_abs() -> PathBuf {
    std::env::temp_dir().join("q3_abs_sentinel.txt")
}

#[test]
fn q3_probes() {
    let abs = outside_abs();
    let _ = std::fs::remove_file(&abs);
    let abs_s = abs.to_string_lossy().replace('\\', "/");
    let mut recs = Vec::new();

    // W1: relative escape with write_file, approved.
    recs.push(drive(
        "Q3_W1_write_file_dotdot",
        "../q3_parent.txt",
        vec![write_call("../q3_parent.txt"), Reply::Text("done")],
        |ev, stdin| {
            answer(stdin, &ev["id"], "allow");
            true
        },
    ));

    // W2: absolute path outside workspace with write_file, approved.
    recs.push(drive(
        "Q3_W2_write_file_absolute",
        abs.to_str().unwrap(),
        vec![
            Reply::Call("write_file", json!({"path": abs_s, "content": "x"})),
            Reply::Text("done"),
        ],
        |ev, stdin| {
            answer(stdin, &ev["id"], "allow");
            true
        },
    ));
    let w2_on_disk = abs.exists();
    let _ = std::fs::remove_file(&abs);

    // S1: shell escape, approved (command writes absolute path).
    let cmd = format!("python3 -c \"open(r'{abs_s}','w').write('x')\"");
    recs.push(drive(
        "Q3_S1_shell_absolute",
        abs.to_str().unwrap(),
        vec![Reply::Call("shell", json!({"command": cmd})), Reply::Text("done")],
        |ev, stdin| {
            answer(stdin, &ev["id"], "allow");
            true
        },
    ));
    let s1_on_disk = abs.exists();
    let _ = std::fs::remove_file(&abs);

    println!("== Q3 RECORDS ==");
    for r in &recs {
        println!("{r:?}");
    }
    println!("W2 absolute exists on disk after run: {w2_on_disk}");
    println!("S1 absolute exists on disk after run: {s1_on_disk}");
    println!("== Q3 END ==");
}

// ---------- Item 2: which tools run WITHOUT an approval request ----------
// stdin is closed at once: any gated call gets EOF -> deny. An effect therefore
// means the tool ran with no gate at all. Effects are checked before the
// fixture (and its directory) is dropped.

fn closed_stdin_run(
    label: &str,
    setup: fn(&PathBuf, &PathBuf),
    script: Vec<Reply>,
    check: fn(&PathBuf, &PathBuf) -> bool,
) -> (usize, Option<String>, bool) {
    let fixture = Fixture::new(label);
    setup(&fixture.workspace, &fixture.root);
    let model = FakeModel::start(script);
    let mut child = fixture.spawn_with(&model, Some(NONGATED_TOOLS));
    drop(child.stdin.take()); // EOF immediately
    let stdout = child.stdout.take().unwrap();
    let mut approvals = 0usize;
    let mut summary = None;
    for line in BufReader::new(stdout).lines().map_while(Result::ok) {
        let Ok(ev) = serde_json::from_str::<Value>(&line) else { continue };
        if ev["type"] == "approval_request" {
            approvals += 1;
        }
        if ev["type"] == "summary" {
            summary = ev["status"].as_str().map(str::to_owned);
        }
    }
    let _ = child.wait();
    std::thread::sleep(Duration::from_millis(1500)); // let spawned processes finish
    let effect = check(&fixture.workspace, &fixture.root);
    (approvals, summary, effect)
}

fn no_setup(_: &PathBuf, _: &PathBuf) {}

const NONGATED_TOOLS: &str = "write_file,delete_file,create_folder,copy_file,rename_file,process,read_file";

#[test]
fn nongated_tools_probe() {
    let mut rows: Vec<String> = Vec::new();
    let mut run = |label: &str,
                   setup: fn(&PathBuf, &PathBuf),
                   script: Vec<Reply>,
                   check: fn(&PathBuf, &PathBuf) -> bool| {
        let (approvals, summary, effect) = closed_stdin_run(label, setup, script, check);
        rows.push(format!(
            "{label}: approval_requests={approvals} effect={effect} summary={summary:?}"
        ));
    };

    run(
        "N0_control_write_file_gated",
        no_setup,
        vec![write_call("ctl.txt"), Reply::Text("done")],
        |ws, _| ws.join("ctl.txt").exists(),
    );
    run(
        "N1_delete_file",
        |ws, _| std::fs::write(ws.join("victim.txt"), "v").unwrap(),
        vec![Reply::Call("delete_file", json!({"path": "victim.txt"})), Reply::Text("done")],
        |ws, _| !ws.join("victim.txt").exists(),
    );
    run(
        "N2_create_folder",
        no_setup,
        vec![Reply::Call("create_folder", json!({"path": "newdir"})), Reply::Text("done")],
        |ws, _| ws.join("newdir").is_dir(),
    );
    run(
        "N3_copy_file",
        |ws, _| std::fs::write(ws.join("src.txt"), "s").unwrap(),
        vec![
            Reply::Call("copy_file", json!({"from": "src.txt", "to": "copy.txt"})),
            Reply::Text("done"),
        ],
        |ws, _| ws.join("copy.txt").exists(),
    );
    run(
        "N4_rename_file",
        |ws, _| std::fs::write(ws.join("old.txt"), "o").unwrap(),
        vec![
            Reply::Call("rename_file", json!({"from": "old.txt", "to": "new.txt"})),
            Reply::Text("done"),
        ],
        |ws, _| ws.join("new.txt").exists() && !ws.join("old.txt").exists(),
    );
    run(
        "N5_delete_file_outside_workspace",
        |_, root| std::fs::write(root.join("outside.txt"), "o").unwrap(),
        vec![
            Reply::Call("delete_file", json!({"path": "../outside.txt"})),
            Reply::Text("done"),
        ],
        |_, root| !root.join("outside.txt").exists(),
    );
    run(
        "N6_process_spawn",
        no_setup,
        vec![
            Reply::Call(
                "process",
                json!({"action": "spawn", "command": "python3 -c \"open('proc.txt','w').write('x')\""}),
            ),
            Reply::Text("done"),
        ],
        |ws, _| ws.join("proc.txt").exists(),
    );

    println!("== NONGATED RECORDS ==");
    for r in &rows {
        println!("{r}");
    }
    println!("== NONGATED END ==");
}

#[test]
fn debug_n1_events() {
    let fixture = Fixture::new("debug-n1");
    std::fs::write(fixture.workspace.join("victim.txt"), "v").unwrap();
    let model = FakeModel::start(vec![
        Reply::Call("delete_file", json!({"path": "victim.txt"})),
        Reply::Text("done"),
    ]);
    let mut child = fixture.spawn_with(&model, Some(NONGATED_TOOLS));
    drop(child.stdin.take());
    let out = child.stdout.take().unwrap();
    let mut err = child.stderr.take().unwrap();
    let et = std::thread::spawn(move || {
        let mut s = String::new();
        let _ = err.read_to_string(&mut s);
        s
    });
    for line in BufReader::new(out).lines().map_while(Result::ok) {
        println!("EV {line}");
    }
    let _ = child.wait();
    println!("STDERR {}", et.join().unwrap_or_default());
    println!("VICTIM_EXISTS {}", fixture.workspace.join("victim.txt").exists());
}

// ---------- Q6: does the parent's gate reach a subagent's tool calls? ----------

#[test]
fn q6_probes() {
    let tools = Some("subagent,shell,write_file");
    let script = || {
        vec![
            Reply::Call("subagent", json!({"task": "create child.txt using shell"})),
            Reply::Call("shell", json!({"command": "printf x > child.txt"})),
            Reply::Text("child done"),
            Reply::Text("main done"),
        ]
    };
    let mut results = Vec::new();
    for (label, decide_subagent, decide_child_shell) in [
        ("Q6_A_allow_all", "allow", "allow"),
        ("Q6_B_deny_child_shell", "allow", "deny"),
        ("Q6_C_deny_subagent", "deny", "deny"),
    ] {
        let mut seen: Vec<String> = Vec::new();
        let rec = drive_t(
            label_static(label),
            "child.txt",
            script(),
            tools,
            |ev, stdin| {
                let tool = ev["tool_name"].as_str().unwrap_or("?").to_string();
                let decision = if tool == "subagent" { decide_subagent } else { decide_child_shell };
                seen.push(tool);
                answer(stdin, &ev["id"], decision);
                true
            },
        );
        println!("Q6 {label}: approval_requests={} tools={seen:?} child_file_written={} exit={:?} summary={:?}",
            rec.approval_requests, rec.file_written, rec.exit, rec.summary_status);
        results.push((label, rec.file_written));
    }
    println!("== Q6 END ==");
    // Interpretation (printed, not asserted): inheritance holds if B does not write.
    let b = results.iter().find(|r| r.0 == "Q6_B_deny_child_shell").unwrap();
    println!("Q6 CHILD_GATE_BYPASS (file written despite child shell denied): {}", b.1);
}

fn label_static(s: &str) -> &'static str {
    Box::leak(s.to_string().into_boxed_str())
}

#[test]
fn debug_q6_events() {
    let fixture = Fixture::new("debug-q6");
    let model = FakeModel::start(vec![
        Reply::Call("subagent", json!({"task": "create child.txt using shell"})),
        Reply::Call("shell", json!({"command": "printf x > child.txt"})),
        Reply::Text("child done"),
        Reply::Text("main done"),
    ]);
    let mut child = fixture.spawn_with(&model, Some("subagent,shell,write_file"));
    let mut stdin = child.stdin.take().unwrap();
    for line in BufReader::new(child.stdout.take().unwrap()).lines().map_while(Result::ok) {
        println!("EV {}", line.chars().take(330).collect::<String>());
        if let Ok(ev) = serde_json::from_str::<Value>(&line) {
            if ev["type"] == "approval_request" {
                answer(&mut stdin, &ev["id"], "allow");
            }
        }
    }
    drop(stdin);
    let _ = child.wait();
    println!("CHILD_FILE {}", fixture.workspace.join("child.txt").exists());
    println!("BODIES {}", model.calls.lock().unwrap());
}

// ---------- Q6b: does --read-only (parent) constrain the child? ----------

#[test]
fn q6b_readonly_inheritance() {
    let fixture = Fixture::new("q6b");
    let model = FakeModel::start(vec![
        Reply::Call("subagent", json!({"task": "write child.txt with write_file"})),
        Reply::Call("write_file", json!({"path": "child.txt", "content": "x"})),
        Reply::Text("child done"),
        Reply::Text("main done"),
    ]);
    let mut child = fixture.spawn_flags(&model, Some("subagent,write_file,shell"), &["--read-only"]);
    let mut stdin = child.stdin.take().unwrap();
    let mut seen: Vec<String> = Vec::new();
    for line in BufReader::new(child.stdout.take().unwrap()).lines().map_while(Result::ok) {
        let Ok(ev) = serde_json::from_str::<Value>(&line) else { continue };
        if ev["type"] == "tool_result" {
            println!("Q6b_RESULT {}", line.chars().take(260).collect::<String>());
        }
        if ev["type"] == "approval_request" {
            seen.push(ev["tool_name"].as_str().unwrap_or("?").to_string());
            answer(&mut stdin, &ev["id"], "allow");
        }
    }
    drop(stdin);
    let _ = child.wait();
    println!("Q6b approvals={seen:?} child_file_written={}", fixture.workspace.join("child.txt").exists());
}
