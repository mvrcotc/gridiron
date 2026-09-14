"""GridIron's player projection model in one place: the weekly stat panel, each player's weighted history (this
season's games before the week at full weight, last season's at a learned weight), the projection formula, expected
PPR points, and the simulator.

The formula is vectorised so the weekly review can score every candidate value on thousands of player-weeks at once;
project.py (the live projections) runs the same function on one player at a time. Fitted tables that are not weights
-- positional baselines, the depth-of-target touchdown curve, the game-script line and each defence's pass
adjustment -- still come from fit1.json and fit_opp.json."""
import os, sys, csv, json, math, sqlite3
from collections import defaultdict
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
CHAMP=os.path.join(HERE,'champion_players.json'); DB=os.path.join(DATA,'history','history.sqlite')
F=json.load(open(os.path.join(HERE,'fit1.json'))); BASE=F['base']; TDC=F['tdcurve']; SLOPE=F['slope']; ICEPT=F['icept']; PLAYS=F['plays']
DEF=json.load(open(os.path.join(HERE,'fit_opp.json')))['DEF']
TS_PRIOR={'WR':.145,'TE':.115,'RB':.085}
STATS=('tgt','rec','ry','rtd','ay','car','ru','rutd','att','cmp','py','ptd','pint')
COLS=dict(tgt='targets',rec='receptions',ry='receiving_yards',rtd='receiving_tds',ay='receiving_air_yards',car='carries',ru='rushing_yards',
          rutd='rushing_tds',att='attempts',cmp='completions',py='passing_yards',ptd='passing_tds',pint='passing_interceptions')
def load_champion(path=CHAMP): return json.load(open(path,encoding='utf-8'))
def fl(v):
    try:
        x=float(v); return x if math.isfinite(x) else 0.0
    except (TypeError,ValueError): return 0.0

class Panel:
    """regular-season player weeks and team pass attempts / carries per game"""
    def __init__(s,rows):
        s.BY=defaultdict(list); s.TW=defaultdict(lambda:[0.0,0.0])
        for g in rows:
            s.BY[g['id']].append(g); t=s.TW[(g['s'],g['w'],g['tm'])]; t[0]+=g['att']; t[1]+=g['car']
        for v in s.BY.values(): v.sort(key=lambda g:(g['s'],g['w']))
        s.POS={pid:v[-1]['pos'] for pid,v in s.BY.items()}
    @staticmethod
    def _row(get):
        return dict(id=get('player_id'),pos=get('position_group'),s=int(fl(get('season'))),w=int(fl(get('week'))),tm=get('team'),opp=get('opponent_team'),
                    **{k:fl(get(c)) for k,c in COLS.items()})
    @classmethod
    def from_csv(cls,seasons):
        """nflverse weekly player stats files the refresh keeps in data/ (stw25.csv, stw26.csv, ...)"""
        rows=[]
        for sea in seasons:
            p=os.path.join(DATA,'stw%02d.csv'%(sea%100))
            if not os.path.exists(p): continue
            for r in csv.DictReader(open(p,encoding='utf-8')):
                if r.get('season_type')=='REG': rows.append(cls._row(r.get))
        return cls(rows)
    @classmethod
    def from_db(cls,first,cutoff=None):
        con=sqlite3.connect(DB); cols=['player_id','position_group','season','week','team','opponent_team']+list(COLS.values())
        q="SELECT %s FROM player_week WHERE season>=? AND season_type='REG'"%','.join(cols); rows=[]
        for r in con.execute(q,(first,)):
            d=dict(zip(cols,r))
            if cutoff and d['season']*100+d['week']>cutoff[0]*100+cutoff[1]: continue
            rows.append(cls._row(d.get))
        con.close(); return cls(rows)
    def sums(s,pid,season,week):
        """this season's totals before the week and last season's totals, each with team attempts and carries"""
        cur=np.zeros(len(STATS)+2); prev=np.zeros(len(STATS)+2)
        for g in s.BY.get(pid,[]):
            if g['s']==season and g['w']<week: tgt=cur
            elif g['s']==season-1: tgt=prev
            else: continue
            t=s.TW.get((g['s'],g['w'],g['tm']),(0.0,0.0))
            tgt+=np.array([g[k] for k in STATS]+[t[0],t[1]])
        return cur,prev

def td_per_target(adot): return np.interp(adot,[c[0] for c in TDC],[c[1] for c in TDC])

def project(Acur,Aprev,spread,opp_adj,pos,P):
    """Vectorised projection. Acur/Aprev: (n,15) totals (STATS + team attempts, team carries); spread from the team's side
    (positive = underdog); opp_adj: the opponent's pass-defence adjustment; pos: position group per row."""
    A=np.asarray(Acur,float)+P['prev_weight']*np.asarray(Aprev,float); a={k:A[:,i] for i,k in enumerate(STATS)}; tatt=A[:,13]; tcar=A[:,14]
    pos=np.asarray(pos); spread=np.asarray(spread,float); opp_adj=np.asarray(opp_adj,float)
    b=lambda key,fb: np.array([BASE.get(p,{}).get(key,fb) for p in pos],float)
    pr_cr,pr_ypt,pr_adot=b('cr',0.65),b('ypt',7.0),b('adot',6.0); tsp=np.array([TS_PRIOR.get(p,.12) for p in pos])
    prate=ICEPT+SLOPE*P['script_scale']*spread; team_att=PLAYS*prate
    ts=np.where(tatt>0,(a['tgt']+P['k_ts']*tsp)/np.maximum(tatt+P['k_ts'],1e-9),tsp); tgt=team_att*ts
    cr=(a['rec']+P['k_cr']*pr_cr)/(a['tgt']+P['k_cr'])
    ypt=np.maximum(2.0,(a['ry']+P['k_ypt']*pr_ypt)/(a['tgt']+P['k_ypt'])+P['opp_scale']*opp_adj)
    adot=np.where(a['tgt']+P['k_adot']>0,(a['ay']+P['k_adot']*pr_adot)/np.maximum(a['tgt']+P['k_adot'],1e-9),pr_adot); tdpt=td_per_target(adot)
    cshare=np.where(tcar>0,(a['car']+P['k_cshare']*0.12)/np.maximum(tcar+P['k_cshare'],1e-9),0.0); car=PLAYS*(1-prate)*cshare
    ypc=(a['ru']+P['k_ypc']*4.3)/(a['car']+P['k_ypc']); rutdpc=(a['rutd']+P['k_rutd']*0.028)/(a['car']+P['k_rutd'])
    qb=a['att']>=20
    pa=np.where(qb,team_att*np.minimum(1.0,a['att']/np.maximum(1.0,tatt)),0.0)
    pcr=np.where(qb,(a['cmp']+P['k_pcmp']*.655)/(a['att']+P['k_pcmp']),0.0)
    ypa=(a['py']+P['k_pass']*7.1)/(a['att']+P['k_pass'])
    py=np.where(qb,pa*ypa,0.0); ptd=np.where(qb,pa*(a['ptd']+P['k_pass']*.045)/(a['att']+P['k_pass']),0.0); pint=np.where(qb,pa*(a['pint']+P['k_pass']*.023)/(a['att']+P['k_pass']),0.0)
    return dict(tgt=tgt,cr=cr,ypt=ypt,tdpt=tdpt,car=car,ypc=ypc,rutdpc=rutdpc,pa=pa,pcr=pcr,py=py,ptd=ptd,pint=pint,n=a['tgt']+a['car']+a['att'],
                known=(A[:,:13].sum(1)>0)&np.array([p in BASE for p in pos]))
def expected_points(pj):
    return pj['tgt']*pj['cr']+0.1*pj['tgt']*pj['ypt']+6*pj['tgt']*pj['tdpt']+0.1*pj['car']*pj['ypc']+6*pj['car']*pj['rutdpc']+0.04*pj['py']+4*pj['ptd']-2*pj['pint']
def actual_points(g): return g['rec']+0.1*g['ry']+6*g['rtd']+0.1*g['ru']+6*g['rutd']+0.04*g['py']+4*g['ptd']-2*g['pint']

def project_one(panel,pid,season,week,spread,opp,pos,P):
    """one player's projection as plain floats, or None when he has no usable history"""
    cur,prev=panel.sums(pid,season,week)
    pj=project(cur[None,:],prev[None,:],[spread],[DEF.get(opp,0.0)],[pos],P)
    if not pj['known'][0]: return None
    return {k:float(v[0]) for k,v in pj.items() if k!='known'}

def simulate(pj,N,P,rng):
    """P['vol'] and P['yshape'] scale the uncertainty; calibrated on held-out weeks"""
    def nb(mean,over):
        mean=max(1e-6,mean); r=max(0.05,mean/max(1e-6,(over-1.0))) if over>1.0 else 1e6; p=r/(r+mean)
        return rng.negative_binomial(r,p,N).astype(float)
    vol,ysh=P['vol'],P['yshape']
    tgt=nb(pj['tgt'],vol); rec=rng.binomial(np.maximum(0,tgt).astype(int),min(.99,max(.01,pj['cr'])))
    ypr=pj['ypt']/max(.05,pj['cr']); ry=rng.gamma(np.maximum(0.02,rec*ysh),ypr/ysh)
    rtd=rng.binomial(np.maximum(0,tgt).astype(int),min(.4,max(0.0,pj['tdpt'])))
    car=nb(pj['car'],vol) if pj['car']>0.2 else np.zeros(N)
    ru=rng.gamma(np.maximum(0.02,car*ysh),pj['ypc']/ysh) if pj['car']>0.2 else np.zeros(N)
    rutd=rng.binomial(np.maximum(0,car).astype(int),min(.3,max(0.0,pj['rutdpc'])))
    if pj['pa']>1:
        pa=nb(pj['pa'],vol); py=rng.gamma(np.maximum(0.02,pa*ysh*1.8),(pj['py']/max(1e-6,pj['pa']))/(ysh*1.8))
        ptd=rng.poisson(max(0,pj['ptd']),N); pint=rng.poisson(max(0,pj['pint']),N)
    else: py=np.zeros(N); ptd=np.zeros(N); pint=np.zeros(N)
    pts=rec*1.0+ry*0.1+rtd*6+ru*0.1+rutd*6+py*0.04+ptd*4-pint*2
    return {'pts':pts,'ry':ry,'rec':rec.astype(float),'ru':ru,'py':py,'tgt':tgt}
