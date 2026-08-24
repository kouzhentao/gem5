# AX46MPV Spec

RTL：`docs/ax45mpv/andes_ip/kv_core/ucore/hdl/kv_ifu.v`。

---

## F0

选出发给 I$/ILM 的地址 `req_addr`。

- `ifu_icu_req_addr` → I$（`kv_icu`）
- `ifu_ilm_req_addr` → ILM

`req_addr` 三个候选：

| 候选 | 什么时候用 |
|------|-----------|
| `redirect_pc` | 分支误判、异常、resume 改向 |
| `f0_pc` | 上拍没发出去（BPU 不 ready、recover、prefetch…），锁住的地址 |
| `target_pc` | 正常顺序/预测前进（BTB 或 `seq_pc`） |

优先级：`redirect_pc` > `f0_pc` > `target_pc`。

`f0_pc` 在 `f0_valid=1` 时锁存上拍地址；`fetch_issue` 后 `f0_valid` 清。
