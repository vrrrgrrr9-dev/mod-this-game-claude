"""Host (x86-64) shim for the mod's engine interface: every engine function declared in yyc.h becomes a
C function that forwards to a pointer the Python harness fills with a ctypes callback; every g_VAR_* /
g_FUNC_* in engine_vars.h becomes a YYVAR with a unique id.  usage: gen_shim.py <yyc.h> <engine_vars.h> <out.c> <out.json>"""
import json, re, sys

yyc, ev, out_c, out_j = sys.argv[1:5]
src = open(yyc).read()
block = src[src.index('/* ---- engine functions'):src.index('extern CInstance *g_pGlobal')]
block = re.sub(r'/\*.*?\*/', '', block, flags=re.S)
protos = [' '.join(p.split()) for p in block.split(';') if '(' in p]

def ctype(t):
    t = t.replace('const ', '').strip()
    if '*' in t: return 'p'
    return {'bool': 'b', 'double': 'd', 'int': 'i', 'float': 'f', 'void': 'v'}[t]

funcs, out = [], ['#include "yyc.h"', '#include <stdint.h>', '']
for p in protos:
    m = re.match(r'(.+?[\s\*])(\w+)\((.*)\)$', p.strip())
    ret, name, params = m.group(1).strip(), m.group(2), m.group(3)
    ps = [x.strip() for x in params.split(',')] if params.strip() else []
    names, types, decl = [], [], []
    for i, q in enumerate(ps):
        mm = re.match(r'(.*?)(\w+)$', q)
        t, n = mm.group(1).strip(), mm.group(2)
        names.append(n); types.append(ctype(t)); decl.append(t)
    funcs.append(dict(name=name, ret=ctype(ret), args=types))
    fp = f'{ret} (*)({", ".join(decl) or "void"})'
    call = f'(({fp})P_{name})({", ".join(names)})'
    out.append(f'void *P_{name};')
    out.append(f'{ret} {name}({params}) {{ {"return " if ret != "void" else ""}{call}; }}')
vars_ = re.findall(r'extern YYVAR (\w+);', open(ev).read())
out.append('CInstance *g_pGlobal; RValue g_undefinedRV;')
for i, v in enumerate(vars_):
    nm = v[6:] if v.startswith('g_VAR_') else v
    out.append(f'YYVAR {v} = {{ "{nm}", {100000 + i}, 0 }};')
out.append('void *host_memset(void *d, int c, unsigned long n);')
open(out_c, 'w').write('\n'.join(out) + '\n')
json.dump(dict(funcs=funcs, vars={(v[6:] if v.startswith('g_VAR_') else v): 100000 + i for i, v in enumerate(vars_)}),
          open(out_j, 'w'), indent=0)
print(len(funcs), 'functions,', len(vars_), 'vars')
