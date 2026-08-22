# 46MPV scalar/LS — RTL notes (cfg-first)

**Rule:** numbers from `cfg.txt`. Read 45 RTL **as if** instantiated with cfg values.
Do **not** copy module `parameter` defaults or VIP `ax45mpv_core_top.v` sample localparams
(that file has e.g. `LSU_MSHR_DEPTH=1`, `ICACHE_WAY=2`, `SB_DEPTH=0` — **not** 46 cfg).

## cfg.txt overlay (46MPV) vs sample top

| knob | cfg.txt | sample `ax45mpv_core_top` | gem5 |
|------|---------|---------------------------|------|
| NDS_NON_BLOCKING_SUPPORT | yes → NBLOAD=1 | LSU_NBLOAD_SUPPORT=1 | `enableAndesNbloadHazard` |
| NDS_LSU_LOW_LATENCY | 1 | LSU_LOW_LATENCY=1 | early mem issue |
| NDS_LSU_MSHR_DEPTH | **16** | 1 (ignore) | D$ mshrs=16, maxAccesses=16 |
| NDS_LSU_SB_DEPTH | **8** | 0 (ignore) | store buffer 8 |
| NDS_MSHR_DEPTH | 8 | MSHR_DEPTH=3 (ignore) | I$ mshrs=8 |
| NDS_*CACHE_WAY | 4 | I$ way=2 (ignore) | assoc 4 |
| NDS_CM_SUPPORT | no | → D$ WBF depth **2** (`kv_dcu`) | `write_buffers=2` |
| NDS_WRITE_AROUND_SUPPORT | yes | CSR `mcache_ctl.dc_waround`; `kv_dcu_wa` | **known gap（冻结）**：classic L1 无 WA；CSR 门控，CoreMark 默认路径影响小；不做假模型 |
| NDS_ITLB/DTLB_ENTRIES | 8/8 | structure | itb/dtb.size=8 |
| NDS_STLB_ENTRIES | 64 | | l2tlb size=64 |
| NDS_PMP_ENTRIES | 4 | | pmp_entries=4 |

`kv_lsu_brg`: `GET_OST = NBLOAD ? LSU_MSHR_DEPTH : 1` → with cfg, outstanding misses = **16**.

## Structure (behavior)

### Scalar pipe stages (`kv_ipipe` ctrl 流水)
已读：控制字沿 **II → EX → MM → LX → WB** 寄存（`ii_ex_*_ctrl` / `ex_*_ctrl` / `mm_*_ctrl` / `lx_*_ctrl` / `wb_*_ctrl`，双发 i0/i1）。
- **alu0/1** 操作数来自 **`ex_src*`**（EX 组合算完，结果可 EX 前递）。
- **alu2/3** 挂在更后级（LX；与 `ii_*_late` / MM load 对齐）。
- 前端另有 IF/FQ 等 → 全家约 **8 级**量级；gem5 Minor 仅 **F1→F2→D→E**，无法逐级对齐，只能用 delay/FU/bypass **近似**。

### Issue / ports (`kv_iiu_scb` + `kv_lsuop`)
- `ls_issue_ready` ← `uop_issue_ready & fsm_norm & ~amo_grant & ~cctl_grant`（`kv_lsuop`）→ **1 LS issue/cycle**（norm 路径；AMO/CCTL 走 FSM）。
- `ii_*_struct_hazard`: LS if `~ls_issue_ready`；MDU if `~mdu_req_ready`；i1 blocks CSR (`fu[7]`), MDU+MDU, FPU+FPU, FPU+MDU；另有 late+`fu[9]` stall。
- Dual-issue width 2 (i0/i1).

### II stall（`kv_iiu.v`）
- `ii_i0_stall = raw|struct|waw|f_*|…|~ls_issue_ready|…`
- **`ii_i1_stall = ii_i0_stall | … | ii_i0_singleissue | …`** → i0 停则 i1 必停（in-order 双发）。
- `id_ctrl[277]`：CSR/fence/system/ACE → single-issue（gem5：`andesOpForcesSingleIssue`）。
- `id_ctrl[76]`：短偏移 branch（≤8）且 `~ifu_pred_hit` → 不可作 i1。gem5：`andesPredHit`←BTBLookup；`andesIsShortUnpredControl` 禁作 i1。
- late 仍在 II **发射**（`ii_ex_rd*_fu[5]`），算在 LX；不是「等 LX 再占 issue」。
- gem5 Minor：issue 口等 scoreboard；late FU 不能表达「已发射指令在 LX 算、II 再双发 early」→ 主 IPC 缺口。
- **4× `kv_alu`:** alu0/1 = EX early（`alu0_op*=ex_src*`）；alu2/3 = LX late（`alu2_op*=lx_src*`，alu3 可 mux `ls_resp_bresult`）— not 4-wide issue。
- All ALUs are **1cy** combinational; late = compute at LX when sources ready (e.g. MM load), then forward — not multi-cycle ALU.
- Same cycle: EX can run **this-issue** early while LX runs **older** late ops → up to 4 ALUs busy；**issue 仍 2**。
- **gem5 缺口（FOCUS late/II，冻结乱拧 opLat）：**
  - RTL：late 在 II 已发射，占管级，LX 才 1cy 组合算；同拍 II 还可再双发 early。
  - Minor：`opLat` = FU 深度 = scoreboard 结果时间。
  - **再试 late `opLat=3`（II→LX）→ gauge ~3.00**，依赖链过长；**回退 `opLat=1`**（对齐 LX 组合 1cy）。
  - II/LX 重叠 = **known Minor gap**；勿加 IssueLimit / 勿再拉 opLat。要拆 occupancy≠result 且结果仍贴 LX，另开设计。
  - 已落地：2 early+2 late、`ii_*_late`、`cantForward` bit0=0 源。
- **RTL late 判定（已读 `kv_iiu_scb.v`）：**
  - `s188`/`s191`：按 rs 命中 EX→MM→默认 的 bypass 选择；默认/`~ren` → `6'h01`（bit0=1）。
  - `ii_i0_late = (ren[1] & ~s188[0]) | (ren[2] & ~s191[0])` — **bit0=0 → late**。
  - EX rd 的 `ii_ex_rd1_fu`（`kv_iiu.v` → scb `s34`）按 **issue FU + late** 拆位：
    | `ii_ex_rd*_fu` bit | 来源 `ii_*_fu` | s174 类结果 | 含义 |
    |--------------------|---------------|-------------|------|
    | [0] | `fu[0] & ~late` | `6'h01` early | **early ALU**（EX） |
    | [5] | `fu[0] & late` | `6'h02` late | **late ALU**（LX） |
    | [1] | `fu[2]\|fu[4]` | `6'h02` late | **LS**（load/store） |
    | [2] | `fu[5]` | | FPU |
    | [3] | `fu[6]` | `6'h00` stall 类 | MDU |
    | [4] | `fu[7]` | `6'h00` | CSR/system |
    | [6..] | `fu[10..]` | late/early 不一 | 其它扩展 |
  - 因此 **`ii_*_late` 不是另类 op**，而是 **同一 ALU op 走 LX**；load 生产者在 scb 里也走 late 选择。
  - `ii_i1_late` 额外：`calu_pair` 跟 i0；`s199[1]/s200[1]` = 同拍 i0 load + i1 RAW；`s280–283` = i0 `fu[16/17]`（V）— **V/calu 标量 CoreMark 无关**；同拍 load→late **已建模**。
  - gem5：early Int / Pred `cantForwardFrom` **lateInt[2–3]+MDU[4]+FP[5]+Mem[7]+Misc[8]**（bit0=0 源）；late Int 无 cantForward。`ii_*_late` 跳过 IntEarly；同拍 loadb use 亦跳过 IntEarly（`s199`）。
  - **ii_i1_struct（标量已落）：** late BR/JAL（`fu[8]&late`）不可与 LS 双发 — gem5 `andesLatePath` + `andesDualIssuePairAllowed`。V/`fu[23]` 项 CoreMark 无关。
  - MM 管线 `s36`：`[0]=early ALU`→bypass bit0；`[1]=LS`→**无 bit0**（load→late）；与 cantForward 一致。
  - 同拍 i0→i1：`s251` 对若干 FU 对拉低以放开 raw（`s213/s218`=i1 读 i0.rd）。
    - `fu[8]=ctrl[145]` ≈ JAL/JALR/BR；`fu[3]=ctrl[159]` 含 LW/LD；`fu[0]=ALU`；`fu[1]=ctrl[143]` 含 AND/OR/XOR 等。
    - `(fu[3] & i1 ALU|BR)` → loadb→int/br；gem5≈`andesSameCycleLateLoadUse`。
    - `(fu[0]/fu[1] early 对)` → 同拍 IntAlu→IntAlu；**须双方 ~late**；gem5≈`andesSameCycleEarlyIntForward` + `andesLatePath`/`andesSrcNeedsLatePath`。
    - **未见** `(i0 fu[8] & i1 ALU)` 例外 → JAL→用 同拍仍 stall；勿放开 call→use。
    - 同拍 WAW：RTL `ii_i1_waw` 同 rd 必停 — gem5 已对齐。
  - `ii_i0_ls_base_bypass`：EX 命中强制 0（基址不走 EX）。
  - `ii_i0_fu[9] & ii_i0_late` → struct stall：`fu[9]=ctrl[278]` = **StackSafe**（`s392 & ALU`；无 StackSafe 时恒 0）→ CoreMark BM 无关。
- Late mispred 7cy / early 5cy — DS §22.8.
- gem5 近似（2026-08-21）：late `relativeLat=ANDES_BYPASS_EX`；`opLat=1`；`IssueLimit=2`。
  bit0 生产者表（标量）已按 FU 索引落到 cantForward；V/calu/ACE `ii_i1_late` 额外项不建模。
  （曾试 late=`BYPASS_MM`，比 EX 更严 → issue 卡住。）

### 前端 vs issue（gauge 观察）
- gem5：`fetchRate≈1.22/cy` > `issue≈1.09` → **不是取指饿死**，卡在 execute/依赖/双发。
- Mem≈21% issued（单 LS 口）；双发满拍~17%。RTL 结构同为单 LS + issue=2。
- `lx_stall = lx_wait_ls_resp & ~ls_resp_valid`（LX 等 LS）；L1 warmup 后几乎满命中 → 非本 gauge 主因。
- `bht_dir_rd_addr = PC_bits ^ BHR[7:0]`；`bht_sel_rd_addr = PC_bits`（**choice 不 xor**）。
- **BHR 更新（kv_bpu_ctrl s150/s153）：** 仅 **BTB hit & ~ucond** 时 `{pred,BHR[7:1]}`；ucond/miss 不推。gem5：`speculativeGHROnUncond=False` + `requiresBTBHit` 时 miss 跳过 `updateHistories`。
- **BHT choice 更新：** RTL WB 总朝 reso ±1（饱和则跳过整次）；gem5 `alwaysUpdateChoice=True`。DirectCond mis ~6.93%；~3.29 CM/MHz。
- gem5 BiMode：direction=`PC^GHR`，choice=`PC` — **已对齐**；表深 256、2bit ctr 已齐。
- 条件方向 ~91%；再抠 BHT 哈希收益有限。主缺口仍在 issue/late 重叠。
- `ex_ls_loadb` (`kv_ipipe`):  
  `load & size==W & addr[1:0]==0` **or** `load & size==D & addr[2:0]==0`，且 `~poisoned`；  
  寄存到 `mm_ls_loadb`。半字/字节 **不是** loadb。
- `ls_base` EX bypass forced 0 → addr relativeLat 0.
- gem5 MemFU（forward 审计）：LW/LD/LWU `extraAssumedLat=1`；LB/LH `=2`；C.* Default `=1`；addr lat=0。
- **DS169 复核（FOCUS load-use）：** D$ hit、late ALU、nbload off：W/D **0cy**（注：须与 load **双发**）；B/H **1cy**。gem5：同拍 loadb→late + word lat1 / ~loadb lat2 相对差对齐。非双发/early 消费者走 `ii_*_late`。无新漏项。
- `ANDES_BYPASS_MM` 保留未接 late（接 MM 曾 fall-through 死锁；late 用 EX）。
- nbload: `ii_*_{ex,mm}_nbload_hazard` only when consuming an **outstanding**
  miss rd (`s75`–`s78`); hit loadb forwards in MM. Independents continue.
  gem5: MemFU `extraAssumedLat` ≈ hit MM; do **not** mark all loads
  unpredictable (that erased hit forward). Same-cycle loadb→int still allowed.

### Vector↔scalar mem hazard (`kv_vpipe` → scb)
- `store_mem_hazard` / `load_mem_hazard` stall scalar store/load when VPU LS pending.
- Scalar-only (`kv_ipipe` stub): both tied **0** → CoreMark path unaffected.

### BPU / RAS (`kv_bpu` + `kv_bpu_ctrl` + `kv_bpu_ras`)
- `RAS_DEPTH=4`（结构）；gem5 `ReturnAddrStack(numEntries=4)`。
- RTL：**BTB 项上的 CALL/RET 位**驱动 RAS（`ras_push = hit&taken&CALL`，`ras_pop = hit&RET`，见 `kv_bpu_ctrl`）→ 前端靠 BTB 认分支类型。
- gem5：`requiresBTBHit=True` 对齐该语义（并把 return 装进 BTB）；日常 gauge ~3.27，与 False 几乎持平。
- `ras_pred_valid = valid[rptr] & ~(priv[rptr] ^ cur_priv)`（特权不一致则无效）；无 RAR 时无效则前端回退 BTB target。
- 干净 stats（`requiresBTBHit`）：Return 提交误预测 **320/2165 (~14.8%)**；`ras.used/correct/incorrect` = 2164/1844/320（错全在 RAS provider）；BTBHit~85%。深度=4 已齐；余量更像 wrap/恢复/嵌套，非再加深 RAS。
- RTL 同拍 `ras_push & ras_pop`：**同一 BTB 项**同时 CALL+RET（`kv_bpu_ctrl` `s164&s165`），写 `s14[s4]` 替换顶、指针不变；不是双发两条指令各 push/pop。
- gem5：旧 `if (call) push; else if (ret) pop` 会丢掉 both；已改为 **先 pop 再 push**（与 squash 路径 / ABI 一致）。CoreMark `.text` 静态 both=0 → 本修对 gauge 无影响。
- **空 RAS / invalid：** RTL `~ras_pred_valid` → 目标走 fall-thru `s162`，不用栈数据。gem5 `usedEntries==0` 时槽里仍可能有旧 PC；已改 **empty 返回 nullptr、不 pop**（对齐 invalid）。诊断：`RAS=32` 与 `4` 的 Return mis 相同 → **非 depth/wrap**。
- **Minor fetch2：** `BadlyPredictedBranchTarget` 原先 squash 后不 `update()`（其它 mispred 会 update）；已补齐。CoreMark gauge/Return% 无变化，属正确性对齐。
- **II ras_ptr 影子（kv_dec / kv_iiu）：** `id_ctrl[46]=s409`（call）、`id_ctrl[74]=s408`（ret）；II issue 时影子 ptr ±1；kill/redirect 时 `redirect_ras_ptr` 写回 FE（`kv_bpu_ras` s18）。gem5 用 predHist squash 近似。
- **RAS squash 满栈：** 旧实现 squash push 用 `pop()`，满栈 wrap 时会错误 `--usedEntries`；已改为保存/还原 TOS+used+被覆盖槽。CoreMark Return% 无变（少触满栈路径）。
- **BP/RAS：** II ras_ptr 影子后 Return mis~**11.9%** / RAS源~88%；余量有限。勿再加深 RAS。
- **BTB tag：** RTL `BTB_TAG_WIDTH=VALEN-1-BTB_RAM_ADDR_WIDTH`；cfg `NDS_VALEN=57`、addr_width=7 → **49**。
- **BTB/BHT index：** RTL `UNUSED_PC_BIT_NUM=1`；BHT 用 `pc[8:1]`。gem5：`instShiftAmt=1`。
- **BTB set：** RTL `gf_hash_67(PC[14:1])` → `AndesBTBSetAssociative`。CallDirect miss ~8%。
- **分数天花板（双发=2）：** issue≈1.17/cy → 若每拍都能发满 2（且不计依赖气泡）粗估 ~5.6 CM/MHz；尺 6.3 要再少 ~1.9× 周期，单靠「填满 issue 口」也不够（还要 late/II 重叠、更少气泡）。勿假加宽。

### MDU (`kv_mdu`)
- cfg `NDS_MULTIPLIER=fast` → `MULTIPLIER_INT=1` → `MUL_DIGIT=1` (fast path).
- `DIV_END_CNT=64` (structure max); DS early-term ≈6–69. gem5: mul opLat=1, div expr.

### Queues (structure; not in cfg)
LSQ DEPTH=4, ROB=3, IIQ/FQ=4, RAS=4.

## gem5 status
- Dual-issue, WAW, loadb MemFU, early mem, same-cycle loadb→ALU bypass: on.
- nbload: hit assumed-lat markup; MSHR/maxAccesses for outstanding.
- **ALU: 2× early (opLat=1) + 2× late (opLat=1, wider relativeLat), IssueLimit=2.**
- Open: write-around（冻）；block-start BTB（冻）；II/LX 机制已上但 CM 无净增益（BM 关）；Return/RAS~12% 余量主要为容量/路径。
- mispred net vs squash：**已查** — DS22.8 全文「resolve 在 EX→5 / LX→7」；gem5 `issueStall` 相对纯 squash 对 CoreMark 几乎无增益（3.227 vs 3.233）；late 罚已用 `andesLatePath`。FOCUS mispred 收束。
- Full changelog: `docs/andes_46mpv_gem5_changes.md`

## D$ prefetch (FOCUS dpf)
- cfg: `NDS_DCACHE_PREFETCH_SUPPORT=yes`, `ENTRIES=4`; CSR `mcache_ctl.dprefetch_en`.
- RTL: `kv_lsu_rpt` / `kv_lsu_rpt_ent` — PC-match stride table, FSM INIT→TRANSIENT→STEADY, degree≈1.
- gem5: classic `StridePrefetcher` `table_entries=4`, `queue_size=4`, `degree=1`（结构对齐）。
- CoreMark L1 已近满分 → DPF 对 gauge 无杠杆；勿为抬分改 degree/假加宽。

## UTAG (FOCUS utag)
- cfg: `NDS_DCACHE_UTAG_SUPPORT=1`, `DEPTH=16`, `BITS=1024`。
- classic L1 **未建模**（`ANDES_UTAG_DEPTH` 仅常量）。CoreMark L1 近满分 → 对 gauge 无杠杆 → **known gap（冻结）**，勿假加 MSHR/assoc 顶替。

## Store→load forward (FOCUS sb-fwd)
- cfg `NDS_LSU_SB_DEPTH=8` → `executeLSQStoreBufferSize=8`（VIP 样本默认 SB_DEPTH=4 **勿用**）。
- RTL `kv_dcu_sb` cmp_hit / beat；Minor `StoreBuffer::canForwardDataToLoad` / `forwardStoreData` 已有完整 forward。
- 结构对齐；CoreMark L1 满分下对 gauge 无杠杆。

## pipe-fwd: late sticky after ready (2026-08-21)
- Bug: `andesSrcNeedsLatePath` 只要 scoreboard 上还有 bit0=0 生产者的 `numResults` 就强制 late，即使 `returnCycle<=now`（值已可当 RF）。
- RTL：过 LX/WB 后 early 可再吃该值。fix：仅当 `returnCycle>now` 或仍 unpredictable 时才 need-late。
- Gauge：cpl=309835 → **3.227**（与修前持平）；结构正确性对齐，非抬分。

## return-ras: II ras_ptr shadow (2026-08-21)
- 落地：Execute issue 时按 decode call/ret 维护 II 影子栈（深 4）；每条 issued 指令打 `andesRasSnap`。
- 误预测 / Unpredicted：Fetch2 在 squash+update 后 `restoreRasSnapshot` → FE RAS（≈ `redirect_ras_ptr`）。
- 结果：Return mis **34%→11.9%**；RAS 源正确率 **~74%→88%**；`ras.incorrect` 1255→644。gauge cpl 仍 ~3.23。

## return-ras: empty → fall-thru (试)
- RTL `s118`: RET & ~ras_pred_valid → fall-thru，不用 BTB。gem5 已接；CoreMark 上 Return% **无变**（空 RAS 很少）→ 余量主要是深度/错栈内容与 call BTB miss。
- Return mis 收在 **~11.9%** / RAS 源 **~88%**；相对 34% 已大幅改善。再抠收益有限；主分差仍 II/LX。

## pipe-fwd: occupancy≠result 试拆（2026-08-21）
- 试 late FU `opLat=3` + scoreboard `resultLat=1`（II→LX 占位、LX 1cy 出结果）。
- Gauge **3.00**（与统一 opLat=3 同）→ in-order commit 仍等 FU drain，依赖链变慢。
- **已回退** `opLat=1`；II/LX 重叠仍为 Minor known gap（需改 commit/ROB 模型才可能）。
- **ii-lx-busy（2026-08-21）：** Minor 已有 `issueLat`（FU 再发间隔）与 `opLat`（结果/管深）。抬 `issueLat` 只会堵 late FU，不缓解 in-order commit 等老指令出 FU；抬 `opLat` 已证伤 gauge。**冻结**：真重叠需 ROB/非严格 in-order commit，勿再拧 latency knobs。

## BTB / BHT block indexing (FOCUS fetch-btb-block)
- RTL：BTB/BHT 按 **bblk_start_pc**（取指块起点）索引；`blk_offset` 存 fall-thru；dir=`start^BHR`，sel=`start`（`kv_bpu_ctrl`/`kv_ipipe` WB update）。
- gem5：按 **分支 PC** 查 SimpleBTB + BiMode；绝对 target（等价 taken 目标，无独立 offset 字段）。
- CoreMark：BTBHit~87%，fetchRate~1.20 > issue~1.11 → **非取指瓶颈**。完整 block-BTB 需改 FE 模型 → **known gap（冻结）**，勿用 line-align 假近似。

## I$ First-Word-First (FOCUS icache-fwf)
- cfg `NDS_ICACHE_FIRST_WORD_FIRST=First-Word-First`；`ax45mpv_core_top` `ICACHE_FIRST_WORD_FIRST_INT=1`（CSR 可见）。
- CoreMark Minor 窗：I$ demandMissRate **~0.042%**（112 miss），总 miss≈6.3k cy vs cpl~304k → FWF 最多省半拍 miss 也几乎不动 gauge。
- classic L1 无独立 FWF 总线折返模型；**known gap（冻结）**，勿为抬分假砍 miss latency。

## Dual-issue fill (FOCUS dual-issue-gap)
- issue≈1.11、IPC≈1.11；fetchRate≈1.20 → 卡在 execute 依赖/配对/误预测，非取指。
- `andes_issue_rules` 已对照 DS168/s251/ctrl[76]/ctrl[277]；未见新的「该双发却被挡」项（JAL→use 同拍仍禁，与 RTL 一致）。
- 再抬 issue 需 II/LX 重叠或更少 RAW 气泡（前者已冻结）。本 FOCUS **收束**，勿为填槽假放宽配对。

## Path to ~6.3 CM/MHz (FOCUS path-to-63, Fri,)
- Gauge now **~3.29**（cpl~304170）；目标 6.3 → 需约 **1.92×** 更少周期。
- 完美双发（IPC 2.0 / 现~1.11）粗估 → ~5.9 CM/MHz，仍略低于 6.3 → **II/LX 重叠**仍必要（已冻结，需 ROB/更深管）。
- 清零 DirectCond+Return 误预测（按 ~10cy/次）约省窗内 **13.6%** 周期 → 对 gauge 有限；BP 已 ~93% cond。
- L1 I/D miss ≈0 → cache/FWF/DPF/UTAG **无杠杆**（已冻结）。
- **可动余量：** 仅剩小正确性对齐；大洞是 Minor 结构 vs AX46 管线重叠。下一 FOCUS 拣仍可 RTL 对齐的小项，或正式记录结构天花板。

## BTB alloc / replace (FOCUS btb-repl)
- RTL `kv_btb_update_ctrl`：alloc / revise / invalid；`kv_bpu_ctrl` alloc 选路用 **s58 LFSR**（非 LRU）。
- gem5：`btbReplPolicy=RandomRP` 对齐 LFSR 选路；LRU→Random 对 CoreMark **无可见差**（BTBHit~87%，~3.29）。
- `updateBTBAtSquash=False`（commit，贴近 MM/WB）再测：Call miss↑、gauge 略降 → **保持 True**。
- 替换策略侧 **收束**。

## Store buffer / WBF (FOCUS wbf-sb)
- cfg `NDS_LSU_SB_DEPTH=8` → `executeLSQStoreBufferSize=8`（已齐）。
- RTL `DCACHE_WBF_DEPTH=2`（CM off）→ `l1d.write_buffers=2`（已齐）。
- CoreMark D$ miss~0.09% → SB/WBF 对 gauge **无杠杆**；结构已对齐 → **收束**。

## TLB / PMP (FOCUS tlb-pmp)
- cfg：ITLB=8、DTLB=8、STLB=64、PMP=4 → gem5 `itb/dtb.size=8`、`l2tlb=64`、`pmp_entries=4` **已齐**。
- baremetal CoreMark 无页表压力 → **收束**。

## Structural ceiling vs 6.3 (FOCUS struct-ceiling)
- Gauge **~3.293 CM/MHz**（cpl~303659）；目标 6.3 → ~**1.9×** 周期。
- IPC/issue ~**1.11**；理想双发 2.0 → ~**5.9** CM/MHz，仍略低于 6.3。
- 清零 Cond+Return 误预测（~10cy/次）约省窗内 **~14%** 周期 — 不够单独到 6.3。
- L1 I/D miss ≈0；FWF/DPF/UTAG/WA/SB/WBF/TLB **无杠杆**（均已冻或已齐）。
- **主洞：** Minor 浅管 + in-order。`ii-lx-impl` 已上 resultLat/提前 commit/bubble：CM 上最多回到基线，**无净增益** → 仍需 ROB/更深重叠才可能逼近 6.3。
- **BP/BTB 余量：** DirectCond~7%、Return~12%、BTBHit~87%、block-start 索引未做 — 正确性可继续抠，对 gauge 边际递减。
- **本 FOCUS 收束：** 结构天花板已量化；下一 FOCUS 仅拣仍可 RTL 对齐的正确性小项（勿假宽/假延迟抬分）。

## Bitmanip / RVB (FOCUS bitmanip-lat)
- cfg `NDS_RVB_SUPPORT=yes`；RTL ALU 类 1cy（与普通 IntAlu 同）。
- CoreMark ELF：**0** 条真实 bitmanip；仅 `zext.b`/`sext.w` 伪指令（andi/addiw）→ 走现有 IntAlu opLat=1。
- 对 gauge **无杠杆** → **收束**；勿为 RVB 假加宽/加 FU。

## II/LX commit-ready (FOCUS ii-lx-commit-ready)
- Minor commit 要求 inFlight **队头**且位于 **FU 管线出口**（`fu->front`）。
- 真 II/LX：结果/可提交在 ~1cy（scoreboard），但 late FU **占位**仍可持续多拍；需拆 `opLat`（管深）与 `resultLat`（记分牌/提交），并允许未到 FU 出口就 commit — **改动面大**。
- 仅抬 `opLat` 已证伤 gauge（commit 等 drain）。本 FOCUS **不半吊子改 commit** → 记入 known gap；与 ii-lx-busy 一并冻结，待正式 ROB/commit 模型。

## Zce (FOCUS zce-audit)
- cfg `NDS_ZCE_SUPPORT=yes`；CoreMark ELF **无** `cm.*` / Zce 指令 → **收束**。

## RVA / AMO (FOCUS rva-amo)
- cfg `NDS_RVA_SUPPORT=yes`；CoreMark ELF **0** 条 LR/SC/AMO → **收束**。

## BP residual (FOCUS bp-residual)
- BHR recover（MM/WB → `bhr_recover_data`）≈ gem5 BiMode squash 后写入 actual；`keep_bhr` 在本配置恒 0。
- FE 推测 BHR（pred）+ 后端 recover 已对齐；block-start 索引仍是 known gap（冻结）。
- DirectCond~7% / Return~12%：余量主要来自 BiMode@256 容量、block BTB、以及 RAS 嵌套/路径，**无新的可拧 RTL knob**（勿假加宽 BHT）。
- 本 FOCUS **收束**。

## jalr / indirect (FOCUS jalr-indirect)
- RTL：间接目标走 **BTB only**（无 ITABLE）。gem5 默认 `SimpleIndirectPredictor` 多余。
- 已设 `indirectBranchPred=NULL`：CallIndirect 误预测 **11→4 /911 (~0.44%)**；gauge **~3.29→~3.293**。
- IndirectUncond 仍 7/24（样本极小）。**收束**。

## Scalar gauge status (FOCUS scalar-gauge-status)
- **Gauge ~3.293 CM/MHz**（cpl~303659；尺 6.3 ≈ 差 **1.91×** 周期）。
- **已齐（RTL/cfg 忠实）：** 双发 DS168/s251、early/late ALU、load-use、MDU fast、LSQ/SB/WBF/MSHR、BTB gf_hash+tag49+RandomRP、BiMode@256（GHR 条件-only、alwaysUpdateChoice、无 iPred）、RAS4+II 影子、mispred 5/7、requiresBTBHit。
- **冻结 known gap：** II/LX 重叠（需 ROB/commit 模型）、block-start BTB/BHT、WA/UTAG/FWF、write-around。
- **BP 余量：** DirectCond~6.9%、Return~12%、CallInd~0.4%、BTBHit~87% — 边际递减，勿假加宽。
- **结论：** 标量 knobs 侧已接近 Minor 能表达的 AX46；到 6.3 的主障碍是 **管线重叠模型**，不是再拧 cache/BP。

## LSU RDB (FOCUS lsu-rdb)
- cfg `NDS_LSU_RDB_DEPTH=0` → HVM read data buffer **关闭**（`kv_lsu_hvm_rdb` 参数化深度）。
- gem5 classic/Minor 无对应 HVM RDB；深度 0 = 不建模即对齐。CoreMark 非 HVM → **收束**。

## Codense (FOCUS codense-audit)
- cfg `NDS_CODENSE_SUPPORT=yes`；CoreMark ELF 未见 Codense 专用助记符；BM 路径不依赖 → **收束**。

## II/LX design sketch (FOCUS ii-lx-design)
最小忠实方案（已在 `ii-lx-impl` 落地，BM 默认关）：
1. **拆延迟：** `resultLat`（scoreboard）与 `opLat`（FU 管深）分离；late：`resultLat=1`，`opLat>1`。
2. **Commit：** inFlight 队头在 result ready 时可提前提交；FU 留气泡占位。
3. **旁路：** 沿用 `andesLatePath` / cantForward。
4. **验收：** CoreMark — `opLat=3→3.251`，`opLat=2→3.293`（=基线），**无净增益** → BM `enableAndesIiLxOverlap=False`。
5. 更深重叠仍需 ROB 级模型。

## StackSafe (FOCUS stacksafe-audit)
- cfg `NDS_STACKSAFE_SUPPORT=yes`；`fu[9]` 仅 StackSafe 时非 0。CoreMark BM **无** StackSafe 指令 → 结构项恒闲，**收束**。

## PowerBrake (FOCUS powerbrake-audit)
- cfg `NDS_POWERBRAKE_SUPPORT=yes`；CSR `mpft_ctl` / `mxstatus.pft_en`。
- 复位：`pft_en=0`、`t_level=0` → **节流默认关**；CoreMark 不写这些 CSR。
- gem5 不建模节流即对齐默认路径 → **收束**；勿为 BM 假加 stall。

## II/LX impl attempt (FOCUS ii-lx-impl)
- 已实现：`MinorFU.resultLat`、scoreboard 用 resultLat、late 队头提前 commit、`FUPipeline::replaceInstWithBubble`、`enableAndesIiLxOverlap`。
- CoreMark：`opLat=3/resultLat=1` → **3.251**；`opLat=2` → **3.293**（=基线）；提前 commit 抵消管深税，**无净增益**。
- BM 配置：`opLat=1`、`enableAndesIiLxOverlap=False`；C++ 路径保留可开。
- 真贴近 6.3 仍需更深重叠/ROB 级模型 → **收束本 FOCUS**（勿再只拧 opLat）。

## ILM/DLM (FOCUS ilm-dlm-audit)
- cfg：`NDS_ILM_SUPPORT=1` / `NDS_DLM_SUPPORT=1` 但 **`NDS_ILM_SIZE=0`、`NDS_DLM_SIZE=0`** → 本地存储器未实例化。
- CoreMark BM 走系统内存 + L1；gem5 无 ILM/DLM 即对齐 → **收束**。

## Multiplier fast (FOCUS multiplier-fast)
- cfg `NDS_MULTIPLIER=fast` → gem5 `AndesMduFU` mul `opLat=1`，div DS 早停表达式；单 MDU 口（禁双发）已齐 → **收束**。

## AHB low latency (FOCUS ahb-lowlat)
- cfg `NDS_AHB_LOW_LATENCY={no}` → **不应**开低延迟 AHB 路径。
- CoreMark L1 miss≈0.04%/0.09% → 总线延迟对 gauge 无杠杆。gem5 SimpleMemory 默认即可 → **收束**。

## WFE / CMO (FOCUS wfe-cmo-audit)
- cfg WFE=1、CMO=yes；CoreMark ELF **无** wfi/cbo/prefetch → **收束**。

## Cfg scrub (BM-irrelevant bundle)
下列 cfg=yes 但对标量 CoreMark BM 路径无指令/无默认使能，不建模即对齐，勿假加行为：
WFE、CMO、PowerBrake（默认关）、StackSafe、Codense、Zce、RVA（CM 无 amo）、RVB（CM 无真实 bitmanip）、HVM/向量扩展（本 gauge 标量）、ILM/DLM SIZE=0。

## Live gauge (FOCUS live-gauge)
- 2026-08-21 确认：`COREMARK/MHz=3.293168`（cpl=303659）；BTBHit~0.871；DirectCond~6.86%；Return~11.8%；CallIndirect~0.44%。
- config：`RandomRP` + `indirectBranchPred=NULL` 已生效。

## Mispredict penalty (FOCUS mispred-penalty)
- DS238 §22.8：EX resolve **5cy** / LX **7cy**。
- gem5：`issueStall` + `andesLatePath` → 5/7；此前相对纯 squash 对 CM 几乎无增益。代码仍在 → **收束**（勿再拧罚分顶分）。

## Decode / issue width (FOCUS decode-width)
- RTL 双发：decode/issue=2；IIQ/FQ depth=4（缓冲≠宽度）。
- gem5：`decodeInputWidth=2`、`executeInputWidth=2`、`executeIssueLimit=2`、`executeInputBufferSize=ANDES_IIQ_DEPTH`、`fetch2InputBufferSize=ANDES_FQ_DEPTH` → **已齐**。

## Unaligned / RAM hold / BIU pf (FOCUS alignment-hold)
- cfg `NDS_UNALIGNED_ACCESS=yes` → PMA `misaligned=mem_ranges`（允许 HW 非对齐，不建模拆拍延迟）。
- CoreMark 无非对齐访问 → gauge **不变 3.293168**。
- `NDS_RAM_RAM_HOLD_DOUT=0`：物理 SRAM hold，非周期模型 → 忽略。
- `NDS_BIU_PREFETCH=no` / `NDS_FENCE_FLUSH_DCACHE=no` / `NDS_CACHE_LINE_SIZE=64`（已 64B）→ **已齐/收束**。

## Remaining cfg scrub (FOCUS cfg-scrub-remain)
- `NDS_STLB_SP_ENTRIES=4` / `NDS_IO_STLB=1`：IO/侧 TLB；CM baremetal 无 IO-MMU 压力 → 不建模，**收束**。
- `NDS_SMEPMP_SUPPORT=0`：关 → 无需 SMEPMP。
- `NDS_ILM/DLM_WAIT_CYCLE=0` 且 SIZE=0 → 无本地存储器等待。
- `NDS_CACHE_COHERENCE_SUPPORT=0`：单核 CM → 无相干流量。
- `NDS_LSU_SOURCE_WIDTH=5`：源 ID 位宽（结构），非延迟 → 忽略。
- 标量 CM 路径可动 cfg 小项已扫完；大洞仍是 II/LX/ROB 结构天花板。


## Gauge hold (FOCUS gauge-hold)
- 复跑确认 **3.293168** CM/MHz（cpl=303659）；BTBHit~0.871；RAS incorrect~638/5468。
- cfg 小项与 II/LX 实验已收束；**勿**再拧冻结 knobs / 假宽 issue。
- 下一实质跃进需 ROB/更深 II-LX 重叠模型（超出当前 Minor 可回退改动）。

## STLB SP entries (FOCUS stlb-sp)
- cfg `NDS_STLB_SP_ENTRIES=4`：STLB **非 kilopage** 旁路 CAM（与 64-entry STLB RAM 并列）。
- gem5：`l2tlb size=64` 统一项；无独立 SP CAM。CoreMark baremetal TLB access≈0 → **无杠杆**，不建模即够用 → **收束**。


## RAS wrap check (FOCUS ras-wrap)
- RTL `RAS_DEPTH=4`、`RAS_WRAP_NUM=3`（ptr 0..3 环绕）≈ gem5 `ReturnAddrStack(numEntries=4)` wrap。
- II `redirect_ras_ptr` 影子已落。Return 误预测余量~12% → 容量/路径，勿假加深 RAS。**收束**。

## RAR vs RAS (FOCUS rar-vs-ras)
- cfg `NDS_RAR_SUPPORT=0`：**不是**关掉 RAS。`kv_bpu_ras` 在 `RAR_SUPPORT==0` 仍例化 `gen_ras_yes_rar_not_support`（DEPTH=4）。
- RAR 差异主要在特权/记录细节；`ras_pred_valid` 仍有 priv 一致性。CM baremetal 恒 M-mode → gem5 无 priv 门控 **无杠杆**。
- gem5 保留 `ReturnAddrStack(4)` 对齐 → **收束**（勿因 RAR=0 删 RAS）。

## PMP granularity / RAM-ctrl scrub (FOCUS pmp-gran)
- cfg `NDS_PMP_GRANULARITY=4096`（G 对应 4KiB）；gem5 `PMP` 无独立 gran 参数（RISC-V G 在实现里固定/CSR）。
- CM baremetal 不配 PMP → **无杠杆**。`pmp_entries=4` 已在 Minor 上齐（warmup TimingCPU 仍默认 16，不影响 score）。
- I/D$ / BTB / STLB 的 `*_RAM_CTRL_*`、`*_ECC_TYPE`：物理实现，非周期模型 → **收束**。
- WT region 全 mask0：无 writethrough 窗口 → 忽略。
- cfg `NDS_*CACHE_LRU=lru` → gem5 L1I/D `LRURP` **已齐**（CM miss≈0）。

## ICU / LSU / BIU widths (FOCUS bus-width)
- cfg `NDS_ICU_DATA_WIDTH=32`：I 侧 refill 口 32b；gem5 `fetch1LineWidth=64` + classic L1 按整行填，**未**建模 32b 折返拍数（并入 icache-fwf known gap，冻结）。
- `NDS_LSU_DATA_WIDTH=64` → gem5 `executeMemoryWidth=8` **已齐**。
- `NDS_BIU_DATA_WIDTH=512` / `NDS_BIU_ADDR_WIDTH=48`：片外总线；CM L1 miss≈0 → **无杠杆**。
- `NDS_CACHE_LINE_SIZE=64` → `cache_line_size=64` / fetch snap 64 **已齐**。

## Debug / trigger (FOCUS debug-trig)
- cfg `NDS_DEBUG_SUPPORT=yes`、`NDS_NUM_TRIGGER=4`、`NDS_TRAP_STATUS_INTERFACE=no`、`NDS_DEBUG_VEC=0`。
- CoreMark BM 不进 debug/trigger 路径 → gem5 不建模即对齐 → **收束**。

## Live dual-issue snapshot (FOCUS gauge-hold)
- IPC **1.115**；fetchRate **1.206**；idleCycles **3111**/361782（~0.86%）。
- 取指仍高于退休 → 后端/依赖/双发填充是主约束（非 I$）。

## Issue-rules reaffirm (FOCUS issue-reaffirm)
- 对照 `kv_iiu_scb` `ii_i1_struct_hazard`：MDU×2、LS×2、CSR/`fu[7]`、FPU×FPU、FPU×MDU、late BR+LS、StackSafe/`fu[9]`、V 相关项 — gem5 `andes_issue_rules` **已覆盖标量 CM 路径**；V/`fu[23]`/ACE 与 CM 无关。
- `enableAndesIiLxOverlap=false`；late `opLat=1`。复跑 CM **3.293168**。

## Struct mem/MDU busy (FOCUS struct-busy)
- `load_mem_hazard`/`store_mem_hazard`：来自 `kv_vpipe`（VPU LS 占用）→ **标量 CM 恒 0**。
- `~mdu_req_ready` / `s95|s96`（EX 槽 MDU 忙）：gem5 单 `AndesMduFU` + `alreadyPushed`/`canInsert` 近似 → **收束**（勿再叠假 stall）。

## Gauge-hold mix (non-BP)
- 承诺指令构成（Minor 窗）：IntAlu **77%**、MemRead **15%**、MemWrite **5%**、MDU **2%**；控制类约 19% 的指令带 IsControl（与 BP 余量分开看）。
- IPC **1.115** vs 理想双发 2.0 → 主因依赖/结构重叠，**不是**再拧 BP。
- 已关：BP residual、假宽 issue；II/LX 机制无 CM 净增益。

## RTL pipe control: early/late ALU (FOCUS ii-lx-pipeline) — 只读 RTL，不试参

来源：`kv_alu.v`（无时钟，纯组合）、`kv_ipipe.v` alu/src/ctrl 接线、`kv_iiu.v` `ii_*_late`。

### ALU 本身
- `kv_alu`：**无 clk**，组合逻辑。早/晚用的是**同一类** 1 拍级内算完的 ALU，不是多拍运算单元。
- 禁止再用 `opLat=2/3` 当成「ALU 变慢」。

### 四级后端（指令带着操作数走）
- 操作数寄存器链：`ii_src` → `ex_src*_reg` → `mm_src*_reg` → `lx_src*_reg`（每级 posedge 打一拍）。
- **early（`~ii_*_late`）**
  - `ii_ex_ctrl[134] = ctrl[142] & ~late` → EX 选 `alu0/1`（`alu0_op*=ex_src*_reg`）。
  - 结果进 `ex_rd*_wdata`（`ctrl[134]`），同拍可前递；再随管线往 MM/LX/WB。
- **late（`ii_*_late`）**
  - `ii_ex_ctrl[134]=0`，`ii_ex_ctrl[149]=ctrl[142]&late` → **EX 不算 ALU**。
  - late 标志：`[149] → ex_mm[164] → mm_lx[146] → mm_lx[183]`（`[183]=[146]&~BR`）。
  - LX：`alu2_op*=lx_src*`，`lx_rd1_wdata` 在 `ctrl[183]` 时取 `alu2_result`（alu3 同理，可 mux `ls_resp_bresult`）。

### 同拍重叠（管线控制要点）
- 同一拍可以：EX 上 **年轻 early** 走 alu0/1，LX 上 **年老 late** 走 alu2/3。
- Issue 仍在 II、宽度 2；late/early 是**同一条 in-order 管上的计算站位**，不是加长 ALU latency。
- 从 II 发射到 late 结果出现在 LX：操作数过 **EX→MM→LX 三级寄存器** 后，在 LX 组合算出（相对 II 出口约 **+3 级** 才有 late 结果可旁路；early 在 EX 即约 **+1 级**）。

### 与 gem5 现状（仅对照，本段不改代码拧参）
- gem5 用独立 late FU + `opLat=1`：把「LX 站位才算」收成「发射后 1 拍出结果」→ **站位/旁路节拍与 RTL 不一致**。
- 正确方向：保持 ALU=1 拍组合；对齐的是 **early@EX / late@LX 的站位与旁路**，以及同拍 EX∥LX，而不是把 ALU 做成多拍 FU。

