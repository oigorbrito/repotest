#!/usr/bin/env bash
cd /home/user/spike
for m in llama3.1:8b granite3.3:8b hermes3:8b; do
  tag=$(echo $m | cut -d: -f1)
  AGENT_CTX=16384 ./run_r4.sh mingbird $m 2 /home/user/spike/r4/mb_$tag
  ./run_r4.sh littlecoder $m 2 /home/user/spike/r4/lc_$tag
done
echo R4_DONE
