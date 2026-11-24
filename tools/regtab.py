import sys,re
lines=open(sys.argv[1]).read().splitlines()
start,end=int(sys.argv[2],16),int(sys.argv[3],16)
R={}; tab={}
fnptr={}  # from relocations listed in comments
for l in lines:
    m=re.match(r'(0x[0-9a-f]+): (\S+)\s+(.*?)\s*(?:; (.*))?$',l)
    if not m: continue
    a=int(m.group(1),16)
    if a<start or a>=end: continue
    op,ops,c=m.group(2),m.group(3).strip(),m.group(4)
    p=[x.strip() for x in ops.split(',')]
    def W(r): return 'x'+r[1:] if r[0] in 'wx' else r
    if op=='mov' and p[1].startswith('#'): R[W(p[0])]=int(p[1][1:],0)
    elif op=='movk':
        sh=int(p[2].split('#')[1]) if len(p)>2 else 0
        R[W(p[0])]=(R.get(W(p[0]),0) & ~(0xffff<<sh)) | (int(p[1][1:],0)<<sh)
    elif op=='add' and c and c.startswith("'"): R[W(p[0])]=('S',c.strip("'"))
    elif op=='adr': R[W(p[0])]=('F',int(p[1][1:],16))
    elif op=='ldr' and c and '->' in c: R[W(p[0])]=('F',int(c.split('->')[1],16)) if c.split('->')[1].startswith('0x') else ('S',c)
    elif op=='ldr' and p[1]=='[x9' : R[W(p[0])]=('ORIG',p[2])
    elif op=='str' and len(p)==3 and p[1]=='[x8' and p[2].endswith(']') and p[2][:-1] in R or (op=='str' and len(p)==3 and p[1]=='[x8'):
        k=W(p[2].rstrip(']'))
        off=R.get(k)
        v=0 if p[0] in('wzr','xzr') else R.get(W(p[0]),'?')
        tab[off]=v
ents={}
for off,v in tab.items():
    if not isinstance(off,int): continue
    i,f=divmod(off-0x15618,24)
    ents.setdefault(i,{})[f]=v
for i in sorted(ents):
    e=ents[i]; n=e.get(0); f=e.get(8)
    print(i+0xe41, n[1] if isinstance(n,tuple) else n, (hex(f[1]) if f and f[0]=='F' else f))
