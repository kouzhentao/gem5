/*
 * Andes AX46MPV 8-stage backend stage tags (II→EX→MM→LX→WB).
 * Phase A: tag in-flight producers; bypass/issue timing unchanged until Phase B.
 */

#ifndef __CPU_MINOR_ANDES_STAGE_HH__
#define __CPU_MINOR_ANDES_STAGE_HH__

#include <cstdint>

#include "base/refcnt.hh"

namespace gem5
{

namespace minor
{

class MinorDynInst;
typedef RefCountingPtr<MinorDynInst> MinorDynInstPtr;

/** RTL pipe stage where a producer first exposes bypass (§5.2). */
enum class AndesPipeStage : uint8_t
{
    II = 0,
    EX,
    MM,
    LX,
    WB
};

/** Per-in-flight-result metadata mirroring ii_ex_rd*_fu + ii_*_late. */
struct AndesStageTag
{
    AndesPipeStage bypassStage = AndesPipeStage::WB;
    bool late = false;
    int fuTag = -1;
    /** RTL ii_ex_rd*_fu[0]: 1 = EX bypass allowed for this producer. */
    bool exBypassBit0 = true;

    bool valid() const { return fuTag >= 0; }
};

const char *andesPipeStageName(AndesPipeStage s);

/** Map issued inst → producer bypass stage (ax46mpv_issue_hazard §8.1). */
AndesStageTag andesComputeProducerTag(const MinorDynInstPtr &inst);

} // namespace minor
} // namespace gem5

#endif /* __CPU_MINOR_ANDES_STAGE_HH__ */
