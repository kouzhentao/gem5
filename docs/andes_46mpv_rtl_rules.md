# Andes AX46MPV scalar RTL rules (3-line format)

One block per signal/hazard. Source priority: cfg.txt → DS238 → ucore RTL.

---

## u_alu0 / u_alu1 — early EX ALU (`kv_core.v` + `kv_ipipe.v`)

- **When:** `~ii_*_late` & IntAlu at II; ops muxed to `ex_src*`; `ii_ex_ctrl[134]` enables `alu0/1` at EX.
- **Blocks / allows:** EX combinational result → `ex_rd*` / EX bypass; does not occupy LX alu2/3.
- **gem5:** `AndesIntFU` opLat=1; early path; `cantForwardFrom` late/MDU/Mem — **aligned intent**; not separate physical EX stage.

## u_alu2 / u_alu3 — late LX ALU (`kv_core.v` + `kv_ipipe.v`)

- **When:** `ii_*_late` & IntAlu; `ii_ex_ctrl[149]` suppresses EX alu; `mm_lx_ctrl[183]` enables `alu2/3` on `lx_src*`.
- **Blocks / allows:** Same-cycle EX can run young early while LX runs old late; ALU is still 1cy combo at LX.
- **gem5:** `AndesLateIntFU` opLat=1; `andesLatePath` + EX `relativeLat` — **known gap:** no EX∥LX same-cycle pipe; Minor FU model not stage-positioned.

## ALU latency (`kv_alu.v`)

- **When:** Any alu0..3; no clock on `kv_alu`.
- **Blocks / allows:** N/A — pure combinational; latency is **stage position**, not FU depth.
- **gem5:** **Do not** use `opLat>1` to mean II→LX; use stage/overlap model or `known gap`.

## ii_i0_late / ii_i1_late — bypass selects LX ALU (`kv_iiu_scb.v`)

- **When:** At II, per src: `s188`/`s191`/`s194`/`s197` mux EX→MM→LX/WB bypass; **`~bit[0]` → late** (`ii_i0_late` = rs1|rs2; `ii_i1_late` adds calu_pair, load→i1 RAW `s199/s200`, V `s280–283`).
- **Blocks / allows:** Late Int/BR skips EX alu (`ii_ex_rd*_fu[5]`); value computed at LX alu2/3; early producers use EX alu0/1 with bit0=1 bypass.
- **gem5:** `andesSrcNeedsLatePath` / `andesIntShouldUseLateFU`; early Int `cantForwardFrom` [2–3,4,5,7,8]; late Int on `AndesLateIntFU` — **aligned intent**; calu/V extras not modeled (CM N/A).

## II operand bypass mux — rs1–rs4 (`kv_ipipe.v` L3466–3469 + `kv_iiu_scb.v` L742–757)

- **When:** At II, each src regfile read muxes: `[0]` RF, `[1–2]` EX rd1/rd2, `[3–4]` MM rd1/rd2, `[5–6]` LX rd1/rd2, `[7–8]` WB rd1/rd2; rs2/rs4 use `ii_i0/i1_bypass[9–17]` (same stage order); bypass select from `ii_i0/i1_mm_bypass` (`s188/s191/s194/s197`) per producer type.
- **Blocks / allows:** EX-stage producers visible to II when `mm_bypass` bit0=1 (early path); `~bit[0]` → late/LX path (see `ii_*_late`); enables dual-issue RAW resolve without stall when mux hits.
- **gem5:** `AndesIntFU`/`AndesLateIntFU` `srcRegsRelativeLats=[ANDES_BYPASS_EX]` (`andes_46mpv_scalar.py`); `cantForwardFrom` [2–3,4,5,7,8] ≈ `~bit[0]` — **approx**; no per-stage mux bits — **known gap** (no `opLat` knob).

## LS address base bypass (`kv_ipipe.v` L6337 + `kv_iiu_scb.v` L740–741, `kv_iiu.v` L821)

- **When:** Load/store at EX: `ls_req_base` muxes `ex_src1_reg` (bit0), `ex_src3_reg` (bit1), or `ls_resp_bresult` (bit2, nbload replay); `ii_i0/i1_ls_base_bypass` **blocks EX** producer (`rs*_match_ex_rd*` → 0) — base must come from MM+ or registered EX src.
- **Blocks / allows:** LS base cannot forward from same-cycle EX ALU result; MM/LX/WB base bypass via `s77/s78`; i0 vs i1 slot encoded in `ii_ls_base_bypass[2:0]`.
- **gem5:** `AndesMemFU` all load/store timings `srcRegsRelativeLats=[0]` — **aligned intent** (no EX fwd on base); `ls_resp_bresult` bit2 — **known gap** (`AndesMemFU` docstring).

## i1 load-consumer EX vs LX bypass (`kv_iiu_scb.v` L754–764, `kv_ipipe.v` loadb path)

- **When:** i1 RAW on i0 load (`s199/s200`): `ii_i1_lx_bypass` selects LX load result vs `ii_i1_ex_bypass` for EX-stage i0 producer (`s213/s218`); pairs with `ii_i1_late` forcing LX ALU for consumer.
- **Blocks / allows:** Same-cycle load→i1 Int/BR uses LX bypass (not EX); early Int i0→i1 uses EX bypass when `~ii_i0_late & ~ii_i1_late` (s251).
- **gem5:** `andesSameCycleLateLoadUse` + Mem `extraAssumedLat` — **aligned** for scalar load→use; EX/LX bypass bit select — **approx** via `relativeLat` only.

## ex_ls_loadb / mm_ls_loadb — word/dword loadb detect (`kv_ipipe.v` L6351–6362)

- **When:** At EX LS issue: `ex_ls_loadb` if load W/D (`func3[1:0]==2'b10|11`) and addr low bits aligned (`ex_ls_addr_lsbs==0`) and not `ex_ls_poisoned`; latched to `mm_ls_loadb` when `ex_mm_ls_valid`.
- **Blocks / allows:** Marks MM-stage load as loadb-capable; scb uses `~mm_ls_loadb` to **skip** MM RAW stall on `fu[2]/fu[4]` consumers (`s253/s260/s267/s274`); enables s251 loadb→i1 Int/BR same-cycle pair.
- **gem5:** `andesOpIsLoadbLoad` (`andes_issue_rules.hh`) + `andesSameCycleLateLoadUse` — **aligned**; poisoned/replay addr cases — **known gap**.

## ii_*_ex/mm_nbload_hazard — nbload consumer stall (`kv_iiu_scb.v` L773–776, `kv_ipipe.v` L3544–3547)

- **When:** At II: consumer src matches in-flight **nbload** producer at EX (`s75/s76` + `rs*_match_ex_rd*`) or MM (`s77/s78` + `rs*_match_mm_rd*`); sets `ii_i0/i1_ex_nbload_hazard` → `ii_ex_*_ctrl[191]`, `ii_*_mm_nbload_hazard` → `ii_ex_*_ctrl[189]`.
- **Blocks / allows:** Stalls/replays consumer until nbload result visible; MM hazard pairs with `ls_resp_nbload` (`ls_resp_status[12]`) for `mm_*_nbload_hazard` abort at LX (`mm_lx_abort`).
- **gem5:** `enableAndesNbloadHazard` + scoreboard bypass exception for loadb→int — **partial**; EX/MM nbload ctrl bits, `ls_resp_nbload` replay — **known gap** (P3-lsu-nbload).

## ls_cmt_nbload_hazard — commit vs in-flight nbload (`kv_ipipe.v` L6385)

- **When:** LS commit cycle: hazard if EX `ctrl[191]` set, MM `ctrl[184]` & `ls_resp_nbload`, or LX i1 bypass from nbload path (`lx_i1_bypass[1|3]`).
- **Blocks / allows:** Prevents LS commit while younger ops still depend on unresolved nbload; feeds LSU `ls_cmt_nbload_hazard` for ROB/queue ordering.
- **gem5:** Minor Mem LSQ in-order commit — **approx**; per-stage `ctrl[191/184]` commit gating — **known gap**.

## nbload_resp — async result to XRF (`kv_lsu_rob.v` L490–495, `kv_ipipe.v` L5781–5791)

- **When:** DCU critical refill (`dcu_cri_valid & s79 & ~s78`) or external BIU nbload (`biu_nbload_valid & biu_nbload_ready`); `nbload_resp_rd/result/status/fload` muxed; DCU wins over BIU (`biu_nbload_ready = ~dcu_cri_valid`).
- **Blocks / allows:** Result writes XRF via `xrf_w3` arb (port 0) while load uop still in ROB/pipe; younger independent ops may issue; dependents stall via `ii_*_nbload_hazard` until write.
- **gem5:** `enableAndesNbloadHazard` + `andesSameCycleLateLoadUse`; `executeLSQRequestsQueueSize=3` (`ANDES_LSU_ROB_DEPTH`) — **partial**; async XRF w3, DCU/BIU mux, `ctrl[191/184]` — **known gap** (`BaseMinorCPU.py` doc).

## ROB m1/m2_nbload early ack (`kv_lsu_rob.v` L411,421 + `kv_lspipe.v` m0/m1/m2_nbload)

- **When:** Load tagged nbload (`m*_func[17]` / `m*_ctrl[27|47]`); DCU ack at m1/m2 completes ROB entry without waiting full blocking load path (`~m*_load | m*_nbload` in `s31/s33`).
- **Blocks / allows:** LSU ROB (depth 3) accepts next LS while nbload outstanding; `rob_valid` still tracks m2 commit for blocking path; nbload does not hold `m2_stall` for data the same way.
- **gem5:** `executeLSQRequestsQueueSize=3` + in-order LSQ — **approx depth**; `m*_nbload` early ROB ack — **known gap** (`andes_46mpv_scalar.py` comment).

## m2_nbload_hazard — BIU issue gate (`kv_lspipe.v` L1368,1932)

- **When:** `lsp_cmt_nbload_hazard` (= `ls_cmt_nbload_hazard` from ipipe) asserted while m2 nbload pending commit ordering; `biu_req_nbload = m2_nbload & ~m2_nbload_hazard`.
- **Blocks / allows:** Stalls external nbload issue until ipipe/LSU commit hazard clears; pairs with `ls_req_stall` on EX nbload replay (`ex_i*_ctrl[191] & ls_resp_nbload`).
- **gem5:** Minor LSQ serializes mem refs — **approx** ordering; `biu_req_nbload` / commit-hazard split — **known gap**.

## ii_i1_struct_hazard — dual-issue port / pairing (`kv_iiu_scb.v` L770)

- **When:** i1 issue: `~ls_issue_ready` (fu[2/4/22]); `~mdu_req_ready` or MDU in EX (fu[6]); fu[7] CSR; MDU×MDU; FPU×FPU; FPU×MDU cross; **late BR/JAL** (`i0 fu[8]&i0_late`) + i1 LS; i0+i1 both LS/MDU/FPU/ACE; V pair (`fu[16]&fu[17]`).
- **Blocks / allows:** Stalls **i1 only** (i0 may still issue); i0 struct stalls both via `ii_i1_stall |= ii_i0_stall` in `kv_iiu.v`.
- **gem5:** `andesDualIssuePairAllowed` — MDU×2, LS×2, FPU×2, FPU×MDU, late ctrl+LS, CSR single-issue — **aligned**; V/ACE/`fu[23]` — **known gap** (CM N/A).

## ii_i0_struct_hazard — single-slot busy (`kv_iiu_scb.v` L769)

- **When:** i0: `~ls_issue_ready` for load/store/AMO-class (fu[2/4/22]); `~mdu_req_ready` or EX already has MDU (s95/s96); `store_mem_hazard`/`load_mem_hazard`; StackSafe `fu[9]&late`; ACE credit stall (fu[13]).
- **Blocks / allows:** Stalls i0 → i1 also stalls (in-order dual-issue).
- **gem5:** LS/MDU occupancy via FU pipelines + Mem port — **partial**; mem_hazard/StackSafe/ACE — **known gap** (CM N/A).

## ii_i1_raw_hazard + s251 — same-cycle i0→i1 RAW (`kv_iiu_scb.v` L675,728–729)

- **When:** Default: i1 src hits i0 dest (EX/MM/LX/WB) → raw stall. **Exceptions (s251):** loadb i0 (`fu[3]`) → i1 IntAlu or BR (`fu[0]|fu[8]`); early IntAlu i0 (`fu[0]|fu[1]`, both **~late**) → i1 IntAlu or BR — requires `~ii_i0_late & ~ii_i1_late`.
- **Blocks / allows:** Blocks i1 unless bypass path exists or s251 pair; load→consumer forces i1 late via `s199/s200`.
- **gem5:** `andesSameCycleWAWAllowed` RAW leg — `andesSameCycleLateLoadUse`, `andesSameCycleEarlyIntForward` + `andesSrcNeedsLatePath` — **aligned** for CM scalar pairs.

## ii_i0_raw_hazard — in-flight RAW at II (`kv_iiu_scb.v` L728)

- **When:** i0 rs1/rs2/rs3/rs4 match EX/MM/LX/WB dest of older ops; producer type sets stall unless EX/MM/LX bypass bit applies (`s252–s265`, `s284–s295`); xrf busy (`s5–s8`).
- **Blocks / allows:** Stalls i0 until bypass or WB clear; LS base addr: **no EX bypass** (`ii_i0_ls_base_bypass` forces MM path).
- **gem5:** Minor scoreboard + `relativeLat`/`extraAssumedLat` — **approx**; LS base no-EX-bypass — **known gap**.

## ii_i0_waw_hazard / ii_i1_waw_hazard (`kv_iiu_scb.v` L771–772)

- **When:** i0 WAW: i0 rd1/rd2 vs EX/MM/LX/WB in-flight dests + xrf busy on i0 rd. i1 WAW: i1 rd vs pipeline dests **or** same-cycle i0 rd == i1 rd (`ii_i0_rd1 == ii_i1_rd1`).
- **Blocks / allows:** Stall until older writer clears; no same-cycle dual-write to same reg.
- **gem5:** `andesSameCycleWAWAllowed` same-dest check — **aligned**; pipeline-depth WAW via scoreboard — **approx**.

## EX ∥ LX same-cycle overlap — RTL vs Minor (`kv_iiu.v` + `kv_ipipe.v`)

- **When:** Each cycle at II: up to 2 ops issue; older **late** ops compute at LX (alu2/3) while younger **early** ops compute at EX (alu0/1) — 4 ALUs busy, issue width still 2.
- **Blocks / allows:** Late does not block II width once issued; occupancy is pipe-stage tagged (EX vs LX), not FU-depth tagged.
- **gem5:** `enableAndesStageOccupancy=False` (**frozen**, `BaseMinorCPU.py`); prototypes `minimumCommitCycle`+`andesLxStageHolds` deadlocked (exlx-3c). **Primary CM gap.**

## Minor gap map — scoreboard ≠ stage occupancy (`exlx-2`, `execute.cc` + `scoreboard.cc`)

- **When:** Any II issue of Int/BR on late path (`andesLatePath` / `IntLate` FU 2–3) while another early Int could issue to FU 0–1 same cycle; or late producer still in MM/LX pipe but RTL would still dual-issue.
- **Blocks / allows:** RTL: issue width 2 decoupled from LX alu2/3 busy (stage tag). Minor: (a) `FUPipeline::alreadyPushed()`/`canInsert()` — one inst per FU pipe, no EX/LX tag; (b) `Scoreboard::canInstIssue` — `returnCycle` + `srcRegsRelativeLats`/`cantForwardFrom`, not pipe stage; (c) strict in-order issue loop — i0 fail blocks i1 (`execute.cc` ~680–684).
- **gem5:** `AndesFUPool` 4×Int (0–1 early, 2–3 late) + `andesIntShouldUseLateFU`/`andesLatePath` — **route approx only**. `Scoreboard::canInstIssue` (`returnCycle`, `srcRegsRelativeLats`, `cantForwardFrom`) ≠ stage tag; `enableAndesStageOccupancy` **frozen** — **known gap** (`andes_46mpv_scalar.py` comment).

## EX∥LX fix requirements — design only (`exlx-design`, no impl)

- **When:** Any cycle where RTL would dual-issue early+late Int while LX alu2/3 still holds an older late op (MM pipe delay) and EX alu0/1 runs a younger early op same cycle.
- **Blocks / allows:** Fix must (1) tag occupancy by **stage** (EX vs LX), not FU `opLat`; (2) late issued @II frees early FU same cycle; (3) not block `inFlight` commit/activity (`exlx-3b/3c deadlocked at 16 inst); (4) keep `opLat=1`, no `resultLat` games.
- **gem5:** Needs new mechanism beyond `minimumCommitCycle`/`andesLxStageHolds` or pending queue — e.g. decouple FU push from stage slot + separate LX retire tick. **Frozen until design chosen**; BM ruler ~3.293 @ `enableAndesStageOccupancy=False`.

## exlx-approach-A — virtual LX slot counter (`exlx-pick`)

- **When:** Late Int issued @II; RTL LX alu2/3 busy for `andesLxStageDepth` cycles independent of `FUPipeline::canInsert` on FU 2–3.
- **Blocks / allows:** Issue uses **counter** `andesLxStageHolds` only (no `minimumCommitCycle` on commit); late still `fu->push` immediately; early FU 0–1 unchecked against late FU pipe busy.
- **gem5:** Extend `execute.cc` slot prune; **avoid** commit stall hooks (exlx-3c failure mode). **Candidate** if user picks A.

## exlx-approach-B — split late execute tick (`exlx-pick`)

- **When:** Late Int: issue @II marks `andesLatePath` + schedules LX ALU eval at `now+depth` without holding FU bubble across depth.
- **Blocks / allows:** FU 2–3 `opLat=1` only on execute cycle; between issue and LX execute, inst lives in side queue **not** `inFlightInsts` head stall.
- **gem5:** New `andesLxDeferred` queue drained before issue; larger `execute.cc` change. **Candidate** if user picks B.

## exlx-approach-C — hold gap, no impl (`exlx-pick`)

- **When:** CM scalar ruler only; accept ~3.29 vs ~6.3 until Minor gets stage tags upstream.
- **Blocks / allows:** No further exlx prototypes; document scoreboard approx as permanent for this project.
- **gem5:** `enableAndesStageOccupancy=False` frozen. **Default** if A/B not requested.
