#!/bin/bash
# Andes gauge: 1m heartbeat. ONE focus per tick (ANDES_STATUS.txt FOCUS=).
cd /home/kou/gem5
while true; do
  sleep 60
  echo 'AGENT_LOOP_STATUS_andes {"prompt":"Continue Andes RTL→gem5. ONE focus only from ANDES_STATUS.txt FOCUS= line (do not switch topics). Work that focus. ALWAYS: (1) first line Status: <summary>; (2) ANDES_STATUS.txt; (3) ANDES_STATUS.log. No Loop tick #. No fake-wide issue/BP. No drive-by edits outside FOCUS."}'
done
