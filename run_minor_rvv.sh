#!/bin/bash
set -e
cd "$(dirname "$0")"
BIN=./build/RISCV/gem5.opt
CFG=configs/example/gem5_library/riscv-minor-rvv.py
RES=${1:-rvv-saxpy}
VLEN=${2:-1024}
exec "$BIN" "$CFG" "$RES" -v "$VLEN"
