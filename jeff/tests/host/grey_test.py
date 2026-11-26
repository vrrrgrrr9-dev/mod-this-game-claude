"""Grey's tests from tests/emu_test.py ([23]..[31]), run on the host build.
usage: grey_test.py <grey host .so> <gen dir> <emu_test.py>"""
import os, re, sys
so, gen, emu = sys.argv[1:4]
sys.argv = [sys.argv[0], so, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shim.json')]
from hostemu import *

DECOR = {}
for l in open(gen + '/stage_decor.h'):
    m_ = re.match(r'\s+(\d+),\s+/\* (\w+) \*/', l)
    if m_: DECOR[m_.group(2)] = int(m_.group(1))

print('[22] Grey: assets')
menu = new_inst(5)
call('grey_load_assets', menu.ptr)
ngr = len(sprites)
check(sum(1 for v in sounds.values() if str(v).startswith('grey_')) == 4, f'loaded {ngr} Grey sprites, 4 sounds')
foe = new_inst(1); enemy = new_inst(1)

src = open(emu).read()
body = src[src.index("print('[23] Grey: create + alarm0')"):src.index("print('\\nRESULT:'")]
exec(compile(body, emu + ' (Grey section)', 'exec'))
print('\nRESULT:', 'ALL PASSED' if not fails else f'{len(fails)} FAILED')
for f in fails: print('  -', f)
sys.exit(1 if fails else 0)
