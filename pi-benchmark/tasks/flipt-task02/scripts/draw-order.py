#!/usr/bin/env python3
"""Sorteio da ordem de execução (original x rust). Não executa nenhum agente.

Algoritmo: random.Random(seed).shuffle() sobre a lista de agentes, na ordem da lista de
entrada, usando o gerador Mersenne Twister do Python (versão registrada no JSON).

Uso:
  python scripts/draw-order.py draw OUT.json [--seed N]
      Sem --seed, a semente é gerada por secrets.randbits(64) e registrada.
  python scripts/draw-order.py verify OUT.json
      Recalcula a ordem a partir da semente gravada e compara com o resultado gravado.
"""
import argparse
import json
import random
import secrets
import sys
from datetime import datetime, timezone

AGENTS = ["pi-original", "pi-rust"]
ALGORITHM = "random.Random(seed).shuffle(list) — Mersenne Twister (CPython)"


def shuffle(seed, items):
    lst = list(items)
    random.Random(seed).shuffle(lst)
    return lst


def draw(out, seed=None):
    generated = seed is None
    if generated:
        seed = secrets.randbits(64)
    order = shuffle(seed, AGENTS)
    record = {
        "drawn_utc": datetime.now(timezone.utc).isoformat(),
        "input": AGENTS,
        "algorithm": ALGORITHM,
        "python_version": sys.version.split()[0],
        "seed": seed,
        "seed_generated_by_script": generated,
        "order": order,
        "execution_rule": "sequencial, um agente por vez; o segundo só inicia após o primeiro terminar",
        "agents_started_by_this_script": False,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1)
    print(f"seed={seed} order={order} -> {out}")
    return 0


def verify(path):
    with open(path, encoding="utf-8") as f:
        rec = json.load(f)
    recomputed = shuffle(rec["seed"], rec["input"])
    ok = recomputed == rec["order"]
    print(f"recalculada={recomputed} gravada={rec['order']} reproduzivel={ok}")
    return 0 if ok else 2


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw")
    d.add_argument("out")
    d.add_argument("--seed", type=int)
    v = sub.add_parser("verify")
    v.add_argument("out")
    args = p.parse_args(argv)
    if args.cmd == "draw":
        return draw(args.out, args.seed)
    return verify(args.out)


if __name__ == "__main__":
    sys.exit(main())
