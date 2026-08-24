# AX46MPV Spec

RTL：`docs/ax45mpv/andes_ip/kv_core/ucore/hdl/`（按 46 `cfg.txt` 实例化）。

8 级顺序双发流水线。FQ(4)、IIQ(4) 是级间双宽 FIFO，不算流水级。

| 级 | 名称 | 本拍干什么 |
|----|------|-----------|
| 1 | IF | 算 next PC，发取指请求 |
| 2 | IC | 等 I$/ILM 返回，入 FQ |
| 3 | ID | 译码，入 IIQ |
| 4 | IS | IIQ 出队，查 hazard，发射 |
| 5 | EX | early ALU/BRU，发 LSU/MDU 请求 |
| 6 | MM | 分支误判判定，BTB 更新 |
| 7 | LX | late ALU/BRU，LSU/MDU 响应合入 |
| 8 | WB | 写回，退休 |

---

## IF — 取指地址

**PC 怎么来：**

- 正常顺序：BTB 命中走预测目标；否则 `seq_pc` = 当前 8B 块 +8。
- 改向：`redirect_pc` 优先级最高。
- 多拍路径：redirect 等 BPU 不 ready 时，PC 锁在 `f0_pc`，下拍继续发。

**两拍寄存器：**

- `f0` 拍：锁 `f0_pc`；组合选出 `req_addr` 发请求。
- `f1` 拍：`f1_va` 打进来；ITLB 查 `f1_va` 得 `f1_pa`；发 I$/ILM 请求。

I$ 是 VIPT：index 用地址 `[10:6]`（4KiB 页内 VA=PA），tag 用 `f1_pa` 高位。

---

## IC — 取指数据

- `f2` 拍：`f2` 锁 `f1` 的 VA/PA；等 I$/ILM 返回指令。
- miss 处理：I$ miss 进 `ST_MH` 等总线回填；ITLB miss 进 `ST_FILL_TLB`。
- 返回后：RVC 拆包、双发对齐，生成 `ifu_i0/i1_pc` 和预测信息，写入 **FQ(4)**。

---

## ID — 译码

- FQ 出队，PC 直接给到译码器（`id_i0_pc` 是组合直通，无寄存器）。
- `kv_dec` 组合译码出 375b 控制字、立即数、功能单元标记。
- 微码指令由 `kv_uins_ctl` 替换控制字。
- 译码结果和 PC 写入 **IIQ(4)**；IIQ 满时 FQ 停 pop。

---

## IS — 发射

- **IIQ** 出队：`ii_i0_pc`、`ii_i0_ctrl` 等进入发射逻辑。
- **hazard 检查**（`kv_iiu_scb`）：
  - RAW：源寄存器与 EX/MM 在途目的寄存器比较。
  - WAW：目的寄存器与 EX/MM/LX/WB 在途写冲突。
  - 结构：LSU/MDU 忙、双 FPU 等。
- **bypass 选择**：`ii_src*` 从 XRF、EX、MM、LX、WB 前递选数据。
- **late 判定**：load 生产 → 消费指令标记 late，操作数到 LX 才算。
- `ii_ready = ~(lx_stall | ii_stall)`；i0 stall 会级联停 i1。

---

## EX — early 执行

- `ex_i0_pc` 锁 PC；`ex_src*_reg` 锁操作数。
- **early ALU**（`alu0/1`）、**early BRU**（`bru0/1`）组合计算，结果 `ex_rd1_wdata` 同拍可前递给 IS。
- **LSU**：`ls_req_valid` 发起，基址 `ex_src*_reg`。
- **MDU**：`mdu_req_valid` 发起，操作数来自 `ex_src*`。
- `lx_stall=1` 时本拍冻结。

---

## MM — 访存解析 / 分支误判

- `mm_i0_pc` 锁 PC；`mm_src*_reg` 锁操作数。
- **分支误判**：`mm_i0_mispred` 比较 `bru0` 预测与实际；误判时 `mm_redirect` 改向，清 IIQ。
- **BTB 更新**：`mm_btb_update` 送 `kv_bpu`（若 WB 没更老指令抢）。
- **load 快路径**：`mm_i0_ctrl[161]` 时 FPU FMIS 结果提前合入。
- `lx_stall=1` 时冻结。

---

## LX — late 执行 / 访存返回

- `lx_i0_pc` 锁 PC；`lx_src*_reg` 锁操作数。
- **late ALU**（`alu2/3`）、**late BRU**（`bru2/3`）组合计算。
- **LSU 响应**：`ls_resp_result` 合入 `lx_rd1_wdata`。
- **MDU 响应**：`mdu_resp_result` 合入。
- **CSR**：`csr_ipipe_resp_rdata` 合入。
- `lx_stall` 由 LSU 等未就绪拉高，冻结 II/EX/MM/LX。

---

## WB — 写回 / 退休

- `wb_i0_pc` 锁 PC；`wb_rd*_wdata` 定稿。
- **写寄存器**：`rf_we` 写 XRF；`frf_we` 写 FRF。
- **退休**：`wb_i0_retire` → `kv_cmt`，处理异常、中断、性能计数。
- **redirect**：`wb_i0_redirect` 时 `redirect_pc = wb_i0_npc`，清后端。

---

## 时序（单条指令，无 stall）

| 拍 | 动作 |
|----|------|
| C0 | `f0` 锁 PC；`req_addr` 发出 |
| C1 | `f1_va` 打进；ITLB 查；I$/ILM 请求 |
| C2 | `f2` 等返回；写入 FQ |
| C3 | FQ 出队；译码；写入 IIQ |
| C4 | IIQ 出队；hazard 检查；发射 |
| C5 | EX 执行；early 结果可前递 |
| C6 | MM 判定分支；BTB 更新 |
| C7 | LX late 执行；LSU/MDU 响应 |
| C8 | WB 写回；退休 |
