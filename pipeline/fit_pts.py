import csv,math,json,os
HERE=os.path.dirname(os.path.abspath(__file__))
DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
from collections import defaultdict

# --- team-week offensive aggregates from player weekly stats (2025) ---
agg=defaultdict(lambda: dict(py=0.0,ry=0.0,ptd=0.0,rtd=0.0,att=0.0,car=0.0,ints=0.0,sk=0.0,fl=0.0))
with open(os.path.join(DATA,'stw25.csv')) as f:
    for r in csv.DictReader(f):
        if r['season_type']!='REG': continue
        k=(r['game_id'],r['team'])
        a=agg[k]
        def n(x):
            v=r.get(x,'') or '0'
            try: return float(v)
            except: return 0.0
        a['py']+=n('passing_yards'); a['ry']+=n('rushing_yards')
        a['ptd']+=n('passing_tds');  a['rtd']+=n('rushing_tds')
        a['att']+=n('attempts');     a['car']+=n('carries')
        a['ints']+=n('passing_interceptions')
        a['sk']+=n('sacks_suffered')
        a['fl']+=n('rushing_fumbles_lost')+n('receiving_fumbles_lost')+n('sack_fumbles_lost')

games={}
with open(os.path.join(DATA,'games_all.csv')) as f:
    for r in csv.DictReader(f):
        if r['season']!='2025' or r['game_type']!='REG': continue
        if not r['home_score']: continue
        games[r['game_id']]=r

rows=[]
for gid,g in games.items():
    for side in ('home','away'):
        t=g[side+'_team']; k=(gid,t)
        if k not in agg: continue
        a=agg[k]
        rows.append(dict(gid=gid,week=int(g['week']),team=t,
            opp=g[('away' if side=='home' else 'home')+'_team'],
            home=1 if side=='home' else 0,
            pts=float(g[side+'_score']),
            yds=a['py']+a['ry'], td=a['ptd']+a['rtd'],
            to=a['ints']+a['fl'], plays=a['att']+a['car']+a['sk']))

print('team-games:',len(rows))

# --- OLS: pts ~ 1 + yds + td  (and a variant adding turnovers) ---
def ols(rows,cols,y='pts'):
    n=len(rows); p=len(cols)+1
    X=[[1.0]+[r[c] for c in cols] for r in rows]
    Y=[r[y] for r in rows]
    XtX=[[sum(X[i][a]*X[i][b] for i in range(n)) for b in range(p)] for a in range(p)]
    XtY=[sum(X[i][a]*Y[i] for i in range(n)) for a in range(p)]
    # gaussian elim
    M=[XtX[i][:]+[XtY[i]] for i in range(p)]
    for c in range(p):
        piv=max(range(c,p),key=lambda r:abs(M[r][c])); M[c],M[piv]=M[piv],M[c]
        d=M[c][c]
        for j in range(c,p+1): M[c][j]/=d
        for r2 in range(p):
            if r2==c: continue
            f=M[r2][c]
            for j in range(c,p+1): M[r2][j]-=f*M[c][j]
    b=[M[i][p] for i in range(p)]
    yb=sum(Y)/n
    sst=sum((v-yb)**2 for v in Y)
    res=[Y[i]-sum(b[a]*X[i][a] for a in range(p)) for i in range(n)]
    sse=sum(v*v for v in res)
    mae=sum(abs(v) for v in res)/n
    return b, 1-sse/sst, math.sqrt(sse/n), mae

for cols in (['yds','td'],['yds','td','to'],['yds','td','to','home']):
    b,r2,rmse,mae=ols(rows,cols)
    print(' + '.join(cols).ljust(24),
          'R2=%.3f RMSE=%.2f MAE=%.2f'%(r2,rmse,mae),
          ' coef: int=%.2f '%b[0]+' '.join('%s=%.4f'%(c,b[i+1]) for i,c in enumerate(cols)))

b,r2,rmse,mae=ols(rows,['yds','td','to'])
json.dump(dict(b0=b[0],byds=b[1],btd=b[2],bto=b[3],r2=r2,rmse=rmse),
          open(os.path.join(HERE,'ptsfit.json'),'w'),indent=1)

ly=sum(r['yds'] for r in rows)/len(rows); lt=sum(r['td'] for r in rows)/len(rows)
lp=sum(r['pts'] for r in rows)/len(rows); lo=sum(r['to'] for r in rows)/len(rows)
lpl=sum(r['plays'] for r in rows)/len(rows)
print('league/game: yds=%.1f td=%.2f to=%.2f pts=%.2f plays=%.1f'%(ly,lt,lo,lp,lpl))
json.dump(dict(yds=ly,td=lt,to=lo,pts=lp,plays=lpl),
          open(os.path.join(HERE,'lgavg.json'),'w'),indent=1)
