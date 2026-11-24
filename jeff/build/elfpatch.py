"""Inject Jeff's linked blob (jeff.elf) into libyoyo.so and wire the hooks.

usage: elfpatch.py <libyoyo.so in> <jeff.elf> <libyoyo.so out>

* appends the blob's two PT_LOAD segments (RX code at 0x3600000, RW data/bss at 0x3700000),
  16 KiB aligned like the rest of the library;
* moves the program header table into the reserved .phdrs area at the start of the RX segment
  (the old table has no room for two more entries) and updates PT_PHDR / e_phoff / e_phnum;
* patches four branches - each one is checked against the exact instruction the Coco mod put
  there, so an unexpected input file aborts instead of producing a broken library.
"""
import struct, subprocess, sys

PAGE = 0x4000
PT_LOAD, PT_PHDR = 1, 6
INJ_VA, INJ_OFF = 0x3000000, 0x1d20000          # the Coco mod's code segment


def read_phdrs(d):
    phoff, = struct.unpack_from('<Q', d, 0x20)
    phentsize, phnum = struct.unpack_from('<HH', d, 0x36)
    assert phentsize == 56
    return [list(struct.unpack_from('<IIQQQQQQ', d, phoff + i * 56)) for i in range(phnum)]


def va2off(phdrs, va):
    for p in phdrs:
        if p[0] == PT_LOAD and p[3] <= va < p[3] + p[5]:
            return va - p[3] + p[2]
    raise ValueError(hex(va))


def enc_b(pc, target, link=False):
    off = (target - pc) >> 2
    assert -(1 << 25) <= off < (1 << 25), 'branch out of range'
    return (0x94000000 if link else 0x14000000) | (off & 0x3ffffff)


def dec_b(w, pc):
    if (w & 0x7c000000) != 0x14000000:
        return None, None
    imm = w & 0x3ffffff
    if imm & 0x2000000:
        imm -= 0x4000000
    return pc + imm * 4, bool(w >> 31)


def symbols(elf):
    out = subprocess.run(['nm', elf], capture_output=True, text=True, check=True).stdout
    return {p[2]: int(p[0], 16) for p in (l.split() for l in out.splitlines()) if len(p) == 3}


def main():
    src, blob, dst = sys.argv[1:4]
    d = bytearray(open(src, 'rb').read())
    j = open(blob, 'rb').read()
    sym = symbols(blob)
    ph = read_phdrs(d)
    jph = [p for p in read_phdrs(j) if p[0] == PT_LOAD]
    assert len(jph) == 2, 'expected RX + RW segments in jeff.elf'
    rx, rw = jph
    for p in ph:
        if p[0] == PT_LOAD:
            assert not (p[3] < rw[3] + rw[5] and rx[3] < p[3] + p[5]), 'VA overlap with existing segment'

    # --- append segments -------------------------------------------------------------------
    def append_seg(seg):
        nonlocal d
        off = (len(d) + PAGE - 1) // PAGE * PAGE
        d += b'\0' * (off - len(d))
        filesz = seg[5]
        d += j[seg[2]:seg[2] + filesz]
        return off
    rx_off = append_seg(rx)
    rw_off = append_seg(rw)

    # --- new program header table -----------------------------------------------------------
    new = []
    last_load = max(i for i, p in enumerate(ph) if p[0] == PT_LOAD)
    for i, p in enumerate(ph):
        if p[0] == PT_PHDR:
            p = list(p)
            p[2], p[3], p[4] = rx_off, rx[3], rx[3]
            p[5] = p[6] = (len(ph) + 2) * 56
        new.append(p)
        if i == last_load:
            new.append([PT_LOAD, 5, rx_off, rx[3], rx[3], rx[5], rx[6], PAGE])
            new.append([PT_LOAD, 6, rw_off, rw[3], rw[3], rw[5], rw[6], PAGE])
    table = b''.join(struct.pack('<IIQQQQQQ', *p) for p in new)
    assert len(table) <= 0x400, 'reserved .phdrs area too small'
    d[rx_off:rx_off + len(table)] = table
    struct.pack_into('<Q', d, 0x20, rx_off)
    struct.pack_into('<H', d, 0x38, len(new))

    # --- hooks ------------------------------------------------------------------------------
    ph2 = [p for p in new]
    patches = [
        # (site VA, expected target, expected is_bl, new target symbol)
        (0x966ea0, 0x3000000, False, 'jeff_initllvm'),      # InitLLVM entry (mod hook)
        (0x13b89a0, 0x3044a70, False, 'jeff_get_char'),      # scr_menu_get_char entry (mod hook)
        (0x3043844, 0x3043880, True, 'jeff_charsel_ext'),    # mod charsel hook: 1st list rebuild
        (0x3043860, 0x3043880, True, 'jeff_charsel_ext'),    # mod charsel hook: 2nd list rebuild
    ]
    for va, exp, is_bl, name in patches:
        off = va2off(ph2, va)
        w, = struct.unpack_from('<I', d, off)
        tgt, bl = dec_b(w, va)
        if tgt != exp or bl != is_bl:
            sys.exit(f'unexpected instruction at {va:#x}: {w:#010x} (target {tgt}); is this the WOTU_COCO69 libyoyo.so?')
        struct.pack_into('<I', d, off, enc_b(va, sym[name], is_bl))
        print(f'patched {va:#x}: -> {name} @ {sym[name]:#x}')

    open(dst, 'wb').write(d)
    print(f'RX {rx[3]:#x} off {rx_off:#x} size {rx[5]:#x}; RW {rw[3]:#x} off {rw_off:#x} '
          f'filesz {rw[5]:#x} memsz {rw[6]:#x}; phnum {len(new)}; out {len(d)} bytes')


if __name__ == '__main__':
    main()
