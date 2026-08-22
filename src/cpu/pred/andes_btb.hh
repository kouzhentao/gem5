/*
 * Andes AX45/46 BTB set indexing (kv_bpu_ctrl gf_hash_67).
 */

#ifndef __CPU_PRED_ANDES_BTB_HH__
#define __CPU_PRED_ANDES_BTB_HH__

#include "cpu/pred/btb_entry.hh"
#include "params/AndesBTBSetAssociative.hh"

namespace gem5
{

/**
 * kv_bpu_ctrl: s121 = PC[14:1]; set = gf_hash_67(s121) (7 bits @ 128 sets).
 */
class AndesBTBSetAssociative : public BTBSetAssociative
{
  public:
    PARAMS(AndesBTBSetAssociative);
    using KeyType = BTBTagType::KeyType;

    AndesBTBSetAssociative(const Params &p);

    std::vector<ReplaceableEntry *>
    getPossibleEntries(const KeyType &key) const override;

    Addr extractTag(const Addr addr) const override;

  private:
    const uint64_t andesTagMask;

    static uint32_t gfHash67(uint32_t addr);
};

} // namespace gem5

#endif // __CPU_PRED_ANDES_BTB_HH__
