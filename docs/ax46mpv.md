# AX46MPV Spec

RTL：`docs/ax45mpv/andes_ip/kv_core/ucore/hdl/`（按 46 `cfg.txt` 实例化）。

**寄存器链（posedge）：** `f0/f1/f2`（`kv_ifu`）→ `fq_*`（`kv_fq`）→ `id_*`（`kv_ipipe` 内）→ `ii_*`（`kv_iiq_wrap`）→ `ex_*` → `mm_*` → `lx_*` → `wb_*`（`kv_ipipe`）。相邻带 `_` 前缀的寄存器组就是一级流水；FQ/IIQ 是带 wptr/rptr 的 FIFO，不是单寄存器级。

---

## IF — `kv_ifu`（`f0`、`f1` 两级寄存器 + 组合选址）

**PC 寄存器：`f0_pc`、`f1_va`。**

### next PC 来源

| 信号 | 来源 | 选择条件 |
|------|------|----------|
| `target_pc` | `kv_pq` 输出 | 正常顺序/预测前进 |
| `seq_pc` | `kv_ifu` 内寄存器 | `req_addr[MSB:3] + 8`（bundle 8B 前进） |
| `redirect_pc` | `kv_ipipe` 输出 | `redirect` 时强制 |
| `f0_pc` | `f0` 寄存器 | `f0_valid=1` 时保持已锁 PC |

`target_pc` MUX（`kv_pq`）：BTB 命中 → `bpu_info_target`；基本块内继续 → latched target；否则 → `seq_pc`。  
`req_addr` MUX（`kv_ifu`）：`redirect ? redirect_pc : f0_valid ? f0_pc : target_pc`。

### `f0` 级

- 寄存器：`f0_valid`、`f0_pc`、`f0_bblk_start`。
- 用途：redirect 等 BPU ready、recover、prefetch、EX9、cache 操作等把 PC 锁在 `f0_pc`；`fetch_issue` 后 `f0_valid` 清。
- `f0_valid` 置位：`f0_valid_set`（redirect 但 stall、resume、retry、prefetch、ECC recover…）；清：`fetch_issue` 或 cctl。

### `f1` 级

- 寄存器：`f1_valid`、`f1_va`、`f1_req_type`、`f1_req_start`。
- `fetch_issue = req_valid & req_ready` 时 `f1_va <= req_addr`。
- 非 ILM 且 MMU 使能：`ifu_itlb_req_valid` 发 ITLB，输入 `f1_va`，返回 `itlb_ifu_pa` → `f1_pa`。
- ILM 命中：走 `ifu_ilm_req_*`，无 ITLB。
- `f1_pa` 输出给 `kv_icu`（`ifu_icu_f1_pa`）；I$ index 用 `[10:6]`（页内 VA=PA），tag 用 `f1_pa` 高位 — VIPT 组织。

---

## IC — `kv_ifu` + `kv_icu`（`f2` 寄存器）

**PC 寄存器：`f2_va`、`f2_pa`。**

- `f2_valid <= f1_valid & ~f2_kill`；`f2_va <= f1_va`；`f2_pa <= f1_pa`。
- 等 I$/ILM 返回 `fetch_resp_inst`；`f2_cache_miss` → `ST_MH`，`f2_itlb_miss` → `ST_FILL_TLB`。
- 返回后经 `kv_pq` 做 RVC/双发对齐，生成 `ifu_i0_pc`、`ifu_i1_pc` 及 `ifu_i0/i1_pred_*`，随 `fq_wr` 写入 **FQ(4)**。
- FQ 是带 `wptr`/`rptr` 的 4 项环形 FIFO（`kv_fq.v`），每项 75b；不是单拍寄存器。

---

## ID — `kv_ipipe`（`id_*` 寄存器）

**PC 寄存器：`id_i0_pc`、`id_i1_pc`。**

- FQ 出队后 `id_i0_pc <= ifu_i0_pc` 等；`kv_dec` 组合译码 `ifd_i0_instr` → `id_i0_ctrl[374:0]`。
- `id_i0_alive`/`id_i1_alive` 由 `kv_uins_ctl` 状态机维护；EX9 lookup 时 `id_uinstr_sel` 替换 i0 控制字。
- `iiq_w_valid = {id_i1_alive, id_i0_alive}`；`id_ready` 满时 FQ 停 pop、前端 `ipipe_ifu_stall`。

---

## IS — `kv_iiq_wrap` + `kv_iiu` + `kv_iiu_scb`（`ii_*` 寄存器）

**PC 寄存器：`ii_i0_pc`、`ii_i1_pc`。**

- IIQ pop 时 `ii_i0_pc <= iiq_i0_pc`（`iiq_i0_pc = id_i0_pc`）。
- `kv_iiu_scb` 组合算 hazard / bypass / late；`ii_ready = ~(lx_stall | ii_*_stall)` 控制 IIQ 是否 pop。
- 发射后 PC 打入 `ex_i0_pc <= ii_i0_pc`。

---

## EX — `kv_ipipe`（`ex_*` 寄存器）

**PC 寄存器：`ex_i0_pc`、`ex_i1_pc`。**

- `ex_i0_pc <= ii_i0_pc`（`ex_ctrl_en` 时）。
- `bru0_pc = ex_i0_pc`、`bru1_pc = ex_i1_pc`；`ls_req_pc = ex_i0/i1_pc[11:0]`。

---

## MM — `kv_ipipe`（`mm_*` 寄存器）

**PC 寄存器：`mm_i0_pc`、`mm_i1_pc`、`mm_bblk_start_pc`。**

- `mm_i0_pc <= ex_i0_pc`；`mm_bblk_start_pc <= mm_bblk_start_pc_nx`（块起始锁存）。
- `mm_i0_bblk_start_pc = mm_i0_start ? mm_i0_pc : mm_bblk_start_pc`。
- BTB 更新：`mm_btb_update_p0_start_pc = mm_i0_bblk_start_pc`，`target_pc = mm_i0_npc`。
- redirect：`redirect_pc` 在 `wb_i0_redirect → wb_i1_redirect → mm_i0_redirect_final → mm_i1_redirect_final` 优先级 MUX。

---

## LX — `kv_ipipe`（`lx_*` 寄存器）

**PC 寄存器：`lx_i0_pc`、`lx_i1_pc`。**

- `lx_i0_pc <= mm_i0_pc`。
- `bru2_pc = lx_i0_pc`、`bru3_pc = lx_i1_pc`（late 分支）。

---

## WB — `kv_ipipe`（`wb_*` 寄存器）

**PC 寄存器：`wb_i0_pc`、`wb_i1_pc`、`wb_bblk_start_pc`。**

- `wb_i0_pc <= wb_i0_pc_nx`（`wb_valid_en` 时）；`wb_i1_pc <= lx_i1_pc`。
- `wb_btb_update_p0_start_pc = wb_i0_bblk_start_pc`，`target_pc = wb_i0_npc`。
- `wb_i0_redirect` 时 `redirect_pc = wb_i0_npc`。

---

## 时序总表（PC 级）

| 拍 | 动作 |
|----|------|
| C0 | `f0_pc` / `target_pc` → `req_addr` |
| C1 | `f1_va <= req_addr`；ITLB 查 `f1_va` |
| C2 | `f2_va/f2_pa <= f1_*`；I$/ILM 返回 → FQ |
| C3 | `id_i0_pc <= fq_i0_pc`；译码 |
| C4 | `ii_i0_pc <= id_i0_pc`；hazard/发射 |
| C5 | `ex_i0_pc <= ii_i0_pc`；EX 执行 |
| C6 | `mm_i0_pc <= ex_i0_pc`；分支判定向量 |
| C7 | `lx_i0_pc <= mm_i0_pc`；late 执行 |
| C8 | `wb_i0_pc <= lx_i0_pc`；写回/退休 |
