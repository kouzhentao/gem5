#!/bin/bash
# Andes agent wake loop — one queue item per tick. Restart if prompt changes.
INTERVAL="${ANDES_LOOP_SEC:-60}"
LOG="${ANDES_LOOP_LOG:-/home/kou/gem5/ANDES_STATUS.log}"
PROMPT='Read ANDES_STATUS.txt FOCUS and ANDES_WORK_QUEUE.md NEXT. Do exactly ONE queue item: RTL→3-line rule in docs/andes_46mpv_rtl_rules.md OR gem5 map for existing rule. Update queue+STATUS+log. Reply first line: Status: <one line>. Forbidden: Loop tick #, brief-only, BP re-audit, opLat/issueLimit games, gauge-hold without progress. CoreMark is ruler only.'
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
