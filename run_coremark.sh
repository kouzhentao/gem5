#!/bin/bash
# Baremetal CoreMark on Andes-aligned Minor+RVV FS
# Default ELF: /home/kou/bm/coremark_bm.elf (ITERATIONS=2 quick gauge).
# Full later:  ./run_coremark.sh /home/kou/bm/coremark_bm_iter4.elf
# Rebuild:     make -C /home/kou/bm ITERATIONS=2 coremark
# Prefer gem5.fast for iteration; fall back to gem5.opt
#
# Stops gem5 soon after the scored-loop report so Minor does not grind
# through CoreMark teardown (multi-minute hang).
set -e
cd "$(dirname "$0")"
COREMARK=${1:-/home/kou/bm/coremark_bm.elf}
OUTDIR=${OUTDIR:-m5out}
if [[ -x ./build/RISCV/gem5.fast ]]; then
  BIN=./build/RISCV/gem5.fast
elif [[ -x ./build/RISCV/gem5.opt ]]; then
  BIN=./build/RISCV/gem5.opt
else
  echo "No gem5.fast/opt found; build with: scons -j\$(nproc) build/RISCV/gem5.fast" >&2
  exit 1
fi
LOG=$(mktemp)
GEM5_PID=""
cleanup() {
  if [[ -n "$GEM5_PID" ]] && kill -0 "$GEM5_PID" 2>/dev/null; then
    kill "$GEM5_PID" 2>/dev/null || true
    wait "$GEM5_PID" 2>/dev/null || true
  fi
  rm -f "$LOG"
}
trap cleanup EXIT

echo "Using $BIN"
mkdir -p "$OUTDIR"
"$BIN" -d "$OUTDIR" configs/example/gem5_library/riscv-minor-rvv-bm.py \
  --binary "$COREMARK" >"$LOG" 2>&1 &
GEM5_PID=$!

# Wait for scored-loop report (or gem5 death / timeout)
ok=0
for _ in $(seq 1 120); do
  if rg -q 'cycle per loop' "$LOG" 2>/dev/null; then
    # allow COREMARK/MHz line to flush
    sleep 0.3
    ok=1
    break
  fi
  if ! kill -0 "$GEM5_PID" 2>/dev/null; then
    break
  fi
  sleep 0.5
done

if [[ "$ok" -eq 1 ]]; then
  echo "(stopping gem5 after COREMARK report — skip Minor teardown)"
  kill "$GEM5_PID" 2>/dev/null || true
  wait "$GEM5_PID" 2>/dev/null || true
  GEM5_PID=""
fi

cat "$LOG"
if [[ -f scripts/get_coremark_gem5.py ]]; then
  python3 scripts/get_coremark_gem5.py "$LOG"
else
  rg -n "COREMARK/MHz|CoreMark 1.0|cycle per loop" "$LOG" || true
fi
