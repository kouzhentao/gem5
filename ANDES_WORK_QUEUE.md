# Andes alignment work queue (agent ticks one `NEXT` per wake)

Handoff: read `ANDES_STATUS.txt` FOCUS → do ONE row → update STATUS + this file + append `ANDES_STATUS.log`.

---

## NEXT

| id | block | action | status |
|----|-------|--------|--------|
| **P4-gauge** | gauge | CoreMark ITER=2 after P4-gem5-map/pred-late | **TODO** |

### Done (P4)

| id | notes |
|----|-------|
| P4-doc-00..01 | issue_hazard bootstrap |
| P4-doc-02 | ctrl 230–286 reg/src |
| P4-doc-03 | §4.5 II→EX 224b 映射 |
| P4-doc-04 | §5.2 s187–s200 bypass |
| P4-doc-05 | §3.4 s251 RAW 例外 |
| P4-doc-06 | §5.4 FP fscb |
| P4-doc-07 | §1.1 FPU/LSU/CSR stage |
| P4-doc-08 | §3.6 DS238↔RTL |
| P4-doc-09 | §9.1 gem5↔RTL |
| P4-doc-10 | ax46mpv Backend 框图 |
| P4-gem5-8stage | issue_hazard §8.1 8级 Minor 草图 |
| P4-gem5-map | cantForward 统一 + s251 FP term6–7 |
| P4-gem5-pred-late | Pred late: andesBranchShouldUseLatePath |
| P3-exlx-pick | exlx **C** frozen |

---

## Closed

Loop/automation, exlx A/B, gauge-hold, BP re-audit, opLat games.

---

## Agent wake prompt

```
Read ANDES_STATUS.txt FOCUS and ANDES_WORK_QUEUE.md NEXT.
Do ONE row. Update handoff files. First line: Status: <one-line>.
```
