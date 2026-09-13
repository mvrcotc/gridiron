import json,math,os,sys
HERE=os.path.dirname(os.path.abspath(__file__))
DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
D=json.load(open(os.path.join(DATA,'gi2.json')))
import hashlib
def _sig(p): return hashlib.md5(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
_ps=D.get('passes') or []
if _ps and isinstance(_ps[-1],dict) and _ps[-1].get('after')==_sig(D['proj']):
    _done=[x.get('p') for x in _ps if isinstance(x,dict)]
else:
    _done=[]; D['passes']=[]      # projections were regenerated since the last pass: start clean
if 'inj' in _done:
    print('inj pass already applied to this exact projection set -- skipped, it would compound'); sys.exit(0)
PJ,PL,IJ=D['proj'],D['players'],D.get('injd',{})
OUT={'O','IR','D','PUP','NFI','SUSP'}          # will not take the field
# weights derived from the 2025 backfill study (m/backfill.json):
# receiving volume disperses broadly, rushing volume concentrates on the next back.
W_SAME, W_OTHER = 1.0, 0.30
W_RUSH = [0.50, 0.30, 0.15, 0.05]
# measured on 2025: teammates with an established role recover only part of the missing
# volume -- the rest is plays that never happen, or leak to players too marginal to project.
AB=json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'absorb.json')))
ABS_T, ABS_C = AB['tgt'], AB['car']

byteam={}
for g,p in PJ.items():
    pl=PL.get(g)
    if pl and pl.get('t'): byteam.setdefault(pl['t'],[]).append(g)

def val(p):
    x=p.get('x') or {}
    return dict(tgt=x.get('tgt',0.0) or 0.0, car=x.get('car',0.0) or 0.0)

REDIST={}
sat_out=[]
for team,ids in byteam.items():
    outs=[g for g in ids if (IJ.get(g) or {}).get('s') in OUT]
    if not outs: continue
    live=[g for g in ids if g not in outs]
    if not live: continue
    free_t=sum(val(PJ[g])['tgt'] for g in outs)*ABS_T
    free_c=sum(val(PJ[g])['car'] for g in outs)*ABS_C
    for g in outs:
        p=PJ[g]
        sat_out.append((PL[g]['n'],PL[g]['p'],team,p.get('med'),(IJ.get(g) or {}).get('s')))
        p['out']=(IJ.get(g) or {}).get('s')
        p['med_if']=p.get('med')                 # keep what he'd have been worth
        for k in ('med','mean','flr','ceil'):
            if p.get(k) is not None: p[k]=0.0
        for k in ('q','qry','qrec','qru'):
            if isinstance(p.get(k),list): p[k]=[0.0 for _ in p[k]]
        for k in ('xry','xrec','xru'):
            if p.get(k) is not None: p[k]=0.0
    gains={}
    # --- targets: broad, weighted by position group ---
    if free_t>0.05:
        outpos={PL[g]['p'] for g in outs}
        wts={g:(W_SAME if PL[g]['p'] in outpos else W_OTHER) for g in live}
        tot=sum(wts.values())
        for g in live:
            if tot>0: gains.setdefault(g,{})['tgt']=free_t*wts[g]/tot
    # --- carries: concentrated on the next backs ---
    if free_c>0.05:
        backs=sorted([g for g in live if PL[g]['p'] in ('RB','FB')],
                     key=lambda g:-val(PJ[g])['car'])
        if backs:
            ws=[W_RUSH[i] if i<len(W_RUSH) else 0.0 for i in range(len(backs))]
            s=sum(ws) or 1.0
            for i,g in enumerate(backs):
                gains.setdefault(g,{})['car']=free_c*ws[i]/s
    moved=[]
    for g,d in gains.items():
        p=PJ[g]; x=p.get('x') or {}
        t0=x.get('tgt',0.0) or 0.0; c0=x.get('car',0.0) or 0.0
        cr=x.get('cr',0.0) or 0.0; ypt=x.get('ypt',0.0) or 0.0; ypc=x.get('ypc',0.0) or 0.0
        dt=d.get('tgt',0.0); dc=d.get('car',0.0)
        if dt<=0.02 and dc<=0.02: continue
        base_med=p.get('med')
        v0=0.1*(t0*cr*ypt)+1.0*(t0*cr)+0.1*(c0*ypc)
        v1=0.1*((t0+dt)*cr*ypt)+1.0*((t0+dt)*cr)+0.1*((c0+dc)*ypc)
        mb=(v1/v0) if v0>1e-9 else 1.0
        m_t=(t0+dt)/t0 if t0>1e-9 else (1.0 if dt<=0 else 2.0)
        m_c=(c0+dc)/c0 if c0>1e-9 else (1.0 if dc<=0 else 2.0)
        if 'tgt' in x: x['tgt']=round(t0+dt,2)
        if 'car' in x: x['car']=round(c0+dc,2)
        if p.get('xry')  is not None: p['xry']=round(p['xry']*m_t,1)
        if p.get('xrec') is not None: p['xrec']=round(p['xrec']*m_t,1)
        if p.get('xru')  is not None: p['xru']=round(p['xru']*m_c,1)
        for k,m in (('qry',m_t),('qrec',m_t),('qru',m_c)):
            if isinstance(p.get(k),list): p[k]=[round(v*m,1) for v in p[k]]
        for k in ('med','mean','flr','ceil'):
            if p.get(k) is not None: p[k]=round(p[k]*mb,1)
        if isinstance(p.get('q'),list): p['q']=[round(v*mb,1) for v in p['q']]
        p['inj']=dict(m=round(mb,3), b=base_med,
                      t=round(dt,2), c=round(dc,2),
                      who=[PL[o]['n'] for o in outs])
        moved.append((PL[g]['n'],PL[g]['p'],base_med,p['med'],round(dt,1),round(dc,1)))
    REDIST[team]=dict(out=sorted([dict(n=PL[o]['n'],p=PL[o]['p'],s=(IJ.get(o) or {}).get('s'),
                               med=PJ[o].get('med_if'),tgt=round(val(PJ[o])['tgt'],1),
                               car=round(val(PJ[o])['car'],1)) for o in outs],
                               key=lambda o:-(o['med'] or 0)),
                      to=[dict(n=m[0],p=m[1],b=m[2],a=m[3],t=m[4],c=m[5]) for m in
                          sorted(moved,key=lambda m:-(m[3]-m[2]))])
D['redist']=REDIST
D['injrule']=dict(out=sorted(OUT),
  note='Players ruled Out, Doubtful or on IR are projected at zero and their volume is handed to '
       'teammates using rates measured on 332 target absences and 156 carry absences in 2025: '
       'receiving disperses across the position group, rushing concentrates on the next back. '
       'Only %d%% of lost targets and %d%% of lost carries are recovered at all \u2014 the rest is volume '
       'that simply never happens.'%(round(ABS_T*100),round(ABS_C*100)))
D.setdefault('passes',[]).append({'p':'inj','after':_sig(D['proj'])})
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('teams with a ruled-out starter: %d'%len(REDIST))
print()
print('%-22s %-4s %-4s %8s %s'%('RULED OUT','pos','tm','was','status'))
for n,p,t,m,s in sorted(sat_out,key=lambda r:-(r[3] or 0)):
    if (m or 0)>0: print('%-22s %-4s %-4s %8.1f %s'%(n[:22],p,t,m,s))
print()
print('%-22s %-4s %8s %8s %7s %7s'%('VOLUME MOVED TO','pos','before','after','+tgt','+car'))
for t,v in REDIST.items():
    for m in v['to'][:3]:
        if m['a']-m['b']<0.15: continue
        print('%-22s %-4s %8.1f %8.1f %7.1f %7.1f   (%s out)'%(m['n'][:22],m['p'],m['b'],m['a'],m['t'],m['c'],', '.join(v['out'][0]['n'].split()[-1:])))
