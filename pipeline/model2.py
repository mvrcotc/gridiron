import csv, json, collections
import numpy as np
exec(open('model.py').read().split('# ------------------------------------------------- 1.')[0])
F=json.load(open('fit1.json')); BASE=F['base']

# ---------------------------------------------------------------- panel by player
BY=collections.defaultdict(list)
for p in P: BY[p['id']].append(p)
for v in BY.values(): v.sort(key=lambda x:x['w'])
POS={pid:v[0]['pos'] for pid,v in BY.items()}

def team_att(w,tm): return TW.get((w,tm),{}).get('att',0.0)

# ---- walk-forward search for the shrinkage constant that actually predicts best ----
def fit_k(stat, ks):
    """stat -> (numerator fn, denominator fn, prior fn). Returns best k by out-of-sample MSE."""
    num,den,prior=stat
    best=None
    for k in ks:
        se=n=0.0
        for pid,games in BY.items():
            pos=POS.get(pid)
            if pos not in BASE: continue
            pr=prior(pos)
            cn=cd=0.0
            for g in games:
                d=den(g)
                if cd>=8 and d>=2:                       # enough history, real sample this week
                    est=(cn+k*pr)/(cd+k)
                    act=num(g)/d
                    se+=(act-est)**2*d; n+=d
                cn+=num(g); cd+=d
        if n: 
            mse=se/n
            if best is None or mse<best[1]: best=(k,mse)
    return best

TS=(lambda g:g['tgt'], lambda g:team_att(g['w'],g['tm']), lambda pos:{'WR':.145,'TE':.115,'RB':.085}.get(pos,.12))
CR=(lambda g:g['rec'], lambda g:g['tgt'], lambda pos:BASE[pos]['cr'])
YP=(lambda g:g['ry'],  lambda g:g['tgt'], lambda pos:BASE[pos]['ypt'])

print('walk-forward search for shrinkage constants (lower MSE = better prediction):\n')
res={}
for name,stat,grid in [('target share',TS,[0,5,15,30,60,100,180,300,500]),
                       ('catch rate',  CR,[0,3,8,15,30,60,120,240]),
                       ('yards/target',YP,[0,3,8,15,30,60,120,240,400])]:
    k,mse=fit_k(stat,grid)
    res[name]=k
    print(f'  {name:<14} best k = {k:<5} (MSE {mse:.5f})')
    # show the cost of getting it wrong
    k0,m0=fit_k(stat,[0]); 
    print(f'  {"":14} k=0 (no regression) MSE {m0:.5f}  -> regression improves by {(m0-mse)/m0*100:.1f}%')
print()
print('Read: k is how many observations of league-average evidence to add before')
print('trusting a player. Target share needs the least, efficiency needs far more.')
json.dump(res,open('fit_k.json','w'))
