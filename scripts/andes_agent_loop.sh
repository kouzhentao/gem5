#!/bin/bash
# Andes agent wake loop — one queue item per tick. Restart if prompt changes.
INTERVAL="${ANDES_LOOP_SEC:-60}"
LOG="${ANDES_LOOP_LOG:-/home/kou/gem5/ANDES_STATUS.log}"
PROMPT='Read ANDES_STATUS.txt (FOCUS) and ANDES_WORK_QUEUE.md (first TODO in NEXT table). Do exactly ONE queue item: P4-doc-* extend docs/ax46mpv_issue_hazard.md OR RTL 3-line rule OR gem5 map. Update queue+STATUS+log. First line: Status: <one-line>. Forbidden: exlx A/B, brief-only, BP re-audit, opLat tuning.'
tick() {
  echo "Status: wake | $(date -R)" >> "$LOG"
  echo "AGENT_LOOP_STATUS_andes {\"prompt\":\"$PROMPT\"} $(date -R)"
}
echo "Status: loop start interval=${INTERVAL}s pid=$$ $(date -R)" >> "$LOG"
tick
while true; do
  sleep "$INTERVAL"
  tick
done
