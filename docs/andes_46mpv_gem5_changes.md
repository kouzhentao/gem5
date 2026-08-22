# Andes AX46MPV → gem5 Minor 改动清单

日期：2026-08-21  
## 0. 工作纪律（防乱改）

**一次只做一个 FOCUS**（写在 `ANDES_STATUS.txt` 的 `FOCUS=`）。  
未写进当前 FOCUS 的：BP / RAS / cache / MDU / 无关 knobs **一律不动**。  
FOCUS 做完再换下一项；禁止「顺手改一点别处」。

建议顺序（主缺口优先）：
1. **late-ALU / II 重叠**（最大结构缺口）
2. 同拍 RAW / `s251` / scoreboard（dependency）
3. Mem/loadb forward（forward）
4. BP/RAS 残余（仅在前三项告一段落）

---

目标：在 **MinorCPU + RVV** 上近似 46MPV **标量 + LS** 微结构；CoreMark/MHz（目标 ~6.3）只作 **gauge 指标**，不刷假宽发/假 BP。


**参数优先级（硬规则）**

1. `cfg.txt` — 46MPV 数字 / 功能开关（权威）
2. DS238 — 族时序表（load-use、双发矩阵、mul/div、误预测…）
3. `docs/ax45mpv/` RTL — **只看结构/行为**；禁止把模块默认参数或 VIP `ax45mpv_core_top` sample localparams 当 46 参数

配套笔记：`docs/andes_46mpv_rtl_notes.md`（RTL 对照）

---

## 1. 改动落点（文件）

| 路径 | 角色 |
|------|------|
| `configs/example/gem5_library/andes_46mpv_scalar.py` | 全部标量 knobs、FU 池、cache、BP、`apply_andes_scalar_cpu()` |
| `configs/example/gem5_library/riscv-minor-rvv-bm.py` | BM 入口，调用 Andes 配置 |
| `src/cpu/minor/andes_issue_rules.{hh,cc}` | 双发配对、同周期 WAW/RAW、loadb→int |
| `src/cpu/minor/execute.cc` / `execute.hh` | 挂接上述规则；误预测 5/7 stall；load 记分板 markup |
| `src/cpu/minor/scoreboard.cc` | WAW inflight 检查 |
| `src/cpu/minor/BaseMinorCPU.py` | Andes 相关 Param |
| `docs/andes_46mpv_rtl_notes.md` | RTL/cfg 对照笔记 |
| `run_coremark.sh` / `scripts/get_coremark_gem5.py` | 短 ITER gauge |

---

## 2. 已改项（逐项：改了啥 / 咋改 / 为啥）

### 2.1 缓存与 LSU 深度（cfg 数字）

| 项 | 依据 | gem5 怎么改 | 为啥 |
|----|------|-------------|------|
| L1I/D 32KiB、4-way | `NDS_*CACHE_SIZE/WAY` | `AndesPrivateL1` / `configure_andes_l1_*` | 容量/相联与 46 一致 |
| I$ MSHR=8 | `NDS_MSHR_DEPTH` | `icache.mshrs=8`，`fetch1FetchLimit=8` | 取指 outstanding |
| D$ MSHR=16 | `NDS_LSU_MSHR_DEPTH` | `dcache.mshrs=16`，`executeMaxAccessesInMemory=16` | nbload 时 outstanding=MSHR |
| Store buffer=8 | `NDS_LSU_SB_DEPTH` | `executeLSQStoreBufferSize=8` | 写缓冲深度 |
| WBF=2 | `NDS_CM_SUPPORT=no` → RTL `DCACHE_WBF_DEPTH=2` | `write_buffers=2`（曾误用 4） | CM 关时 WBF 为 2，不是 cfg 里另有字段 |
| DPF table=4 | `NDS_DCACHE_PREFETCH_ENTRIES` | prefetcher `table_entries=4`（勿用 utag=16） | entries≠utag |
| tag/data/response lat=1 | DS/结构近似 | L1 latencies=1 | 低延迟 L1 |
| 单 LS 口 | `ls_issue_ready` / DS168 | `executeMemoryIssueLimit=1`，commit=1 | 每拍最多 1 条 LS |
| LSU low-lat | `NDS_LSU_LOW_LATENCY=1` | `executeAllowEarlyMemoryIssue=True` | 允许提前发访存 |
| Mem 宽 8B | `LSU_DATA_WIDTH` 结构 | `executeMemoryWidth=8` | 标量数据通路宽 |

### 2.2 队列 / 流水缓冲（RTL 结构，不在 cfg）

| 项 | 依据 | gem5 | 为啥 |
|----|------|------|------|
| IIQ=4 | `kv_iiq` DEPTH | `executeInputBufferSize` / decode buffer=4 | 发射队列深度 |
| FQ=4 | `kv_fq` | `fetch2InputBufferSize=4` | 取指队列 |
| LSQ=4 | `kv_lsq` | `executeLSQTransfersQueueSize=4` | 传输队列近似 |
| LSU ROB=3 | `kv_lsu_rob` | `executeLSQRequestsQueueSize=3` | 请求/ROB 近似 |
| 双发宽=2 | i0/i1 | `decode/execute InputWidth`、`IssueLimit`、`CommitLimit`=2 | 2-wide in-order |
| pipe 前递 delay=1 | Minor 凑 8 级 | F1→F2→D→E forward=1 | 避免默认过长 |

### 2.3 BPU / MMU

| 项 | 依据 | gem5 | 为啥 |
|----|------|------|------|
| BTB 256、2-way | cfg `NDS_BTB_SIZE` + RTL `BTB_RAM_NUM=2` | `btb.numEntries/associativity` | 与 46/结构一致 |
| RAS=4 | `kv_bpu` RAS_DEPTH | `ReturnAddrStack(4)` | 结构 |
| BiMode @256 | cfg dynamic + BHT 宽 | `BiModeBP` global/choice=256，2-bit ctr | 近似 RTL BHT |
| `updateBTBAtSquash` | 行为 | True | squash 时更新 BTB |
| ITLB/DTLB=8，STLB=64，PMP=4 | cfg | `itb/dtb.size`，`l2tlb`，`pmp_entries` | MMU 容量 |

### 2.4 FU 池与时序

| 项 | 依据 | gem5 | 为啥 |
|----|------|------|------|
| **2× early IntFU** | `kv_core` `u_alu0/1`（EX） | `AndesIntFU`×2，`opLat=1`，`IntEarly`，relativeLat=`ANDES_BYPASS_EX` | 双发 early ALU，组合逻辑 1cy |
| **2× late IntFU** | `u_alu2/3`（LX） | `AndesLateIntFU`×2，`opLat=1`（RTL 组合 1cy；曾用 +2 垫 LX 时刻，已撤），`IntLate`，relativeLat 更宽 | 不是 4 宽发；EX 发不出时 fall-through；**IssueLimit 仍为 2** |
| 单 MDU | `~mdu_req_ready` | `AndesMduFU` 一份；mul `opLat=1`；div TimingExpr ≈6–69 | cfg fast mul + DS173 |
| MemFU loadb / ~loadb | `ex_ls_loadb` + DS169 | LW/LD/LWU `extraAssumedLat=1`；LB/LH `=2`；addr relativeLat=`[0]`（禁 EX ls_base） | hit MM 前递；半字更慢；基址不走 EX bypass |
| Pred / FPU / Misc | DS 表 | 各自 timings（含 FENCE ~13cy） | 族时序 |
| Bypass 常数 | Minor：越大越早可发 | `ANDES_BYPASS_EX=3`（early）；**`ANDES_BYPASS_MM=1` 接 late IntFU** | load 结果仍靠 MemFU `extraAssumedLat`；early 禁 Mem 前递 |

**ALU 说明（重要）**

- RTL 4 个 ALU = **2 EX early + 2 LX late**，每拍 **issue 仍 2**；ALU 本身都是 **1 拍**，late 表示在 LX、数据齐了再算并能前递。
- gem5：`AndesFUPool` 顺序 early→late，优先占 early；`executeIssueLimit=2` **禁止** 做成 4-wide。

### 2.5 C++：发射规则（`andes_issue_rules` + `execute.cc`）

| 项 | 咋改 | 为啥 |
|----|------|------|
| `enableAndesDualIssueRules` | DS168 / `kv_iiu_scb`：禁 MDU+MDU、LS+LS、双 FPU、FPU+MDU、CSR/system、宽 Int 等 | 仅 `IssueLimit=2` 不够，要对配对 |
| `enableAndesWAWHazard` | 同周期 WAW；同周期 RAW（除 loadb→int）；scoreboard WAW inflight | 对齐 `ii_i1_waw` / RAW |
| `andesSameCycleLateLoadUse` | 同拍 loadb(LW/LD/…)→整数非 mem/非 MDU 放行 | RTL `mm_ls_loadb` late 路径 |
| `enableAndesNbloadHazard` | **现含义**：打开上述 loadb 同拍旁路；**不再**把所有 load 标 unpredictable | cfg `NON_BLOCKING=yes`；outstanding 靠 MSHR/maxAccesses |
| Load 记分板 markup | 仅 `extraAssumedLat==0` 才 unpredictable（已撤回「凡 load 皆不可预测」） | 否则废掉 MemFU hit 前递，和 RTL「只有 outstanding miss 才 nbload_hazard」相反 |
| 误预测惩罚 5 / 7 | `executeBranchMispredictPenalty` / `…Late`；仅 `BadlyPredictedBranch*`；**Late=`andesLatePath`**（BR 在 Pred，勿用 fuIndex） | DS22.8 EX/LX |

### 2.6 近期纠正（曾做错、已改回）

| 错法 | 为何错 | 现状 |
|------|--------|------|
| 所有 load 强制 unpredictable | 把 hit MM 前递打掉 | 恢复 assumed-lat markup |
| WBF=4 | 把 CM 开时深度套到 CM=no | `write_buffers=2` |
| DPF 用 utag=16 | entries≠utag | table_entries=4 |
| 误预测打在 BTB miss | 几乎每条 taken 都 stall | 只打真 mispredict |
| VIP/RTL 默认 MSHR=1 等 | 不是 46 cfg | 一律 cfg 优先 |

---

## 3. 还没改 / 只近似（Open）

| 项 | RTL / cfg | gem5 现状 | 备注 |
|----|-----------|-----------|------|
| **真 8 级流水** F1…WB | 有 | Minor 仍 4 级 F/D/E | 用 delay/relativeLat **凑** |
| **`ii_*_late` 精确分流** | bypass 位 → EX vs LX ALU | early 禁 Mem + 显式跳过 IntEarly；late@LX 语义 | 仍无完整 s174 全类型表 |
| **LX 上「数据 ready 再算」** | 指令已发射，LX 吃 MM 前递 | Minor 多在 issue 口等源 | 语义不完全等同 |
| **Write-around** | cfg=yes，CSR `dc_waround` | classic L1 仍 write-allocate | 无现成 WA knob |
| **UTAG** | cfg depth=16 / support=1 | 未建模 | 仅常量 `ANDES_UTAG_DEPTH` |
| **nbload hit/miss 区分** | 仅 outstanding miss hazard | hit 靠 assumed lat；miss 无专用 markup | 无 issue 时 hit 检测 |
| **误预测净代价** | 5/7 + squash | 有 extra stall；A/B：penalty 0→~3.28 vs 5/7→~3.26，**几乎无影响** | 双计不是主缺口 |
| **向量↔标量 mem hazard** | VPU 挂起时 stall 标量 LS | 标量 stub=0；CoreMark 无影响 | 向量负载另说 |
| **分数对齐** | 目标尺 ~6.3 CoreMark/MHz | 快路径 ~3.27；双发满拍粗估仅 ~17% | 主缺口 late/II 重叠 + 依赖气泡 |

**明确不做**

- 不加假 `IssueLimit>2`、假大 BTB/BHT 刷分  
- 不用 VIP sample localparam 当 46 参数  
- 日常用短 ITER（默认 2）gauge；ITER=4 只留最终  

---

## 4. 当前 FU 池快照（`AndesFUPool`）

```
AndesIntFU ×2        # EX early, opLat=1
AndesLateIntFU ×2    # LX late,  opLat=1（RTL 组合逻辑；relativeLat 区分 MM→LX）
AndesMduFU ×1
AndesFloatSimdFU ×1
AndesPredFU ×1       # RVV pred，不是标量分支
AndesMemFU ×1
AndesMiscFU ×1
```

`executeIssueLimit = 2`（始终）。

---

## 5. 怎么跑 gauge

```bash
# 短 ITER（默认 coremark_bm.elf = ITER=2）
./run_coremark.sh

# 最终 ITER=4
./run_coremark.sh /home/kou/bm/coremark_bm_iter4.elf

# C++ 改过后若 gem5.fast 时间戳不更新
bash scripts/force_link_gem5.sh
```

纯 Python（`andes_46mpv_scalar.py`）改动无需重编；`execute.cc` / `andes_issue_rules.*` 需 `scons` + 必要时 force-link。

---

## 6. 建议下一批（按对齐优先级）

1. ~~early 禁 Mem 前递 + late relativeLat≥EX~~（已落；对齐 load→late / fall-through）  
2. ~~读清 `ii_ex_rd*_fu` 位：`[0]=early ALU,[5]=late ALU,[1]=LS`~~（`kv_iiu.v`）  
3. ~~`ii_*_late`：IntEarly 若 src 来自 cantForward（Mem）则跳过，改走 IntLate~~（execute.cc）  
4. ~~write-around~~ → **known gap 冻结**（classic 无 WA；CSR 门控）  
5. ~~读 `kv_ipipe`：II→EX→MM→LX→WB；alu0@EX / alu2@LX~~  
6. ~~剖析 IPC~1.09~~：L1 满命中；issue≈1.10；误预测粗税~12%；**Return≈67%**（RAS_DEPTH=4 已对齐 RTL）。试 `requiresBTBHit=True`（FE/RAS 语义）→ cpl **305622 (~3.27)** 几乎持平；完整 Return% 需干净 stats（teardown 仍易挂）。  
7. ~~读 `kv_bpu_ctrl` RAS~~：`ras_push=BTB.CALL&UCOND`，`ras_pop=BTB.RET`（靠 BTB 类型位）→ 支撑 `requiresBTBHit=True`  
8. ~~干净 stats~~：`riscv-minor-rvv-bm.py --score-ticks`（默认 5e9）切 Minor 后限时退出并写 stats。`requiresBTBHit=True` 下 Return **~85%**（曾 ~67%），BTBHit~85%；cpl 仍 ~3.27。  
9. ~~late/II~~：路由（early cantForward late/MDU/Mem、`ii_*_late`）已齐；`opLat=1`；II/LX 重叠 = **Minor known gap**（勿拉 opLat）。  
10. ~~FOCUS dependency~~：`s251` IntAlu→IntAlu / loadb→int|br / IntAlu→br；同拍 WAW 齐。  
11. ~~FOCUS forward~~：loadb/ls_base 齐；`BYPASS_MM` 试过回退（Minor 无法只禁 EX）。  
12. ~~FOCUS BP/RAS~~：BTB `gf_hash_67` / PC>>1 / tag49 / RAS empty+both-flag / fetch2 update。Call miss~8%。Return~34% = **known gap**。  
13. `./run_coremark.sh` / `--score-ticks` 日常 gauge  

---

## 7. 一句话总结

**已按 cfg+RTL 落下：** cache/MSHR/SB/WBF、单 LS、双发宽与配对、WAW、loadb 时序、MDU、BPU/MMU 容量、误预测 5/7、2 early+2 late IntFU（IssueLimit=2）、nbload 不再误杀 hit 前递。  

**最大缺口：** Minor 无法重叠「II 双发 early + LX 算已发射 late」（4 ALU busy / issue=2）；4 级 vs ~8 级；Return mis~34%；CoreMark ~3.29 vs 尺 6.3。**未对上 46MPV。**

---

## 8. 持续更新日志（每次改完 / 跑完 gauge 补这里）

> 维护约定：改 `andes_46mpv_scalar.py` 或 Minor Andes C++ 后，**同步改本文件**；CoreMark 结束后把分数 + 分支预测正确率填进下表。

### 8.1 分支预测 — 当前配置（已落地）

| 项 | 值 | 依据 |
|----|-----|------|
| 条件预测器 | **BiModeBP** | cfg `NDS_BRANCH_PREDICTION=dynamic`；RTL BHT≈taken/ntaken/choice |
| BHT / choice 表 | **256**，ctr **2 bit** | RTL BHT addr[7:0] |
| BTB | **256** 项，**2-way** | cfg `NDS_BTB_SIZE` + `BTB_RAM_NUM=2` |
| RAS | **4** | `kv_bpu` RAS_DEPTH |
| `updateBTBAtSquash` | True | squash 路径更新 |
| `requiresBTBHit` | **True** | 对齐高性能前端：BTB 命中才知分支类型并做 RAS（`kv_bpu`）；False 时不把 return 装进 BTB |
| 误预测 extra stall | 真 mispred 时 EX **5** / 条件 late **7** | DS22.8；不打 UnpredictedBranch |

**正确率怎么算（跑完后从 `m5out/stats.txt`）：**

```text
direction_accuracy = 1 - condIncorrect / condPredicted
```

关注字段：

- `system.cpu.branchPred.condPredicted`
- `system.cpu.branchPred.condIncorrect`
- （可选）`BTBLookups` / `mispredictDueToBTBMiss` / `mispredictDueToPredictor`

### 8.2 分支预测正确率 — 实测

| 时间 | workload | condPredicted | condIncorrect | **方向正确率** | 备注 |
|------|----------|---------------|---------------|----------------|------|
| 2026-08-21 | ITER=2；`requiresBTBHit=True` + `--score-ticks` | 64393 | 5647 | **~91.2%** | Return **85.2%**（320/2165）；cpl=305622→**~3.27**；BTBHit~85% |
| 2026-08-21 | mispred Late 仅 late IntFU（勿对所有 cond 打 7） | — | — | — | cpl=304702→**~3.28** |
| 2026-08-21 | PredFU `cantForwardFrom Mem`（对齐 load→br late） | — | — | — | cpl 持平 **~3.28** |
| 2026-08-21 | early Int `cantForward`=[lateInt,MDU,Mem] | — | — | — | cpl 持平 **~3.28**（路由更贴 bit0） |
| 2026-08-21 | scb-bit0：同拍 loadb→IntLate；cantForward+FP/Misc | — | — | — | cpl 持平 **~3.291**（CoreMark 少 FP/CSR） |
| 2026-08-21 | ii-struct：late-BR + LS 禁双发 | — | — | — | **~3.227**（此前过松；对齐 RTL） |
| 2026-08-21 | ii-lx：试 late `opLat=3`（II→LX） | — | — | — | **~3.001** → **回退 opLat=1**（known gap） |
| 2026-08-21 | cond-bp: BiMode `speculativeGHROnUncond=False` + BTB-miss 不推 GHR（RTL s150） | — | — | DirectCond **~7.1%**（原~8.6%） | cpl~304943→**~3.28** |
| 2026-08-21 | bht-choice-upd: `alwaysUpdateChoice=True`（RTL WB 总±1 choice） | — | — | DirectCond **~6.93%** | cpl~304170→**~3.29** |
| 2026-08-21 | mispred：late 罚 7 改 `andesLatePath`（原 fuIndex 无效） | — | — | — | 持平 **~3.227** |
| 2026-08-21 | mispred：罚 0 vs 5/7 诊断 | — | — | — | 3.233 vs 3.227（叠 squash 可忽略） |
| 2026-08-21 | **bugfix `Penalty=5` 裸 int 未写入（一直 0）；改 `Cycles(5/7)` | — | — | — | 配置已生效；gauge **~3.227** |
| 2026-08-21 | dual-issue：fence/barrier→`andesOpForcesSingleIssue` | — | — | — | 持平；ctrl[76] known gap |
| 2026-08-21 | dual-issue：ctrl[76] 短直跳+BTB miss 禁 i1 | — | — | — | **~3.227** |
| 2026-08-21 | return-ras：RAS squash 满栈精确还原 | Return mis~34% | — | — | gauge 持平；II ras_ptr 仍 gap |
| 2026-08-21 | issue-dep：s251 同拍 early 须双方 ~late | — | — | — | **~3.227** |
| 2026-08-21 | dependency：`s251` 近似 IntAlu→IntAlu 同拍 RAW | — | — | — | cpl=303589→**~3.29** |
| 2026-08-21 | dependency：`s251` IntAlu→br | — | — | — | cpl=303225→**~3.30** |
| 2026-08-21 | forward：ls_base 试 `BYPASS_MM` | — | — | — | 掉到 ~3.21 → **回退 lat=0** |
| 历史（早先 Tournament/试 BiMode 阶段） | CoreMark | — | 误预测约 9k–12k 量级 | 未记正式 % | 仅作数量级 |

### 8.3 CoreMark gauge 轨迹

| 时间 | 配置要点 | CoreMark/MHz | IPC | ratio vs 6.3 |
|------|----------|--------------|-----|--------------|
| 较早 | #1–#23 基线量级 | ~3.15 | ~1.0 | ~0.50 |
| 较早 | Int opLat=1 等 | ~3.19–3.7 | ~1.1–1.2 | ~0.51–0.59 |
| 2026-08-21 | nbload 曾强制全 load unpredictable | ~3.3 档 | ~1.16 | ~0.53 |
| 2026-08-21 | Timing→Minor；Late opLat=1 | **~3.28** | ~1.09 | **~0.52** |
| 2026-08-21 | early 禁 Mem + late=`BYPASS_MM`（过严） | **~3.21** 后易卡住 | — | — |
| 2026-08-21 | early 禁 Mem + late=`BYPASS_EX`（fall-through 修复） | **~3.28**（cpl=304573） | n/a（报告后 teardown 长，已杀） | **~0.52** |
| 2026-08-21 | pipe-fwd：`andesSrcNeedsLatePath` 仅 returnCycle>now 才强制 late | — | — | — | gauge **3.227** 持平 |
| 2026-08-21 | return-ras：II ras_ptr 影子写回 FE | Return mis **11.9%**；RAS 对 **88%** | — | — | cpl~3.23；incorrect 644 |
| 2026-08-21 | pipe-fwd：试 late FU占位3 / 结果1 拆开 | — | — | — | gauge **3.00** → 回退 opLat=1 |

**Warmup（日常快 gauge）：** Timing→Minor 仅计分圈；`--score-ticks`（默认 5e9）避免 teardown 挂死并写出 stats。`./run_coremark.sh` 也可在报告后杀进程。勿用 `GEM5_EXIT_AFTER_SCORE`（scored body 前易卡）。

**Log 说明：** gem5 timing 跑中间几乎不往 log 打字；`stats.txt` 要等仿真**正常退出**才写。墙钟仍是分钟级（Minor 段），不是卡死。

**ITER 与 cache：**

| ITER | `GEM5_LOOP_SCORE` 量哪圈 | cache |
|------|--------------------------|-------|
| 1 | i=0（唯一一圈） | **偏冷**，miss 偏多，分数偏悲观 |
| 2 | i=1（最后一圈） | Timing 暖 L1 后 Minor 计第 2 圈 |
| ≥4 | i=3（第 4 圈） | 对齐 Andes VIP 口径 |

### 8.4 本日新增（相对上一版 changelog）

| 改动 | 咋改 | 为啥 |
|------|------|------|
| 2 early + 2 late IntFU | `AndesIntFU`×2 + `AndesLateIntFU`×2；late `opLat=3`≈LX；`IssueLimit=2` | 对齐 RTL `u_alu0..3` |
| Timing→Minor warmup | BM 默认 warmup；CoreMark `GEM5_WARMUP_SWITCH` + `m5_switch_cpu` | 墙钟加速；计分仍在 Minor |
| Semihosting PortProxy | `portProxyImpl` 按 TC 重建 | CPU switch 后勿粘 warmup TC |
| Port pybind | `takeOverFrom`/`unbind`/`isConnected` | 调试端口切换用 |
| nbload markup | 不再「凡 load 皆 unpredictable」 | 恢复 hit 前递 |
| 本文件 | 持续更新 | 「改了啥 / 分数」 |

---

## 9. 一句话（BP）

**配置上**已是 BiMode@256 + BTB256/2way + RAS4 + 误预测 5/7。  
**正确率数字**：等下一轮干净退出的 `stats.txt`；当前 gauge **~3.26 CM/MHz**（warmup 后 Minor）。

| 2026-08-21 | icache-fwf：I$ miss~0.04%，FWF 无杠杆 → 冻结 | — | — | — | ~3.29 不变 |
| 2026-08-21 | btb-repl: RandomRP（RTL LFSR）；commit-update 再测回退 | — | — | BTBHit~87% | ~3.29 |
| 2026-08-21 | bitmanip-lat：CoreMark 无真实 RVB；收束 | — | — | — | ~3.29 |
| 2026-08-21 | ii-lx-commit-ready：需拆 resultLat vs 管深+改 commit；不半吊子 → 冻结 | — | — | — | ~3.29 |
| 2026-08-21 | bp-residual：BHR recover 对齐；Cond~7%/Ret~12% 无新 knob → 收束 | — | — | — | ~3.29 |
| 2026-08-21 | jalr: `indirectBranchPred=NULL`（RTL 仅 BTB） | — | CallInd **0.44%** | Cond~6.86% | **~3.293** |
| 2026-08-21 | scalar-gauge-status：~3.293；主洞 II/LX；knobs 侧近饱和 | — | Cond~6.9% Ret~12% | — | **~3.293** |
| 2026-08-21 | ii-lx-design：resultLat/busyLat+提前 commit 草图钉 notes；仍冻结实现 | — | — | — | ~3.293 |
| 2026-08-21 | ii-lx-impl：确认需 FU 中段摘出/ROB；不重复 opLat 实验 → 冻结 | — | — | — | ~3.293 |
| 2026-08-21 | live-gauge 确认 RandomRP+无 iPred | — | Cond~6.86% Ret~11.8% CallInd~0.44% | BTBHit~87% | **3.293** |

| 2026-08-21 | ii-lx-impl：resultLat+early commit+bubble；opLat3=3.251 opLat2=3.293；BM 关 overlap | — | — | — | **~3.293** |
| 2026-08-21 | alignment-hold：PMA misaligned=DRAM（UNALIGNED=yes）；CM 无杠杆 | — | — | — | **3.293** |
| 2026-08-21 | warmup TimingCPU pmp_entries=4（cfg 齐）；CM 不变 | — | — | — | **3.293** |
| 2026-08-22 | gap-map nbload: param doc + ROB depth comment; rtl_rules↔gem5 refs | — | — | — | no gauge |
| 2026-08-22 | gap-map bypass mux + ls_base: ANDES_BYPASS_* comment, AndesMemFU doc | — | — | — | no gauge |
| 2026-08-22 | gap-map EX∥LX/scoreboard: frozen stage params doc; exlx-2 rtl↔gem5 | — | — | — | no gauge |
