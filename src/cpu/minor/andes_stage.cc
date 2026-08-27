/*
 * Andes AX46MPV 8-stage producer tag computation.
 */

#include "cpu/minor/andes_stage.hh"

#include "cpu/minor/dyn_inst.hh"
#include "enums/OpClass.hh"

namespace gem5
{

namespace minor
{

const char *
andesPipeStageName(AndesPipeStage s)
{
    switch (s) {
      case AndesPipeStage::II: return "II";
      case AndesPipeStage::EX: return "EX";
      case AndesPipeStage::MM: return "MM";
      case AndesPipeStage::LX: return "LX";
      case AndesPipeStage::WB: return "WB";
      default: return "?";
    }
}

AndesStageTag
andesComputeProducerTag(const MinorDynInstPtr &inst)
{
    AndesStageTag t;
    if (!inst || inst->isFault() || inst->isBubble())
        return t;

    t.fuTag = static_cast<int>(inst->fuIndex);
    t.late = inst->andesLatePath;

    switch (inst->fuIndex) {
      case 0:
      case 1: /* IntEarly alu0/1 */
        if (inst->andesLatePath) {
            t.bypassStage = AndesPipeStage::LX;
            t.late = true;
            t.exBypassBit0 = false;
        } else {
            t.bypassStage = AndesPipeStage::EX;
            t.exBypassBit0 = true;
        }
        break;
      case 2:
      case 3: /* IntLate alu2/3 */
        t.bypassStage = AndesPipeStage::LX;
        t.late = true;
        t.exBypassBit0 = false;
        break;
      case 4: /* MDU */
        t.bypassStage = AndesPipeStage::MM;
        t.exBypassBit0 = false;
        break;
      case 5: /* FP */
        if (inst->staticInst->opClass() == enums::FloatMisc) {
            t.bypassStage = AndesPipeStage::EX;
            t.exBypassBit0 = true;
        } else {
            t.bypassStage = AndesPipeStage::MM;
            t.exBypassBit0 = false;
        }
        break;
      case 6: /* Pred / BRU early or late */
        if (inst->andesLatePath) {
            t.bypassStage = AndesPipeStage::LX;
            t.late = true;
            t.exBypassBit0 = false;
        } else {
            t.bypassStage = AndesPipeStage::EX;
            t.exBypassBit0 = true;
        }
        break;
      case 7: /* Mem */
        t.bypassStage = AndesPipeStage::MM;
        t.exBypassBit0 = false;
        break;
      case 8: /* Misc / CSR */
        t.bypassStage = AndesPipeStage::LX;
        t.exBypassBit0 = false;
        break;
      default:
        t.bypassStage = AndesPipeStage::WB;
        t.fuTag = -1;
        break;
    }
    return t;
}

} // namespace minor
} // namespace gem5
