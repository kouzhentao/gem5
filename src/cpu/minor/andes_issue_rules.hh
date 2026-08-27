/*
 * Andes AX45/46MPV dual-issue pairing rules (kv_iiu_scb struct/WAW subset).
 */

#ifndef __CPU_MINOR_ANDES_ISSUE_RULES_HH__
#define __CPU_MINOR_ANDES_ISSUE_RULES_HH__

#include "cpu/minor/dyn_inst.hh"
#include "cpu/minor/scoreboard.hh"
#include "enums/OpClass.hh"

class ThreadContext;

namespace gem5
{

namespace minor
{

/** RTL ii_i1_struct: second slot cannot pair with first on shared resources. */
bool andesDualIssuePairAllowed(MinorDynInstPtr first, MinorDynInstPtr second);

/** RTL ii_i1_waw: i1 dest must not match i0 in-flight dest same cycle.
 *  Also enforces s251 same-cycle RAW exceptions (needs scoreboard for
 *  ~ii_i1_late on early-int pairs). */
bool andesSameCycleWAWAllowed(MinorDynInstPtr first, MinorDynInstPtr second,
    Scoreboard &scoreboard, ThreadContext *thread_context,
    const std::vector<bool> &cant_forward_from_fu_indices, Cycles now);

/** Same-cycle loadb→int use (mm_ls_loadb late path); bypass nbload scoreboard. */
bool andesSameCycleLateLoadUse(MinorDynInstPtr first, MinorDynInstPtr second);

/**
 * RTL s251: certain i0/i1 FU pairs clear same-cycle RAW stall (i0→i1 forward).
 * Approx: both IntAlu (fu[0]/fu[1] early subclass); not mem/MDU.
 * loadb→int is andesSameCycleLateLoadUse (also forces IntLate via
 * execute.cc / s199[1]); V/calu pairs omitted (BM N/A).
 */
bool andesSameCycleEarlyIntForward(MinorDynInstPtr first,
    MinorDynInstPtr second);

/** RTL s251 terms 6–7: i0 FP FMIS/FMV (fu[16/17]) → i1 Int/BR same-cycle RAW OK. */
bool andesSameCycleFpMisFmvToIntForward(MinorDynInstPtr first,
    MinorDynInstPtr second);

inline bool
andesOpUsesMdu(const MinorDynInstPtr &inst)
{
    if (inst->isFault() || inst->isBubble())
        return false;
    const OpClass op = inst->staticInst->opClass();
    return op == enums::IntMult || op == enums::IntDiv;
}

inline bool
andesOpUsesLsu(const MinorDynInstPtr &inst)
{
    if (inst->isFault() || inst->isBubble())
        return false;
    return inst->staticInst->isMemRef();
}

inline bool
andesOpIsSystem(const MinorDynInstPtr &inst)
{
    if (inst->isFault() || inst->isBubble())
        return false;
    const OpClass op = inst->staticInst->opClass();
    return op == enums::InstPrefetch || op == enums::System;
}

/** kv_dec id_ctrl[277]: CSR/fence/system/ACE → ii_i0_singleissue / i1 stall. */
inline bool
andesOpForcesSingleIssue(const MinorDynInstPtr &inst)
{
    if (andesOpIsSystem(inst))
        return true;
    if (inst->isFault() || inst->isBubble())
        return false;
    StaticInstPtr s = inst->staticInst;
    /* s404 = FENCE/FENCE.I (MISC_MEM) in ctrl[277]. */
    if (s->isFullMemBarrier() || s->isReadBarrier() || s->isWriteBarrier())
        return true;
    return false;
}

/**
 * kv_dec id_ctrl[76]: s394 (BR/JAL) & (offset<=8) & ~ifu_pred_hit.
 * Such ops must not occupy i1 (ii_i1_stall).
 */
bool andesIsShortUnpredControl(MinorDynInstPtr inst);

/** FP arithmetic / convert / compare (not mem); same FU cannot dual-issue. */
inline bool
andesOpUsesFpuArith(const MinorDynInstPtr &inst)
{
    if (inst->isFault() || inst->isBubble())
        return false;
    const OpClass op = inst->staticInst->opClass();
    return op == enums::FloatAdd || op == enums::FloatCmp ||
           op == enums::FloatCvt || op == enums::FloatMult ||
           op == enums::FloatMultAcc || op == enums::FloatDiv ||
           op == enums::FloatSqrt || op == enums::FloatMisc;
}

/** Word/dword int load that can set mm_ls_loadb (kv_ipipe ex_ls_loadb).
 *  32-bit: LW/LD/LWU. Compressed: C.LW/C.LD/C.LWSP/C.LDSP (funct3 010/011).
 *  Alignment not known at issue (RTL also checks addr lsbs). */
inline bool
andesOpIsLoadbLoad(const MinorDynInstPtr &inst)
{
    if (inst->isFault() || inst->isBubble())
        return false;
    StaticInstPtr s = inst->staticInst;
    if (!s->isLoad() || s->isFloating() || s->isVector())
        return false;
    const uint32_t enc = static_cast<uint32_t>(s->getEMI());
    if ((enc & 0x3) == 0x3) {
        /* 32-bit / expanded */
        const uint32_t key = enc & 0x707F;
        return key == 0x2003 || /* LW */
               key == 0x3003 || /* LD */
               key == 0x6003;   /* LWU */
    }
    /* Compressed quadrant */
    const uint16_t c = enc & 0xffff;
    const unsigned op = c & 0x3;
    const unsigned f3 = (c >> 13) & 0x7;
    if (f3 != 0x2 && f3 != 0x3) /* not W/D */
        return false;
    return op == 0x0 || op == 0x2; /* C.LW/C.LD or C.LWSP/C.LDSP */
}

/** Wide multi-dest / multi-src int ops (DSP 3R/4R/2W / ACE heavy): single-issue. */
inline bool
andesOpIsWideInt(const MinorDynInstPtr &inst)
{
    if (inst->isFault() || inst->isBubble())
        return false;
    StaticInstPtr s = inst->staticInst;
    if (!s->isInteger() || s->isMemRef() || andesOpUsesMdu(inst))
        return false;
    return s->numSrcRegs() >= 3 || s->numDestRegs() >= 2;
}

/**
 * kv_iiu: ii_*_late when bypass select bit0=0 (e.g. LS producer rd_fu[1]).
 * True for int or BR/JAL when any src still needs forward from a bit0=0 FU
 * (returnCycle > now, or still unpredictable). Once returnCycle <= now the
 * value is treated as RF-visible — early path OK (RTL past LX/WB).
 */
bool andesSrcNeedsLatePath(Scoreboard &scoreboard, MinorDynInstPtr inst,
    ThreadContext *thread_context,
    const std::vector<bool> &cant_forward_from_fu_indices, Cycles now);

/**
 * Early IntFU: if andesSrcNeedsLatePath, skip IntEarly → IntLate.
 */
bool andesIntShouldUseLateFU(Scoreboard &scoreboard, MinorDynInstPtr inst,
    ThreadContext *thread_context,
    const std::vector<bool> &cant_forward_from_fu_indices, Cycles now);

/** Pred FU: BR/JAL with bit0=0 src → LX bru (andesLatePath); use MM/LX bypass lat. */
bool andesBranchShouldUseLatePath(Scoreboard &scoreboard, MinorDynInstPtr inst,
    ThreadContext *thread_context,
    const std::vector<bool> &cant_forward_from_fu_indices, Cycles now);

} // namespace minor
} // namespace gem5

#endif /* __CPU_MINOR_ANDES_ISSUE_RULES_HH__ */
