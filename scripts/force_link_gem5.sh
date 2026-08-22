#!/bin/bash
# Force-link gem5.{opt,fast} using SCons-generated rsp (SCons CLI Entry skips LINK).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build/RISCV"
LABEL="${1:-fast}"
ENVF="$BUILD/gem5.${LABEL}.link.env"
RSP="$BUILD/gem5.${LABEL}.link.rsp"
if [[ ! -f "$ENVF" || ! -f "$RSP" ]]; then
  echo "Missing $ENVF or $RSP — run: scons -n --ignore-style build/RISCV/gem5.$LABEL" >&2
  exit 1
fi

CXX=$(sed -n 's/^CXX=//p' "$ENVF")
LINKFLAGS=$(sed -n 's/^LINKFLAGS=//p' "$ENVF")
LIBS=$(sed -n 's/^LIBS=//p' "$ENVF")
LIBPATH=$(sed -n 's/^LIBPATH=//p' "$ENVF")
LIBFLAGS=$(sed -n 's/^LIBFLAGS=//p' "$ENVF")
LIBDIRFLAGS=$(sed -n 's/^LIBDIRFLAGS=//p' "$ENVF")
OUT=$(sed -n 's/^OUT=//p' "$ENVF")

# Prefer SCons-expanded $_LIBDIRFLAGS / $_LIBFLAGS when present.
EXTRA=()
rewrite_tok() {
  local tok="$1"
  case "$tok" in
    -Lext/*|-L./ext/*) echo "-L$BUILD/${tok#-L}" ;;
    -L/*) echo "$tok" ;;
    -L*) echo "-L$BUILD/${tok#-L}" ;;
    ext/*|*.a)
      if [[ "$tok" == /* ]]; then echo "$tok"
      else echo "$BUILD/$tok"; fi
      ;;
    *) echo "$tok" ;;
  esac
}
if [[ -n "${LIBDIRFLAGS}" ]]; then
  for tok in $LIBDIRFLAGS; do EXTRA+=("$(rewrite_tok "$tok")"); done
else
  for d in $LIBPATH; do
    [[ -n "$d" ]] || continue
    EXTRA+=("$(rewrite_tok "-L$d")")
  done
fi
if [[ -n "${LIBFLAGS}" ]]; then
  for tok in $LIBFLAGS; do EXTRA+=("$(rewrite_tok "$tok")"); done
else
  for l in $LIBS; do
    [[ -n "$l" ]] || continue
    case "$l" in
      *.a) EXTRA+=("$(rewrite_tok "$l")") ;;
      *) EXTRA+=("-l$l") ;;
    esac
  done
fi
# Host libs often missing from $LIBS expansion when taken outside SCons.
EXTRA+=(-lpng -lpthread -ldl -lutil)

echo "[force-link] $OUT  objs=$(wc -l < "$RSP")  starting..."
mapfile -t OBJS < "$RSP"
# shellcheck disable=SC2086
"$CXX" -o "$OUT" $LINKFLAGS "${OBJS[@]}" "${EXTRA[@]}"
chmod +x "$OUT"
ls -lh "$OUT"
echo "[force-link] OK"
