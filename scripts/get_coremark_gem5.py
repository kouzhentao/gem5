#!/usr/bin/env python3
"""Extract CoreMark/MHz (Andes getcoremark.pl formula: 1e6 / cycles_per_loop)."""

from __future__ import annotations

import argparse
import re
import sys

REPORT_MARK = "======= COREMARK report ======="
CYCLES_RE = re.compile(r"cycle per loop\s*=\s*(\d+)")
SCORE_RE = re.compile(r"COREMARK/MHz\s*=\s*([0-9.+-eE]+)")
TOTAL_SCORE_RE = re.compile(
    r"CoreMark 1\.0\s*:\s*([0-9.+-eE]+)\s*/", re.MULTILINE
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("log", nargs="?", default="-")
    p.add_argument("--target", type=float, default=6.3)
    args = p.parse_args()
    text = sys.stdin.read() if args.log == "-" else open(args.log, encoding="utf-8").read()

    cycles_m = CYCLES_RE.search(text)
    score_m = SCORE_RE.search(text)
    total_m = TOTAL_SCORE_RE.search(text)

    if cycles_m and score_m:
        cycles, score, method = int(cycles_m.group(1)), float(score_m.group(1)), "loop"
    elif total_m:
        score = float(total_m.group(1)) / 1000.0
        cycles = int(round(1_000_000.0 / score)) if score > 0 else 0
        method = "total/1000"
    else:
        print("No CoreMark score found.", file=sys.stderr)
        return 1

    print("======= COREMARK report (gem5) =======")
    print(f"method           = {method}")
    print(f"cycle per loop   = {cycles}")
    print(f"COREMARK/MHz     = {score:.6f}")
    print(f"46MPV target     = {args.target:.1f}")
    print(f"ratio gem5/46    = {score / args.target:.3f}")
    print("======================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
