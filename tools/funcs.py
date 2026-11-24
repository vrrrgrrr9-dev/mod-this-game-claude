import re,collections,sys
asm=open('inj.asm').read().splitlines()
L=[]
for l in asm:
    m=re.match(r'(0x[0-9a-f]+): (\S+)\s+(.*?)\s*(?:; (.*))?$',l)
    if m: L.append((int(m.group(1),16),m.group(2),m.group(3),m.group(4) or ''))
idx={a:i for i,(a,*_) in enumerate(L)}
starts={}
for l in open('patches.txt'):
    p=l.split()
    if p[1] in('B','BL'):
        t=int(p[2],16); n=re.sub(r'^_Z\d+','',p[3]); n=re.sub(r'P9CInstance.*|PKc.*|P9SLLVM.*','',n)
        starts.setdefault(t,set()).add(('hookB:' if p[1]=='B' else 'callBL:')+n)
for l in open(sys.argv[1]):  # regtab output
    p=l.split()
    if len(p)==3 and p[2].startswith('0x'): starts.setdefault(int(p[2],16),set()).add('event:'+p[1])
for a,op,s,c in L:
    if op=='bl' and s.startswith('#'):
        t=int(s[1:],16)
        if 0x3000000<=t<0x3056000: starts.setdefault(t,set())
    if op=='adr':
        t=int(s.split('#')[1],16)
        if 0x3000000<=t<0x3056000: starts.setdefault(t,set())
# prologue detection
for i,(a,op,s,c) in enumerate(L):
    if op=='stp' and s.startswith('x29, x30, [sp, #-') or (op=='sub' and s.startswith('sp, sp')) :
        if i>0 and L[i-1][1] in('ret','b','nop','udf','br'): starts.setdefault(a,set())
S=sorted(starts)
out=[]
for k,a in enumerate(S):
    e=S[k+1] if k+1<len(S) else 0x3056000
    if a not in idx: continue
    body=L[idx[a]:idx.get(e,len(L))]
    calls=collections.Counter(); strs=[]; tramp=None
    for _,op,s,c in body:
        if op in('bl','b','blr','br') and c and not c.startswith('[') : calls[c.replace('-> ','')]+=1
        for q in re.findall(r"'([^']+)'",c):
            if q not in strs: strs.append(q)
    out.append((a,e-a,sorted(starts[a]),calls,strs))
for a,sz,tags,calls,strs in out:
    print(f"== {a:#x} size={sz:#x} {' '.join(tags)}")
    if calls: print('   calls:',', '.join(f"{n}x{v}" if v>1 else n for n,v in calls.most_common(40)))
    if strs: print('   strs:',strs[:60])
