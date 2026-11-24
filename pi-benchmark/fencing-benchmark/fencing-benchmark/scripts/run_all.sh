#!/usr/bin/env bash
# Full reproducible run: real services -> scenarios (N per scenario) -> races -> failover -> latency -> results.json
#   REPS=100 PERF_OPS=1000 scripts/run_all.sh
# Each candidate has its own service instances (see bench/harness.py TOPOLOGY), so the four tracks run in
# parallel without sharing a coordinator. Latency runs last and sequentially, so tracks do not skew it.
set -euo pipefail
cd "$(dirname "$0")/.."
REPS=${REPS:-100}
PERF_OPS=${PERF_OPS:-1000}
IMPLS="statepact-redis zk-redis-lua statepact-pg etcd-pg"
PY=.venv/bin/python
mkdir -p raw/logs

python3 scripts/svc.py stop-all >/dev/null 2>&1 || true
scripts/start_services.sh

for impl in $IMPLS; do
  (
    $PY bench/harness.py --impl "$impl" --phase scenarios --reps "$REPS" --out raw > "raw/logs/$impl-scenarios.out" 2>&1
    $PY bench/harness.py --impl "$impl" --phase race      --reps "$REPS" --out raw > "raw/logs/$impl-race.out" 2>&1
    $PY bench/harness.py --impl "$impl" --phase failover  --reps "$REPS" --out raw > "raw/logs/$impl-failover.out" 2>&1
    if [ "$impl" = "etcd-pg" ]; then   # ablation of the v1 design (race only), after the candidate on the same services
      $PY bench/harness.py --impl etcd-pg-v1 --phase race --reps "$REPS" --out raw > "raw/logs/etcd-pg-v1-race.out" 2>&1
    fi
    echo "track $impl finished" >> raw/logs/tracks.out
  ) &
done
wait

for impl in $IMPLS; do
  $PY bench/harness.py --impl "$impl" --phase perf --perf-ops "$PERF_OPS" --out raw > "raw/logs/$impl-perf.out" 2>&1
done

$PY bench/analyze.py
python3 scripts/svc.py stop-all >/dev/null 2>&1 || true
echo "done"
