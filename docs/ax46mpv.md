# AX46MPV Spec

RTL：`docs/ax45mpv/andes_ip/kv_core/ucore/hdl/kv_ifu.v`。

---

## f0 — PC 锁存与选择

f0 是取指第一拍寄存器级，管两件事：

1. **锁 PC**：redirect 等后端 stall、resume、retry、prefetch、recover 时，把地址锁在 `f0_pc`，`f0_valid=1`。
2. **选地址**：组合逻辑选出本拍发给 I$/ILM 的 `req_addr`。

`req_addr` 优先级：`redirect_pc` > `f0_pc` > `target_pc`。

`target_pc` 来自 `kv_pq`（BTB/BHT/RAS 预测或 `seq_pc` 顺序 +8）。

`f0_pc` 的源：redirect、resume、retry、prefetch、recover、EX9、cache flush、ECC 修正。

`fetch_issue = req_valid & req_ready` 时 `f0_valid` 清，地址进 f1。
