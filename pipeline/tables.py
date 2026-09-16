"""Player-model tables fitted on one finished season: positional baselines (catch rate, yards and air yards per target by
position group), the touchdown-per-target curve by depth of target, the game-script line (pass rate by spread) with plays
per game, and each defence's pass-yards-per-target adjustment (ridge regression, net of the offences it faced).

A season is always projected with the tables of the season before it, so no projection -- on the live page or in the
learning loop's walk-forward tests -- uses tables built from games that had not been played yet. Pooling several seasons
was tested on 2023-25 player-weeks and did worse (mean miss 4.570 previous season, 4.585 three seasons, 4.598 every season
since 2016), so each file holds one season.

   python3 pipeline/tables.py                 fit every missing season from 2019 through last season
   python3 pipeline/tables.py --refit 2025    refit named seasons"""
import os, sys, csv, json, sqlite3, datetime
from collections import defaultdict
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
TDIR=os.path.join(HERE,'tables'); DB=os.path.join(DATA,'history','history.sqlite')
POS=('RB','TE','WR'); BINS=((0,5),(5,9),(9,13),(13,100)); LAM=60.0; FIRST=2019
COLS=['position_group','season','week','team','opponent_team','targets','receptions','receiving_yards','receiving_tds','receiving_air_yards','attempts','carries']

def season_now():
    t=datetime.date.today(); return t.year if t.month>=3 else t.year-1
def fl(v):
    try: return float(v or 0)
    except (TypeError,ValueError): return 0.0
def path(season): return os.path.join(TDIR,'%d.json'%season)

def rows_for(season):
    """regular-season player weeks: the nflverse weekly CSV the refresh keeps, else the history database"""
    p=os.path.join(DATA,'stw%02d.csv'%(season%100))
    if os.path.exists(p):
        rs=[r for r in csv.DictReader(open(p,encoding='utf-8')) if r.get('season_type')=='REG' and str(r.get('season'))==str(season)]
        if rs: return rs,'stw%02d.csv'%(season%100)
    if os.path.exists(DB):
        con=sqlite3.connect(DB)
        rs=[dict(zip(COLS,r)) for r in con.execute("SELECT %s FROM player_week WHERE season=? AND season_type='REG'"%','.join(COLS),(season,))]
        con.close()
        if rs: return rs,'history database'
    return [],None

def fit(season):
    rows,src=rows_for(season); SP={}
    for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'),encoding='utf-8')):
        if r['game_type']!='REG' or int(r['season'])!=season or r['spread_line'] in ('','NA'): continue
        sp=float(r['spread_line']); w=int(r['week']); SP[(w,r['home_team'])]=-sp; SP[(w,r['away_team'])]=sp      # from each team's side: positive = underdog
    if not rows or not SP: return None
    TW=defaultdict(lambda:[0.0,0.0])
    for g in rows: t=TW[(int(fl(g['week'])),g['team'])]; t[0]+=fl(g['attempts']); t[1]+=fl(g['carries'])
    xs=[]; ys=[]
    for k,(a,c) in TW.items():
        if k in SP and a+c>=30: xs.append(SP[k]); ys.append(a/(a+c))
    slope,icept=np.linalg.lstsq(np.vstack([xs,np.ones(len(xs))]).T,np.array(ys),rcond=None)[0]
    plays=float(np.mean([a+c for a,c in TW.values() if a+c>=30]))
    G=defaultdict(lambda:defaultdict(float))
    for g in rows:
        x=G[g['position_group']]
        for k,c in (('tgt','targets'),('rec','receptions'),('ry','receiving_yards'),('rtd','receiving_tds'),('ay','receiving_air_yards')): x[k]+=fl(g[c])
    base={p:dict(cr=G[p]['rec']/G[p]['tgt'],ypt=G[p]['ry']/G[p]['tgt'],tdpt=G[p]['rtd']/G[p]['tgt'],adot=G[p]['ay']/G[p]['tgt']) for p in POS if G[p]['tgt']>=50}
    tdc=[]
    for lo,hi in BINS:
        tg=td=0.0
        for g in rows:
            t=fl(g['targets'])
            if t>=1 and lo<=fl(g['receiving_air_yards'])/t<hi: tg+=t; td+=fl(g['receiving_tds'])
        if tg>60: tdc.append([(lo+hi)/2 if hi<100 else 16.0,td/tg])
    R=[g for g in rows if fl(g['targets'])>=1 and g['team'] and g['opponent_team']]
    teams=sorted({g['team'] for g in R}|{g['opponent_team'] for g in R}); TI={t:i for i,t in enumerate(teams)}; T=len(teams)
    X=np.zeros((len(R),2*T+1)); y=np.zeros(len(R)); w=np.zeros(len(R))
    for i,g in enumerate(R): X[i,TI[g['team']]]=1; X[i,T+TI[g['opponent_team']]]=1; X[i,-1]=1; y[i]=fl(g['receiving_yards'])/fl(g['targets']); w[i]=fl(g['targets'])
    A=X*np.sqrt(w)[:,None]; b=y*np.sqrt(w); reg=LAM*np.eye(2*T+1); reg[-1,-1]=0
    beta=np.linalg.solve(A.T@A+reg,A.T@b); DEF={t:float(beta[T+TI[t]]-beta[T:2*T].mean()) for t in teams}
    return dict(season=season,fitted=datetime.date.today().isoformat(),source=src,player_weeks=len(rows),base=base,tdcurve=tdc,
                slope=float(slope),icept=float(icept),plays=plays,DEF=DEF,
                about='Fitted on the %d regular season; used to project %d. Script: pass rate = icept + slope x spread (team side, positive = underdog). '
                      'DEF: pass yards per target a defence allows relative to average, net of the offences it faced (ridge, lambda %g).'%(season,season+1,LAM))

_CACHE={}
def load(season):
    if season not in _CACHE:
        _CACHE[season]=json.load(open(path(season),encoding='utf-8')) if os.path.exists(path(season)) else None
    return _CACHE[season]
def for_season(season):
    """the tables a season is projected with: the previous season's, or the nearest earlier season on file"""
    for s in range(int(season)-1,FIRST-1,-1):
        T=load(s)
        if T: return T
    raise SystemExit('no player-model tables for any season before %s; run python3 pipeline/tables.py'%season)

if __name__=='__main__':
    last=season_now()-1
    want=[int(a) for a in sys.argv[sys.argv.index('--refit')+1:]] if '--refit' in sys.argv else [s for s in range(FIRST,last+1) if not os.path.exists(path(s))]
    os.makedirs(TDIR,exist_ok=True); done=[]
    for s in want:
        T=fit(s)
        if not T: print('  %d: no player weeks or lines available; not fitted'%s); continue
        json.dump(T,open(path(s)+'.part','w',encoding='utf-8'),indent=1); os.replace(path(s)+'.part',path(s)); done.append(s)
        print('  %d from %s: %d player-weeks, pass rate %.4f %+.5f x spread, %.1f plays, WR catch %.3f, TD curve %s'%(
            s,T['source'],T['player_weeks'],T['icept'],T['slope'],T['plays'],T['base']['WR']['cr'],[round(x[1],4) for x in T['tdcurve']]))
    print('tables: %s'%('fitted %s'%done if done else 'every season through %d already on file'%last))
