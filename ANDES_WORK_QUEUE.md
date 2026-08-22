# Andes alignment work queue (agent ticks one `NEXT` per wake)

Tick contract: complete **one** row below, or implement gem5 for an existing rule in `docs/andes_46mpv_rtl_rules.md`.

## NEXT (do this first)

| id | block | action |
|----|-------|--------|
| **P3-exlx-design** | gem5 design | **done** — fix requirements in `rtl_rules.md` (exlx-design); impl frozen |
| **P3-exlx-impl** | gem5 | **blocked** — user pick A/B/C in `rtl_rules.md` exlx-pick |
| **P3-exlx-pick** | design | Approach options A/B/C documented — **done** |
| **P3-post-rebase** | verify | `execute.o` builds on `scalar` @ upstream/stable `62c7bf2848` — **done** |

### P3-gem5-ex-lx sub-steps (in order)

| step | action | status |
|------|--------|--------|
| exlx-1 | Document RTL rule (EX∥LX) in `rtl_rules.md` | done |
| exlx-2 | Map Minor gap: issue uses 4 FU pipes but no stage tag; scoreboard ≠ pipe occupancy | done |
| exlx-3 | Prototype: `andesStageOccupancy` — late issued inst frees early FU same cycle | done |
| exlx-4 | Gauge only after exlx-3; keep `enableAndesIiLxOverlap=False` until then | done — **deadlock** (16 commit/20B ticks); BM off |
| exlx-3b | Fix LX pending deadlock (inFlight vs FU drain) | partial — idle+pre-commit drain; still 16inst stall; redesign |
| exlx-3c | Redesign: `minimumCommitCycle` + LX slot holds (no pending queue) | done — **deadlock** (16 inst); BM off |
| exlx-freeze | Stage-occupancy prototypes frozen until Minor stage model rethink | frozen → P3-ipipe-bypass |

### exlx-A impl sketch (if user picks A)

| step | action |
|------|--------|
| exlx-A1 | Strip `minimumCommitCycle` / `head_inst_might_commit` hooks from late path (`execute.cc` L968–969, L1592, L1881) |
| exlx-A2 | Keep `andesLxStageHolds` + slot block @ issue only (`L851–852`); late always `fu->push` |
| exlx-A3 | Gauge once; if deadlock → revert, try B |

## P1 cfg.txt (verify → rule if missing)

| id | status | notes |
|----|--------|-------|
| P1-cache-mshr | done | MSHR 8/16, SB 8, L1 32K/4way — `andes_46mpv_scalar.py` |
| P1-btb-bp | done | BTB 256, BiMode 256, RAS 4 — frozen BP residual |
| P1-lsu-nb | done | `NDS_NON_BLOCKING_SUPPORT`, `NDS_LSU_LOW_LATENCY` |
| P1-write-around | gap | cfg yes; classic L1 no WA — frozen |

## P2 DS238 (verify → rule if missing)

| id | status | notes |
|----|--------|-------|
| P2-DS168-dual | done | dual-issue matrix → `andes_issue_rules.cc` |
| P2-DS169-loaduse | done | W/D 0cy, B/H 1cy → MemFU `extraAssumedLat` |
| P2-DS172-muldiv | done | fast mul 1cy, div expr |
| P2-DS228-mispred | done | EX 5 / LX 7 → `executeBranchMispredictPenalty*` |

## P3 RTL (systematic 3-line rules)

| id | file | status |
|----|------|--------|
| P3-iiu-scb | `kv_iiu_scb.v` | done — 6 rules in `rtl_rules.md` (late/struct/raw/waw) |
| P3-ipipe-bypass | `kv_ipipe.v` | done — 3 rules (operand mux, ls_base, i1 load-consumer) |
| P3-ipipe-loadb | `kv_ipipe.v` | done — 3 rules (ex_ls_loadb, nbload_hazard, ls_cmt_nbload) |
| P3-lsu-nbload | `kv_lsu*.v` | done — 3 rules (nbload_resp, ROB nbload, m2_nbload_hazard) |
| P3-kv_core-alu | `kv_core.v` | done |
| P3-gem5-ex-lx | gem5 map | frozen — exlx-3c deadlock; BM off |

## Closed (do not reopen without user)

gauge-hold cfg-scrub, BP residual, opLat games, fake-wide issue, II/LX `resultLat` trials (mechanism kept, BM off).
