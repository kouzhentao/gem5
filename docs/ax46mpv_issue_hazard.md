# AX46MPV — Issue / Hazard / Bypass（RTL 对照）

**真理顺序：** `cfg.txt` → DS238 Table 168/169 → ucore RTL（`kv_dec.v`, `kv_iiu.v`, `kv_iiu_scb.v`, `kv_ipipe.v`）。

**gem5 现状：** hazard/issue 规则在 `andes_issue_rules.cc`；**无 8 级 stage 模型** → EX∥LX、load-use 旁路节拍为 **known gap**（见 §8）。实现须先本文档对齐，再考虑 8 级 pipe 或 Minor 扩展。

**Agent 约定：** 每 tick 扩展一节（标记 `TODO`→`done`），更新 `ANDES_WORK_QUEUE.md` + `ANDES_STATUS.txt`。

---

## 1. 8 级流水线（标量 backend）

Andes 对外称 **8-stage**；backend 可视为 **FQ 之后** 的 in-order 双槽管：

| 级 | RTL 模块/信号 | 每拍最多 | 做什么 |
|----|---------------|----------|--------|
| F0–F2 + FQ | `kv_ifu` / `kv_fq` | — | 取指（见 `ax46mpv.md` Frontend） |
| **ID** | `kv_dec` → `id_i*_ctrl` | 2 | 译码，生成 **375b `id_ctrl`** |
| **IS** | `kv_iiq` | 2 | 发射队列（深度 4） |
| **II** | `kv_iiu` + `kv_iiu_scb` | **2**（i0/i1） | 记分板、hazard、选 bypass、`ii_*_fu` |
| **EX** | `kv_ipipe` `ex_i*` | 2 | early ALU0/1、MDU 请求、LS 地址、FPU 入口 |
| **MM** | `mm_i*` | 2 | load 数据/旁路、FPU 中间 |
| **LX** | `lx_i*` | 2 | **late ALU2/3**、load 结果、CSR 读 |
| **WB** | `wb_i*` | 2 | 退休、CSR 写 |

**同拍重叠（RTL 要点）：** 不同 **指令** 可占 **不同 stage**——例如 young **early @ EX**（alu0/1）与 old **late @ LX**（alu2/3）。Late 不是「延迟事件」，是 **stage 站位**（`ex_src→mm_src→lx_src` 三级寄存器链）。

---

## 2. `ii_i0_fu` / `ii_i1_fu`（26b，II 阶段 hazard 用）

来源：`kv_iiu.v` — 从 **`ii_*_ctrl`** 抽位（与 `id_ctrl` 同编号，经 IIQ 传递）。

| fu | `ii_*_ctrl` | 指令类 | 物理资源 | i0/i1 |
|----|-------------|--------|----------|-------|
| 0 | 142 | Int ALU（主） | alu0/1 early 或 alu2/3 late | 两槽 |
| 1 | 143 | Int ALU（副/bitmanip/calu） | 同上 | 两槽 |
| 2 | 158 | Int Load（W/D） | LSU | 两槽；**LS+LS 禁** |
| 3 | 159 | Int LoadB（B/H） | LSU（loadb） | 两槽 |
| 4 | 162 | Int Store | LSU | 两槽 |
| 5 | 161 | MDU 快乘 | `kv_fastmul` | 两槽；×MDU/FPU 禁 |
| 6 | 160 \| s37 | MDU 除/慢乘 | `kv_mdu` | 两槽；**MDU+MDU 禁** |
| 7 | 147 | CSR | CSR 口 | **仅 i0**（i1 struct + ctrl277） |
| 8 | 145 | Branch/JAL | bru0/1/2/3 | 两槽；短距未预测 **禁 i1** |
| 9 | 278 | StackSafe | — | ctrl277 相关 |
| 10–12 | 148–150 | DSP stage | `kv_dsp` | 两槽；**DSP+DSP 禁** |
| 13 | 141 | ACE | ACE FIFO | 两槽；**ACE+ACE 禁** |
| 14 | 152 | FP Load | **LSU**（非 kv_fpu） | 两槽 |
| 15 | 157 | FP Store | **LSU** | 两槽 |
| 16 | 155 | FP FMIS | `kv_fpu` | 两槽；**FPU+FPU 禁** |
| 17 | 156 | FP FMV | `kv_fpu` | 两槽 |
| 18 | 153 | FP FMAC32 | `kv_fpu` | 两槽 |
| 19 | 154 | FP FMAC64 | `kv_fpu` | 两槽 |
| 20 | 151 | FP FDIV | `kv_fpu` | 两槽；`~fdiv_req_ready` stall |
| 21 | 174 | VPU | `kv_vpipe` | 两槽；多种 V pair 禁 |
| 22 | 170 | VPU Load/Store | VLSU | 两槽 |
| 23 | 173 | VPU | VPU | 两槽 |
| 24 | 144 | CALU pair | i0 分支 + i1 ALU | **必须配对** |
| 25 | 175 | VPU | VPU | 两槽 |

**FPU 入口（`kv_ipipe.v`）：** `fpu_i0/i1_valid` 仅 **151/153/154/155/156**（算术）；152/157 走 LSU。

---

## 3. Issue hazard 表（≈ DS238 Table 168 + `kv_iiu_scb.v` L769–770）

### 3.1 i0 struct（`ii_i0_struct_hazard`）

| 条件 | 含义 |
|------|------|
| `fu[6]` & `~mdu_req_ready` | MDU 忙 |
| `fu[6]` & EX 已有 MDU（s95/s96） | EX 槽 MDU 占用 |
| `fu[2/4/22]` & `~ls_issue_ready` | LSU 口忙 |
| `fu[13]` & ACE credit | ACE FIFO 满 |
| `fu[9]` & `ii_i0_late` | StackSafe + late |
| `fu[4]` & store_mem_hazard | store 结构冒险 |
| `fu[2]` & load_mem_hazard | load 结构冒险 |

### 3.2 i1 struct（`ii_i1_struct_hazard`）— 在 i0 基础上 **额外**

| 条件 | 含义 |
|------|------|
| **`fu[7]`** | CSR **不可在 i1** |
| `fu[6]`×`fu[6]`、`fu[5]`×`fu[5]` | 双 MDU |
| `fu[16]`×`fu[17]`（s167&s168） | 双 FPU 类 |
| `fu[13]`×`fu[13]` | 双 ACE |
| FPU×MDU 交叉（5/6） | |
| `(i1 LS) & (i0 fu[8] & i0_late)` | late 分支 + i1 LS |
| V 交叉（21/23/25 等） | 见 RTL L770 |

### 3.3 i1 硬 stall（非 struct，直接 `ii_i1_stall`）

| 条件 | 含义 |
|------|------|
| `ii_i0_stall` | i0 stall → i1 必 stall |
| `ii_i0_singleissue`（**ctrl[277]**） | FENCE/CSR/系统/ACE sync… 占 i0，整拍 i1 空 |
| **`ii_i1_ctrl[277]`** | 该指令 **不能占 i1** |
| **`ii_i1_ctrl[76]`** | 短距未预测分支不能 i1 |

### 3.4 RAW / WAW（摘要）

| Hazard | 规则 | 例外（s251） |
|--------|------|--------------|
| **RAW i0→i1** | 默认 stall | loadb i0（fu3）→ i1 Int/BR；early Int i0→i1 Int/BR（均 ~late） |
| **WAW** | 同周期同 reg stall | 无 |
| **load→i1** | 强制 i1 late（s199/s200） | loadb 特例见上 |

### 3.5 双发配对矩阵（i0 已发 → i1 能否同拍）

| i0 ↓ \ i1 → | ALU | Load/Store | MDU | FP arith | CSR |
|-------------|:---:|:----------:|:---:|:--------:|:---:|
| ALU | ✅* | ✅ | ✅ | ✅ | ❌ |
| Load/Store | ✅ | ❌ | ✅ | ✅ | ❌ |
| MDU | ✅ | ✅ | ❌ | ❌ | ❌ |
| FP arith | ✅ | ✅ | ❌ | ❌ | ❌ |
| CSR | — | — | — | — | 单发 |

\* early Int + early Int 需 bypass；见 §5。

---

## 4. `id_ctrl` / `ii_*_ctrl` 关键位（375b， hazard/FU 相关）

**宽度：** `kv_dec.v` 输出 **`id_ctrl[374:0]`** → IIQ → **`ii_i0_ctrl` / `ii_i1_ctrl`**（同宽）。EX 级另有一套 **`ex_i*_ctrl[204:0]`**（`ii_ex_*_ctrl` 重映射，勿与 II 位混用）。

### 4.1 FU / 资源类（→ `ii_*_fu`，§2）

| ctrl | 赋值来源（`kv_dec.v`） | 含义 |
|------|------------------------|------|
| 142 | Int ALU 主类 | fu[0] |
| 143 | Int ALU 副类 | fu[1] |
| 144 | calu 相关 | fu[24] |
| 145 | BR/JAL/JALR 类 | fu[8] |
| 147 | `instr_csr` | fu[7] |
| 148–150 | DSP `s85[*]` | fu[10–12] |
| 151–156 | FP：fdiv/fmac/fmis/fmv | fu[20,18–19,16–17] |
| 152–157 | FP load / FP store | fu[14–15] |
| 158–159 | Int load W/D vs B/H | fu[2–3] |
| 160–161 | MDU s472/s473 | fu[6–5] |
| 162 | Int store | fu[4] |
| 141 | ACE | fu[13] |
| 170–175,173–174 | VPU decode | fu[22,21,23,25] |
| 278 | StackSafe & alu | fu[9] |

### 4.2 Issue / stall 控制

| ctrl | 含义 |
|------|------|
| **277** | **单发**：FENCE、CSR、系统、halt/step、ACE sync、宽 ACE reg… → `ii_i0_singleissue`；**i1 禁** |
| **76** | 短距 BR/JAL（offset≤8）& ~pred_hit → **i1 禁** |
| 253/259/265/271 | rs1/rs2/rs3/rs4 ren |
| 236–247 / 248–271 | rd 地址、wen |
| 280–281 | src 选择（`ii_*_src*_sel`） |

### 4.3 early/late ALU 使能（II→EX，`kv_ipipe.v`）

| `ii_ex_i0_ctrl` | 来自 `ii_i0_ctrl` | 含义 |
|-----------------|-------------------|------|
| 134 | 142 & **~late** | EX 开 alu0（early） |
| 149 | 142 & **late** | 标记 late（LX 开 alu2） |
| 148 | late | `ii_i0_late` 打入 EX |

### 4.4 EX 级 MDU/FPU 重映射（易混）

| `ex_i0_ctrl` | 来自 `ii_i0_ctrl` | 含义 |
|--------------|-------------------|------|
| 152 | **160**（非 152！） | `mdu_req_valid` |
| 153 | **161** | `fmul_req` |

II 的 ctrl[152]=FP load；EX 的 bit152=MDU — **同名不同义**。

---

## 5. Data bypass / forward

### 5.1 生产者标签 `ii_ex_rd1_fu` / `ii_ex_rd2_fu`（20b，`kv_iiu.v` L707–746）

EX 阶段在飞写回的标签，供 II scb 选 bypass。**i0→rd1，i1→rd2**（singleissue 时 rd2 可能来自 i0 第二写口）。

| ex_rd*_fu | 来源 `ii_*_fu` | 含义 |
|-----------|----------------|------|
| [0] | fu[0], ~late | early Int ALU |
| [5] | fu[0], late | late Int ALU |
| [1] | fu[2]\|fu[4] | Load/Store 地址类 |
| [2] | fu[5] | 快乘 |
| [3] | fu[6] | MDU |
| [4] | fu[7] | CSR |
| [6–19] | fu[10–23,14–20,24] | DSP/FP/V/ACE… |

### 5.2 II 旁路选择（`kv_iiu_scb.v`）

| 信号 | 位 | 含义 |
|------|-----|------|
| `ii_i0_bypass` | 2 | rs1/rs2：EX vs MM 路径 |
| `ii_i0_mm_bypass` | 2 | **bit0=1 → early**（EX 可旁路）；**bit0=0 → late**（consumer 须 `ii_*_late`） |
| `ii_i1_ex_bypass` | 4 | i1 选 i0 EX 或 load LX |
| `ii_i1_lx_bypass` | 2 | i1 用 LX load 结果 |
| `ii_mdu_bypass` | 16 | MDU 操作数 EX/MM/LX/WB/ls |

**Late 判定（`ii_i0_late`）：** 任一 src 的 mm_bypass **bit0=0** → 该槽 late（LX ALU）。

**Early Int 不可 forward 的生产者（gem5 `cantForwardFrom`）：** late Int、MDU、FP、Mem、CSR（ex_rd fu 对应 bit0=0 类）。

### 5.3 操作数寄存器链（stage forward）

```
ii_src*  →  ex_src*_reg  →  mm_src*_reg  →  lx_src*_reg  →  WB
              ↑ alu0/1 @EX              ↑ alu2/3 @LX
```

Load 结果：`ls_resp` → MM/LX mux → `ls_resp_bresult`（loadb 同拍 i1 特例）。

---

## 6. i0 / i1 与物理 FU 绑定

| 槽 | early @ EX | late @ LX | 备注 |
|----|------------|-----------|------|
| **i0** | alu0, bru0 | alu2, bru2 | MDU tag 优先 i0 |
| **i1** | alu1, bru1 | alu3, bru3 | calu pair 时 i1 为 ALU 操作数 |

---

## 7. TODO 分节（agent 逐 tick 填）

| id | 节 | 状态 |
|----|-----|------|
| P4-doc-01 | §2 fu 表补 V/ACE 细节 | **done**（首版） |
| P4-doc-02 | §4 补全 ctrl 248–281 reg 域 | TODO |
| P4-doc-03 | §4 `ex_i*_ctrl` 全映射表 | TODO |
| P4-doc-04 | §5 bypass 逐信号 s187–s200 真值 | TODO |
| P4-doc-05 | §3 RAW 完整 s251 展开 | TODO |
| P4-doc-06 | §5 FP bypass `kv_iiu_fscb.v` | TODO |
| P4-doc-07 | §1 FPU/LSU/CSR 时序站 | TODO |
| P4-doc-08 | DS238 Table 168/169 原文对照列 | TODO |
| P4-doc-09 | gem5 `andes_issue_rules` 逐条 ↔ RTL 行号 | TODO |

---

## 8. gem5 实现注记（非本文档范围，但选型记录）

| 话题 | RTL | gem5 Minor 现状 |
|------|-----|-----------------|
| 8 级 stage | EX/MM/LX 独立 valid | Execute 单阶段 + FU pipe |
| EX∥LX | 同拍不同 stage | **gap**；exlx A/B 均为近似，**B 非 stage 忠实** |
| 建议路径 | — | **先 hazard/issue/bypass 文档 + rules 对齐** → 再评估 8 级 stage 模型或换 CPU 模板 |

**exlx 决策：** 选 **C**（冻结 stage 重叠原型）；CM 标尺 ~3.29 接受为 Minor 结构 gap。

---

## 9. RTL 索引

| 文件 | 内容 |
|------|------|
| `kv_dec.v` | `id_ctrl[*]` 生成 |
| `kv_iiu.v` | `ii_*_fu`, stall, `ii_ex_rd*_fu` |
| `kv_iiu_scb.v` | struct/raw/waw/bypass/late |
| `kv_iiu_fscb.v` | FP reg scoreboard |
| `kv_ipipe.v` | stage 寄存器、alu/lsu/fpu 接线 |
| `andes_issue_rules.cc` | gem5 双发配对 |
