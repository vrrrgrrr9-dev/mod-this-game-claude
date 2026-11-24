"""Add the o_jeff object (index 685, parent o_parent_character) to game.droid.

usage: droidpatch.py <game.droid in> <game.droid out>

GameMaker data files are full of absolute file offsets, so nothing is inserted in the middle:
* the OBJT pointer list grows by one entry into the dead bytes the Coco mod left after it (the
  old copy of object 0 that the mod relocated; verified unreferenced before writing);
* the new object struct, its name and its event lists are appended at the end of the file
  (inside the last chunk, AUDO, exactly where the mod put its own objects); FORM/AUDO sizes grow.

Event CodeIds index the YYC function table: 0xe65.. are Jeff's functions appended by
src/hooks.c (jeff_initllvm), the rest are reused original functions.
"""
import struct, sys

OBJ_PARENT_CHARACTER = 420
OBJ_PARENT_SOLID = 425
CODE = dict(create=0xe65, step=0xe66, draw=0xe67, draw64=0xe68, destroy=0xe69,
            alarm0=0xe6a, alarm2=0xe6b, alarm3=0xe6c,
            alarm4=3052,            # gml_Object_o_plr_erbitobkr_Alarm_4  (parent.can_attack = true)
            solid=3057)             # gml_Object_o_plr_erbitobkr_Collision_o_parent_solid
# event type -> [(subtype, code id)]   (0 create, 1 destroy, 2 alarm, 3 step, 4 collision, 8 draw)
EVENTS = {
    0: [(0, CODE['create'])],
    1: [(0, CODE['destroy'])],
    2: [(0, CODE['alarm0']), (2, CODE['alarm2']), (3, CODE['alarm3']), (4, CODE['alarm4'])],
    3: [(0, CODE['step'])],
    4: [(OBJ_PARENT_SOLID, CODE['solid'])],
    8: [(0, CODE['draw']), (64, CODE['draw64'])],
}
NAME = 'o_jeff'


def u32(d, o): return struct.unpack_from('<I', d, o)[0]


def chunks(d):
    out, p = {}, 8
    while p < len(d):
        out[d[p:p + 4].decode()] = (p + 8, u32(d, p + 4))
        p += 8 + u32(d, p + 4)
    return out


def main():
    src, dst = sys.argv[1:3]
    d = bytearray(open(src, 'rb').read())
    assert d[:4] == b'FORM'
    ch = chunks(d)
    objt, objt_sz = ch['OBJT']
    n = u32(d, objt)
    names = []
    for i in range(n):
        q = u32(d, objt + 4 + 4 * i); s = u32(d, q); names.append(d[s:s + u32(d, s - 4)].decode())
    if NAME in names:
        sys.exit('o_jeff already present')
    assert n == 685 and names[OBJ_PARENT_CHARACTER] == 'o_parent_character', 'unexpected game.droid'
    list_end = objt + 4 + 4 * n
    # the next 4 bytes must be unreferenced leftovers (no aligned u32 anywhere in the file points there)
    import array
    arr = array.array('I'); arr.frombytes(bytes(d[:len(d) // 4 * 4]))
    assert arr.count(list_end) == 0, 'slot after the object list is referenced'
    # template: copy the physics block of o_green_nature (a working mod character)
    tpl = u32(d, objt + 4 + 4 * names.index('o_green_nature'))
    phys = d[tpl + 9 * 4: tpl + 21 * 4]            # usesPhysics .. kinematic (12 dwords)

    audo, audo_sz = ch['AUDO']
    assert audo + audo_sz == len(d), 'AUDO is expected to be the last chunk'
    base = (len(d) + 3) & ~3
    blob = bytearray()

    def here(): return base + len(blob)

    def put(fmt, *v): blob.extend(struct.pack(fmt, *v))

    # name string: [len][bytes][0]; pointers point at the bytes
    put('<I', len(NAME)); name_ptr = here(); blob.extend(NAME.encode() + b'\0')
    while len(blob) % 4: blob.append(0)

    # actions + events first (so the object can point at them)
    type_lists = {}
    for etype, evs in EVENTS.items():
        ev_ptrs = []
        for sub, code in evs:
            act = here()
            put('<14i', 1, 603, 7, 0, 0, 0, 2, 0, code, 0, -1, 0, 0, 0)
            ev = here()
            put('<III', sub, 1, act)
            ev_ptrs.append(ev)
        lst = here()
        put('<I', len(ev_ptrs)); [put('<I', p) for p in ev_ptrs]
        type_lists[etype] = lst
    for etype in range(15):
        if etype not in type_lists:
            type_lists[etype] = here(); put('<I', 0)

    obj = here()
    put('<I', name_ptr)
    put('<iIIIiIiI', -1, 1, 1, 0, 0, 0, OBJ_PARENT_CHARACTER, 0xffffffff)   # sprite..mask
    blob.extend(phys)
    put('<I', 15); [put('<I', type_lists[t]) for t in range(15)]

    # write: grow the pointer list into the dead slot, append blob, fix sizes
    struct.pack_into('<I', d, objt, n + 1)
    struct.pack_into('<I', d, list_end, obj)
    d += b'\0' * (base - len(d))
    d += blob
    struct.pack_into('<I', d, audo - 4, len(d) - audo)
    struct.pack_into('<I', d, 4, len(d) - 8)
    open(dst, 'wb').write(d)
    print(f'o_jeff = object {n} at {obj:#x}; events', {k: [hex(c) for _, c in v] for k, v in EVENTS.items()})


if __name__ == '__main__':
    main()
