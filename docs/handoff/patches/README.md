# Patches para revisão

## mingbird-mcp-start-new-session.patch

Aplica-se a `Mingbird/mingbird-agent` no commit `c6574a8`, com `git apply`.

Adiciona `start_new_session=(os.name != "nt")` aos dois `subprocess.Popen` de servidores MCP
(`_StdioSession.__init__` e `_probe_stdio`). Sem isso, `_kill_proc_tree` faz `os.killpg` no grupo do
processo pai e mata o próprio app em Linux/macOS.

Verificação (clone local, sem o plugin de patch):
- Antes: a suíte morre (exit 137) em `test_mcp_broker.py` e `test_v200_perf.py`.
- Depois: a suíte termina: 685 passed, 33 failed, 12 skipped (730 coletados).
- Os dois arquivos que matavam o processo: 12 passed.
- `tests/test_issue7_loopback.py::test_local_open_bypasses_proxy` falha também no código original
  (provável efeito do proxy HTTPS do sandbox). Não relacionado à mudança.
