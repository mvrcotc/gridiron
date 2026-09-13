import csv, json, collections
import numpy as np
exec(open('model.py').read().split('# ------------------------------------------------- 1.')[0])
F=json.load(open('fit1.json')); BASE=F['base']; K=json.load(open('fit_k.json'))
BY=collections.defaultdict(list)
for p in P: BY[p['id']].append(p)
for v in BY.values(): v.sort(key=lambda x:x['w'])
POS={pid:v[0]['pos'] for pid,v in BY.items()}
TEAMS=sorted({p['tm'] for p in P})
TI={t:i for i,t in enumerate(TEAMS)}

# ------------------------------------ opponent adjustment (ridge, net of schedule)
rows=[r for r in P if r['tgt']>=1 and r['opp'] in TI and r['tm'] in TI]
n=len(rows); T=len(TEAMS)
X=np.zeros((n,2*T+1)); y=np.zeros(n); w=np.zeros(n)
for i,r in enumerate(rows):
    X[i,TI[r['tm']]]=1; X[i,T+TI[r['opp']]]=1; X[i,-1]=1
    y[i]=r['ry']/r['tgt']; w[i]=r['tgt']
lam=60.0
W=np.sqrt(w)[:,None]
A=X*W; b=y*np.sqrt(w)
reg=lam*np.eye(2*T+1); reg[-1,-1]=0
beta=np.linalg.solve(A.T@A+reg, A.T@b)
DEF={t: float(beta[T+TI[t]]-beta[T:2*T].mean()) for t in TEAMS}
OFF={t: float(beta[TI[t]]-beta[:T].mean()) for t in TEAMS}
raw=collections.defaultdict(lambda:[0.0,0.0])
for r in rows: raw[r['opp']][0]+=r['ry']; raw[r['opp']][1]+=r['tgt']
rawypt={t:(raw[t][0]/raw[t][1]) for t in raw if raw[t][1]>50}
lg=float(np.average(y,weights=w))
print('opponent adjustment (yards per target allowed, net of who they faced)\n')
srt=sorted(DEF.items(), key=lambda kv: kv[1])
print('  toughest 5:')
for t,v in srt[:5]:
    print(f'    {t:<4} adjusted {v:+.2f}   raw {rawypt.get(t,0)-lg:+.2f}   (rank moves {"" if abs(v-(rawypt.get(t,0)-lg))<.15 else "materially"})')
print('  softest 5:')
for t,v in srt[-5:]:
    print(f'    {t:<4} adjusted {v:+.2f}   raw {rawypt.get(t,0)-lg:+.2f}')
rawv=np.array([rawypt.get(t,lg)-lg for t in TEAMS]); adjv=np.array([DEF[t] for t in TEAMS])
print(f'\n  correlation raw vs adjusted: {np.corrcoef(rawv,adjv)[0,1]:.3f}')
print(f'  spread shrinks from {rawv.std():.2f} (raw) to {adjv.std():.2f} (adjusted) yds/tgt')
print('  -> raw allowed-stats overstate defensive spread; much of it is schedule.')

# dispersion of weekly targets around a player's own mean (for the simulation)
rs=[]
for pid,g in BY.items():
    tg=[x['tgt'] for x in g if x['tgt']>0]
    if len(tg)>=8:
        m=np.mean(tg); v=np.var(tg)
        if m>2: rs.append(v/m)
disp=float(np.median(rs))
print(f'\ntarget dispersion (variance/mean): {disp:.2f}  -> weekly volume is over-dispersed, '
      f'so targets are drawn from a negative binomial, not a Poisson')
json.dump({'DEF':DEF,'OFF':OFF,'lg_ypt':lg,'disp':disp},open('fit_opp.json','w'))
