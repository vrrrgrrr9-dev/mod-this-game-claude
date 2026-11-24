import sys,re,struct
a0,a1=int(sys.argv[1],16),int(sys.argv[2],16)
R={};pend=None;out=[]
for l in open('inj.asm'):
    m=re.match(r'(0x[0-9a-f]+): (\S+)\s+(.*?)\s*(?:; (.*))?$',l)
    if not m: continue
    a=int(m.group(1),16)
    if not a0<=a<a1: continue
    op,s,c=m.group(2),m.group(3),m.group(4) or ''
    p=[x.strip() for x in s.split(',')]
    if op=='mov' and p[0][0]=='x' and p[1].startswith('#'): R[p[0]]=int(p[1][1:],0)&0xffffffffffffffff
    elif op=='movk' and p[0] in R:
        sh=int(p[2].split('#')[1]) if len(p)>2 else 0; R[p[0]]=(R[p[0]]&~(0xffff<<sh))|(int(p[1][1:],0)<<sh)
    elif op=='stp' and p[1]=='xzr' and p[0] in R: pend=struct.unpack('<d',struct.pack('<Q',R[p[0]]))[0]
    elif op=='stp' and p[0]=='xzr' and p[1]=='xzr': pend=0.0
    elif "'" in c and op=='add': pend=c
    m2=re.search(r'\[g_VAR_(\w+)\+0x8\]',c)
    if m2 and op=='ldr':
        out.append(f"{m2.group(1)}={pend if pend is not None else '?'}"); pend=None
print(', '.join(out))
