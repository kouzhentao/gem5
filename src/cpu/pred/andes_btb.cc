/*
 * Andes AX45/46 BTB set indexing (kv_bpu_ctrl gf_hash_67).
 */

#include "cpu/pred/andes_btb.hh"

#include "base/intmath.hh"

namespace gem5
{

AndesBTBSetAssociative::AndesBTBSetAssociative(const Params &p)
    : BTBSetAssociative(p), andesTagMask(mask(p.tag_bits))
{}

uint32_t
AndesBTBSetAssociative::gfHash67(uint32_t addr)
{
    auto b = [addr](unsigned i) { return (addr >> i) & 1u; };
    uint32_t h = 0;
    h |= (b(6) ^ b(9) ^ b(10) ^ b(11) ^ b(12) ^ b(13)) << 6;
    h |= (b(5) ^ b(8) ^ b(9) ^ b(10) ^ b(11) ^ b(12) ^ b(13)) << 5;
    h |= (b(4) ^ b(7) ^ b(8) ^ b(9) ^ b(10) ^ b(11) ^ b(12) ^ b(13)) << 4;
    h |= (b(3) ^ b(7) ^ b(8) ^ b(13)) << 3;
    h |= (b(2) ^ b(7) ^ b(9) ^ b(10) ^ b(11)) << 2;
    h |= (b(1) ^ b(8) ^ b(11) ^ b(12) ^ b(13)) << 1;
    h |= (b(0) ^ b(7) ^ b(10) ^ b(11) ^ b(12) ^ b(13));
    return h;
}

std::vector<ReplaceableEntry *>
AndesBTBSetAssociative::getPossibleEntries(const KeyType &key) const
{
    const uint32_t set_idx = gfHash67((key.address >> 1) & 0x3fff) & setMask;
    assert(set_idx < sets.size());
    return sets[set_idx];
}

Addr
AndesBTBSetAssociative::extractTag(const Addr addr) const
{
    return (addr >> 1) & andesTagMask;
}

} // namespace gem5
