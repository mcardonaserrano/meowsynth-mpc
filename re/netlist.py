import parse_se as P, sys, json
r=P.run(1, verbose=False)
O=r.objs
plug_owner={}
for i,d in O.items():
    if 'plugs' in d:
        for k,p in enumerate(d['plugs']):
            if p is not None: plug_owner[p]=(i,k)
def mname(i):
    d=O[i]; return '%s#%x'%(d['name'] or d['type'],i)
def pname(p):
    d=O[p]
    own=plug_owner.get(p)
    nm=d.get('name','')
    return '%s.%s[%s]'%(mname(own[0]) if own else '?', own[1] if own else '?', nm) if True else ''
def other_ends(p):
    out=[]
    for l in O[p]['lines']:
        L=O[l]; q=L['to'] if L['from']==p else L['from']
        out.append(('->' if L['from']==p else '<-')+pname(q))
    return out
def dump(ci,ind=0):
    c=O[ci]; pad='  '*ind
    print('%s=== CONTAINER %s (#%x) rect %s'%(pad,c['name'],ci,c['rect']))
    for k,p in enumerate(c['plugs']):
        d=O[p]
        if d['lines'] or d['cls']=='CPlugIO2':
            print('%s  cplug %d %s "%s" def=%r partner=%s : %s'%(pad,k,d['cls'],d.get('name',''),d['default'],d.get('partner'),' '.join(other_ends(p))))
    pm=O[c['pm']] if c['pm'] else {'names':{},'params':[]}
    if pm['names'] or pm['params']: print(pad,' PM names',pm['names'], 'nparams',len(pm['params']))
    for ch in c['children']:
        d=O[ch]
        if d['cls']=='CLine2': continue
        if d['cls']=='CContainer': dump(ch,ind+1); continue
        extra=''
        if 'vals' in d: extra=' vals[0:6]=%s handle=%d'%([round(v,4) for v in d['vals'][:6]],d['handle'])
        print('%s- %s <%s/%s> #%x rect %s%s'%(pad,d['name'],d['cls'],d['type'],ch,d['rect'],extra))
        for k,p in enumerate(d['plugs']):
            q=O[p]
            nm=q.get('name','')
            ends=other_ends(p)
            lst=q.get('list','')
            print('%s    %d%s def=%r%s %s'%(pad,k,(' "%s"'%nm) if nm else '',q['default'],(' list=%r'%lst) if lst else '',' '.join(ends)))
if __name__=='__main__':
    root=min(i for i,d in O.items() if d['cls']=='CContainer')
    dump(root)
