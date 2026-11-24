"""Agente ARTIFICIAL para testes de integração. Não é o Pi nem o Pi-Rust; não chama modelo.

Escreve ok.txt no cwd (workspace permitido). Se FAKE_TOUCH_TASK estiver definido, também
altera ../TASK.md (fora do que o isolamento permite). Emite um message_end com custo 0.2.
"""
import json
import os
import sys

open("ok.txt", "w", encoding="utf-8").write("x")
if os.environ.get("FAKE_TOUCH_TASK"):
    with open(os.path.join("..", "TASK.md"), "a", encoding="utf-8") as f:
        f.write("alterado pelo agente artificial\n")
event = {"type": "message_end", "message": {"role": "assistant", "usage": {
    "input": 1, "output": 1, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 2,
    "cost": {"total": 0.2}}}}
print(json.dumps(event), flush=True)
sys.exit(0)
