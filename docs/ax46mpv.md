# AX46MPV 取指 — f0 / f1 / f2

RTL：`kv_ifu.v`（`docs/ax45mpv/andes_ip/kv_core/ucore/hdl/`）。

取指是 **三级流水寄存器**：`f0` → `f1` → `f2`。FQ(4) 在 f2 之后，是 FIFO，不算流水级。

---

## f0 — PC 锁存与选择

**干什么：** 锁 PC 或选 next PC，发取指请求。

**`req_addr`（发给 I$/ILM 的地址）：**

```
req_addr = redirect ? redirect_pc
         : f0_valid ? f0_pc
         : target_pc;
```

优先级：`redirect_pc` > `f0_pc` > `target_pc`。

**`f0_pc` 的源（`f0_pc_nx`）：**

| 条件 | 源 |
|------|-----|
| `resume` | `resume_pc` |
| `redirect` | `redirect_pc` |
| cache flush | `f0_pc_flush_init_value` |
| `retry` | `retry_pc` |
| `ex9_lookup_valid` | `ex9_lookup_pc` |
| `fetch_recover` | `recover_pc` |
| prefetch | `prefetch_addr` |

**`f0_valid` 置位：** redirect 但后端 stall、resume、retry、prefetch、recover、EX9、ECC 修正、cctl。清：`fetch_issue`。

---

## f1 — 地址打拍 + ITLB

**干什么：** 把 `req_addr` 打进 `f1_va`，发 ITLB 和 I$/ILM 请求。

- `fetch_issue = req_valid & req_ready` 时 `f1_va <= req_addr`。
- ITLB 查 `f1_va` → `f1_pa`；ILM 命中则无 ITLB。
- 发 `ifu_icu_req_*`（I$）或 `ifu_ilm_req_*`（ILM）。
- I$ VIPT：index `[10:6]`（页内 VA=PA），tag `f1_pa` 高位。

---

## f2 — 取指返回

**干什么：** 等 I$/ILM 返回指令，写 FQ。

- `f2 <= f1`（`f2_valid <= f1_valid`，`f2_va <= f1_va`，`f2_pa <= f1_pa`）。
- I$ miss 进 `ST_MH` 等回填；ITLB miss 进 `ST_FILL_TLB`。
- 返回后 RVC 拆包、双发对齐，生成 `ifu_i0/i1_pc`，`fq_wr` 写入 **FQ(4)**。

---

## 时序

| 拍 | 动作 |
|----|------|
| C0 | `f0` 锁/选 PC；`req_addr` 发出 |
| C1 | `f1_va <= req_addr`；ITLB 查；发请求 |
| C2 | `f2 <= f1`；等返回；写 FQ |
