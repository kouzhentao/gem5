# Andes alignment work queue (agent ticks one `NEXT` per wake)

Tick contract: complete **one** row in **P4-doc** (extend `docs/ax46mpv_issue_hazard.md`) **OR** one RTL rule in `docs/andes_46mpv_rtl_rules.md` **OR** gem5 map for existing rule.

**Doc-first policy:** hazard / issue / bypass / ctrl mapping **must be in `ax46mpv_issue_hazard.md` before gem5 8-stage work.** exlx frozen (**C**).

Handoff: read `ANDES_STATUS.txt` FOCUS → do ONE row → update STATUS + this file + append `ANDES_STATUS.log`.

---

## NEXT (do this first — top incomplete row)

| id | block | action | status |
|----|-------|--------|--------|
| **P4-doc-02** | `ax46mpv_issue_hazard.md` §4 | 补全 ctrl **248–281** reg 域（rs/rd/ren/wen）RTL 行号 | **TODO** |
| P4-doc-03 | §4 | `ex_i*_ctrl[204:0]` 完整 II→EX 重映射表 | TODO |
| P4-doc-04 | §5 | bypass `s187–s200` 逐信号真值表（`kv_iiu_scb.v`） | TODO |
| P4-doc-05 | §3 | RAW **s251** 全项展开 + 例子 | TODO |
| P4-doc-06 | §5 | FP bypass `kv_iiu_fscb.v` 表 | TODO |
| P4-doc-07 | §1 | FPU/LSU/CSR 在各 stage 行为一节 | TODO |
| P4-doc-08 | §3 | DS238 Table **168/169** 原文列 ↔ RTL 行号 | TODO |
| P4-doc-09 | §9 | `andes_issue_rules.cc` 逐条 ↔ `kv_iiu_scb` 行号 | TODO |
| P4-doc-10 | `ax46mpv.md` | Backend 框图（II/EX/MM/LX + FU） | TODO |
| P4-rtl-dec | `kv_dec.v` | ≥1 条 ctrl 位 → 3-line rule in `rtl_rules.md` | TODO |
| P4-gem5-8stage | design | 8 级 stage 模型设计草图（**blocked** until P4-doc-02..09 done） | blocked |

### Done (P4 bootstrap)

| id | status | notes |
|----|--------|-------|
| P4-doc-00 | done | 创建 `docs/ax46mpv_issue_hazard.md` + `ax46mpv.md` Backend 链 |
| P4-doc-01 | done | §2 fu 表、§3 hazard 表、§5 bypass 首版、§8 exlx=C |
| P3-exlx-pick | done | **选 C** — LX=stage；A/B 非 stage 忠实；不实现 exlx |

---

## P1 cfg.txt — done

| id | status |
|----|--------|
| P1-cache-mshr / P1-btb-bp / P1-lsu-nb | done |
| P1-write-around | gap frozen |

## P2 DS238 — done

| id | status |
|----|--------|
| P2-DS168-dual → `andes_issue_rules.cc` | done |
| P2-DS169-loaduse | done |
| P2-DS172-muldiv | done |
| P2-DS228-mispred | done |

## P3 RTL rules — done (unless P4-rtl-dec extends)

| id | status |
|----|--------|
| P3-iiu-scb / ipipe-bypass / loadb / lsu-nbload / kv_core-alu | done |
| P3-gem5-ex-lx | **frozen C** |

## Closed (do not reopen without user)

exlx A/B prototypes, gauge-hold, BP re-audit, opLat games, fake-wide issue.

---

## Agent wake prompt (paste Automations)

```
Read ANDES_STATUS.txt FOCUS and ANDES_WORK_QUEUE.md — first TODO in NEXT table.
Extend docs/ax46mpv_issue_hazard.md for that id (mark §7 row done).
Update ANDES_WORK_QUEUE.md, ANDES_STATUS.txt, append ANDES_STATUS.log.
First line: Status: <one-line>. Forbidden: exlx impl, opLat tuning, brief-only.
```
