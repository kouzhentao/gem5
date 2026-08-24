# AX46MPV Spec

RTL：`docs/ax45mpv/andes_ip/kv_core/ucore/hdl/`（按 46 `cfg.txt` 实例化）。

---

## 流水级与寄存器

| 级 | 寄存器组 | 本拍动作 |
|----|----------|----------|
| **f0** | `f0_pc`, `f0_valid`, `f0_bblk_start` | 锁 PC：redirect/resume/retry/prefetch/recover 时置 `f0_valid`；`req_addr = redirect ? redirect_pc : f0_valid ? f0_pc : target_pc` |
| **f1** | `f1_va`, `f1_valid`, `f1_req_type` | `fetch_issue = req_valid & req_ready` 时 `f1_va <= req_addr`；ITLB 查 `f1_va` → `f1_pa`；发 ICU/ILM 请求 |
| **f2** | `f2_va`, `f2_pa`, `f2_valid` | `f2 <= f1`；等 I$/ILM 返回 `fetch_resp_inst`；`f2_cache_miss` → `ST_MH`，`f2_itlb_miss` → `ST_FILL_TLB` |
| **FQ** | `s0[0..3]`（`kv_fq`） | `fq_wr = \|fetch_resp_valid`；环形 FIFO，每项 75b（inst + valid + xcpt + bblk） |
| **ID** | `id_i0_alive`（`kv_uins_ctl`） | FQ 出队 `ifu_i0_pc` 组合给 `id_i0_pc`；`kv_dec` 译码；`iiq_w_valid = {id_i1_alive, id_i0_alive}` |
| **IS** | IIQ 项 → `ii_*` | IIQ pop：`ii_i0_pc` 从队列出；`kv_iiu_scb` 算 hazard/bypass/late；`ii_ready = ~(lx_stall \| ii_*_stall)` |
| **EX** | `ex_valid`, `ex_src*_reg`, `ex_i0_pc` | `ex_i0_pc <= ii_i0_pc`；early ALU/BRU；`ls_req`/`mdu_req` 发起 |
| **MM** | `mm_valid`, `mm_src*_reg`, `mm_i0_pc` | `mm_i0_pc <= ex_i0_pc`；分支判定向量；`mm_redirect`；BTB 更新 |
| **LX** | `lx_valid`, `lx_src*_reg`, `lx_i0_pc` | `lx_i0_pc <= mm_i0_pc`；late ALU/BRU；`ls_resp`/`mdu_resp` 合入 |
| **WB** | `wb_valid`, `wb_i0_pc` | `wb_i0_pc <= wb_i0_pc_nx`；`rf_we` 写 XRF/FRF；`kv_cmt` 退休 |

---

## IF 级详细（`kv_ifu`）

### next PC 生成

| 信号 | 来源 | 选择逻辑 |
|------|------|----------|
| `target_pc` | `kv_pq` | BTB 命中 → `bpu_info_target`；基本块内 → latched target；否则 → `seq_pc` |
| `seq_pc` | `kv_ifu` | `req_addr[MSB:3] + 8`（bundle 8B 前进） |
| `redirect_pc` | `kv_ipipe` | `redirect` 时强制 |
| `f0_pc` | `f0` 寄存器 | `f0_valid=1` 时保持 |

`req_addr = redirect ? redirect_pc : f0_valid ? f0_pc : target_pc`

### f0 寄存器

- `f0_valid_set`：redirect 且 stall/`~req_ready`/`~bpu_rd_ready`、resume、retry、prefetch、recover、EX9、ECC revise、cctl。
- `f0_valid_clr`：`fetch_issue` 或 `ic_op_req_pulse`。
- `f0_pc_update` 同 `f0_valid_set` 条件；`f0_pc <= f0_pc_nx`。

### f1 寄存器

- `f1_valid_nx = fetch_issue & ~f1_kill & ~ex9_lookup_valid \| (redirect & ...)`。
- `f1_va <= req_addr` when `fetch_issue`。
- `f1_req_type <= pf_req_type`；`f1_req_start <= req_bblk_start`。
- ITLB：`f1_translate_en = MMU使能 & ~resp_sel_ilm`；`ifu_itlb_req_valid = f1_valid & ~f2_stall & f1_translate_en`；`f1_pa = f1_translate_en ? itlb_ifu_pa : f1_va`。

### f2 寄存器

- `f2_valid_nx = f1_valid & ~f2_kill`。
- `f2_va <= f1_va`；`f2_pa <= f1_pa`；`f2_itlb_miss <= f1_itlb_miss` 等 fault 位。
- `f2_cache_miss = f2_alive & fetch_icu_valid & icu_ifu_resp_status[22] & ...`。
- `fq_wr = |fetch_resp_valid`；`fetch_resp_inst` 来自 ILM 或 ICU。

---

## ID 级（`kv_ipipe` 内 `kv_uins_ctl` + `kv_dec`）

- `id_i0_pc = ifu_i0_pc`（组合直通，正常路径无寄存器）。
- `id_i0_alive = ifu_valid[0] & ~ifd_stall[0]`（`kv_uins_ctl` 状态机 `IDLE` 时）。
- `kv_dec` 组合：`ifd_i0_instr` → `id_i0_ctrl[374:0]`、imm、FU 位。
- `iiq_w_valid = {id_i1_alive, id_i0_alive}`；`id_ready` 满时 FQ 停 pop。

---

## IS 级（`kv_iiq_wrap` + `kv_iiu` + `kv_iiu_scb`）

- IIQ 4 项 FIFO（`kv_iiq.v`），项内容 `{pc, npc, ctrl, imm, pred_info, ecc}`。
- `ii_i0_pc` 从 IIQ 队头出；`ii_ready = ~(lx_stall | ii_i0_stall)` 控制 pop。
- `kv_iiu_scb` 组合：RAW/WAW/struct hazard、bypass 向量、late 判定。
- 发射后 `ex_i0_pc <= ii_i0_pc`。

---

## EX 级（`kv_ipipe`）

- `ex_ctrl_en = ii_valid[0] & ~lx_stall`；`ex_i0_pc <= ii_i0_pc`。
- `bru0_pc = ex_i0_pc`；`ls_req_pc = ex_i0_pc[11:0]`。
- early ALU `alu0/1` 组合计算；`ls_req_valid`、`mdu_req_valid` 发起。

---

## MM 级（`kv_ipipe`）

- `mm_ctrl_en = ex_i0_valid & ~lx_stall`；`mm_i0_pc <= ex_i0_pc`。
- `mm_i0_mispred` 分支判定；`mm_redirect` → IFU `redirect_pc`。
- `mm_btb_update_p0_start_pc = mm_i0_bblk_start_pc`；`mm_btb_update_p0_target_pc = mm_i0_npc`。

---

## LX 级（`kv_ipipe`）

- `lx_ctrl_en = mm_alive[0] & ~lx_stall`；`lx_i0_pc <= mm_i0_pc`。
- `bru2_pc = lx_i0_pc`（late 分支）。
- `lx_rd1_wdata` 合入 `ls_resp_result`、`mdu_resp_result`、`alu2_result`。

---

## WB 级（`kv_ipipe`）

- `wb_ctrl_en = lx_i0_valid & ~lx_stall`；`wb_i0_pc <= wb_i0_pc_nx`。
- `rf_we1 = wb_i0_doable & wb_i0_ctrl[135]`；`kv_cmt` 退休。
- `wb_i0_redirect` 时 `redirect_pc = wb_i0_npc`。

---

## 时序总表

| 拍 | 动作 |
|----|------|
| C0 | `f0_pc`/`target_pc` → `req_addr` |
| C1 | `f1_va <= req_addr`；ITLB 查 `f1_va` |
| C2 | `f2_va <= f1_va`；I$/ILM 返回 → FQ |
| C3 | FQ 出队 → `id_i0_pc`（组合）；译码 |
| C4 | IIQ pop → `ii_i0_pc`；hazard/发射 |
| C5 | `ex_i0_pc <= ii_i0_pc`；EX 执行 |
| C6 | `mm_i0_pc <= ex_i0_pc`；分支判定 |
| C7 | `lx_i0_pc <= mm_i0_pc`；late 执行 |
| C8 | `wb_i0_pc <= lx_i0_pc`；写回/退休 |
