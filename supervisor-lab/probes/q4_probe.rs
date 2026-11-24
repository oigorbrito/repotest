//! PROBE (supervisor-lab, Q4): does a shell timeout end grandchildren?
//! Not upstream. Records sentinel growth after the tool reports timeout.

use std::time::Duration;

use orca_harness_core::{CancellationToken, Tool, ToolContext};
use orca_harness_tools::ShellTool;
use serde_json::json;

#[tokio::test]
async fn q4_timeout_grandchild_probe() {
    let tmp = std::env::temp_dir();
    let sentinel = tmp.join("q4_grandchild_sentinel.txt");
    let _ = std::fs::remove_file(&sentinel);
    let s = sentinel.to_string_lossy().replace(r"\", "/");
    let script = tmp.join("q4_grandchild.py");
    let body = format!(
        "import time\nfor i in range(75):\n    open(r'{s}','a').write('x')\n    time.sleep(0.2)\n"
    );
    std::fs::write(&script, body).unwrap();
    let sp = script.to_string_lossy().replace(r"\", "/");
    // sh is the direct child of the tool; python is its child (grandchild of the tool's spawn).
    let cmd = format!("python3 \"{sp}\" & wait");
    let tool = ShellTool::local().timeout(Some(Duration::from_secs(1)));
    let ctx = ToolContext {
        call_id: "q4".into(),
        tool_name: "shell".into(),
        cancellation: CancellationToken::new(),
        deadline: None,
    };
    let result = tool.call(json!({"command": cmd}), &ctx).await;
    println!("TOOL RESULT: {result:?}");
    tokio::time::sleep(Duration::from_millis(1500)).await;
    let s1 = std::fs::read(&sentinel).map(|b| b.len()).unwrap_or(0);
    tokio::time::sleep(Duration::from_millis(1500)).await;
    let s2 = std::fs::read(&sentinel).map(|b| b.len()).unwrap_or(0);
    println!("Q4 sentinel bytes at +1.5s: {s1}, at +3.0s: {s2}");
    println!("Q4 GRANDCHILD_ALIVE_AFTER_TIMEOUT: {}", s2 > s1);
    let _ = std::fs::remove_file(&sentinel);
    let _ = std::fs::remove_file(&script);
}
