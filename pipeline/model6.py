exec(open('model4.py').read().split("print('calibrating")[0])
import numpy as np, json, collections
CAL=json.load(open('fit_cal.json')); INFL=CAL['infl']
D=json.load(open('gi2.json'))

# who is on a depth chart, and what game are they in
GCTX={}
for gi,g in enumerate(D['games']):
    im=implied={'h':None,'a':None}
    if g.get('ou') is not None and g.get('spread') is not None:
        ou=float(g['ou']); sp=float(g['spread'])
        implied={'h':ou/2-sp/2,'a':ou/2+sp/2}
    # spread_line convention: g['spread'] is home-relative, negative = home favoured
    sp=float(g['spread']) if g.get('spread') is not None else 0.0
    GCTX[g['h']]={'opp':g['a'],'spread':sp,'gi':gi,'imp':implied['h'],'state':g.get('state')}
    GCTX[g['a']]={'opp':g['h'],'spread':-sp,'gi':gi,'imp':implied['a'],'state':g.get('state')}

want=set()
for t,v in D['depth'].items():
    for side in ('o','d'):
        for lst in v[side].values():
            for e in lst: want.add((e['g'],t))

QS=[2,5,10,20,25,30,40,50,60,70,75,80,85,90,95,98]
PROJ={}; skipped=0
for pid,team in want:
    ctx=GCTX.get(team)
    if not ctx or ctx.get('state')=='post': continue
    hist=BY.get(pid)
    pos=POS.get(pid)
    if not hist or pos not in BASE: skipped+=1; continue
    pj=project(pid,hist,ctx['spread'],ctx['opp'],pos)
    if not pj or (pj['tgt']+pj['car']+pj['pa'])<1.5: skipped+=1; continue
    s=simulate(pj,20000,INFL)
    def q(a,dec=1): return [round(float(x),dec) for x in np.percentile(a,QS)]
    rec={'med':round(float(np.median(s['pts'])),1),
         'flr':round(float(np.percentile(s['pts'],25)),1),
         'ceil':round(float(np.percentile(s['pts'],85)),1),
         'mean':round(float(s['pts'].mean()),1),
         'q':q(s['pts']),
         'x':{'tgt':round(pj['tgt'],1),'cr':round(pj['cr'],3),'ypt':round(pj['ypt'],2),
              'tdpt':round(pj['tdpt'],4),'car':round(pj['car'],1),'ypc':round(pj['ypc'],2),
              'adj':round(DEF.get(ctx['opp'],0.0),2),'n':round(pj['n'],0)}}
    if pj['tgt']>=1.5:
        rec['qry']=q(s['ry'],0); rec['qrec']=q(s['rec'],0)
        rec['xry']=round(pj['tgt']*pj['ypt'],1); rec['xrec']=round(pj['tgt']*pj['cr'],1)
    if pj['car']>=2:
        rec['qru']=q(s['ru'],0); rec['xru']=round(pj['car']*pj['ypc'],1)
    if pj['pa']>=10:
        rec['qpy']=q(s['py'],0); rec['xpy']=round(pj['py'],1)
    PROJ[pid]=rec

D['proj']=PROJ
D['cal']={'pit':CAL['pit'],'dev':round(CAL['dev'],3),'qs':QS,
          'k':{'ts':K['target share'],'cr':K['catch rate'],'ypt':K['yards/target']},
          'script':{'slope':round(SLOPE,5),'icept':round(ICEPT,4),'plays':round(PLAYS,1)},
          'def':{t:round(v,2) for t,v in DEF.items()},
          'base':{p:{k:round(v,4) for k,v in b.items()} for p,b in BASE.items()},
          'n':CAL.get('n',2301)}
json.dump(D,open('gi2.json','w'),separators=(',',':'))
print(f'projected {len(PROJ)} players (skipped {skipped} with no 2025 base or negligible role)')
print(f'bytes: {len(open("gi2.json").read()):,}\n')
top=sorted(PROJ.items(),key=lambda kv:-kv[1]['med'])[:12]
print(f'{"player":<24}{"floor":>7}{"median":>8}{"ceiling":>9}   projection built from')
print('-'*94)
for pid,r in top:
    n=D['players'][pid]['n']; x=r['x']
    src=f"{x['tgt']:.1f} tgt x {x['cr']*100:.0f}% x {x['ypt']:.2f} y/t"
    if x['car']>=2: src+=f" + {x['car']:.1f} car x {x['ypc']:.1f}"
    if x['adj']: src+=f"  [opp {x['adj']:+.2f}]"
    print(f'{n:<24}{r["flr"]:>7.1f}{r["med"]:>8.1f}{r["ceil"]:>9.1f}   {src}')
