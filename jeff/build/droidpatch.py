"""Add the o_jeff (685), o_scyther (686) and o_grey (687) objects (parent o_parent_character) to game.droid.

usage: droidpatch.py <game.droid in> <game.droid out>

GameMaker data files are full of absolute file offsets, so nothing is inserted in the middle:
* the OBJT pointer list grows by three entries into the dead bytes the Coco mod left after it (the
  old copy of object 0 that the mod relocated; both slots verified unreferenced before writing);
* the new object structs, names and event lists are appended at the end of the file (inside the
  last chunk, AUDO, exactly where the mod put its own objects); FORM/AUDO sizes grow.

Event CodeIds index the YYC function table: 0xe65.. are Jeff's, 0xe6d.. Scyther's, 0xe76.. Grey's functions
appended by src/hooks.c (jeff_initllvm); the rest are reused original functions.

Also carries the "shaderfix" (from the user's WOTU_Scyther_shaderfix.apk): the game's screen
distortion shader computes `0.05 / d` with d = min(0.25, dot(B,B)), which is 0 at the exact centre
of the effect; it is clamped to >= 0.01 instead. Same length, patched in place in the STRG chunk.
"""
import struct, sys

OBJ_PARENT_CHARACTER = 420
OBJ_PARENT_SOLID = 425
ALARM4 = 3052               # gml_Object_o_plr_erbitobkr_Alarm_4  (parent.can_attack = true)
SOLID = 3057                # gml_Object_o_plr_erbitobkr_Collision_o_parent_solid
# event type -> [(subtype, code id)]  (0 create, 1 destroy, 2 alarm, 3 step, 4 collision, 8 draw:
# subtype 0 = Draw, 64 = Draw GUI, 72 = Draw Begin)
OBJECTS = [
    ('o_jeff', {
        0: [(0, 0xe65)], 1: [(0, 0xe69)],
        2: [(0, 0xe6a), (2, 0xe6b), (3, 0xe6c), (4, ALARM4)],
        3: [(0, 0xe66)], 4: [(OBJ_PARENT_SOLID, SOLID)],
        8: [(0, 0xe67), (64, 0xe68)]}),
    ('o_scyther', {
        0: [(0, 0xe6d)], 1: [(0, 0xe72)],
        2: [(0, 0xe73), (2, 0xe74), (3, 0xe75), (4, ALARM4)],
        3: [(0, 0xe6e)], 4: [(OBJ_PARENT_SOLID, SOLID)],
        8: [(0, 0xe6f), (64, 0xe70), (72, 0xe71)]}),
    ('o_grey', {
        0: [(0, 0xe76)], 1: [(0, 0xe7a)],
        2: [(0, 0xe7b), (2, 0xe7c), (3, 0xe7d), (4, ALARM4)],
        3: [(0, 0xe77)], 4: [(OBJ_PARENT_SOLID, SOLID)],
        8: [(0, 0xe78), (64, 0xe79), (72, 0xe7e)]}),
]


SHADER_FIX = (b'min( 0.25, dot( B,B ) ', b'clamp(dot(B,B),.01,.25')


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
    for name, _ in OBJECTS:
        if name in names:
            sys.exit(f'{name} already present')
    assert n == 685 and names[OBJ_PARENT_CHARACTER] == 'o_parent_character', 'unexpected game.droid'
    list_end = objt + 4 + 4 * n
    # the next len(OBJECTS) slots must be unreferenced leftovers (no aligned u32 in the file points there)
    import array
    arr = array.array('I'); arr.frombytes(bytes(d[:len(d) // 4 * 4]))
    for k in range(len(OBJECTS)):
        assert arr.count(list_end + 4 * k) == 0, f'slot {k} after the object list is referenced'
    # template: copy the physics block of o_green_nature (a working mod character)
    tpl = u32(d, objt + 4 + 4 * names.index('o_green_nature'))
    phys = d[tpl + 9 * 4: tpl + 21 * 4]            # usesPhysics .. kinematic (12 dwords)

    audo, audo_sz = ch['AUDO']
    assert audo + audo_sz == len(d), 'AUDO is expected to be the last chunk'
    base = (len(d) + 3) & ~3
    blob = bytearray()

    def here(): return base + len(blob)

    def put(fmt, *v): blob.extend(struct.pack(fmt, *v))

    objs = []
    for name, events in OBJECTS:
        # name string: [len][bytes][0]; pointers point at the bytes
        put('<I', len(name)); name_ptr = here(); blob.extend(name.encode() + b'\0')
        while len(blob) % 4: blob.append(0)
        type_lists = {}
        for etype, evs in events.items():
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
        objs.append(obj)

    # the distortion shader's divide by zero (see the module docstring)
    strg, strg_sz = ch['STRG']
    old, new = SHADER_FIX
    assert len(old) == len(new)
    k = d.find(old, strg, strg + strg_sz)
    if k >= 0 and d.find(old, k + 1, strg + strg_sz) < 0:
        d[k:k + len(old)] = new
        print(f'shader fix applied at {k:#x}')
    else:
        print('shader fix: pattern not found exactly once, left as is')

    # write: grow the pointer list into the dead slots, append blob, fix sizes
    struct.pack_into('<I', d, objt, n + len(objs))
    for k, obj in enumerate(objs):
        struct.pack_into('<I', d, list_end + 4 * k, obj)
    d += b'\0' * (base - len(d))
    d += blob
    struct.pack_into('<I', d, audo - 4, len(d) - audo)
    struct.pack_into('<I', d, 4, len(d) - 8)
    open(dst, 'wb').write(d)
    for k, (name, events) in enumerate(OBJECTS):
        print(f'{name} = object {n + k} at {objs[k]:#x}; events', {t: [hex(c) for _, c in v] for t, v in events.items()})


if __name__ == '__main__':
    main()
