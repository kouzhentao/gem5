#!/usr/bin/env python3
"""Shared Andes 46MPV scalar knobs for MinorCPU.

Parameter truth (strict):
  1) cfg.txt — 46MPV numbers / feature enables (authoritative)
  2) DS238  — family timing tables (load-use, dual-issue matrix, mul/div…)
  3) docs/ax45mpv RTL — hardware structure only (iiu/lsu/bpu dataflow).
     Do NOT take RTL module default parameters when cfg.txt has the value
     (e.g. RTL LSU_LOW_LATENCY default 0 vs cfg NDS_LSU_LOW_LATENCY=1).

CoreMark is an alignment gauge only (not a score to chase).
"""

# --- cfg.txt (46MPV) ---
ANDES_BTB_ENTRIES = 256          # NDS_BTB_SIZE
# kv_bpu_ctrl: BTB_TAG_WIDTH = VALEN - 1 - BTB_RAM_ADDR_WIDTH (7 for 128 sets)
# cfg NDS_VALEN=57 → tag = 57 - 1 - 7 = 49 (gem5 SimpleBTB default 16 is too short)
ANDES_BTB_TAG_BITS = 49
ANDES_L1I_MSHRS = 8              # NDS_MSHR_DEPTH
ANDES_L1D_MSHRS = 16             # NDS_LSU_MSHR_DEPTH
ANDES_LSU_MSHR_DEPTH = 16        # NDS_LSU_MSHR_DEPTH
ANDES_LSU_SB_DEPTH = 8           # NDS_LSU_SB_DEPTH
ANDES_L1_SIZE = "32KiB"          # NDS_ICACHE/DCACHE_SIZE=32
ANDES_L1_ASSOC = 4               # NDS_*CACHE_WAY
ANDES_DPF_ENTRIES = 4            # NDS_DCACHE_PREFETCH_ENTRIES
ANDES_UTAG_DEPTH = 16            # NDS_DCACHE_UTAG_DEPTH
ANDES_PMP_ENTRIES = 4            # NDS_PMP_ENTRIES
ANDES_LSU_LOW_LATENCY = True     # NDS_LSU_LOW_LATENCY=1 → early mem issue
# cfg NDS_NON_BLOCKING_SUPPORT=yes → model non-blocking loads (nbload).
ANDES_NON_BLOCKING_LOAD = True

# --- DS238 timing (family) ---
ANDES_MDU_DIV_LAT_MIN = 6
ANDES_MDU_DIV_LAT_MAX = 69
ANDES_MDU_MUL_LAT = 1            # DS172 fast mul
ANDES_BHT_ENTRIES = 256          # BiMode / BHT size (cfg: dynamic BP; size via DS/RTL)

# --- 45 RTL structure only (not in cfg.txt) ---
ANDES_RAS_ENTRIES = 4            # kv_bpu RAS
ANDES_BTB_ASSOC = 2              # kv_bpu BTB
ANDES_IIQ_DEPTH = 4              # kv_iiq DEPTH
ANDES_FQ_DEPTH = 4               # kv_fq FQ_DEPTH
ANDES_LSQ_DEPTH = 4              # kv_lsq DEPTH
ANDES_LSU_ROB_DEPTH = 3          # kv_lsu_rob DEPTH
ANDES_WBF_DEPTH = 2              # kv_dcu: CM_SUPPORT=no → DCACHE_WBF_DEPTH=2 (not in cfg)
ANDES_DPF_QUEUE = 4              # PF queue (structure; entries from cfg)
# Minor srcRegsRelativeLats: HIGHER = earlier issue while producer in-flight.
# RTL EX earlier than MM → EX relativeLat > MM. ls_base forces EX off (lat=0).
ANDES_BYPASS_EX = 3
ANDES_BYPASS_MM = 1

# RISC-V LOAD opcode=0000011; mask opcode|funct3
_RV_LOAD_MASK = 0x707F
_RV_LW = 0x2003
_RV_LD = 0x3003
_RV_LWU = 0x6003
_RV_LH = 0x1003
_RV_LHU = 0x5003
_RV_LB = 0x0003
_RV_LBU = 0x4003
# FENCE: opcode=0001111
_RV_FENCE_MASK = 0x7F
_RV_FENCE = 0x0F

from m5.objects import (
    AndesBTBSetAssociative,
    BiModeBP,
    BranchPredictor,
    BTBSetAssociative,
    Cycles,
    LocalBP,
    MinorDefaultFloatSimdFU,
    MinorDefaultIntFU,
    MinorDefaultMemFU,
    MinorDefaultMiscFU,
    MinorDefaultPredFU,
    MinorFU,
    MinorFUPool,
    MinorFUTiming,
    RandomRP,
    ReturnAddrStack,
    RiscvTLB,
)
from m5.objects.BaseMinorCPU import minorMakeOpClassSet
from m5.objects.TimingExpr import (
    TimingExprBin,
    TimingExprIf,
    TimingExprLet,
    TimingExprLiteral,
    TimingExprRef,
    TimingExprSrcReg,
    TimingExprUn,
)
from m5.params import NULL

from gem5.components.boards.abstract_board import AbstractBoard
from gem5.components.cachehierarchies.classic.caches.l1dcache import L1DCache
from gem5.components.cachehierarchies.classic.caches.l1icache import L1ICache
from gem5.components.cachehierarchies.classic.private_l1_cache_hierarchy import (
    PrivateL1CacheHierarchy,
)
from gem5.isas import ISA
from gem5.utils.override import overrides


def _lit(v):
    return TimingExprLiteral(value=v)


def _bin(op, left, right):
    return TimingExprBin(op=op, left=left, right=right)


def _un(op, arg):
    return TimingExprUn(op=op, arg=arg)


def _if(cond, t, f):
    return TimingExprIf(cond=cond, trueExpr=t, falseExpr=f)


# DS173: div 6–69cy early termination (operand-width approx).
ANDES_DIV_EXTRA_LAT_EXPR = TimingExprLet(
    defns=[
        TimingExprSrcReg(index=0),
        TimingExprSrcReg(index=1),
        _un("timingExprSizeInBits", _un("timingExprAbs", TimingExprRef(index=0))),
        _un("timingExprSizeInBits", _un("timingExprAbs", TimingExprRef(index=1))),
        _if(
            _bin("timingExprULessThan", TimingExprRef(index=2), TimingExprRef(index=3)),
            _lit(0),
            _bin("timingExprSub", TimingExprRef(index=2), TimingExprRef(index=3)),
        ),
    ],
    expr=_if(
        _bin("timingExprEqual", TimingExprRef(index=1), _lit(0)),
        _lit(ANDES_MDU_DIV_LAT_MAX - ANDES_MDU_DIV_LAT_MIN),
        _if(
            _bin("timingExprEqual", TimingExprRef(index=1), _lit(1)),
            _lit(0),
            _if(
                _bin(
                    "timingExprUGreaterThan",
                    TimingExprRef(index=4),
                    _lit(ANDES_MDU_DIV_LAT_MAX - ANDES_MDU_DIV_LAT_MIN),
                ),
                _lit(ANDES_MDU_DIV_LAT_MAX - ANDES_MDU_DIV_LAT_MIN),
                TimingExprRef(index=4),
            ),
        ),
    ),
)


class AndesMemFU(MinorDefaultMemFU):
    """LS timing from DS169 + 45 RTL loadb / ls_base structure.

    ex_ls_loadb (kv_ipipe): aligned LW/LD(/LWU) → extraAssumedLat=1.
    LB/LH (~loadb): DS169 +1cy → extraAssumedLat=2; not same-cycle late dual-issue.
    ls_base: EX match forced 0; MM load OK. gem5 addr lat=0 (conservative;
    tried BYPASS_MM=1 → gauge 3.30→3.21, cannot ban EX-only in Minor).
    """

    opClasses = minorMakeOpClassSet(
        [
            "MemRead",
            "MemWrite",
            "FloatMemRead",
            "FloatMemWrite",
            "SimdUnitStrideLoad",
            "SimdUnitStrideStore",
            "SimdUnitStrideMaskLoad",
            "SimdUnitStrideMaskStore",
            "SimdStridedLoad",
            "SimdStridedStore",
            "SimdIndexedLoad",
            "SimdIndexedStore",
            "SimdUnitStrideFaultOnlyFirstLoad",
            "SimdWholeRegisterLoad",
            "SimdWholeRegisterStore",
            "SimdUnitStrideSegmentedLoad",
            "SimdUnitStrideSegmentedStore",
            "SimdUnitStrideSegmentedFaultOnlyFirstLoad",
            "SimdStrideSegmentedLoad",
            "SimdStrideSegmentedStore",
        ]
    )
    timings = [
        # loadb path: forwardable hit (extraAssumedLat>0)
        # addr: RTL ls_base bans EX; MM load OK. Minor cannot ban-EX-only —
        # relativeLat=0 (must be ready) is the faithful conservative choice.
        # Tried BYPASS_MM=1 → gauge dropped 3.30→3.21; reverted.
        MinorFUTiming(
            description="LoadWord",
            opClasses=minorMakeOpClassSet(["MemRead"]),
            mask=_RV_LOAD_MASK,
            match=_RV_LW,
            srcRegsRelativeLats=[0],
            extraAssumedLat=1,
        ),
        MinorFUTiming(
            description="LoadDword",
            opClasses=minorMakeOpClassSet(["MemRead"]),
            mask=_RV_LOAD_MASK,
            match=_RV_LD,
            srcRegsRelativeLats=[0],
            extraAssumedLat=1,
        ),
        MinorFUTiming(
            description="LoadWordU",
            opClasses=minorMakeOpClassSet(["MemRead"]),
            mask=_RV_LOAD_MASK,
            match=_RV_LWU,
            srcRegsRelativeLats=[0],
            extraAssumedLat=1,
        ),
        # ~loadb: DS169 latency=1 (not same-cycle late dual-issue). Forwardable
        # but later than word; same-cycle RAW still blocked (andesOpIsLoadbLoad).
        MinorFUTiming(
            description="LoadHalf",
            opClasses=minorMakeOpClassSet(["MemRead"]),
            mask=_RV_LOAD_MASK,
            match=_RV_LH,
            srcRegsRelativeLats=[0],
            extraAssumedLat=2,
        ),
        MinorFUTiming(
            description="LoadHalfU",
            opClasses=minorMakeOpClassSet(["MemRead"]),
            mask=_RV_LOAD_MASK,
            match=_RV_LHU,
            srcRegsRelativeLats=[0],
            extraAssumedLat=2,
        ),
        MinorFUTiming(
            description="LoadByte",
            opClasses=minorMakeOpClassSet(["MemRead"]),
            mask=_RV_LOAD_MASK,
            match=_RV_LB,
            srcRegsRelativeLats=[0],
            extraAssumedLat=2,
        ),
        MinorFUTiming(
            description="LoadByteU",
            opClasses=minorMakeOpClassSet(["MemRead"]),
            mask=_RV_LOAD_MASK,
            match=_RV_LBU,
            srcRegsRelativeLats=[0],
            extraAssumedLat=2,
        ),
        MinorFUTiming(
            description="MemReadDefault",
            opClasses=minorMakeOpClassSet(["MemRead", "FloatMemRead"]),
            srcRegsRelativeLats=[0],
            # C.LW/C.LD etc. miss 32-bit mask/match → treat as loadb (hit MM fwd)
            extraAssumedLat=1,
        ),
        # Store: base lat=0 (ls_base); store data may use EX (rs2 ≠ ls_base).
        MinorFUTiming(
            description="MemWrite",
            opClasses=minorMakeOpClassSet(["MemWrite", "FloatMemWrite"]),
            srcRegsRelativeLats=[0, ANDES_BYPASS_EX],
            extraAssumedLat=1,
        ),
        MinorFUTiming(
            description="SimdMem",
            srcRegsRelativeLats=[0],
            extraAssumedLat=0,
        ),
    ]
    opLat = 1
    issueLat = 1


class AndesIntFU(MinorDefaultIntFU):
    """EX early ALU (kv_core u_alu0/1). 1cy; dual-issue.

    cantForwardFromFUIndices: RTL early bypass bit0=1 only. Producers with
    bit0=0 (kv_iiu_scb s174/s176…): late Int[2–3], MDU[4], FP[5], Mem[7],
    Misc/CSR[8] → consumer must be ii_*_late (LX). Pred[6] has no int dest.
    """
    opLat = 1
    issueLat = 1
    # AndesFUPool: 0-1 early Int, 2-3 late Int, 4 MDU, 5 FP, 6 Pred, 7 Mem, 8 Misc
    cantForwardFromFUIndices = [2, 3, 4, 5, 7, 8]
    timings = [
        MinorFUTiming(description="IntEarly", srcRegsRelativeLats=[ANDES_BYPASS_EX])
    ]


class AndesLateIntFU(MinorDefaultIntFU):
    """LX late ALU (kv_core u_alu2/3). RTL ALU is combinational **1cy** at LX
    (same as early at EX). late = *where* it computes, not multi-cycle ALU.
    """
    opLat = 1
    issueLat = 1
    timings = [
        MinorFUTiming(
            description="IntLate",
            # ≥ ANDES_BYPASS_EX so fall-through works; Mem consumers arrive
            # here because early Int rejects Mem forward.
            srcRegsRelativeLats=[ANDES_BYPASS_EX],
        )
    ]


class AndesPredFU(MinorDefaultPredFU):
    """Branch/pred. RTL: load/late/MDU/FP/CSR-sourced compares are late
    (bit0=0); mirror AndesIntFU cantForward (Pred has no int dest to list)."""
    opLat = 1
    issueLat = 1
    cantForwardFromFUIndices = [2, 3, 4, 5, 7, 8]
    timings = [
        MinorFUTiming(description="Pred", srcRegsRelativeLats=[ANDES_BYPASS_EX])
    ]


class AndesMduFU(MinorFU):
    """kv_mdu: single shared mul/div (struct ~mdu_req_ready). cfg MULTIPLIER=fast."""

    opClasses = minorMakeOpClassSet(["IntMult", "IntDiv"])
    opLat = ANDES_MDU_MUL_LAT
    issueLat = 1
    timings = [
        MinorFUTiming(
            description="MulFast",
            opClasses=minorMakeOpClassSet(["IntMult"]),
            srcRegsRelativeLats=[ANDES_BYPASS_EX],
        ),
        MinorFUTiming(
            description="DivEarlyTerm",
            opClasses=minorMakeOpClassSet(["IntDiv"]),
            srcRegsRelativeLats=[ANDES_BYPASS_EX],
            extraCommitLat=ANDES_MDU_DIV_LAT_MIN - ANDES_MDU_MUL_LAT,
            extraCommitLatExpr=ANDES_DIV_EXTRA_LAT_EXPR,
        ),
    ]


class AndesFloatSimdFU(MinorDefaultFloatSimdFU):
    """DS238 Tables 174–176 (DP supported): FMAC lat 4, FDIV.D 32, FMISC 2, FMV 1."""
    issueLat = 1
    opLat = 1
    timings = [
        MinorFUTiming(
            description="Fmac",
            opClasses=minorMakeOpClassSet(
                ["FloatAdd", "FloatMult", "FloatMultAcc"]
            ),
            srcRegsRelativeLats=[ANDES_BYPASS_EX],
            extraCommitLat=3,  # total ~4 with opLat
        ),
        MinorFUTiming(
            description="FdivSqrt",
            opClasses=minorMakeOpClassSet(["FloatDiv", "FloatSqrt"]),
            srcRegsRelativeLats=[ANDES_BYPASS_EX],
            extraCommitLat=31,  # FDIV.D ≈32 (S would be 18; scalar DP cfg)
        ),
        MinorFUTiming(
            description="Fmv",
            opClasses=minorMakeOpClassSet(["FloatMisc"]),
            srcRegsRelativeLats=[ANDES_BYPASS_EX],
        ),
        MinorFUTiming(
            description="FmiscCvtCmp",
            opClasses=minorMakeOpClassSet(["FloatCmp", "FloatCvt", "Bf16Cvt"]),
            srcRegsRelativeLats=[ANDES_BYPASS_EX],
            extraCommitLat=1,  # Table 176 lat 2
        ),
    ]


class AndesMiscFU(MinorDefaultMiscFU):
    """CSR/system/No_Op; DS238 §22.12 FENCE flush ≈13cy (no outstanding mem)."""
    opLat = 1
    issueLat = 1
    timings = [
        MinorFUTiming(
            description="Fence",
            mask=_RV_FENCE_MASK,
            match=_RV_FENCE,
            srcRegsRelativeLats=[0],
            extraCommitLat=12,  # +opLat ≈13
        ),
    ]


class AndesFUPool(MinorFUPool):
    # 4× ALU like RTL: alu0/1 early then alu2/3 late (prefer early by order).
    # IssueLimit=2 — late FUs for LX overlap, not 4-wide issue.
    funcUnits = [
        AndesIntFU(),
        AndesIntFU(),
        AndesLateIntFU(),
        AndesLateIntFU(),
        AndesMduFU(),
        AndesFloatSimdFU(),
        AndesPredFU(),
        AndesMemFU(),
        AndesMiscFU(),
    ]


def make_andes_branch_predictor():
    # cfg NDS_BRANCH_PREDICTION=dynamic; kv_bpu ≈ BiMode (taken/ntaken/choice).
    bp = BranchPredictor(
        conditionalBranchPred=BiModeBP(
            globalPredictorSize=ANDES_BHT_ENTRIES,  # RTL BHT addr[7:0]
            choicePredictorSize=ANDES_BHT_ENTRIES,  # sel table same width
            globalCtrBits=2,   # RTL dir_data[1:0]
            choiceCtrBits=2,   # RTL sel_data[1:0]
            speculativeGHROnUncond=False,  # kv_bpu: BHR only on cond hits
            alwaysUpdateChoice=True,  # kv_ipipe: always ±1 choice toward reso
        ),
        # RTL kv_bpu: indirect targets from BTB only (no separate ITABLE).
        indirectBranchPred=NULL,
        ras=ReturnAddrStack(numEntries=ANDES_RAS_ENTRIES),
        # Commit update (RTL MM/WB alloc|revise) re-tried 2026-08-21: Call miss
        # 8.3→9.1%, CM 3.29→3.28 — keep squash update.
        updateBTBAtSquash=True,
        # RTL BPU: branch type/RAS need BTB hit (kv_bpu). Minor sees decode,
        # but requiresBTBHit=True installs returns into BTB like a real FE.
        requiresBTBHit=True,
    )
    return bp


def apply_andes_scalar_cpu(cpu) -> None:
    cpu.branchPred = make_andes_branch_predictor()
    # RTL indexes BTB/BHT with PC>>UNUSED_PC_BIT_NUM (1). Keep BP hash in sync.
    cpu.branchPred.instShiftAmt = 1
    cpu.branchPred.btb.numEntries = ANDES_BTB_ENTRIES  # cfg NDS_BTB_SIZE=256
    cpu.branchPred.btb.associativity = ANDES_BTB_ASSOC
    cpu.branchPred.btb.tagBits = ANDES_BTB_TAG_BITS
    # kv_bpu_ctrl s58 LFSR picks alloc way — not LRU. RandomRP ≈ that.
    cpu.branchPred.btb.btbReplPolicy = RandomRP()
    # Re-bind indexing so tag_bits/assoc/entries match (Parent proxies bake early).
    cpu.branchPred.btb.btbIndexingPolicy = AndesBTBSetAssociative(
        assoc=ANDES_BTB_ASSOC,
        num_entries=ANDES_BTB_ENTRIES,
        set_shift=1,  # PC[14:1] inside hash; shift kept for tagShift math
        tag_bits=ANDES_BTB_TAG_BITS,
    )
    cpu.mmu.itb.size = 8
    cpu.mmu.dtb.size = 8
    cpu.mmu.pmp.pmp_entries = ANDES_PMP_ENTRIES
    cpu.mmu.l2tlb = RiscvTLB(entry_type="unified", size=64)
    cpu.mmu.itb.next_level = cpu.mmu.l2tlb
    cpu.mmu.dtb.next_level = cpu.mmu.l2tlb

    cpu.executeFuncUnits = AndesFUPool()
    cpu.fetch2CycleInput = True
    # Dual-issue width = 2; IIQ/FQ depth = buffer size, not issue width.
    cpu.decodeInputWidth = 2
    cpu.decodeCycleInput = True
    cpu.executeInputWidth = 2
    cpu.executeCycleInput = True
    cpu.executeIssueLimit = 2
    cpu.executeCommitLimit = 2
    cpu.executeInputBufferSize = ANDES_IIQ_DEPTH

    cpu.fetch1FetchLimit = ANDES_L1I_MSHRS
    cpu.fetch1LineWidth = 64
    cpu.fetch1LineSnapWidth = 64
    cpu.fetch1ToFetch2ForwardDelay = 1
    cpu.fetch2ToDecodeForwardDelay = 1
    # II is one pipe reg (kv_iiq); Minor executeInputBuffer ≈ IIQ — delay=1 not 2
    cpu.decodeToExecuteForwardDelay = 1
    cpu.fetch2InputBufferSize = ANDES_FQ_DEPTH
    cpu.decodeInputBufferSize = ANDES_IIQ_DEPTH
    cpu.executeLSQStoreBufferSize = ANDES_LSU_SB_DEPTH
    cpu.executeLSQTransfersQueueSize = ANDES_LSQ_DEPTH
    # kv_lsu_rob DEPTH=3: outstanding LS uops; approximates m1/m2 pipe only.
    # Gap: RTL m*_nbload early ack + nbload_resp XRF w3 ≠ Minor blocking retire.
    cpu.executeLSQRequestsQueueSize = ANDES_LSU_ROB_DEPTH
    cpu.executeMaxAccessesInMemory = ANDES_LSU_MSHR_DEPTH
    cpu.executeMemoryIssueLimit = 1  # single LS port (DS168)
    cpu.executeMemoryCommitLimit = 1
    cpu.executeMemoryWidth = 8
    cpu.executeAllowEarlyMemoryIssue = ANDES_LSU_LOW_LATENCY

    # kv_iiu_scb structure: pairing + same-cycle WAW/RAW (late loadb excepted).
    cpu.enableAndesDualIssueRules = True
    cpu.enableAndesWAWHazard = True
    # cfg NDS_NON_BLOCKING_SUPPORT=yes → partial nbload model (no gauge target):
    # enableAndesNbloadHazard + loadb same-cycle + ROB depth above; gaps in
    # BaseMinorCPU.enableAndesNbloadHazard doc / rtl_rules nbload_* blocks.
    cpu.enableAndesNbloadHazard = ANDES_NON_BLOCKING_LOAD
    # Late ALU is 1cy (same as early); do not fake multi-cycle opLat.
    # II/LX overlap ≠ longer ALU — enableAndesIiLxOverlap stays off until
    # real pipe-control model exists (not opLat games).
    cpu.enableAndesIiLxOverlap = False
    # exlx-3: II→LX stage queue prototype — off until exlx-4 gauge.
    cpu.enableAndesStageOccupancy = False
    cpu.andesLxStageDepth = 3
    cpu.andesLxStageSlots = 2
    # DS238 §22.8: 5cy EX / 7cy LX on true mispredict only (see execute.cc).
    # Bare int was silently ignored (config.ini stayed at Param default 0).
    cpu.executeBranchMispredictPenalty = Cycles(5)
    cpu.executeBranchMispredictPenaltyLate = Cycles(7)
    cpu.executeBranchDelay = 1
    cpu.fetch1ToFetch2BackwardDelay = 1
    cpu.executeLSQMaxStoreBufferStoresPerCycle = 1


def configure_andes_mem_ctrl(mem_ctrl) -> None:
    pass


def configure_andes_l1_icache(cache) -> None:
    cache.size = ANDES_L1_SIZE
    cache.assoc = ANDES_L1_ASSOC
    cache.mshrs = ANDES_L1I_MSHRS
    cache.tag_latency = 1
    cache.data_latency = 1
    cache.response_latency = 1
    cache.tgts_per_mshr = 4
    cache.prefetcher = NULL


def configure_andes_l1_dcache(cache) -> None:
    cache.size = ANDES_L1_SIZE
    cache.assoc = ANDES_L1_ASSOC
    cache.mshrs = ANDES_L1D_MSHRS
    cache.tag_latency = 1
    cache.data_latency = 1
    cache.response_latency = 1
    cache.tgts_per_mshr = 4
    cache.write_buffers = ANDES_WBF_DEPTH  # kv_dtag structure (not in cfg)
    # Prefetch entries from cfg; utag depth is a separate D$ feature.
    cache.prefetcher.table_entries = str(ANDES_DPF_ENTRIES)
    cache.prefetcher.queue_size = ANDES_DPF_QUEUE
    cache.prefetcher.degree = 1
    cache.prefetcher.table_assoc = 4
    cache.prefetcher.confidence_threshold = 50
    cache.sequential_access = False


def make_andes_l1_icache() -> L1ICache:
    cache = L1ICache(size=ANDES_L1_SIZE, assoc=ANDES_L1_ASSOC, mshrs=ANDES_L1I_MSHRS)
    configure_andes_l1_icache(cache)
    return cache


def make_andes_l1_dcache() -> L1DCache:
    cache = L1DCache(size=ANDES_L1_SIZE, assoc=ANDES_L1_ASSOC, mshrs=ANDES_L1D_MSHRS)
    configure_andes_l1_dcache(cache)
    return cache


class AndesPrivateL1(PrivateL1CacheHierarchy):
    def __init__(
        self,
        l1d_size: str = ANDES_L1_SIZE,
        l1i_size: str = ANDES_L1_SIZE,
        assoc: int = ANDES_L1_ASSOC,
    ):
        super().__init__(l1d_size=l1d_size, l1i_size=l1i_size)
        self._assoc = assoc

    @overrides(PrivateL1CacheHierarchy)
    def incorporate_cache(self, board: AbstractBoard) -> None:
        board.connect_system_port(self.membus.cpu_side_ports)
        for _, port in board.get_mem_ports():
            self.membus.mem_side_ports = port

        n = board.get_processor().get_num_cores()
        self.l1icaches = [
            L1ICache(size=self._l1i_size, assoc=self._assoc, mshrs=ANDES_L1I_MSHRS)
            for _ in range(n)
        ]
        for cache in self.l1icaches:
            configure_andes_l1_icache(cache)

        self.l1dcaches = [
            L1DCache(size=self._l1d_size, assoc=self._assoc, mshrs=ANDES_L1D_MSHRS)
            for _ in range(n)
        ]
        for cache in self.l1dcaches:
            configure_andes_l1_dcache(cache)

        if board.has_coherent_io():
            self._setup_io_cache(board)

        for i, cpu in enumerate(board.get_processor().get_cores()):
            cpu.connect_icache(self.l1icaches[i].cpu_side)
            cpu.connect_dcache(self.l1dcaches[i].cpu_side)
            self.l1icaches[i].mem_side = self.membus.cpu_side_ports
            self.l1dcaches[i].mem_side = self.membus.cpu_side_ports
            self._connect_table_walker(i, cpu)
            if board.get_processor().get_isa() == ISA.X86:
                cpu.connect_interrupt(
                    self.membus.mem_side_ports, self.membus.cpu_side_ports
                )
            else:
                cpu.connect_interrupt()
