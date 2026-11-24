#!/usr/bin/env bash
# Start (idempotently) every real service the benchmark needs. Requires scripts/svc.py init to have run once.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/svc.py init
python3 scripts/svc.py start redis-6400 redis-6401 redis-6402 redis-6403 zk etcd pg pg2
python3 scripts/svc.py status
