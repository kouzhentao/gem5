# Andes alignment work queue (agent ticks one `NEXT` per wake)

Handoff: read `ANDES_STATUS.txt` FOCUS → do ONE row → update STATUS + this file + append `ANDES_STATUS.log`.

---

## NEXT

| id | block | action | status |
|----|-------|--------|--------|
| **P4-gem5-8stage-B** | issue_rules | `andesSrcNeedsLatePath` 改读 `resultStageTags` | **TODO** |

### Done (P4)

| id | notes |
|----|-------|
| P4-doc-00..10 | issue_hazard + ax46mpv backend |
| P4-gem5-8stage | §8.1 草图 |
| P4-gem5-map | cantForward + s251 FP |
| P4-gem5-pred-late | Pred late bypass |
| P4-gauge | CM/MHz=3.108 |
| **P4-gem5-8stage-A** | AndesStageTag + scoreboard |
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
