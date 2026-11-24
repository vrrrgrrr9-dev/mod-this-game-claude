import sys, struct, bisect, subprocess
L=sys.argv[1]
data=open(L,'rb').read()
# symbols
syms={}
out=subprocess.run(['nm','-D','--defined-only',L],capture_output=True,text=True).stdout
for l in out.splitlines():
    p=l.split()
    if len(p)==3 and p[1] in 'TtWw': syms[int(p[0],16)]=p[2]
addrs=sorted(syms)
INJ0,INJ1=0x3000000,0x305f7b9
# scan original text 0x8d0f90..0x1b8a350 + plt
hits=[]
for off in range(0x8d0f90,0x1bb8290,4):
    w=struct.unpack_from('<I',data,off)[0]
    if (w & 0x7c000000)==0x14000000:  # B / BL
        imm=w&0x3ffffff
        if imm&0x2000000: imm-=0x4000000
        t=off+imm*4
        if INJ0<=t<INJ1:
            i=bisect.bisect_right(addrs,off)-1
            hits.append((off, 'BL' if w>>31 else 'B', t, syms[addrs[i]] if i>=0 else '?', off-addrs[i]))
    elif (w & 0x9f000000)==0x90000000: # ADRP
        immlo=(w>>29)&3; immhi=(w>>5)&0x7ffff
        imm=(immhi<<2)|immlo
        if imm&(1<<20): imm-=1<<21
        t=(off&~0xfff)+(imm<<12)
        if INJ0<=t<0x3110000:
            i=bisect.bisect_right(addrs,off)-1
            hits.append((off,'ADRP',t,syms[addrs[i]],off-addrs[i]))
for h in hits: print(hex(h[0]),h[1],hex(h[2]),h[3][:110],'+'+hex(h[4]))
