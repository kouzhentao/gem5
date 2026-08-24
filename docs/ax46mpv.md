# AX46MPV Spec

RTL：`docs/ax45mpv/andes_ip/kv_core/ucore/hdl/kv_ifu.v`。

---

## F0

F0 选出 `req_addr`：

- 发 I$ 或 ILM → 取本拍 PC 的指令
- 发 BTB → 查 next_pc（下拍 F0 用）

`req_addr` 三个 source：

| Source | 一句话 |
|--------|--------|
| `redirect_pc` | 本拍 backend 改向（分支/异常） |
| `f0_pc` | 上拍改向没发出去，锁存重发 |
| `target_pc` | 正常顺序/预测前进 |

---

### 1. `redirect_pc`

| 细分 | 来源 | 场景 |
|------|------|------|
| `redirect_pc` | WB（LX branch） | late 分支误判 |
| `redirect_pc` | MM（EX branch） | early 分支误判 |
| `redirect_pc` | 异常 | illegal instruction、page fault 等 |

---

### 2. `f0_pc`

- 锁存：`f0_valid_set`（redirect 但 `req_ready=0` / stall）
- 清零：`fetch_issue` 后 `f0_valid_clr`（发出去了，不用再锁）

11 个来源（`f0_pc_nx` MUX）：

| 优先级 | Source | 来源 | 场景 |
|--------|--------|------|------|
| 1 | `resume_pc` | CSR | `mret`、`sret`、`uret` 返回 |
| 2 | `redirect_pc` | backend（WB/MM） | 分支误判、异常 |
| 3 | `f0_pc_flush_init_value` | 内部 | cache flush 初始化地址 |
| 4 | `ic_flush_addr_nx_ext` | I$ | flush 下一行地址 |
| 5 | `ic_op_addr_ext` | CCTL | cache 控制指令地址 |
| 6 | `retry_pc` | MMU | ITLB miss 处理完，重取 |
| 7 | `ex9_lookup_pc` | EX9 | 非标准扩展查找 |
| 8 | `f2_ecc_inv_addr` | F2 | ECC 错误，重取修正地址 |
| 9 | `seq_pc` | 顺序 | EX9 fetch 顺序下一条 |
| 10 | `recover_pc` | 内部 | F1/F2 被 kill 后恢复 |
| 11 | `prefetch_addr` | 预取 | 硬件预取下一行 |

---

### 3. `target_pc`

`target_pc` 来自 `kv_pq.v`，来自 F1 的 next_pc，BTB 预测优先，否则 `seq_pc`：

| 优先级 | Source | 场景 |
|--------|--------|------|
| 1 | BTB 预测命中 | 跳到预测目标地址 |
| 2 | `seq_pc` | 顺序执行，PC+4（或+2 RVC） |

`seq_pc` 在 `fetch_issue` 后更新为下一条顺序地址。

---

优先级：`redirect_pc` > `f0_pc` > `target_pc`。
