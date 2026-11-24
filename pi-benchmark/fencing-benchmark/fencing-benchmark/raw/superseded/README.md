# raw/superseded/

Data produced by a harness version that had a defect, kept for transparency. Not used in any metric.

- `zk-redis-lua-FAILOVER-before-sync-fix.jsonl`: ZooKeeper + Redis Lua failover run started BEFORE the fix that waits for
  the replica to be fully synchronised before each repetition. Replaced by the rerun in `raw/zk-redis-lua/FAILOVER.jsonl`.

The first StatePact Redis failover run (also before the fix) was overwritten by its rerun, so its raw lines are not kept.
Its observed state at the time it was stopped: 59 token regressions in 60 repetitions, all caused by promoting a replica
that had not finished its resync (see RESULTS.md, "Registro de problemas").
