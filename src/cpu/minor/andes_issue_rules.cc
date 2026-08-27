/*
 * Andes AX45/46MPV dual-issue pairing (DS238 Table 168 + kv_iiu_scb).
 */

#include "cpu/minor/andes_issue_rules.hh"

#include "cpu/minor/scoreboard.hh"
#include "cpu/reg_class.hh"

namespace gem5
{

namespace minor
{

bool
andesIsShortUnpredControl(MinorDynInstPtr inst)
{
    if (!inst || inst->isFault() || inst->isBubble())
        return false;
    if (inst->andesPredHit)
        return false;
    StaticInstPtr s = inst->staticInst;
    /* Direct BR/JAL only (PC-relative). JALR needs RF for full s474; skip. */
    if (!s->isControl() || !s->isDirectCtrl() || !inst->pc)
        return false;
    std::unique_ptr<PCStateBase> tgt = s->branchTarget(*inst->pc);
    if (!tgt)
        return false;
    int64_t off = static_cast<int64_t>(tgt->instAddr()) -
        static_cast<int64_t>(inst->pc->instAddr());
    if (off < 0)
        off = -off;
    return off <= 8;
}

bool
andesDualIssuePairAllowed(MinorDynInstPtr first, MinorDynInstPtr second)
{
    if (!first || !second || first->isBubble() || second->isBubble())
        return true;

    /* Single MDU: MUL/DIV + MUL/DIV = No (DS168). */
    if (andesOpUsesMdu(first) && andesOpUsesMdu(second))
        return false;

    /* Single LS port: Load/Store + Load/Store = No (DS168). */
    if (andesOpUsesLsu(first) && andesOpUsesLsu(second))
        return false;

    /* kv_iiu_scb: (i1 LS) & (i0 fu[8] & i0_late) — late BR/JAL + LS. */
    if (first->andesLatePath && first->staticInst->isControl() &&
        andesOpUsesLsu(second))
        return false;

    /* kv_dec id_ctrl[76]: short (|imm|<=8) branch/jump with ~pred_hit
     * cannot issue as i1 (ii_i1_stall |= ii_i1_ctrl[76]). */
    if (andesIsShortUnpredControl(second))
        return false;

    /* CSR / fence / system: single-issue (RTL ctrl[277] / ii_i0_singleissue). */
    if (andesOpForcesSingleIssue(first) || andesOpForcesSingleIssue(second))
        return false;

    /* DS168: DSP/ACE (3R/4R/2W) never dual-issues. */
    if (andesOpIsWideInt(first) || andesOpIsWideInt(second))
        return false;

    /* DS §22.3.2: same FP FU cannot pair (approx: any two FP arith). */
    if (andesOpUsesFpuArith(first) && andesOpUsesFpuArith(second))
        return false;

    /* DS168: Load/Store + MUL/DIV = Yes — do NOT block. */

    /* kv_iiu_scb: (ii_i1_fu[5] & ii_i0_fu[6]) | (ii_i1_fu[6] & ii_i0_fu[5])
     * FPU arith and MDU cannot dual-issue together. */
    if ((andesOpUsesFpuArith(first) && andesOpUsesMdu(second)) ||
        (andesOpUsesMdu(first) && andesOpUsesFpuArith(second)))
        return false;

    return true;
}

bool
andesSameCycleWAWAllowed(MinorDynInstPtr first, MinorDynInstPtr second,
    Scoreboard &scoreboard, ThreadContext *thread_context,
    const std::vector<bool> &cant_forward_from_fu_indices, Cycles now)
{
    if (!first || !second || first->isFault() || second->isFault())
        return true;

    StaticInstPtr a = first->staticInst;
    StaticInstPtr b = second->staticInst;
    const unsigned num_dests_a = a->numDestRegs();

    /* ii_i1_waw_hazard: same-cycle WAW. */
    for (unsigned di = 0; di < b->numDestRegs(); di++) {
        const RegId &dest_b = b->destRegIdx(di);
        if (dest_b.index() == 0 && dest_b.classValue() == IntRegClass)
            continue;

        for (unsigned ai = 0; ai < num_dests_a; ai++) {
            const RegId &dest_a = a->destRegIdx(ai);
            if (dest_a.index() == 0 && dest_a.classValue() == IntRegClass)
                continue;
            if (dest_a.classValue() == dest_b.classValue() &&
                dest_a.index() == dest_b.index())
                return false;
        }
    }

    /* Same-cycle RAW: default no i0→i1 (ii_i1_raw), except s251 pairs:
     * loadb→int (late) and early IntAlu→IntAlu (fu[0]/fu[1], both ~late). */
    for (unsigned si = 0; si < b->numSrcRegs(); si++) {
        const RegId &src_b = b->srcRegIdx(si);
        if (src_b.index() == 0 && src_b.classValue() == IntRegClass)
            continue;
        for (unsigned ai = 0; ai < num_dests_a; ai++) {
            const RegId &dest_a = a->destRegIdx(ai);
            if (dest_a.index() == 0 && dest_a.classValue() == IntRegClass)
                continue;
            if (dest_a.classValue() == src_b.classValue() &&
                dest_a.index() == src_b.index()) {
                if (andesSameCycleLateLoadUse(first, second) &&
                    dest_a.classValue() == IntRegClass)
                    continue;
                if (andesSameCycleEarlyIntForward(first, second) &&
                    dest_a.classValue() == IntRegClass) {
                    /* s251 requires ~ii_i1_late as well. */
                    if (andesSrcNeedsLatePath(scoreboard, second,
                            thread_context, cant_forward_from_fu_indices,
                            now))
                        return false;
                    continue;
                }
                if (andesSameCycleFpMisFmvToIntForward(first, second) &&
                    dest_a.classValue() == IntRegClass) {
                    if (andesSrcNeedsLatePath(scoreboard, second,
                            thread_context, cant_forward_from_fu_indices,
                            now))
                        return false;
                    continue;
                }
                return false;
            }
        }
    }

    return true;
}

bool
andesSameCycleLateLoadUse(MinorDynInstPtr first, MinorDynInstPtr second)
{
    if (!first || !second || first->isFault() || second->isFault())
        return false;
    if (!andesOpIsLoadbLoad(first))
        return false;
    StaticInstPtr b = second->staticInst;
    /* i1 may be IntAlu or branch (s251: fu[3]→fu[0]|fu[8]). */
    if (b->isMemRef() || andesOpUsesMdu(second))
        return false;
    if (!b->isInteger() && !b->isControl())
        return false;

    StaticInstPtr a = first->staticInst;
    for (unsigned si = 0; si < b->numSrcRegs(); si++) {
        const RegId &src_b = b->srcRegIdx(si);
        if (src_b.index() == 0 && src_b.classValue() == IntRegClass)
            continue;
        for (unsigned ai = 0; ai < a->numDestRegs(); ai++) {
            const RegId &dest_a = a->destRegIdx(ai);
            if (dest_a.classValue() == IntRegClass &&
                dest_a.index() == src_b.index() &&
                src_b.classValue() == IntRegClass)
                return true;
        }
    }
    return false;
}

bool
andesSameCycleEarlyIntForward(MinorDynInstPtr first, MinorDynInstPtr second)
{
    /* kv_iiu_scb s251: fu[0]/fu[1] early pairs; also fu[1]→BR (fu[8]).
     * All exceptions require ~ii_i0_late & ~ii_i1_late. */
    if (!first || !second || first->isFault() || second->isFault())
        return false;
    if (first->andesLatePath)
        return false;
    StaticInstPtr a = first->staticInst;
    StaticInstPtr b = second->staticInst;
    if (a->opClass() != enums::IntAlu)
        return false;
    if (a->isMemRef() || b->isMemRef())
        return false;
    if (andesOpUsesMdu(first) || andesOpUsesMdu(second))
        return false;
    /* i0 must not be a control (no JAL→use same-cycle). */
    if (a->isControl())
        return false;
    /* i1: IntAlu or branch/JAL class (fu[8]). */
    if (b->opClass() == enums::IntAlu && !b->isControl())
        return true;
    if (b->isControl() && b->isInteger())
        return true;
    return false;
}

bool
andesSameCycleFpMisFmvToIntForward(MinorDynInstPtr first,
    MinorDynInstPtr second)
{
    /* kv_iiu_scb s251: fu[16]/fu[17] → fu[0]|fu[8] (~bogus on i1 BR). */
    if (!first || !second || first->isFault() || second->isFault())
        return false;
    if (first->andesLatePath)
        return false;
    StaticInstPtr a = first->staticInst;
    StaticInstPtr b = second->staticInst;
    if (a->isMemRef() || b->isMemRef())
        return false;
    const OpClass aop = a->opClass();
    if (aop != enums::FloatMisc)
        return false;
    if (b->opClass() == enums::IntAlu && !b->isControl())
        return true;
    if (b->isControl() && b->isInteger())
        return true;
    return false;
}

bool
andesSrcNeedsLatePath(Scoreboard &scoreboard, MinorDynInstPtr inst,
    ThreadContext *thread_context,
    const std::vector<bool> &cant_forward_from_fu_indices, Cycles now)
{
    /* kv_iiu_scb: ~bypass[0] → ii_*_late (int or BR/JAL fu[8]).
     * Only while the bit0=0 producer still requires FU forward. After
     * returnCycle, RTL treats the value as past LX/WB → early OK. */
    if (!inst || inst->isFault() || inst->isBubble())
        return false;
    StaticInstPtr s = inst->staticInst;
    if (s->isMemRef() || andesOpUsesMdu(inst))
        return false;
    if (!s->isInteger() && !s->isControl())
        return false;
    if (cant_forward_from_fu_indices.empty())
        return false;

    auto *isa = thread_context->getIsaPtr();
    const unsigned num_srcs = s->numSrcRegs();
    for (unsigned src_index = 0; src_index < num_srcs; src_index++) {
        RegId reg = s->srcRegIdx(src_index).flatten(*isa);
        Scoreboard::Index index;
        if (!scoreboard.findIndex(reg, index))
            continue;
        if (scoreboard.numResults[index] == 0 &&
            scoreboard.numUnpredictableResults[index] == 0)
            continue;
        int src_fu = scoreboard.fuIndices[index];
        if (src_fu == Scoreboard::invalidFUIndex)
            continue;
        if (src_fu >= static_cast<int>(cant_forward_from_fu_indices.size()) ||
            !cant_forward_from_fu_indices[src_fu])
            continue;
        /* Still waiting on miss data → stay late-capable. */
        if (scoreboard.numUnpredictableResults[index] != 0)
            return true;
        /* Result already scoreboard-ready: no FU forward needed. */
        if (scoreboard.returnCycle[index] <= now)
            continue;
        return true;
    }
    return false;
}

bool
andesIntShouldUseLateFU(Scoreboard &scoreboard, MinorDynInstPtr inst,
    ThreadContext *thread_context,
    const std::vector<bool> &cant_forward_from_fu_indices, Cycles now)
{
    if (!inst || inst->isFault() || inst->isBubble())
        return false;
    StaticInstPtr s = inst->staticInst;
    if (!s->isInteger() || s->isMemRef() || andesOpUsesMdu(inst))
        return false;
    return andesSrcNeedsLatePath(scoreboard, inst, thread_context,
        cant_forward_from_fu_indices, now);
}

bool
andesBranchShouldUseLatePath(Scoreboard &scoreboard, MinorDynInstPtr inst,
    ThreadContext *thread_context,
    const std::vector<bool> &cant_forward_from_fu_indices, Cycles now)
{
    if (!inst || inst->isFault() || inst->isBubble())
        return false;
    StaticInstPtr s = inst->staticInst;
    if (!s->isControl())
        return false;
    return andesSrcNeedsLatePath(scoreboard, inst, thread_context,
        cant_forward_from_fu_indices, now);
}

} // namespace minor
} // namespace gem5
