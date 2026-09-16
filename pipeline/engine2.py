import csv,math,json,os
from collections import defaultdict
D=os.path.dirname(os.path.abspath(__file__))
DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(D),'data')
def num(v):
    try: return float(v)
    except: return 0.0

TW=[]
import glob as _glob
YEARS=sorted(int(os.path.basename(p)[2:6]) for p in _glob.glob(os.path.join(DATA,'tw[0-9][0-9][0-9][0-9].csv')))
for y in YEARS:
    for r in csv.DictReader(open(os.path.join(DATA,'tw%d.csv'%y))):
        if r.get('season_type')!='REG': continue
        TW.append(dict(season=int(r['season']),week=int(r['week']),team=r['team'],
            opp=r['opponent_team'],gid=r['game_id'],
            yds=num(r['passing_yards'])+num(r['rushing_yards']),
            plays=num(r['attempts'])+num(r['carries'])+num(r['sacks_suffered']),
            epa=num(r['passing_epa'])+num(r['rushing_epa']),
            td=num(r['passing_tds'])+num(r['rushing_tds']),
            to=num(r['passing_interceptions'])+num(r['rushing_fumbles_lost'])
               +num(r['receiving_fumbles_lost'])+num(r['sack_fumbles_lost'])))
G={r['game_id']:r for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'))) if r['game_type']=='REG'}
for t in TW:
    g=G.get(t['gid'])
    t['pts']=None if (not g or not g['home_score']) else (
        float(g['home_score']) if g['home_team']==t['team'] else float(g['away_score']))
BY_SW=defaultdict(list)
for t in TW: BY_SW[(t['season'],t['week'])].append(t)

LG={}; LG_N={}
for s in YEARS:
    rs=[t for t in TW if t['season']==s]; n=len(rs) or 1; LG_N[s]=len(rs)
    P=max(sum(t['plays'] for t in rs),1); Y=max(sum(t['yds'] for t in rs),1)
    LG[s]=dict(ypp=Y/P, plays=sum(t['plays'] for t in rs)/n, tdpy=sum(t['td'] for t in rs)/Y,
               topp=sum(t['to'] for t in rs)/P, epp=sum(t['epa'] for t in rs)/P,
               ppg=sum(t['pts'] for t in rs if t['pts'] is not None)/n)
def _lg_for(s):
    """league baseline for season s; a season with too few games falls back to the last full one"""
    full=[k for k in LG if LG_N.get(k,0)>=200]
    if s in LG and LG_N.get(s,0)>=200: return LG[s]
    prev=[k for k in full if k<=s]
    return LG[max(prev)] if prev else LG[max(full)]
PF=json.load(open(os.path.join(D,'ptsfit.json')))
# box-score points: pts = b0 + byds*yds + btd*TD + bto*TO, fitted on each season's team games. A season's ratings use the
# previous season's conversion (the first season on file uses its own), so no rating comes from a fit on later games.
# ptsfit.json keeps the 2025 fit for the Model page.
import numpy as _np
CONV={}
for _s in YEARS:
    _rs=[t for t in TW if t['season']==_s and t['pts'] is not None]
    if len(_rs)<200: continue
    CONV[_s]=[float(x) for x in _np.linalg.lstsq(_np.array([[1.0,t['yds'],t['td'],t['to']] for t in _rs]),_np.array([t['pts'] for t in _rs]),rcond=None)[0]]
def conv_for(s):
    prev=[k for k in CONV if k<s]; return CONV[max(prev)] if prev else CONV[min(CONV)]
def pts_box(y,td,to,s):
    b=conv_for(s); return b[0]+b[1]*y+b[2]*td+b[3]*to

class Mul:
    def __init__(s,k,carry,decay=1.0):
        s.k=k;s.carry=carry;s.decay=decay
        s.n=defaultdict(float);s.d=defaultdict(float);s.p=defaultdict(lambda:1.0)
    def rate(s,t):
        if s.d[t]<=0: return s.p[t]
        w=s.d[t]/(s.d[t]+s.k); return w*(s.n[t]/s.d[t])+(1-w)*s.p[t]
    def add(s,t,n,d): s.n[t]+=n; s.d[t]+=d
    def fade(s):
        if s.decay<1.0:
            for t in s.n: s.n[t]*=s.decay
            for t in s.d: s.d[t]*=s.decay
    def roll(s):
        for t in set(list(s.n)+list(s.p)): s.p[t]=1.0+s.carry*(s.rate(t)-1.0)
        s.n.clear();s.d.clear()

class Add:
    def __init__(s,k,carry,decay=1.0):
        s.k=k;s.carry=carry;s.decay=decay
        s.n=defaultdict(float);s.d=defaultdict(float);s.p=defaultdict(float)
    def rate(s,t): return (s.n[t]+s.k*s.p[t])/(s.d[t]+s.k)
    def add(s,t,n,d): s.n[t]+=n; s.d[t]+=d
    def fade(s):
        if s.decay<1.0:
            for t in s.n: s.n[t]*=s.decay
            for t in s.d: s.d[t]*=s.decay
    def roll(s):
        for t in set(list(s.n)+list(s.p)): s.p[t]=s.carry*s.rate(t)
        s.n.clear();s.d.clear()

def run(P,ret_state=False,stop=None,until=None):
    dc=P['decay']
    oY=Mul(P['kY'],P['cY'],dc); dY=Mul(P['kY'],P['cY'],dc)
    oP=Mul(P['kP'],P['cP'],dc); dP=Mul(P['kP'],P['cP'],dc)
    oT=Mul(P['kT'],P['cT'],dc); dT=Mul(P['kT'],P['cT'],dc)
    oO=Mul(P['kO'],P['cO'],dc); dO=Mul(P['kO'],P['cO'],dc)
    oE=Add(P['kE'],P['cE'],dc); dE=Add(P['kE'],P['cE'],dc)   # epa/play
    oS=Add(P['kS'],P['cS'],dc); dS=Add(P['kS'],P['cS'],dc)   # points/game
    ALL=(oY,dY,oP,dP,oT,dT,oO,dO,oE,dE,oS,dS)
    def _snap(s): return dict(oY=oY,dY=dY,oP=oP,dP=dP,oT=oT,dT=dT,oO=oO,dO=dO,oE=oE,dE=dE,oS=oS,dS=dS,L=_lg_for(s))
    hfa=P['hfa']; wB,wE,wS=P['wB'],P['wE'],P['wS']
    out=[]; snap={}
    for s in sorted(set(t['season'] for t in TW)):
        if stop is not None and s>stop: break
        if until is not None and s>until[0]: break
        L=LG[s]
        for w in sorted(set(t['week'] for t in TW if t['season']==s)):
            if until is not None and (s,w)>=tuple(until):
                snap=_snap(s); return (out,snap) if ret_state else out
            rows=BY_SW[(s,w)]
            seen=set()
            for t in rows:
                gid=t['gid']
                if gid in seen: continue
                seen.add(gid)
                g=G.get(gid)
                if not g or not g['home_score']: continue
                h,a=g['home_team'],g['away_team']
                pr={}
                for tm,op in ((h,a),(a,h)):
                    ypp=L['ypp']*oY.rate(tm)*dY.rate(op)
                    pl =L['plays']*oP.rate(tm)*dP.rate(op)
                    yd =ypp*pl
                    td =yd*L['tdpy']*oT.rate(tm)*dT.rate(op)
                    to =pl*L['topp']*oO.rate(tm)*dO.rate(op)
                    pB =pts_box(yd,td,to,s)
                    pE =L['ppg']+(oE.rate(tm)+dE.rate(op))*pl
                    pS =L['ppg']+oS.rate(tm)+dS.rate(op)
                    pr[tm]=dict(yd=yd,td=td,to=to,pl=pl,pB=pB,pE=pE,pS=pS,
                                p=wB*pB+wE*pE+wS*pS)
                hv=hfa if (g.get('location') or 'Home')=='Home' else 0.0     # no home edge at a neutral site
                ph=pr[h]['p']+hv/2.0; pa=pr[a]['p']-hv/2.0
                out.append(dict(season=s,week=w,gid=gid,home=h,away=a,ph=ph,pa=pa,
                    margin=ph-pa,total=ph+pa,
                    amargin=float(g['home_score'])-float(g['away_score']),
                    atotal=float(g['home_score'])+float(g['away_score']),
                    vs=num(g['spread_line']) if g['spread_line'] else None,
                    vt=num(g['total_line']) if g['total_line'] else None,
                    hd=pr[h],ad=pr[a]))
            for R in ALL: R.fade()
            for t in rows:
                if t['plays']<=0 or t['pts'] is None: continue
                op=t['opp']
                oY.add(t['team'],t['yds'],t['plays']*L['ypp']*dY.rate(op))
                dY.add(op,t['yds'],t['plays']*L['ypp']*oY.rate(t['team']))
                oP.add(t['team'],t['plays'],L['plays']*dP.rate(op))
                dP.add(op,t['plays'],L['plays']*oP.rate(t['team']))
                oT.add(t['team'],t['td'],t['yds']*L['tdpy']*dT.rate(op))
                dT.add(op,t['td'],t['yds']*L['tdpy']*oT.rate(t['team']))
                oO.add(t['team'],t['to'],t['plays']*L['topp']*dO.rate(op))
                dO.add(op,t['to'],t['plays']*L['topp']*oO.rate(t['team']))
                e=t['epa']/t['plays']-L['epp']
                oE.add(t['team'],(e-dE.rate(op))*t['plays'],t['plays'])
                dE.add(op,(e-oE.rate(t['team']))*t['plays'],t['plays'])
                d=t['pts']-L['ppg']
                oS.add(t['team'],d-dS.rate(op),1.0)
                dS.add(op,d-oS.rate(t['team']),1.0)
        if until is not None and s==until[0]:
            snap=_snap(s); return (out,snap) if ret_state else out
        for R in ALL: R.roll()
        if stop is not None and s==stop:
            snap=_snap(s)
    if until is not None and not snap:
        snap=_snap(until[0])
    return (out,snap) if ret_state else out

def rep(out,seasons,minweek=5,label=''):
    rs=[o for o in out if o['season'] in seasons and o['week']>=minweek and o['vs'] is not None]
    n=len(rs); rt=[o for o in rs if o['vt']]
    mm=sum(abs(o['margin']-o['amargin']) for o in rs)/n
    vm=sum(abs(o['vs']-o['amargin']) for o in rs)/n
    mt=sum(abs(o['total']-o['atotal']) for o in rt)/len(rt)
    vt=sum(abs(o['vt']-o['atotal']) for o in rt)/len(rt)
    dm=sum(abs(o['margin']-o['vs']) for o in rs)/n
    print('%-18s n=%-4d MARGIN gi %.2f / vegas %.2f (%+.2f)  TOTAL gi %.2f / vegas %.2f (%+.2f)  |gi-vegas| %.2f'
          %(label,n,mm,vm,mm-vm,mt,vt,mt-vt,dm))
    return dict(n=n,mm=mm,vm=vm,mt=mt,vt=vt,dm=dm)
