"""Player projections in one pass: base model inputs -> weather -> injury redistribution -> simulate.
Adjustments change the model's INPUTS and every distribution is simulated afterwards, so count stats
stay whole numbers, and before/after comparisons share a per-player seed so noise cancels."""
import os, sys, json, hashlib
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
E2N={'LAR':'LA','WSH':'WAS'}; nf=lambda t:E2N.get(t,t)
def src(name,reps):
    s=open(os.path.join(HERE,name),encoding='utf-8').read()
    for a,b in reps:
        assert a in s,(name,a); s=s.replace(a,b)
    return s
PANEL=src('model.py',[("open('games_all.csv')","open(os.path.join(DATA,'games_all.csv'))"),
                      ("open('stw25.csv')","open(os.path.join(DATA,'stw25.csv'))")]).split('# ------------------------------------------------- 1.')[0]
exec(src('model4.py',[("exec(open('model.py').read().split('# ------------------------------------------------- 1.')[0])","exec(PANEL)"),
                      ("open('fit1.json')","open(os.path.join(HERE,'fit1.json'))"),("open('fit_k.json')","open(os.path.join(HERE,'fit_k.json'))"),
                      ("open('fit_opp.json')","open(os.path.join(HERE,'fit_opp.json'))")]).split("print('calibrating")[0])
INFL=json.load(open(os.path.join(HERE,'fit_cal.json')))['infl']; CAL=json.load(open(os.path.join(HERE,'fit_cal.json')))
WXF=json.load(open(os.path.join(HERE,'wxfit.json'))); CEN=json.load(open(os.path.join(HERE,'wxcentre.json'))); AB=json.load(open(os.path.join(HERE,'absorb.json')))
D=json.load(open(os.path.join(DATA,'gi2.json'))); PL=D['players']; IJ=D.get('injd',{})
LGW=(D.get('wxfit') or {}).get('lg') or dict(att=33.73,ypa=7.19,car=26.81,ypc=4.36)
OUT={'O','IR','D','PUP','NFI','SUSP'}; QS=[2,5,10,20,25,30,40,50,60,70,75,80,85,90,95,98]; N=20000

def wxmult(g):
    dome=1.0 if (g.get('indoor') or str(g.get('roof') or '').lower() in ('dome','closed')) else 0.0
    if dome: wind,temp=0.0,70.0
    else:
        wind=g.get('wsus') if g.get('wsus') is not None else g.get('rwind'); wind=float(wind or 0)
        temp=g.get('temp') if g.get('temp') not in (None,'') else g.get('rtemp'); temp=60.0 if temp in (None,'') else float(temp)
    w=max(0.0,wind-8.0); c=max(0.0,45.0-temp)/10.0
    d={k:WXF[k]['w']*(w-CEN['w'])+WXF[k]['c']*(c-CEN['c'])+WXF[k]['dome']*(dome-CEN['dome']) for k in ('att','ypa','car','ypc')}
    return {k:1+d[k]/LGW[k] for k in d}, dict(wind=round(wind,1),temp=round(temp),dome=bool(dome),**{'d_'+k:round(v,2) for k,v in d.items()})

GCTX={}; D['wx']={}
for g in D['games']:
    m,info=wxmult(g); D['wx'][g['id']]=dict(m={k:round(v,4) for k,v in m.items()},**info)
    sp=float(g['spread']) if g.get('spread') is not None else 0.0
    GCTX[g['h']]=dict(opp=g['a'],spread=sp,state=g.get('state'),m=m); GCTX[g['a']]=dict(opp=g['h'],spread=-sp,state=g.get('state'),m=m)
want=sorted({(e['g'],t) for t,v in D['depth'].items() if t in GCTX for s in ('o','d') for lst in v[s].values() for e in lst})

base={}; skipped=0
for pid,team in want:
    ctx=GCTX[team]; hist=BY.get(pid); pos=POS.get(pid)
    if ctx['state']=='post' or pid in base: continue
    if not hist or pos not in BASE: skipped+=1; continue
    pj=project(pid,hist,ctx['spread'],nf(ctx['opp']),pos)          # nflverse code: opponent adjustments are keyed LA / WAS
    if not pj or pj['tgt']+pj['car']+pj['pa']<1.5: skipped+=1; continue
    base[pid]=dict(team=team,pos=pos,pj=pj)

def weathered(pj,m):
    q=dict(pj); q['tgt']*=m['att']; q['ypt']*=m['ypa']; q['car']*=m['car']; q['ypc']*=m['ypc']
    q['pa']*=m['att']; q['py']*=m['att']*m['ypa']; q['ptd']*=m['att']; q['pint']*=m['att']; return q
for pid,b in base.items(): b['wx']=weathered(b['pj'],GCTX[b['team']]['m']); b['fin']=dict(b['wx']); b['dt']=b['dc']=0.0; b['who']=[]

REDIST={}
for team in sorted({b['team'] for b in base.values()}):
    ids=[p for p,b in base.items() if b['team']==team]
    outs=[p for p in ids if (IJ.get(p) or {}).get('s') in OUT]; live=[p for p in ids if p not in outs]
    if not outs or not live: continue
    ft=sum(base[p]['wx']['tgt'] for p in outs)*AB['tgt']; fc=sum(base[p]['wx']['car'] for p in outs)*AB['car']
    opos={base[p]['pos'] for p in outs}; wt={p:(1.0 if base[p]['pos'] in opos else 0.30) for p in live}; tw=sum(wt.values())
    backs=sorted([p for p in live if base[p]['pos']=='RB'],key=lambda p:-base[p]['wx']['car']); rw=[0.5,0.3,0.15,0.05][:len(backs)]
    for p in live:
        dt=ft*wt[p]/tw if tw else 0.0; dc=(fc*rw[backs.index(p)]/sum(rw)) if p in backs and rw else 0.0
        base[p]['fin']['tgt']+=dt; base[p]['fin']['car']+=dc; base[p]['dt']=dt; base[p]['dc']=dc
        base[p]['who']=[PL[o]['n'] for o in outs]
    REDIST[team]={'outs':outs,'live':live}

def sim(pid,pj):
    globals()['rng']=np.random.default_rng(int(hashlib.md5(pid.encode()).hexdigest()[:8],16))
    return simulate(pj,N,INFL)
q=lambda a,dec=1:[round(float(x),dec) for x in np.percentile(a,QS)]
PROJ={}
for pid,b in sorted(base.items()):
    s0=sim(pid,b['pj']); s1=sim(pid,b['wx']); fin=b['fin']; x=fin
    med0,med1=round(float(np.median(s0['pts'])),1),round(float(np.median(s1['pts'])),1)
    xrec={'tgt':round(x['tgt'],2),'cr':round(x['cr'],3),'ypt':round(x['ypt'],2),'tdpt':round(x['tdpt'],4),'car':round(x['car'],2),
          'ypc':round(x['ypc'],2),'adj':round(DEF.get(nf(GCTX[b['team']]['opp']),0.0),2),'n':round(x['n'],0)}
    if (IJ.get(pid) or {}).get('s') in OUT:
        PROJ[pid]={'med':0.0,'flr':0.0,'ceil':0.0,'mean':0.0,'q':[0.0]*16,'x':xrec,'out':IJ[pid]['s'],'med_if':med1}; continue
    s2=sim(pid,fin); r={'med':round(float(np.median(s2['pts'])),1),'flr':round(float(np.percentile(s2['pts'],25)),1),
        'ceil':round(float(np.percentile(s2['pts'],85)),1),'mean':round(float(s2['pts'].mean()),1),'q':q(s2['pts']),'x':xrec}
    if fin['tgt']>=1.5: r.update(qry=q(s2['ry'],0),qrec=q(s2['rec'],0),xry=round(fin['tgt']*fin['ypt'],1),xrec=round(fin['tgt']*fin['cr'],1))
    if fin['car']>=2: r.update(qru=q(s2['ru'],0),xru=round(fin['car']*fin['ypc'],1))
    if fin['pa']>=10: r.update(qpy=q(s2['py'],0),xpy=round(fin['py'],1))
    m0,m1,m2=float(s0['pts'].mean()),float(s1['pts'].mean()),float(s2['pts'].mean())
    if m0>0 and abs(m1/m0-1)>=0.004: r['wx']={'m':round(m1/m0,3),'b':med0,'a':med1}
    if b['dt']>0.02 or b['dc']>0.02: r['inj']={'m':round(m2/m1,3) if m1>0 else 1.0,'b':med1,'a':r['med'],'t':round(b['dt'],2),'c':round(b['dc'],2),'who':b['who']}
    PROJ[pid]=r
OUTREC={}
for team,v in REDIST.items():
    OUTREC[team]={'out':sorted([{'n':PL[p]['n'],'p':PL[p]['p'],'s':IJ[p]['s'],'med':PROJ[p]['med_if'],'tgt':round(base[p]['wx']['tgt'],1),
                                 'car':round(base[p]['wx']['car'],1)} for p in v['outs']],key=lambda o:-o['med']),
                  'to':sorted([{'n':PL[p]['n'],'p':PL[p]['p'],'b':PROJ[p]['inj']['b'],'a':PROJ[p]['inj']['a'],'t':PROJ[p]['inj']['t'],
                                'c':PROJ[p]['inj']['c']} for p in v['live'] if 'inj' in PROJ[p]],key=lambda m:-(m['a']-m['b']))}
D['proj']=PROJ; D['redist']={nf(t):v for t,v in OUTREC.items()}; D.pop('passes',None)
D['injrule']={'out':sorted(OUT),'note':'Players ruled Out, Doubtful or on IR are projected at zero and their volume is handed to teammates '
  'using rates measured on 2025 absences: receiving disperses across the position group, rushing concentrates on the next back. '
  'Only %d%% of lost targets and %d%% of lost carries are recovered at all — the rest is volume that simply never happens.'%(round(100*AB['tgt']),round(100*AB['car']))}
D['cal']={'pit':CAL['pit'],'dev':round(CAL.get('dev',0),3),'qs':QS,'k':{'ts':K['target share'],'cr':K['catch rate'],'ypt':K['yards/target']},
          'script':{'slope':round(SLOPE,5),'icept':round(ICEPT,4),'plays':round(PLAYS,1)},'def':{t:round(v,2) for t,v in DEF.items()},
          'base':{p:{k:round(v,4) for k,v in bb.items()} for p,bb in BASE.items()},'n':CAL.get('n',2301)}
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
fp=hashlib.md5(json.dumps(PROJ,sort_keys=True).encode()).hexdigest()[:12]
print('projected %d players (%d ruled out, %d skipped); injury fallout on %d teams; fingerprint %s'%(
    len(PROJ),sum(1 for v in PROJ.values() if v.get('out')),skipped,len(OUTREC),fp))
