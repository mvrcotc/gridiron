"""GridIron's pregame game model in one place: the versioned champion weights, per-game features built only from
games before each game's week, and the formula that turns team ratings plus those features into a projected score.

predict.py (the live numbers), backtest.py (the published record) and learn.py (the learning loop) all call this
module, so the three can never describe different models."""
import os, sys, json, math, csv, bisect, statistics
from collections import defaultdict, Counter
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0,HERE)
import engine2
from engine2 import DATA

CHAMP=os.path.join(HERE,'champion.json'); SPEC=os.path.join(HERE,'learning','spec.json')
RATING_KEYS=('kY','cY','kP','cP','kT','cT','kO','cO','kE','cE','kS','cS','decay')
FEATS=('neutral','qb','rest','venue','dome','windx','coldx','ref')
REL={'STL':'LA','SD':'LAC','OAK':'LV'}

def load_champion(path=CHAMP): return json.load(open(path,encoding='utf-8'))
def load_spec(path=SPEC): return json.load(open(path,encoding='utf-8'))
def wk(s,w): return int(s)*100+int(w)
def version(C,v): return next(x for x in C['versions'] if x['v']==v)
def current(C): return version(C,C['current'])
def in_force(C,s,w):
    """the version whose fitting data all predates season s week w; games inside the origin's own fitting window get the origin"""
    live=[x for x in C['versions'] if wk(*x['cutoff'])<wk(s,w)]
    return max(live,key=lambda x:x['v']) if live else min(C['versions'],key=lambda x:x['v'])
def fnum(v,fb=None):
    try:
        x=float(v); return x if math.isfinite(x) else fb
    except (TypeError,ValueError): return fb

# ------------------------------------------------------------------ team ratings (cached per rating-parameter set)
_RUNS={}
def components(P):
    """gid -> (home box-score pts, home EPA pts, home points-path pts, away ...) from the walk-forward engine"""
    key=tuple(round(float(P[k]),8) for k in RATING_KEYS)
    if key not in _RUNS:
        hp={k:float(P[k]) for k in RATING_KEYS}; hp.update(hfa=0.0,wB=1.0,wE=0.0,wS=0.0)
        _RUNS[key]={o['gid']:(o['hd']['pB'],o['hd']['pE'],o['hd']['pS'],o['ad']['pB'],o['ad']['pE'],o['ad']['pS']) for o in engine2.run(hp)}
    return _RUNS[key]

# ------------------------------------------------------------------ features, walk-forward
class Series:
    """values added in time order; mean of those strictly before a week, optionally since a week"""
    def __init__(s): s.k=[]; s.c=[0.0]
    def add(s,k,v): s.k.append(k); s.c.append(s.c[-1]+v)
    def mean(s,before,since=None,min_n=1):
        j=bisect.bisect_left(s.k,before); i=0 if since is None else bisect.bisect_left(s.k,since)
        n=j-i
        return (s.c[j]-s.c[i])/n if n>=min_n and n>0 else None

class Book:
    def __init__(s):
        rows=[r for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'))) if r['game_type']=='REG']
        rows.sort(key=lambda r:(int(r['season']),int(r['week'])))
        s.rows={r['game_id']:r for r in rows}
        s.by_espn={str(r['espn']).split('.')[0]:r['game_id'] for r in rows if r.get('espn')}
        s.home=defaultdict(Series); s.road=defaultdict(Series); s.all=Series(); s.ref=defaultdict(Series); s.qb=defaultdict(list)
        for r in rows:
            if not r['home_score']: continue
            k=wk(r['season'],r['week']); sea=int(r['season'])
            for side in ('home','away'):
                if r[side+'_qb_id']: s.qb[(sea,r[side+'_team'])].append((k,r[side+'_qb_id']))
            m=float(r['home_score'])-float(r['away_score'])
            if r['location']=='Home' and sea>=2015:
                s.home[REL.get(r['home_team'],r['home_team'])].add(k,m); s.road[REL.get(r['away_team'],r['away_team'])].add(k,-m); s.all.add(k,m)
            if (r.get('referee') or '').strip() and fnum(r.get('total_line')) is not None:
                s.ref[r['referee'].strip()].add(k,float(r['home_score'])+float(r['away_score'])-float(r['total_line']))
    def primary(s,sea,team,w):
        c=Counter(q for k,q in s.qb[(sea,team)] if k<wk(sea,w))
        return c.most_common(1)[0][0] if c else None
    def backup(s,sea,team,w,qb_id):
        p=s.primary(sea,team,w)
        return int(bool(p and qb_id and qb_id!=p))
    def venue(s,team,sea,w):
        k=wk(sea,w); t=REL.get(team,team); lg=s.all.mean(k)
        h=s.home[t].mean(k,min_n=16); r=s.road[t].mean(k,min_n=16)
        return 0.0 if (lg is None or h is None or r is None) else h-r-2*lg
    def referee(s,name,sea,w):
        v=s.ref[(name or '').strip()].mean(wk(sea,w),since=wk(sea-2,0),min_n=16) if (name or '').strip() else None
        return 0.0 if v is None else v
    def features(s,r,live=None):
        """features for a schedule row; live overrides (qb flags, forecast weather, referee) come from the refresh"""
        sea,w=int(r['season']),int(r['week']); live=live or {}
        neutral=float(live['neutral']) if 'neutral' in live else float(r['location']!='Home')
        qb=live['qb'] if 'qb' in live else s.backup(sea,r['away_team'],w,r.get('away_qb_id'))-s.backup(sea,r['home_team'],w,r.get('home_qb_id'))
        hr,ar=fnum(r.get('home_rest')),fnum(r.get('away_rest'))
        rest=max(-7.0,min(7.0,hr-ar)) if hr is not None and ar is not None else 0.0
        if 'dome' in live: dome,wind,temp=bool(live['dome']),live.get('wind') or 0.0,live.get('temp')
        else:
            dome=(r.get('roof') or '').lower() in ('dome','closed'); wind=fnum(r.get('wind'),0.0); temp=fnum(r.get('temp'))
        wind=0.0 if dome else float(wind or 0.0); temp=70.0 if dome else (60.0 if temp is None else float(temp))
        return dict(neutral=neutral,qb=float(qb),rest=float(rest),venue=0.0 if neutral else s.venue(r['home_team'],sea,w),
                    dome=float(dome),windx=max(0.0,wind-8.0),coldx=max(0.0,45.0-temp)/10.0,
                    ref=s.referee(live['ref'] if 'ref' in live else r.get('referee'),sea,w))
    def completed(s,first=2019,last=None):
        """played regular-season games with a closing spread, in week order"""
        out=[]
        for r in s.rows.values():
            sea=int(r['season'])
            if sea<first or (last is not None and sea>last) or not r['home_score'] or fnum(r.get('spread_line')) is None: continue
            out.append(r)
        return out

# ------------------------------------------------------------------ the formula
def team_points(P,c):
    return (P['wB']*c[0]+P['wE']*c[1]+P['wS']*c[2], P['wB']*c[3]+P['wE']*c[4]+P['wS']*c[5])
def shifts(P,f):
    """margin shifts (move points between the teams) and total additions (add to both), each as (label, points)"""
    sh=[('hfa',0.0 if f['neutral'] else P['hfa']),('venue',0.0 if f['neutral'] else P['venue']*f['venue']),('qb',P['qb']*f['qb']),('rest',P['rest']*f['rest'])]
    ta=[('weather',P['wx_dome']*f['dome']+P['wx_wind']*f['windx']+P['wx_cold']*f['coldx']),('ref',P['ref']*f['ref'])]
    return sh,ta
def score(P,c,f):
    h0,a0=team_points(P,c); sh,ta=shifts(P,f); m=sum(v for _,v in sh); t=sum(v for _,v in ta)
    return h0+m/2+t/2, a0-m/2+t/2
def win_prob(P,margin):
    return 0.5*(1+math.erf((P['wp_a']+P['wp_b']*margin)/(P['wp_sd']*math.sqrt(2))))
def blended(P,mine,market):
    return None if market is None else P['blend']*mine+(1-P['blend'])*market

# vectorised versions for the learning loop
_erf=np.vectorize(math.erf)
def score_arrays(P,C,F):
    """C: (n,6) components, F: dict of feature arrays -> projected home and away points"""
    h0=P['wB']*C[:,0]+P['wE']*C[:,1]+P['wS']*C[:,2]; a0=P['wB']*C[:,3]+P['wE']*C[:,4]+P['wS']*C[:,5]
    m=np.where(F['neutral']>0,0.0,P['hfa']+P['venue']*F['venue'])+P['qb']*F['qb']+P['rest']*F['rest']
    t=P['wx_dome']*F['dome']+P['wx_wind']*F['windx']+P['wx_cold']*F['coldx']+P['ref']*F['ref']
    return h0+m/2+t/2, a0-m/2+t/2
def wp_arrays(a,b,sd,margin): return 0.5*(1+_erf((a+b*margin)/(sd*math.sqrt(2))))

def track_rows(C=None,first=2019,last=None,book=None):
    """every completed game predicted by the version in force at its week -- the honest walk-forward record"""
    C=C or load_champion(); book=book or Book(); out=[]
    for r in book.completed(first,last):
        sea,w=int(r['season']),int(r['week']); V=in_force(C,sea,w); P=V['params']
        comp=components(P).get(r['game_id'])
        if comp is None: continue
        f=book.features(r); ph,pa=score(P,comp,f)
        h0,a0=team_points(P,comp)
        out.append(dict(gid=r['game_id'],s=sea,w=w,home=r['home_team'],away=r['away_team'],v=V['v'],f=f,
                        ph=ph,pa=pa,m=ph-pa,t=ph+pa,m0=ph-pa-P['qb']*f['qb'],wp=win_prob(P,ph-pa),
                        am=float(r['home_score'])-float(r['away_score']),at=float(r['home_score'])+float(r['away_score']),
                        vs=fnum(r['spread_line']),vt=fnum(r['total_line'])))
    return out
