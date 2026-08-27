# AX46MPV Spec

RTL：`kv_ifu.v`（IFU）、`kv_icu.v` / `kv_ic_ctrl.v`（I$）、`kv_bpu.v` + `kv_pq.v`（BPU）、`kv_fq.v`（FQ）。

---

# Frontend

取指前端 = **PC 选择 → I$/ILM 取指 + BPU 预测（并行）→ FQ → 双发射到 ID**。流水站：`F0` / `F1` / `F2`。BPU、I$ 细节见独立章节。

## 整体框图

```
  redirect_pc ──┐
  f0_pc ────────┤  MUX          F0              FF        F1              FF        F2
  target_pc ────┘  (pri)        │               │         │               │         │
       │                        │               │         │               │         │
       │   ┌────────────────────┴───────────────┴─────────┴───────────────┴─────────┴──────────┐
       ▼   │                                                                                   │
   req_addr│  ┌─────────────┐      ┌──┐   ┌─────────────┐      ┌──┐   ┌─────────────────────┐ │
   ────────┼─►│ fetch_issue │─────►│FF│──►│ f1_va       │─────►│FF│──►│ f2_va / f2_pa       │ │
           │  │ valid&ready │      │  │   │             │      │  │   │                     │ │
           │  └──────┬──────┘      └──┘   └──────┬──────┘      └──┘   └──────────┬──────────┘ │
           │         │  I$/ILM VA                 │ ITLB→PA                        │             │
           │         ▼  index 发读                ▼ ICU latch                      ▼             │
           │  ┌─────────────┐              ┌─────────────┐              ┌─────────────────────┐ │
           │  │ I$ / ILM    │              │ wait f1_pa  │              │ tag cmp (PA)        │ │
           │  │ req         │              │             │              │ hit→data / miss→MH  │ │
           │  └─────────────┘              └─────────────┘              │ pack → kv_fq        │─┼──► ID
           │                                                             │   i0/i1 ≤2/cycle    │ │   (ipipe)
           │                                                             └─────────────────────┘ │
           │                                                                                     │
           │  BPU（相对 bpu_rd：+0 / +1 / +2，可与上面 fetch 拍错位）                              │
           │  ┌─────────────┐              ┌─────────────┐              ┌─────────────────────┐ │
           │  │ +0 查表     │              │ +1          │              │ +2 bpu_rd_ack       │ │
           │  │ BTB∥BHT    │──────────────►│ BTB tag比   │──────────────►│ bpu_info_*         │ │
           │  │ bpu_rd_valid│              │ 锁 BHT 读数 │              │ RAS push/pop       │ │
           │  └─────────────┘              └─────────────┘              │ target_pc ─────────┼─┼──► 回 MUX
           │                                                             └─────────────────────┘ │   (via kv_pq)
           └─────────────────────────────────────────────────────────────────────────────────────┘

  backend redirect ──────────────────────────────────────────────────────────────► MUX（最高优先）
  miss: fb×2 / bus_ost≤2 ── TileLink ──► L2；next-line prefetch 可选
```

| 站 | 取指路径 | BPU |
|----|----------|-----|
| F0 | `req_addr` MUX → `fetch_issue` → I$/ILM 发读 | `bpu_rd`：BTB∥BHT（同 PC，≠`req_addr`） |
| FF | `f1_va` 等 | （BPU 自有流水） |
| F1 | ITLB VA→PA；ICU 等 PA | +1：BTB tag / 锁 BHT |
| FF | `f2_va`/`f2_pa` | |
| F2 | **tag 比** → data / `ST_MH`；写 `kv_fq` | +2：ack、`target_pc`、RAS |

**MUX**：`redirect_pc` > `f0_pc` > `target_pc`（`target_pc` 来自 F2 ack 后 `kv_pq`，**不是** F1 当拍回环）。

**宽度**：I$ 返回最多 **64b**；FQ→ID 最多 **2 条/拍**。

---

## F0

选 `req_addr`；`fetch_issue = req_valid & req_ready` 时发 I$/ILM，并可并行发起 BPU 查表。

### `req_addr` 优先级

`redirect_pc` > `f0_pc` > `target_pc`

| Source | 一句话 |
|--------|--------|
| `redirect_pc` | 本拍 backend 改向 |
| `f0_pc` | 上拍未发出，锁存重发 |
| `target_pc` | 正常前进（BPU ack 后 `kv_pq`） |

**`redirect_pc`**

| 细分 | 来源 | 场景 |
|------|------|------|
| WB | LX branch | late 误判 |
| MM | EX branch | early 误判 |
| 异常 | — | illegal、page fault 等 |

**`f0_pc`**：`f0_valid_set` 锁存 / `fetch_issue` → `f0_valid_clr`。

| 优先级 | Source | 场景 |
|--------|--------|------|
| 1 | `resume_pc` | `mret` / `sret` / `uret` |
| 2 | `redirect_pc` | 分支误判、异常 |
| 3 | `f0_pc_flush_init_value` | cache flush 初始化 |
| 4 | `ic_flush_addr_nx_ext` | I$ flush 下一行 |
| 5 | `ic_op_addr_ext` | CCTL |
| 6 | `retry_pc` | ITLB miss 后重取 |
| 7 | `ex9_lookup_pc` | EX9 |
| 8 | `f2_ecc_inv_addr` | I$ ECC 重取 |
| 9 | `seq_pc` | EX9 顺序 |
| 10 | `recover_pc` | F1/F2 kill 恢复 |
| 11 | `prefetch_addr` | I$ next-line 预取 |

**`target_pc` / `seq_pc`**

| 信号 | 来源 |
|------|------|
| `target_pc` | taken → `bpu_info_target`；否则 `seq_pc` |
| `seq_pc` | `fetch_issue` 后：`{req_addr[…:3],3'b0} + 8` |

### 本站与旁路

| 路径 | 本站动作（细节见专章） |
|------|------------------------|
| I$/ILM | 发 VA req；读 tag/data index（VIPT） |
| BPU | `bpu_rd`：BTB∥BHT 读；RAS 无 |
| 握手 | 见下节「F0↔F1」 |

---

## F1

`f1_va` 在 `fetch_issue` 锁存；ITLB 出 PA 送 ICU。

| 信号 | 说明 |
|------|------|
| `f1_va` | `<= req_addr` |
| `f1_pa` / `ifu_icu_f1_pa` | ITLB 或 VA bypass |
| `ifu_itlb_req_valid` | `f1_valid & ~f2_stall`（非 BPU） |
| `resp_sel_ilm` | `fetch_issue` 时锁 `req_hit_ilm` |

ILM hit 通常不走 ITLB。

| 路径 | 本站动作 |
|------|----------|
| I$ | ICU 锁 addr；等 PA，下拍 tag 比 |
| BPU | 相对 `bpu_rd` **+1**：BTB tag 比、锁 BHT 读数 |

---

## F2

`f2_valid`：`f1_valid` 打入（`f2_stall` / kill 可挂）。

### 取指返回 → FQ → ID

| 信号 | 说明 |
|------|------|
| `f2_va` / `f2_pa` | 跟 F1 |
| `fetch_resp_*` | I$/ILM 数据（`f2_alive`） |
| `fq_wr` | 写 `kv_fq` |
| `inst0/1_issue` | ≤2 条/拍 → ID |

| 异常 / miss | 下一状态 |
|-------------|---------|
| `f2_cache_miss` | `ST_MH` |
| `f2_itlb_miss` | `ST_FILL_TLB` |
| miss / ECC / no_ack | `recover_pc` |

| 路径 | 本站动作 |
|------|----------|
| I$ | PA tag 比 → hit data / miss fill；可 next-line 预取 |
| BPU | 相对 `bpu_rd` **+2**：`bpu_rd_ack`，出 `bpu_info_*`；RAS push/pop；`target_pc` 回 F0 |

`fetch_nxt_seq_kill_needed_f2`：预测 taken 但已顺序取指 → 杀 F1。

---

## F0↔F1 握手与 outstanding

F0 选好地址；**打入 F1 以 `fetch_issue` 为准**。`req_valid` 可先于 `req_ready`。

### 握手

| 信号 | 含义 |
|------|------|
| `req_valid` | F0 想发 |
| `req_ready` | 端口可接 ∧ outstanding 门控 |
| `fetch_issue` | 真正 issue → 打 F1 |

`req_ready` = `(ILM ? ilm_ready : icu_ready)` ×（同端口 \| `no_outstanding_req` \| `redirect`）。  
`icu_ifu_req_ready` 受 `fill2cache` 影响，**不**直连 `bus_req_full`。

**`req_valid`（OR）**

| # | 条件 | 场景 |
|---|------|------|
| 1 | `init_ctr_done & ~fetch_stall & fetch_normal` | 正常 `ST_FETCH` |
| 2 | `redirect & ~ipipe_ifu_stall & ~redirect_for_cti` | 普通改向 |
| 3 | `redirect & … & redirect_for_cti & bpu_rd_ready` | CTI 改向 |
| 4 | `f0_valid & ~init_ctr_done` | init 重发 |
| 5 | `f0_valid & ~fetch_normal & ~redirect & …` | recover / prefetch / MH 等 |

`fetch_stall` = `ipipe_ifu_stall` \| `fq_full_stall` \| `no_addr_valid_stall` \| `ST_XCPT_STALL` \| `f2_stall`（仅 ILM）。  
**I$ miss 不进 `fetch_stall`**：靠 `ST_MH` → `fetch_normal=0`。

**`fetch_issue` 当拍**

| 动作 | 说明 |
|------|------|
| `f1_va` / `f1_valid` | 进 F1 |
| `resp_sel_ilm` | 锁端口 |
| `f0_valid_clr` | 清锁存 |
| `seq_pc` | 8B 对齐 +8 |
| `num_outstanding_req++` | 仅 `fetch_normal` |

### IFU outstanding

| 计数 | 含义 |
|------|------|
| `num_outstanding_req` | 已 issue、F2 未 `resp_valid` |
| `fq_ncnt` | FQ 未读出 |
| `ost_max_num` | 之和；=4 → `fq_full_stall` |

有在途时 **ILM↔I$ 不混发**（除非无在途或 `redirect`）。

### Miss 与第 3 路 fill

fb0/fb1 满 → `icu_ifu_bus_req_full`。**不拉 `req_ready`**：进 `ST_MH`，`req_valid` 正常路径关；`miss_handle_wait` 等 fb 空再 `line_aq` → `ST_RECOVER`。

---

# BPU

RTL：`kv_bpu.v`、`kv_bpu_ctrl.v`、`kv_bpu_bht.v`、`kv_bpu_ras.v`、`kv_pq.v`。

## 发起与流水

`kv_pq` 拉 `bpu_rd_valid`；`bpu_rd_valid & bpu_rd_ready` 当拍查表。与 `fetch_issue` **并行、不对齐**。

| 结构 | 同拍 `bpu_rd`？ | 说明 |
|------|-----------------|------|
| BTB | 是 | 读 2-way RAM |
| BHT | 是 | 同 PC 读 dir/sel |
| RAS | **否** | F2 ack 才 push/pop |
| ITLB | **否** | 属 I$ F1 |

`csr_mmisc_ctl_brpe=0` 或 BTB 未 init → 不查。

| 相对 `bpu_rd` | 动作 |
|---------------|------|
| +0（F0） | BTB 读；BHT 发地址 |
| +1 | BTB tag 比；锁 BHT 读数 |
| +2 | `bpu_rd_ack`；`bpu_info_*`；GHR/RAS 更新 |

## 查表粒度：bblk

- 一次 `bpu_rd` = 一个 **bblk**（`start_pc` + 块内 `offset`）。
- **不是** `PC[N:3]` 的 8B fetch-group index；只半字对齐（丢 `PC[0]`）。
- `kv_pq` 用 offset 对齐当前取指包；一 bblk 可跨多拍取指。

**查表 PC**（BTB/BHT 共用；≠ I$ `req_addr`）

| 条件 | 地址 |
|------|------|
| `redirect` | `redirect_pc` |
| 其余 | 预测链 `bpu_info_target` |

## Index（RV32）

| | 用的位 | 丢掉 |
|--|--------|------|
| 公共 | halfword | `PC[0]` |
| BTB index | `gf_hash_67(PC[14:1])` → 7 bit | `PC[0]` |
| BTB tag | `PC[31:8]` | — |
| BHT dir | `PC[8:1] ⊕ GHR` | `PC[0]` |
| BHT sel | `PC[8:1]` | `PC[0]` |

**不**抹 `PC[2:1]`。（RV64：`PC[15:2]` / `PC[9:2]`。）

## BTB

256 项，2-way。

| 项 | 说明 |
|----|------|
| 条目 | target 低位 + tag 高位、`offset[9:0]`、`ucond`、`call`/`ret`、`valid` |
| 替换 | 伪随机 way；WB `btb_update_p0/p1` |

## BHT

BiMode，256×3，2-bit 饱和。

| 表 | 作用 |
|----|------|
| `bht_taken` / `bht_ntaken` | 方向计数 |
| `bht_sel` | 选上两组之一 |

GHR 8-bit；条件 hit 移位；误判 `bhr_recover`。

## RAS

深度 4。无 PC 查表；TOS 常驻。F2：`call`→push，`ret`→pop；误判 `redirect_ras_ptr`。

## 预测结果（ack 拍）

**方向**

| BTB 类型 | 预测 |
|----------|------|
| `ucond` / `ret` | 恒 taken |
| 条件 | BHT selector → 计数 MSB |

**目标**

| 条件 | 地址 |
|------|------|
| `ret` + RAS 有效 | `ras_pred_target` |
| `ret` + RAS 空 | fall-through |
| taken | `{tag_high, target_low}` |
| ntaken / miss | fall-through / `seq_pc` |

→ `kv_pq` 输出 `target_pc` / `ifu_i0/i1_pred_*`。训练用 bblk `start_pc`。

---

# I-Cache

RTL：`kv_icu.v`、`kv_ic_ctrl.v`、`kv_fb.v`。VIPT：index=VA，tag=PA（**F2 比**）。

## 与流水对齐

| 站 | 动作 |
|----|------|
| F0 | `ifu_icu_req_addr`=VA；读 tag/data RAM index |
| F1 | 锁 req；收 `ifu_icu_f1_pa` |
| F2 | `tag_rdata == PA[TAG]` → hit data / `f2_cache_miss` |

指令可见：`f2_alive & icu_ifu_resp_valid`。ILM hit 不经 ICU。

## 取指宽度

| 层 | 宽度 |
|----|------|
| 一次返回 | **64 bit**（最多 4×16b 或 2×32b） |
| 顺序前进 | +8B（`seq_pc`） |
| 未对齐 | `PC[2:1]` → 有效半字 4/3/2/1 |
| 双发射 | FQ→ID，≤2 条/拍（非 I$ 宽度） |

## Miss / fill / 总线 outstanding

| 资源 | 深度 | 含义 |
|------|------|------|
| Fill buffer | **2**（fb0/fb1，`FB_DEPTH`） | 每槽 **1×64B line** |
| `bus_ost_cnt` | **≤2** | 在途 TileLink Get |

+1：`agent_a_valid & ready`；−1：`fb_wr_last`（cacheable 常 2×256b beat）。  
`icu_ifu_bus_req_full`：两 fb 都占满 → 第 3 miss 等（IFU `ST_MH`）。

## Next-line 预取

开关：`csr_mcache_ctl_iprefetch_en`。非 BPU 流式。

| 项 | 说明 |
|----|------|
| 触发 | F2 miss 且 fb 有空、CSR 开 |
| 地址 | cacheable **+64B**；uncacheable **+8B** |
| 发法 | `prefetch_valid`，`pf_req_type=3'd1` |
| 与 demand | 共用 fb/总线；**不写 FQ** |

D$ 预取（`dprefetch_en`）在 LSU，与 IFU 无关。

---

# Backend（Issue / Hazard / Bypass）

**详表：** [`docs/ax46mpv_issue_hazard.md`](ax46mpv_issue_hazard.md)（agent 逐 tick 扩展）。

## 8 级流水（标量）

```
FQ → ID → IS(IIQ) → II → EX → MM → LX → WB
                      i0/i1 双槽
```

- **II：** `kv_iiu` + `kv_iiu_scb` — `ii_i*_fu[25:0]`、struct/RAW/WAW、bypass 选择、`ii_*_late`
- **EX：** early `alu0/1`、MDU、LS 地址、`fpu_i0/i1`
- **LX：** late `alu2/3`、load 数据、CSR 读
- **同拍 EX∥LX：** 不同指令占不同阶段（非 FU 延迟队列）

## 控制字

| 名称 | 宽度 | 产生 | 用途 |
|------|------|------|------|
| `id_ctrl` | 375b | `kv_dec.v` | 译码：FU 类、reg、CSR、单发位 |
| `ii_i0/i1_ctrl` | 375b | IIQ | 同 id；抽 `ii_*_fu` |
| `ex_i0/i1_ctrl` | 205b | `ii_ex_*_ctrl` 重映射 | EX 级 ALU/MDU/LS（**bit 编号与 II 不同**） |

## gem5

- Issue 规则：`src/cpu/minor/andes_issue_rules.cc`（≈ DS238 Table 168）
- **实现 gap：** Minor 无 EX/MM/LX stage → EX∥LX 冻结（exlx **C**）；后续若要对齐 46MPV 需 **8 级 stage 模型**（文档先行，见 issue_hazard §8）
