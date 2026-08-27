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

### 1.1 FPU / LSU / CSR 在各 stage（`kv_ipipe.v` / `kv_lsu.v`）

| 资源 | EX | MM | LX | WB | 备注 |
|------|:--:|:--:|:--:|:--:|------|
| **Int ALU early** | alu0/1 算 | 结果在 `mm_src` | — | WB | bypass @ EX/MM |
| **Int ALU late** | — | 地址/旁路 | alu2/3 算 | WB | `ii_*_late` |
| **Branch** | bru0/1 目标 @ EX | — | bru2/3 late | WB | mispred 5/7 cyc |
| **LSU** | 地址、TLB、发总线 | load 数据回、store 继续 | load 结果、`ls_resp` | WB | **1× LSU**；`ls_issue_ready` struct |
| **MDU** | `mdu_req` / fastmul | 中间 | 结果 | WB | `mdu_req_ready` struct |
| **FPU 算术** | `fpu_i0`/`fpu_i1` 入口（i0 优先） | pipe 中间 | 结果 | WB FRF | **1× pipe**；152/157 走 LSU |
| **FP load/store** | 同 LSU 地址级 | 同 load | 同 load | FRF/GPR | fu[14/15]=LSU |
| **CSR** | — | presync 等 | CSR 读 | CSR 写 | fu[7] **仅 i0**；`ctrl[277]` 单发 |

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

### 3.4 RAW / WAW（`kv_iiu_scb.v` L728–729）

| Hazard | RTL | 规则 |
|--------|-----|------|
| **RAW i0→i1** | `ii_i1_raw_hazard` L729 | 默认 stall；**s251=0** 时 i0→i1 同 reg 可放行（见下） |
| **RAW i0 自身** | `ii_i0_raw_hazard` L728 | rs1/rs2/rs3/rs4 vs EX/MM/WB/LSU/MDU… |
| **WAW** | L771–772 | 同周期同 rd stall（i0/i1 写口冲突） |
| **load→i1 late** | `s199/s200` L754–755 | i0 load（fu[2]）→ i1 用 LX 路径 |

#### 3.4.1 `s251` 例外全项（L675，RAW i0→i1 放行条件）

`s251=0`（允许同拍 RAW）当 **任一** 下列为真（RTL 为 De Morgan 形式）：

| # | i0 fu | i1 fu | 额外条件 | 场景 |
|---|-------|-------|----------|------|
| 1 | **[3] LoadB** | **[0] Int ALU** | ~i1 fu[9] | loadb → i1 整数 |
| 2 | **[3] LoadB** | **[8] Branch** | ~i1_bogus, ~i1 fu[9] | loadb → i1 分支 |
| 3 | **[1] ALU 副** | **[0] Int ALU** | ~i0_late, ~i1_late | early 副→主 |
| 4 | **[1] ALU 副** | **[8] Branch** | ~i1_bogus, ~both late | 副→BR |
| 5 | **[0] ALU 主** | **[1] ALU 副** | i0 非 bogus BR；~both late | 主→副 |
| 6 | **[16] FP FMIS** | **[0] 或 [8] BR** | ~i1_bogus（BR 时） | FMIS→Int/BR |
| 7 | **[17] FP FMV** | 同上 | 同上 | FMV→Int/BR |

**gem5：** `andesSameCycleLateLoadUse` / `andesSameCycleEarlyIntForward`（`andes_issue_rules.cc` L145–199）；`s251` 还需 `~ii_i1_late`（L129–133）。

**例子：** `lbu t0,0(a0)` (i0,fu3) + `addi t1,t0,1` (i1,fu0) → s251 term1 命中，**不 stall**（loadb→Int，i1 走 late/LX bypass）。

---

| i0 ↓ \ i1 → | ALU | Load/Store | MDU | FP arith | CSR |
|-------------|:---:|:----------:|:---:|:--------:|:---:|
| ALU | ✅* | ✅ | ✅ | ✅ | ❌ |
| Load/Store | ✅ | ❌ | ✅ | ✅ | ❌ |
| MDU | ✅ | ✅ | ❌ | ❌ | ❌ |
| FP arith | ✅ | ✅ | ❌ | ❌ | ❌ |
| CSR | — | — | — | — | 单发 |

\* early Int + early Int 需 bypass；见 §5。

### 3.6 DS238 Table 168 / 169 ↔ RTL（repo 无 DS238 原文）

| DS238（代码注释） | RTL `kv_iiu_scb.v` | gem5 |
|-------------------|-------------------|------|
| Table **168** 双发配对 | L769–770 struct；L675 s251 RAW 例外 | `andesDualIssuePairAllowed` L38–81 |
| Table **169** load-use | L754–755 s199/s200；L766 `ii_i1_late` | `andesSameCycleLateLoadUse`；`cantForwardFrom` Mem |
| MDU 双发禁 | L770 `fu[5/6]×fu[5/6]` | L44–45 |
| LS+LS 禁 | L769–770 `fu[2/4/22]` | L48–49 |
| FPU+FPU / FPU+MDU | L770 s167&s168；fu5/6 交叉 | L70–79 |
| CSR 单发 | `ctrl[277]`；L770 `i1 fu[7]` | L62–63 |
| 短距 unpred BR i1 禁 | `ctrl[76]` | L58–59, `andesIsShortUnpredControl` |
| late BR + i1 LS | L770 `(i1 LS)&(i0 fu[8]&i0_late)` | L52–54 |

---

## 4. `id_ctrl` / `ii_*_ctrl` 关键位（375b， hazard/FU 相关）

**宽度：** `kv_dec.v` 输出 **`id_ctrl[374:0]`** → IIQ → **`ii_i0_ctrl` / `ii_i1_ctrl`**（同宽）。EX 级 **`ex_i*_ctrl[223:0]`** 由 **`ii_ex_i*_ctrl`** 组合（见 §4.5），勿与 II 位号混用。

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
| 276 | `s212` — EX9/lookup abort 相关（`kv_ipipe.v` L2664） |
| 278 | StackSafe & ALU（`STACKSAFE_SUPPORT`）→ fu[9] |
| 279 | StackSafe / SP check（`s505\|s507`）→ EX ctrl[212] |

### 4.3 寄存器域 ctrl[230–281]（`kv_dec.v` L1488–1502；II 用法 `kv_iiu.v` / `kv_ipipe.v`）

**写口（rd / wen）— scoreboard WAW 用**

| ctrl | decode 源 | II 信号 | 含义 |
|------|-----------|---------|------|
| **236–240** | `s20`（rd1 索引） | `ii_i0/i1_rd1` | 第一写寄存器号 |
| **241** | `rd1_wen` | `ii_i0/i1_rd1_wen` | 写 rd1；**x0 强制不写**（`rd!=0`） |
| **242–246** | `s26`（rd2 索引） | `ii_i0_rd2` | 第二写寄存器（ACE/DSP 第二写口） |
| **247** | `rd2_wen` | `ii_i0_rd2_wen` | 写 rd2 enable |

**读口（rs / ren）— RAW hazard 用**

| ctrl | decode 源 | II RF 地址 / ren | 含义 |
|------|-----------|------------------|------|
| **248–252** | `s21`（rs1 索引） | `ii_rs1`, `rf_raddr1` | rs1 寄存器号 |
| **253** | `rs1_ren` | `rs1_ren` | 读 rs1 enable |
| **254–258** | `s23`（rs2 索引） | `ii_rs2`, `rf_raddr2` | rs2 寄存器号 |
| **259** | `rs2_ren` | `rs2_ren` | 读 rs2 enable |
| **260–264** | `s24`（rs3 索引） | 见下 mux | rs3（三/四操作数、ACE） |
| **265** | `rs3_ren` | `rs3_ren` | 读 rs3 enable |
| **266–270** | `s25`（rs4 索引） | 见下 mux | rs4 |
| **271** | `rs4_ren` | `rs4_ren` | 读 rs4 enable |

**双发时读口 mux（`kv_ipipe.v` L3172–3179）**

| 信号 | 正常双发 | `ctrl[277]` 单发 | calu pair / cmv |
|------|----------|------------------|-----------------|
| `ii_rs1` | i0 `[248+:5]` | 同左 | 同左 |
| `ii_rs2` | i0 `[254+:5]` | 同左 | 同左 |
| `ii_rs3` | i1 `[248+:5]` | i0 `[260+:5]` | cmv: i1 `[254+:5]` |
| `ii_rs4` | i1 `[254+:5]` | i0 `[266+:5]` | pair: i1 `[236+:5]` |
| `rs3_ren` | i1 `[253]` | i0 `[265]` | `\| cmv_pair` |
| `rs4_ren` | i1 `[259]` | i0 `[271]` | `\| calu_pair` |

**其它 hazard 相关**

| ctrl | decode | 用途 |
|------|--------|------|
| 230 | `s89` | micro-op / 1st pp 标记 → EX[192] |
| 231–232 | pred_brk / pred_start | 分支预测信息 → EX[193–194] |

### 4.4 操作数 src 选择 ctrl[280–286]（7b `src1_sel`，`kv_dec.v` L1502）

`id_ctrl[280+:7] = {s34, s33, s22, s31, s32, s30, s27}` → `ii_i0_src1_sel`；i1 用 `ii_i1_ctrl[280+:7]`，**单发或 calu_cmv 时 i1_src1_sel 强制为 `7'b1`（立即数）**（`kv_ipipe.v` L1436）。

| sel bit | decode 位 | 条件 | `ii_src1` 来源（L3522） |
|---------|-----------|------|-------------------------|
| [0] | s27 = `rs1_ren` | ren | **GPR rs1**（`rs1_rf_rdata`） |
| [1] | s30 = s28\|s29 | — | **立即数** `ii_src1_imm` |
| [2] | s31 | halt 下 load/store/jalr | **PC** `ii_i0_pc_ext` |
| [3] | s32 = s97 | — | DEBUG 向量 |
| [4] | s33 = s60 | — | exec IT JAL base |
| [5] | s34 = s61 | — | 全 1 常量 |
| [6] | s22 = id_ctrl[48] | — | **VL** `ii_vl_zext`（向量） |

`ii_src2`：`rs2_ren \| ctrl[157]`（FP store）→ RF，否则 i0 立即数（L3523）。`ii_src3` 用 i1 的 `src1_sel` 同编码选 rs3/imm/PC…（L3524）。

**gem5：** Minor 无 `src1_sel` 位域；操作数来自译码 imm/RegId — **known gap**（仅 hazard 需 rs/rd/ren/wen 对齐 scoreboard）。

### 4.5 完整 II→EX 重映射（`ii_ex_i*_ctrl[223:0]` → `ex_i*_ctrl`，`kv_ipipe.v` L3531–3925）

**宽度：** II/EX 均为 **224b**（`[223:0]`）；MM/LX 截断为 **205b**（`[204:0]`）。i0/i1 **同映射规则**，下列「EX」列对两槽对称；**例外**单独标 i0/i1。

#### 4.5.1 译码直通区（低 52b + ALU 子域）

| EX `[hi:lo]` | II 源 | 含义 |
|--------------|-------|------|
| `[0:1]` | `ii[0:1]` | 指令属性低位 |
| `[2]` | **i0:** `ace_sync_ack_status`；**i1:** 0 | ACE sync 应答 |
| `[3:51]` | `ii[2:50]` | 译码直通（**ex[n]=ii[n−1]，n≥3**） |
| `[44:51]` | `ii[43:50]` | （含于上，ALU op 子域） |
| `[72:74]` | `ii[71:73]` | postsync |
| `[75:76]` | `ii[74:75]` | |

#### 4.5.2 FU / 资源使能（**位号与 II 不同者加粗**）

| EX | II 源 | 物理含义 |
|----|-------|----------|
| 134 | 142 & **~late** | Int ALU **early**（alu0/1） |
| 149 | 142 & **late** | Int ALU **late**（alu2/3） |
| 135 | 144 & ~late | CALU early |
| 136 | 145 & ~late | Branch early |
| 150 | 145 & late | Branch late |
| 148 | **`ii_*_late`**（scb） | late 标志打入 EX |
| 137 | 147 | CSR |
| 133 | 141 | ACE |
| 138–140 | 148–150 | DSP stage |
| **141** | **151** | FP FDIV |
| **142** | **152** | **FP Load**（II fu[14]） |
| **143** | **153** | FP FMAC32 |
| **144** | **154** | FP FMAC64 |
| **145** | **155** | FP FMIS |
| **146** | **156** | FP FMV |
| **147** | **157** | FP Store |
| 151 | 158 | Int Load W/D |
| **152** | **160** | **MDU div/slow**（II fu[6]） |
| **153** | **161** | MDU fastmul |
| 154 | 162 | Int Store |
| 155 | 163 | （store 扩展） |
| 156 | 170 | VPU Load/Store |
| 157 | 173 | VPU |
| 158 | 174 | VPU |
| 159 | 175 | VPU |
| 125 | 100 | 其它译码标志 |
| 131 | 114 | FRD 相关 |
| 132 | 118 | |

**陷阱：** II `ctrl[152]`=FP load → EX `[142]`；II `ctrl[160]`=MDU → EX `[152]`。**勿按位号同名假设。**

#### 4.5.3 寄存器写口（与 §4.3 一致，打入 EX）

| EX | II | 含义 |
|----|-----|------|
| `[198:202]` | `[236:240]` | rd1 |
| 203 | 241 | rd1_wen |
| `[204:208]` | `[242:246]` | rd2 |
| 209 | 247 | rd2_wen |
| `[126:130]` | `[109:113]` | FRD 索引 |
| `[220]` | 361 | VPU SRF |
| `[221:222]` | `[362:363]` | VPU |

#### 4.5.4 II 记分板注入（**非 decode**，来自 `kv_iiu_scb`）

| EX | 来源 | 含义 |
|----|------|------|
| `[168:179]` | `ii_*_mm_bypass` | MM 旁路选择 |
| `[162:165]` | **i1:** `ii_i1_lx_bypass`；**i0:** 0 | LX load 旁路 |
| `[77:80]` | **i1:** `ii_i1_ex_bypass`；**i0:** 0 | EX 旁路 |
| 191 | `ii_*_ex_nbload_hazard` | EX non-blocking load |
| 189 | `ii_*_mm_nbload_hazard` | MM nb load |
| 81 | **i0:** calu_pair & ~trigger；**i1:** 0 | CALU pair 标记 |

#### 4.5.5 分支 / 异常 / 预测

| EX | II / 其它 | 含义 |
|----|-----------|------|
| 192 | 230 | micro-op / 1st pp |
| 193 | 231 | pred_brk |
| 194 | 232 | pred_start |
| `[195:197]` | `ii_*_ras_ptr` | RAS 指针 |
| 210 | pred_replay mux | 误预测重放 |
| 160 | 176 \| trigger \| HSS | exception valid |
| 223 | 369 \| trigger | fault / xcpt |
| `[82:87]` | cause mux | xcpt cause |
| `[88:90]` | 369? `[84:86]` : dcause | detailed cause |
| `[107:109]` | 93+:3 / illegal_csr | dcause sub |
| `[214:216]` | trigger result | debug trigger |
| 190 | 207 | |
| 213 | 288 | |
| 217 | 293 | |
| 218 | 295 | |
| 219 | 299 | |
| 211 | 278 | StackSafe |
| 212 | 279 | SP check |
| `[166:167]` | `[205:206]` | |

#### 4.5.6 CSR / ECC（EX 级生成或 widening）

| EX | 来源 | 含义 |
|----|------|------|
| `[93:104]` | `ii_*_csr_addr` | CSR 地址（非 ii ctrl 直通） |
| `[113:120]` | `ii_*_ecc_code` | ECC |
| 121 | ecc_corr | |
| `[122:124]` | ecc_ramid | |
| 91 | **i0:** ii[87]；**i1:** 0 | |
| 92 | 88 | |
| `[105:106]` | `[90:91]` | |
| 110–112 | 96–98 | |
| 49 | 48 | VL 相关 |
| `[180:188]` | **i0:** `ii_fstore_wdata_sel`；**i1:** 0 | FP store 写数据选择 |

#### 4.5.7 EX→MM 截断

`mm_*_ctrl[204:0]` 为 EX `[204:0]` 子集；`[180+:9]` fstore sel 等在 MM 仍可见（`ex_mm_i0_ctrl[140+:9] ← ex[180+:9]`，L2361）。

**gem5：** Minor Execute 无 224b ctrl 影子；FU 类型来自 op class，**known gap** — 对齐 hazard 时只 mirror §4.5.2 FU 位语义，不模拟全 ctrl 总线。

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

### 5.2 II 旁路选择（`kv_iiu_scb.v` L742–777）

**输出打包（L756–764）：**

| 输出 | 组成 | 操作数 |
|------|------|--------|
| `ii_i0_bypass[17:0]` | `{s190,s187}` | i0 rs2, rs1（各 9b） |
| `ii_i0_mm_bypass[11:0]` | `{s191,s188}` | i0 rs2, rs1 mm（各 6b） |
| `ii_i1_bypass[17:0]` | `{s196,s193}` | i1 rs3, rs4 |
| `ii_i1_mm_bypass[11:0]` | `{s197,s194}` | i1 rs3, rs4 mm |
| `ii_i1_lx_bypass[3:0]` | `{s200,s199}` | i1 rs4, rs3 LX load |
| `ii_mdu_bypass[15:0]` | `{s192,s189}` 或 `{s198,s195}` | MDU 槽选 i0/i1 操作数 |

#### 5.2.1 `s187–s200` 真值（优先级 mux，L742–755）

**rs1 路径 `s187`（9b）— 优先级从上到下：**

| 条件 | 值 | 含义 |
|------|-----|------|
| `rs1_match_ex_rd2` | `s175` | EX i1/rd2 生产者 |
| `rs1_match_ex_rd1` | `s173` | EX i0/rd1 生产者 |
| `rs1_match_mm_rd2` | `s180` | MM rd2 |
| `rs1_match_mm_rd1` | `s177` | MM rd1 |
| `s202`（rs2==i0_rd2 WAW） | `s186` | WB 口 |
| `s201`（rs1==i0_rd2） | `s185` | WB |
| `s204` | `s184` | WB rd2 |
| `s203` | `s183` | WB rd1 |
| default | `9'h001` | **读 RF** |

**rs1 mm `s188`（6b）：** `~rs1_ren`→`6'h01`；否则同序选 `s176/s174/s181/s178`（EX/MM 路径）；default `6'h01`。

**rs1 mm flags `s189`（8b）：** ex_rd2→`8'h04`；ex_rd1→`8'h02`；mm 用 `s182/s179`；WB→`8'h80/8'h40`；default `8'h01`。

**rs2 路径 `s190–s192`：** 与 rs1 对称，用 `s205–s212`（rs2 对 i0_rd1/rd2 的 match）替代 `s201–s204`。

**rs3 路径 `s193–s195`：** 同 rs1 结构，操作数 `ii_rs3`（i1）。

**rs4 路径 `s196–s198`：** 同 rs2 结构，操作数 `ii_rs4`。

**LX load `s199–s200`（2b each）：**

| 信号 | 值 | 含义 |
|------|-----|------|
| `s199` | `(s213 & i0_fu[2]) ? 2'h2 : 2'h1` | rs3：i0 load→i1 时 **LX** |
| `s200` | `(s218 & i0_fu[2]) ? 2'h2 : 2'h1` | rs4 同上 |

`s213/s218` = i1 rs3/rs4 与 **i0_rd1** 同 reg 且 i0 写 enable（L434–443）。

**`s173–s186` 生产者编码（L730–737）：** 按 EX/MM 在飞 FU one-hot（ALU early `9'h002`、late `6'h02`、load `9'h008`、MDU `9'h020`、…）。

**Late 判定（L765–766）：** `mm_bypass[*][0]=0` → `ii_*_late`；i1 另加 load `s199/s200[1]`、calu_pair、FPU 交叉等。

**Early Int 不可 forward（gem5 `cantForwardFrom`）：** late Int、MDU、FP、Mem、CSR。

### 5.3 操作数寄存器链（stage forward）

```
ii_src*  →  ex_src*_reg  →  mm_src*_reg  →  lx_src*_reg  →  WB
              ↑ alu0/1 @EX              ↑ alu2/3 @LX
```

Load 结果：`ls_resp` → MM/LX mux → `ls_resp_bresult`（loadb 同拍 i1 特例）。

### 5.4 FP 旁路（`kv_iiu_fscb.v` L713–766）

**与 Int scb 平行：** FR 记分板 + `ii_i*_frs*_bypass[8:0]`（9b one-hot）。

| 输出 | 操作数 | bit 含义（L713–766） |
|------|--------|----------------------|
| `ii_i0_frs1_bypass` | i0 FP rs1 | [5:6] EX rd1/rd2 FMIS/FMAC；[7:8] MM；[3:4] MM FMAC lane |
| `ii_i0_frs2_bypass` | i0 FP rs2 | 同上；**[0]**=无旁路且 `fu[15]` store |
| `ii_i0_frs3_bypass` | i0 FP rs3 | 同结构 |
| `ii_i1_frs1/2/3_bypass` | i1 | 同 i0，match 改为 rs3/rs4 |

**Struct（L778–779）：** i1 FDIV 忙；**FPU+FPU**（同 type fu[16–20]）；FR rs 与 FDIV/FMAC 冲突。

**RAW 例外 `s160`（L596）：** ~(i0 FP arith × i1 FP store) 等 — 近似 DS168 FP 配对。

**gem5 gap：** Minor 无 FR scoreboard 9b bypass；仅 Int `cantForwardFrom` + issue pairing。

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
| P4-doc-02 | §4 ctrl 248–281 reg 域 | **done** |
| P4-doc-03 | §4.5 II→EX 全映射 | **done** |
| P4-doc-04 | §5.2 s187–s200 真值 | **done** |
| P4-doc-05 | §3.4 s251 全项 | **done** |
| P4-doc-06 | §5.4 FP bypass | **done** |
| P4-doc-07 | §1.1 FPU/LSU/CSR stage | **done** |
| P4-doc-08 | §3.6 DS238↔RTL | **done** |
| P4-doc-09 | §9.1 gem5↔RTL | **done** |
| P4-doc-10 | `ax46mpv.md` Backend 框图 | **done** |

---

## 8. gem5 实现注记（非本文档范围，但选型记录）

| 话题 | RTL | gem5 Minor 现状 |
|------|-----|-----------------|
| 8 级 stage | EX/MM/LX 独立 valid | Execute 单阶段 + FU pipe |
| EX∥LX | 同拍不同 stage | **gap**；exlx A/B 均为近似，**B 非 stage 忠实** |
| 建议路径 | — | **先 hazard/issue/bypass 文档 + rules 对齐** → 再评估 8 级 stage 模型或换 CPU 模板 |

**exlx 决策：** 选 **C**（冻结 stage 重叠原型）；CM 标尺 ~3.29 接受为 Minor 结构 gap。

### 8.1 8 级 Minor 扩展草图（P4-gem5-8stage，**设计 only**）

**目标：** 在 Minor Execute 上挂 **stage tag**，使 EX∥LX、bypass 站、late ALU 可对照 RTL，而非 `returnCycle` 近似。

| RTL stage | Minor 拟议 | 行为 |
|-----------|------------|------|
| II | Issue0（现有） | `andes_issue_rules` + `andesLatePath` 标志 |
| EX | **ExStage** 新 ID | early FU：Int ALU0/1、BRU0/1、MDU issue、LS addr、FPU 入口 |
| MM | **MmStage** | load 数据可见；MM bypass 站；store 继续 |
| LX | **LxStage** | late ALU2/3、BRU2/3；load 最终结果；CSR 读 |
| WB | Writeback0（现有） | 不变 |

**指令携带：**

```cpp
enum AndesPipeStage { II, EX, MM, LX, WB };
struct AndesStageTag {
  AndesPipeStage stage;   // 当前占用的最前级
  bool late;              // ii_*_late → LX ALU
  bool exOccupied, mmOccupied, lxOccupied;
};
```

**Scoreboard 扩展：**

- 每条在飞结果带 `{stage, fuTag, late}`，不只 FU index + `returnCycle`
- bypass 判定 mirror §5.2：match EX/MM rd1/rd2 → 选 `s173–s186` 同类
- `cantForwardFrom` 映射 ex_rd*_fu bit0=0 生产者

**EX∥LX 同拍（exlx C 的后续实现路径）：**

- 同一 cycle：`ExStage` 可发射 young early，`LxStage` 可执行 old late
- Execute 不再单阶段串行；或 Execute=FU pipe + **side band** stage shift

**实施顺序：**

1. ~~`AndesStageTag` + scoreboard 扩展（只 tag，不改 timing）~~ → **P4-gem5-8stage-A done**
2. `andesIntShouldUseLateFU` 改读 tag 而非 `returnCycle` 启发（**P4-gem5-8stage-B**）
3. 拆 Execute→Ex/Mm/Lx 三级 valid（大改）；或 LX 计数器近似（**非目标**）
4. CoreMark gauge 复测

**blocked 于：** user 确认拆 Execute 范围；当前 doc 已够 gem5 小步（late + issue_rules）先行。

---

## 9. RTL 索引 + gem5 对照

| 文件 | 内容 |
|------|------|
| `kv_dec.v` | `id_ctrl[*]` 生成 |
| `kv_iiu.v` | `ii_*_fu`, stall, `ii_ex_rd*_fu` |
| `kv_iiu_scb.v` | struct/raw/waw/bypass/late |
| `kv_iiu_fscb.v` | FP reg scoreboard |
| `kv_ipipe.v` | stage 寄存器、alu/lsu/fpu 接线 |
| `andes_issue_rules.cc` | gem5 双发配对 |

### 9.1 `andes_issue_rules.cc` ↔ RTL

| gem5 函数 | RTL | 行号 |
|-----------|-----|------|
| `andesDualIssuePairAllowed` | `ii_i1_struct_hazard` 各 term 的 **禁止**配对 | scb **L769–770**；dec **277/76** |
| `andesOpUsesMdu` ×2 | `fu[5/6]` 双 MDU | L770 |
| `andesOpUsesLsu` ×2 | `fu[2/4/22]` LS+LS | L769–770 |
| late BR + i1 LS | `(i1 LS)&(i0 fu[8]&i0_late)` | L770 |
| `andesIsShortUnpredControl` | `ii_i1_ctrl[76]` | dec L1524 |
| `andesOpForcesSingleIssue` | `ctrl[277]` / `ii_i0_singleissue` | dec L1522 |
| FPU×FPU / FPU×MDU | s167&s168；fu5/6 交叉 | L770 |
| `andesSameCycleWAWAllowed` | `ii_i1_waw_hazard` / `ii_i0_waw_hazard` | L771–772 |
| `andesSameCycleLateLoadUse` | **s251** term1/2；`s199/s200` | L675,754–755 |
| `andesSameCycleEarlyIntForward` | **s251** term3–5 | L675 |
| `andesSameCycleFpMisFmvToIntForward` | **s251** term6–7 (FMIS/FMV→Int/BR) | L675 |
| `andesBranchShouldUseLatePath` | Pred FU ii_*_late issue bypass | L765–766 |
| `andesSrcNeedsLatePath` | `~mm_bypass[0]` → `ii_*_late` | L765–766 |
| `andesIntShouldUseLateFU` | late ALU @ LX | ipipe alu2/3 |
| `cantForwardFrom`（config） | ex_rd*_fu bit0=0 类 | iiu L707–746 |

**未覆盖（known gap）：** VPU 交叉（L770 末）、ACE credit、DSP 宽指令、`ii_mdu_bypass` 16b、FP `fscb` 全路径。
