"""The player projection model's part of the weekly review (learn.py runs it). Same process as the game models: for
every week of the evaluation seasons, re-tune one weight group using only player-weeks before that week, then score
it player-week by player-week (expected PPR points) against the player weights that were in force, on player-weeks
neither side saw."""
import os, sys, json, math, csv, copy, sqlite3, subprocess
from collections import defaultdict
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0,HERE)
import gamemodel as gm, playermodel as pm

SPEC_PATH=os.path.join(HERE,'learning','spec_players.json')
def load_spec(): return json.load(open(SPEC_PATH,encoding='utf-8'))

def weeks_through():
    if not os.path.exists(pm.DB): return None
    con=sqlite3.connect(pm.DB)
    try: r=con.execute("SELECT MAX(season*100+week) FROM player_week WHERE season_type='REG'").fetchone()
    except sqlite3.Error: r=(None,)
    con.close(); return r[0]
def data_ready(cutoff,update=False):
    """player weeks through the cutoff are in the history database; optionally load the newest nflverse files first"""
    have=weeks_through()
    if (have is None or have<gm.wk(*cutoff)) and update:
        r=subprocess.run([sys.executable,os.path.join(HERE,'history.py'),'--from','2019','--tables','player_week,plays'],capture_output=True,text=True)
        print('  history database update: %s'%((r.stdout or r.stderr).strip().split('\n')[-1][:140]),flush=True)
        have=weeks_through()
    return have is not None and have>=gm.wk(*cutoff)

class Rows:
    """every player-week from the first season on in which a projectable player had a target, carry or pass attempt,
    with the history totals a projection for that week may use: this season before the week, and last season"""
    def __init__(s,first,cutoff):
        panel=pm.Panel.from_db(first-1,cutoff); SP={}
        for r in csv.DictReader(open(os.path.join(gm.DATA,'games_all.csv'))):
            if r['game_type']!='REG' or gm.fnum(r['spread_line']) is None: continue
            k=(int(r['season']),int(r['week'])); sp=float(r['spread_line'])
            SP[k+(r['home_team'],)]=-sp; SP[k+(r['away_team'],)]=sp
        rec=[]; CUR=[]; PREV=[]
        for pid,games in panel.BY.items():
            tot=defaultdict(lambda:np.zeros(len(pm.STATS)+2)); run=defaultdict(lambda:np.zeros(len(pm.STATS)+2)); vecs=[]
            for g in games:
                t=panel.TW.get((g['s'],g['w'],g['tm']),(0.0,0.0)); v=np.array([g[k] for k in pm.STATS]+[t[0],t[1]]); vecs.append(v); tot[g['s']]+=v
            for g,v in zip(games,vecs):
                sp=SP.get((g['s'],g['w'],g['tm']))
                if g['s']>=first and g['pos'] in pm.BASE and sp is not None and g['tgt']+g['car']+g['att']>=1:
                    cur,prev=run[g['s']].copy(),tot[g['s']-1].copy()
                    if cur[:13].sum()+prev[:13].sum()>0:
                        rec.append((g['s']*100+g['w'],g['s'],pid,g['pos'],sp,pm.TB.for_season(g['s'])['DEF'].get(g['opp'],0.0),pm.actual_points(g),g['rec'],g['ry']+g['ru']))
                        CUR.append(cur); PREV.append(prev)
                run[g['s']]+=v
        order=sorted(range(len(rec)),key=lambda i:(rec[i][0],rec[i][2]))
        col=lambda j,dt=float:np.array([rec[i][j] for i in order],dtype=dt)
        s.wk=col(0,int); s.season=col(1,int); s.pid=np.array([rec[i][2] for i in order]); s.pos=np.array([rec[i][3] for i in order])
        s.spread=col(4); s.adj=col(5); s.pts=col(6); s.rec=col(7); s.yds=col(8)
        s.CUR=np.array([CUR[i] for i in order]); s.PREV=np.array([PREV[i] for i in order]); s.n=len(order)
    def before(s,w): return int(np.searchsorted(s.wk,w,'left'))

def predict(R,P,i=0,j=None):
    """every season in the slice is projected with the tables fitted on the season before it"""
    j=R.n if j is None else j; out={k:np.zeros(j-i) for k in ('pts','rec','yds')}
    for s in np.unique(R.season[i:j]):
        m=np.where(R.season[i:j]==s)[0]+i
        pj=pm.project(R.CUR[m],R.PREV[m],R.spread[m],R.adj[m],R.pos[m],P,pm.TB.for_season(int(s)))
        out['pts'][m-i]=pm.expected_points(pj); out['rec'][m-i]=pj['tgt']*pj['cr']; out['yds'][m-i]=pj['tgt']*pj['ypt']+pj['car']*pj['ypc']
    return out
def losses(metric,R,pr,i=0,j=None):
    j=R.n if j is None else j
    return np.abs(pr[metric]-getattr(R,metric)[i:j])

# ------------------------------------------------------------------ one weight group as a point in a small space
def origin_params(C): return min(C['versions'],key=lambda x:x['v'])['params']
def vec(cat,P,O):
    if cat['kind']=='ratio': return np.array([math.log(P[cat['params'][0]]/O[cat['params'][0]])])
    return np.array([float(P[p]) for p in cat['params']])
def apply(cat,P,v,O):
    Q=dict(P)
    if cat['kind']=='ratio':
        for p in cat['params']: Q[p]=round(O[p]*math.exp(float(v[0])),4)
    else:
        for p,x in zip(cat['params'],v): Q[p]=round(float(x),4)
    return Q
def steps(cat,a,b):
    if cat['kind']=='ratio': return abs(float(b[0]-a[0]))/math.log(cat['step'])
    return float(np.max(np.abs(b-a)))/cat['step']
def material(cat,a,b):
    if cat['kind']=='ratio': return abs(float(b[0]-a[0]))>=math.log(cat['min_change'])-1e-9
    return float(np.max(np.abs(b-a)))>=cat['min_change']-1e-9
def clip(cat,v):
    if cat['kind']=='ratio':
        lo,hi=cat['ratio_bounds']; return np.clip(v,math.log(lo),math.log(hi))
    lo,hi=cat['bounds'][cat['params'][0]]; return np.clip(v,lo,hi)
def toward(cat,a,b,limit=1.0):
    s=steps(cat,a,b); return b.copy() if s<=limit+1e-9 else a+(b-a)*(limit/s)
def fmt(cat,P,O):
    if cat['kind']=='ratio': return '×%.2f of launch values'%(P[cat['params'][0]]/O[cat['params'][0]])
    return '×%g'%P[cat['params'][0]]
def get_vec(cat,P): return np.array([float(P[p]) for p in cat['params']])

class Tuner:
    def __init__(s,R,cat,P,O):
        s.R,s.cat,s.P,s.O=R,cat,P,O; s.cur=vec(cat,P,O); G=[s.cur]
        if cat['kind']=='ratio':
            lo,hi=cat['ratio_bounds']
            G+=[np.array([s.cur[0]+math.log(r)]) for r in cat['ratios'] if math.log(lo)-1e-9<=s.cur[0]+math.log(r)<=math.log(hi)+1e-9]
        else:
            G+=[np.array([x]) for x in cat['values']]
        seen=set(); s.G=[]
        for g in G:
            key=tuple(np.round(g,6))
            if key not in seen: seen.add(key); s.G.append(g)
        L=np.array([losses(cat['metric'],R,predict(R,apply(cat,P,g,O))) for g in s.G])
        s.cum=np.concatenate([np.zeros((len(s.G),1)),np.cumsum(L,axis=1)],axis=1); s.dist=np.array([steps(cat,s.cur,g) for g in s.G])
    def best(s,i): return s.G[int(np.argmin(s.cum[:,i]+1e-7*s.dist))].copy()

def evaluate(R,C,cutoff,rid,spec,boot,seed_of,only=None):
    O=origin_params(C); cur=gm.current(C); P=cur['params']
    ev_first=max(min(v['cutoff'][0] for v in C['versions'])+1,int(cutoff[0])-spec['eval_last_seasons']+1)
    weeks=sorted(set(R.wk[R.season>=ev_first].tolist())); i0=R.before(weeks[0]) if weeks else R.n; out=[]
    for cat in spec['categories']:
        if only and cat['id']!=only: continue
        tuners={}
        def tuner(V):
            if V['v'] not in tuners: tuners[V['v']]=Tuner(R,cat,V['params'],O)
            return tuners[V['v']]
        T=tuner(cur); curv=T.cur; best=clip(cat,T.best(R.n))
        res=dict(model='players',category=cat['id'],name=cat['name'],what=cat['what'],metric=cat['metric'],from_params={p:P[p] for p in cat['params']})
        if not material(cat,curv,best):
            res.update(status='holds',summary='%s: the best-fitting value is within one grid step of the current weight, so nothing to test.'%cat['name']); out.append(res); continue
        onoff=bool(cat['kind']=='linear' and (abs(curv[0])<1e-9)!=(abs(best[0])<1e-9))
        variants=[('full',best)]
        if steps(cat,curv,best)>1+1e-9 and not onoff: variants.append(('step',toward(cat,curv,best)))
        fits=[]
        for w in weeks:
            i,j=R.before(w),R.before(w+1); V=gm.in_force(C,w//100,w%100); Tv=tuner(V); fits.append((i,j,V,Tv.best(i),Tv.cur))
        for vname,target in variants:
            PB={k:np.zeros(R.n-i0) for k in ('pts','rec','yds')}; PC={k:np.zeros(R.n-i0) for k in PB}
            for i,j,V,b,base in fits:
                if j<=i: continue
                tv=clip(cat,b if vname=='full' else toward(cat,base,b))
                pb=predict(R,V['params'],i,j); pc=predict(R,apply(cat,V['params'],tv,O),i,j)
                for k in PB: PB[k][i-i0:j-i0]=pb[k]; PC[k][i-i0:j-i0]=pc[k]
            lb=losses(cat['metric'],R,PB,i0); lc=losses(cat['metric'],R,PC,i0); d=lb-lc
            p,se=boot(d,R.wk[i0:],seed_of(rid,'players',cat['id'],vname),spec['bootstrap'])
            seas=R.season[i0:]
            blocks=[dict(season=int(x),n=int((seas==x).sum()),base=round(float(lb[seas==x].mean()),4),cand=round(float(lc[seas==x].mean()),4)) for x in sorted(set(seas.tolist()))]
            sec={k:(float(losses(k,R,PB,i0).mean()),float(losses(k,R,PC,i0).mean())) for k in ('pts','rec','yds')}
            to=apply(cat,P,clip(cat,target),O); tuned=[f[3] for f in fits]
            c=dict(res,variant=vname,title='%s %s → %s'%(cat['name'],fmt(cat,P,O),fmt(cat,to,O)),to_params={p:to[p] for p in cat['params']},
                   steps=round(steps(cat,curv,clip(cat,target)),2),onoff=onoff,turns=(('on' if abs(curv[0])<1e-9 else 'off') if onoff else None),
                   n=int(len(d)),base=round(float(lb.mean()),4),cand=round(float(lc.mean()),4),delta=round(float(d.mean()),4),se=round(se,5),p=round(p,5),
                   blocks=blocks,sec=sec,tuned_spread=round(float(max(steps(cat,tuned[-1],x) for x in tuned[-8:])),2) if tuned else 0.0,
                   _evidence=dict(pid=R.pid[i0:],wk=R.wk[i0:],**{'base_'+k:v.astype(np.float32) for k,v in PB.items()},**{'cand_'+k:v.astype(np.float32) for k,v in PC.items()}))
            out.append(c)
    return out

def rollback_check(R,C,cutoff,rid,boot,seed_of,spec):
    V=gm.current(C)
    if V['how'] not in ('auto','approved'): return None
    prev=max((x for x in C['versions'] if x['v']<V['v']),key=lambda x:x['v'])
    i=R.before(gm.wk(*V['cutoff'])+1); n=R.n-i
    if n<max(1,spec['rollback']['min_games']): return dict(version=V['v'],games=int(n),status='too early')
    lv=losses('pts',R,predict(R,V['params'],i),i); lp=losses('pts',R,predict(R,prev['params'],i),i)
    p,_=boot(lv-lp,R.wk[i:],seed_of(rid,'players','rollback'),spec['bootstrap'])
    out=dict(version=V['v'],previous=prev['v'],games=int(n),new=round(float(lv.mean()),4),old=round(float(lp.mean()),4),p=round(p,5))
    out['status']='rolled back' if p<spec['rollback']['alpha'] else 'kept'
    return out

def save_evidence(path,ev): np.savez_compressed(path,**ev)
