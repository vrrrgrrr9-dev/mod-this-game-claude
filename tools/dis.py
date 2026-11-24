import sys, struct, bisect, subprocess, re, pickle, os
from capstone import *
L=sys.argv[1]; start=int(sys.argv[2],16); end=int(sys.argv[3],16)
data=open(L,'rb').read()
cache='syms.pkl'
if os.path.exists(cache): syms,relmap,strs=pickle.load(open(cache,'rb'))
else:
    syms={}
    out=subprocess.run(['nm','-D','--defined-only',L],capture_output=True,text=True).stdout
    for l in out.splitlines():
        p=l.split()
        if len(p)==3: syms[int(p[0],16)]=p[2]
    # PLT/GOT imports
    relmap={}
    out=subprocess.run(['readelf','-rW',L],capture_output=True,text=True).stdout
    for l in out.splitlines():
        p=l.split()
        if len(p)>=5 and ('JUMP_SLOT' in l or 'GLOB_DAT' in l or 'ABS64' in l):
            try: relmap[int(p[0],16)]=p[4]
            except: pass
        elif len(p)>=4 and 'RELATIVE' in l:
            try: relmap[int(p[0],16)]=('R',int(p[-1],16))
            except: pass
    strs=None
    pickle.dump((syms,relmap,strs),open(cache,'wb'))
addrs=sorted(syms)
def v2o(va):
    if va<0x1bb8290: return va
    if 0x1bbc290<=va<0x1c78d00: return va-0x4000
    if 0x1c7c8e0<=va<0x1d23750: return va-0x8000
    if 0x3000000<=va<0x305f7b9: return va-0x3000000+0x1d20000
    if 0x3060000<=va<0x3061910: return va-0x3060000+0x1d80000
    return None
def cstr(va):
    o=v2o(va)
    if o is None: return None
    e=data.find(b'\0',o,o+200)
    if e<0: return None
    s=data[o:e]
    if len(s)>=3 and all(32<=c<127 for c in s): return s.decode()
    return None
def name(t):
    if t in syms: return syms[t]
    i=bisect.bisect_right(addrs,t)-1
    if i>=0 and t-addrs[i]<0x4000 and t<0x3000000: return f"{syms[addrs[i]]}+{t-addrs[i]:#x}"
    return None
def dem(n):
    if not n: return n
    m=re.match(r'_Z(\d+)(\w+)',n)
    if m:
        k=int(m.group(1)); return m.group(2)[:k]+n[len(m.group(1))+2+k:][:0]
    return n
md=Cs(CS_ARCH_ARM64,CS_MODE_ARM); md.detail=False
o=v2o(start)
code=data[o:o+(end-start)]
regs={}
def W(r): return 'x'+r[1:] if r and r[0] in 'wx' and r[1:].isdigit() else r
def imm(t):
    t=t.strip().lstrip('#')
    return int(t,0)
def label(va):
    cs=cstr(va)
    if cs: return repr(cs)
    n=name(va)
    if n: return dem(n)
    r=relmap.get(va)
    if isinstance(r,str): return 'got:'+dem(r)
    return hex(va)
for ins in md.disasm(code,start):
    c=''
    op=ins.mnemonic; s=ins.op_str
    p=[x.strip() for x in s.split(',')]
    d=W(p[0]) if p else None
    try:
        if op in('bl','b') and s.startswith('#'):
            t=int(s[1:],16); n=name(t)
            if n: c=dem(n)
            elif 0x1b8a350<=t<0x1bb8290:
                po=v2o(t); ws=struct.unpack('<4I',data[po:po+16])
                immlo=(ws[0]>>29)&3; immhi=(ws[0]>>5)&0x7ffff; v=(immhi<<2)|immlo
                if v&(1<<20): v-=1<<21
                pg=(t&~0xfff)+(v<<12); imm12=((ws[1]>>10)&0xfff)*8
                c='plt:'+dem(str(relmap.get(pg+imm12)))
        elif op=='adrp': regs[d]=imm(p[1])
        elif op=='adr': regs[d]=imm(p[1]); c=label(regs[d])
        elif op=='mov' and p[1].startswith('#'): regs[d]=imm(p[1])
        elif op=='mov' and W(p[1]) in regs: regs[d]=regs[W(p[1])]
        elif op=='movk':
            sh=imm(p[2].split('#')[1]) if len(p)>2 else 0
            regs[d]=(regs.get(d,0)&~(0xffff<<sh))|(imm(p[1])<<sh)
        elif op in('add','sub') and len(p)>=3 and p[2].startswith('#') and W(p[1]) in regs:
            v=imm(p[2]); 
            if len(p)>3 and 'lsl #12' in p[3]: v<<=12
            regs[d]=regs[W(p[1])]+(v if op=='add' else -v)
            if 0x1000<regs[d]<0x3200000: c=label(regs[d])
        elif op in('add','sub') and len(p)>=3 and W(p[1]) in regs and W(p[2]) in regs:
            regs[d]=regs[W(p[1])]+(regs[W(p[2])] if op=='add' else -regs[W(p[2])])
            if 0x1000<regs[d]<0x3200000: c=label(regs[d])
        elif op in('ldr','ldrb','ldrh','ldrsw','ldur','str','strb','stur','strh') and len(p)>=2 and p[1].startswith('['):
            base=W(p[1].strip('[]!'))
            off=imm(p[2].strip(']!')) if len(p)>2 and p[2].strip(']!').startswith('#') else 0
            if base in regs:
                va=regs[base]+off
                r=relmap.get(va)
                if op=='ldr' and isinstance(r,tuple):
                    regs[d]=r[1]; c=f'[{va:#x}]->'+label(r[1])
                elif isinstance(r,str): c=f'[got:{dem(r)}]'; regs.pop(d,None)
                else:
                    c=f'[{label(va)}]'
                    if op.startswith('ld'): regs.pop(d,None)
            elif op.startswith('ld'): regs.pop(d,None)
        elif op in('blr','br') and d in regs: c='-> '+label(regs[d])
        elif op=='csel' and W(p[1]) in regs: regs[d]=regs[W(p[1])]
        elif d and d in regs and op not in('cmp','cmn','tst','cbz','cbnz','tbz','tbnz','str','stp','strb','fcmp','b.eq','b.ne'):
            regs.pop(d,None)
        if op in('bl','blr'):
            for r in ['x%d'%i for i in range(19)]: regs.pop(r,None)
    except Exception as e: c='?'
    print(f"{ins.address:#x}: {op:8s}{s:40s} {('; '+c) if c else ''}")
