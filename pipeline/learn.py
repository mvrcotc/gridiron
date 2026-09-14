"""GridIron's learning loop for the pregame odds model and the live in-game model.

Once a week, after every game of the week is final, it re-tests each weight group in learning/spec.json (pregame) and
learning/spec_live.json (live):

  1. Re-tune.   For every week of the last few seasons, find the value that would have fitted best using only games
                before that week (walk-forward), exactly as the loop would have done live.
  2. Compare.   Score those walk-forward values against the weights that were actually in force, game by game (or play
                by play), on games neither side had seen. Evidence is resampled by week to get a confidence level,
                corrected for how many ideas were tested for that model in the same review.
  3. Check.     Hard checks: enough games, genuinely better, significant after correction, better in most seasons,
                no damage to the other measures.
  4. Weigh.     Pros and cons are scored in the open (size of the gain, consistency, how far the weight moves, added
                complexity, distance from the market, fragility). Cons must not outweigh pros.
  5. Confirm.   A change must pass again in a later review with new games before anything moves.
  6. Act.       A small move within limits applies automatically (at most one per model per review, at most one step
                per category per season, a cooldown between changes). A big move, or switching a factor on or off,
                becomes a proposal for the owner. A change that then does worse on new games than the version it
                replaced is rolled back automatically.

  python3 learn.py review [--force] [--update-history]   weekly review (skips a model with no new completed week)
  python3 learn.py approve <proposal-id>                  apply a proposal after re-checking its evidence on current data
  python3 learn.py reject <proposal-id>
  python3 learn.py status
"""
import os, sys, json, math, zlib, argparse, datetime, copy
from collections import defaultdict
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0,HERE)
import gamemodel as gm, engine2

LDIR=os.path.join(HERE,'learning'); EDIR=os.path.join(LDIR,'evidence'); os.makedirs(EDIR,exist_ok=True)
P_LOG,P_STATE,P_PROPS,P_SUM,P_NEW=[os.path.join(LDIR,f) for f in ('log.json','state.json','proposals.json','summary.json','new_proposals')]
SPEC=gm.load_spec(); CATS={c['id']:c for c in SPEC['categories']}
MODELS=('pregame','live'); MNAME={'pregame':'Pregame odds model','live':'Live in-game model'}

def jload(p,fb):
    try: return json.load(open(p,encoding='utf-8'))
    except FileNotFoundError: return fb
def jsave(p,o):
    json.dump(o,open(p+'.part','w',encoding='utf-8'),indent=1,ensure_ascii=False); os.replace(p+'.part',p)
def seq(cut): return int(cut[0])*18+min(int(cut[1]),18)
def today(): return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
def nf(x): return '%.4f'%x if abs(x)<1 else '%.3f'%x

# ------------------------------------------------------------------ data (pregame)
def latest_cutoff(book):
    """last week whose every game is final and has team box scores; a week still in progress does not count"""
    have={t['gid'] for t in engine2.TW}; weeks=defaultdict(list)
    for r in book.rows.values(): weeks[(int(r['season']),int(r['week']))].append(r)
    played=sorted(k for k,rs in weeks.items() if any(r['home_score'] for r in rs))
    if not played: return None
    last=played[-1]
    if all(r['home_score'] and r['game_id'] in have for r in weeks[last]): return list(last)
    return list(played[-2]) if len(played)>1 else None

class Frame:
    """every completed game from the first season through the cutoff, in week order"""
    def __init__(s,book,cutoff):
        rows=[r for r in book.completed(SPEC['first_season']) if gm.wk(r['season'],r['week'])<=gm.wk(*cutoff)]
        rows.sort(key=lambda r:(int(r['season']),int(r['week']),r['game_id'])); s.rows=rows; s.n=len(rows)
        s.gid=[r['game_id'] for r in rows]
        s.season=np.array([int(r['season']) for r in rows]); s.week=np.array([int(r['week']) for r in rows]); s.wk=s.season*100+s.week
        F=[book.features(r) for r in rows]; s.F={k:np.array([f[k] for f in F],float) for k in gm.FEATS}
        s.am=np.array([float(r['home_score'])-float(r['away_score']) for r in rows]); s.at=np.array([float(r['home_score'])+float(r['away_score']) for r in rows])
        s.vs=np.array([gm.fnum(r['spread_line']) for r in rows],float); s.vt=np.array([gm.fnum(r['total_line'],np.nan) for r in rows],float)
        s.train=~((s.season==SPEC['first_season'])&(s.week<=SPEC['cold_weeks_2019']))
        s._comp={}
    def comp(s,P):
        key=tuple(round(float(P[k]),8) for k in gm.RATING_KEYS)
        if key not in s._comp:
            c=gm.components(P); s._comp[key]=np.array([c[g] for g in s.gid],float)
        return s._comp[key]
    def before(s,w): return int(np.searchsorted(s.wk,w,'left'))

def predict(fr,P,idx=None):
    C=fr.comp(P); F=fr.F
    if idx is not None: C=C[idx]; F={k:v[idx] for k,v in F.items()}
    ph,pa=gm.score_arrays(P,C,F); m=ph-pa; t=ph+pa
    vs=fr.vs if idx is None else fr.vs[idx]; vt=fr.vt if idx is None else fr.vt[idx]
    return dict(m=m,t=t,wp=gm.wp_arrays(P['wp_a'],P['wp_b'],P['wp_sd'],m),bm=P['blend']*m+(1-P['blend'])*vs,bt=P['blend']*t+(1-P['blend'])*vt)

def losses(fr,metric,pr,idx=None):
    """per-game loss for a metric, and which games it is defined for"""
    am=fr.am if idx is None else fr.am[idx]; at=fr.at if idx is None else fr.at[idx]; vt=fr.vt if idx is None else fr.vt[idx]
    ok=np.ones(len(am),bool)
    if metric=='margin': return np.abs(pr['m']-am),ok
    if metric=='total': return np.abs(pr['t']-at),ok
    if metric=='margin_total': return (np.abs(pr['m']-am)+np.abs(pr['t']-at))/2,ok
    if metric=='logloss':
        p=np.clip(pr['wp'],1e-6,1-1e-6); y=(am>0).astype(float); ok=am!=0
        return np.where(ok,-(y*np.log(p)+(1-y)*np.log(1-p)),0.0),ok
    if metric=='blend':
        ok=~np.isnan(vt); return np.where(ok,(np.abs(pr['bm']-am)+np.abs(np.nan_to_num(pr['bt'])-at))/2,0.0),ok
    raise ValueError(metric)

# ------------------------------------------------------------------ a pregame weight group as a point in a small space
def origin_params(C): return min(C['versions'],key=lambda x:x['v'])['params']
def vec(cat,P,O):
    if cat['kind']=='engine_ratio': return np.array([math.log(P[cat['params'][0]]/O[cat['params'][0]])])
    return np.array([float(P[p]) for p in cat['params']])
def apply(cat,P,v,O):
    Q=dict(P)
    if cat['kind']=='engine_ratio':
        r=math.exp(float(v[0]))
        for p in cat['params']: Q[p]=round(min(O[p]*r,cat.get('cap',1e9)),4)
    else:
        for p,x in zip(cat['params'],v): Q[p]=round(float(x),4)
    return Q
def steps(cat,a,b):
    if cat['kind']=='engine_ratio': return abs(float(b[0]-a[0]))/math.log(cat['step'])
    st=np.array([cat['step'][p] for p in cat['params']]) if isinstance(cat['step'],dict) else cat['step']
    return float(np.max(np.abs(b-a)/st))
def material(cat,a,b):
    if cat['kind']=='engine_ratio': return abs(float(b[0]-a[0]))>=math.log(cat['min_change'])-1e-9
    mc=np.array([cat['min_change'][p] for p in cat['params']]) if isinstance(cat['min_change'],dict) else cat['min_change']
    return bool(np.any(np.abs(b-a)>=mc-1e-9))
def clip(cat,v):
    if cat['kind']=='engine_ratio':
        lo,hi=cat['ratio_bounds']; return np.clip(v,math.log(lo),math.log(hi))
    if cat['kind']=='mix': v=np.clip(v,0,1); return v/v.sum()
    b=cat.get('bounds') or {}
    return np.array([min(max(x,b[p][0]),b[p][1]) if p in b else x for p,x in zip(cat['params'],v)])
def is_off(v): return bool(np.all(np.abs(v)<1e-9))
def toward(cat,a,b,limit=1.0):
    """move from a toward b by at most `limit` steps"""
    s=steps(cat,a,b)
    return b.copy() if s<=limit+1e-9 else a+(b-a)*(limit/s)
def fmt(cat,P):
    p=cat['params']
    if cat['kind']=='mix': return 'yards %d%% / EPA %d%% / points %d%%'%tuple(round(100*P[x]) for x in p)
    if cat['kind']=='engine_ratio': return ', '.join('%s %g'%(x,P[x]) for x in p)
    if cat['id']=='wp_cal': return 'a %.2f, b %.3f, sd %.2f'%(P['wp_a'],P['wp_b'],P['wp_sd'])
    if cat['id']=='weather_total': return 'roof %+.2f, wind %+.3f/mph, cold %+.2f/10°F'%(P['wx_dome'],P['wx_wind'],P['wx_cold'])
    if cat['id']=='blend': return '%d%% GridIron'%round(100*P['blend'])
    return '%g'%P[p[0]]
def fmt_ratio(cat,P,O): return '×%.2f of launch values'%(P[cat['params'][0]]/O[cat['params'][0]])

class Tuner:
    """a weight group's candidate values, as seen from one version's weights, with walk-forward best-fit lookups"""
    def __init__(s,fr,cat,P,O):
        s.fr,s.cat,s.P,s.O=fr,cat,P,O; k=cat['kind']; s.cur=vec(cat,P,O)
        if k in ('ols_wp','ols_total'): s._ols(); return
        G=[s.cur]
        if k=='mix':
            n=int(round(1/cat['grid']))
            G+=[np.array([i,j,n-i-j],float)/n for i in range(n+1) for j in range(n+1-i)]
        elif k=='engine':
            lo,hi=cat['bounds'][cat['params'][0]]
            G+=[np.array([round(s.cur[0]+o,4)]) for o in cat['offsets'] if lo-1e-9<=s.cur[0]+o<=hi+1e-9]
        elif k=='engine_ratio':
            lo,hi=cat['ratio_bounds']
            G+=[np.array([s.cur[0]+math.log(r)]) for r in cat['ratios'] if math.log(lo)-1e-9<=s.cur[0]+math.log(r)<=math.log(hi)+1e-9]
        elif k=='linear':
            p=cat['params'][0]; lo,hi=cat['bounds'][p]
            G+=[np.array([round(x,4)]) for x in np.arange(lo,hi+1e-9,cat['grid'])]
        seen=set(); s.G=[]
        for g in G:
            key=tuple(np.round(g,6))
            if key not in seen: seen.add(key); s.G.append(g)
        s.preds=[predict(fr,apply(cat,P,g,O)) for g in s.G]
        L=[]
        for pr in s.preds:
            l,ok=losses(fr,cat['metric'],pr); L.append(l*(ok&fr.train))
        s.cum=np.concatenate([np.zeros((len(s.G),1)),np.cumsum(np.array(L),axis=1)],axis=1)
        s.dist=np.array([steps(cat,s.cur,g) for g in s.G])
    def _ols(s):
        fr,P=s.fr,s.P; pr=predict(fr,P); m=fr.train.astype(float)
        if s.cat['kind']=='ols_wp':
            X=np.column_stack([np.ones(fr.n),pr['m']]); y=fr.am
        else:
            base=pr['t']-(P['wx_dome']*fr.F['dome']+P['wx_wind']*fr.F['windx']+P['wx_cold']*fr.F['coldx'])
            X=np.column_stack([np.ones(fr.n),fr.F['dome'],fr.F['windx'],fr.F['coldx']]); y=fr.at-base
        X=X*m[:,None]; y=y*m
        s.XX=np.concatenate([np.zeros((1,X.shape[1],X.shape[1])),np.cumsum(X[:,:,None]*X[:,None,:],axis=0)])
        s.Xy=np.concatenate([np.zeros((1,X.shape[1])),np.cumsum(X*y[:,None],axis=0)])
        s.yy=np.concatenate([[0.0],np.cumsum(y*y)]); s.nn=np.concatenate([[0],np.cumsum(m)])
    def best(s,i):
        """best-fitting value using only the first i games (games before the week being predicted)"""
        if s.cat['kind'] in ('ols_wp','ols_total'):
            if s.nn[i]<100: return s.cur.copy()
            XX,Xy=s.XX[i],s.Xy[i]; b=np.linalg.solve(XX+1e-9*np.eye(len(Xy)),Xy)
            if s.cat['kind']=='ols_wp':
                rss=s.yy[i]-2*b@Xy+b@XX@b; sd=math.sqrt(max(rss,1e-9)/max(s.nn[i]-2,1))
                return clip(s.cat,np.array([b[0],b[1],sd]))
            return clip(s.cat,b[1:])
        tot=s.cum[:,i]+1e-7*s.dist
        return s.G[int(np.argmin(tot))].copy()
    def pred_at(s,v,idx):
        if s.cat['kind'] in ('engine','engine_ratio'):
            j=int(np.argmin([np.max(np.abs(g-v)) for g in s.G]))
            return {k:x[idx] for k,x in s.preds[j].items()},s.G[j]
        return predict(s.fr,apply(s.cat,s.P,v,s.O),idx),v

# ------------------------------------------------------------------ statistics
def boot(d,cl,seed,B):
    u,inv=np.unique(cl,return_inverse=True); sums=np.bincount(inv,weights=d); cnt=np.bincount(inv).astype(float)
    rng=np.random.default_rng(seed); ix=rng.integers(0,len(u),size=(B,len(u)))
    means=sums[ix].sum(1)/cnt[ix].sum(1)
    return float((1+np.sum(means<=0))/(B+1)),float(np.std(means))
def holm(ps):
    order=sorted(range(len(ps)),key=lambda i:ps[i]); m=len(ps); adj=[1.0]*m; run=0.0
    for rank,i in enumerate(order):
        run=max(run,min(1.0,(m-rank)*ps[i])); adj[i]=run
    return adj
def seed_of(*parts): return zlib.crc32('|'.join(str(p) for p in parts).encode())

def secondary(fr,idx,pb,pc):
    """the other measures a change could quietly damage, baseline vs candidate"""
    out={}
    for met in ('margin','total','logloss'):
        lb,ok=losses(fr,met,pb,idx); lc,_=losses(fr,met,pc,idx)
        out[met]=(float(lb[ok].mean()),float(lc[ok].mean()))
    am,vs=fr.am[idx],fr.vs[idx]
    def ats(pr):
        e=(am-vs)*(pr['m']-vs); k=e!=0
        return 100*float(np.mean(e[k]>0)) if k.any() else 50.0
    out['ats']=(ats(pb),ats(pc)); out['gap']=(float(np.mean(np.abs(pb['m']-vs))),float(np.mean(np.abs(pc['m']-vs))))
    return out

# ------------------------------------------------------------------ the pregame model's candidates
MLAB={'margin':'margin error','total':'total error','margin_total':'average of margin and total error','logloss':'win-probability log loss',
      'blend':'blended-line error','brier':'win-probability Brier score','final_margin':'final-margin error','final_total':'final-total error'}

def evaluate(fr,C,cutoff,review_id,only=None):
    O=origin_params(C); Cur=gm.current(C); P=Cur['params']
    # evaluation seasons: after the launch weights' own fitting window, and no more than the last few seasons
    ev_first=max(min(v['cutoff'][0] for v in C['versions'])+1,int(cutoff[0])-SPEC['eval_last_seasons']+1)
    ev=np.where(fr.season>=ev_first)[0]; weeks=sorted(set(fr.wk[ev].tolist()))
    cands=[]
    for cat in SPEC['categories']:
        if only and cat['id']!=only: continue
        tuners={}
        def tuner(V):
            if V['v'] not in tuners: tuners[V['v']]=Tuner(fr,cat,V['params'],O)
            return tuners[V['v']]
        T=tuner(Cur); best=clip(cat,T.best(fr.n)); cur=T.cur
        res=dict(model='pregame',category=cat['id'],name=cat['name'],what=cat['what'],metric=cat['metric'],
                 from_params={p:P[p] for p in cat['params']},best_params={p:v for p,v in apply(cat,P,best,O).items() if p in cat['params']})
        if not material(cat,cur,best):
            res.update(status='holds',summary='%s: the best-fitting value is within %s of the current weight, so nothing to test.'%(cat['name'],
                       'one grid step' if cat['kind'] not in ('ols_wp','ols_total') else 'the minimum meaningful change'))
            cands.append(res); continue
        onoff=is_off(cur)!=is_off(best); variants=[('full',best)]
        if steps(cat,cur,best)>1+1e-9 and not onoff: variants.append(('step',toward(cat,cur,best,1.0)))
        for vname,target in variants:
            # walk-forward: for every evaluation week, the version in force and the value it would have re-tuned to
            B={k:[] for k in ('m','t','wp','bm','bt')}; Cd={k:[] for k in B}; tuned_hist=[]; order=[]
            for w in weeks:
                idx=np.where(fr.wk==w)[0]; idx=idx[idx>=ev[0]]
                if not len(idx): continue
                V=gm.in_force(C,w//100,w%100); Tv=tuner(V); b=Tv.best(fr.before(w)); base=Tv.cur
                tv=b if vname=='full' else toward(cat,base,b,1.0)
                pb=predict(fr,V['params'],idx); pc,_=Tv.pred_at(clip(cat,tv),idx)
                for k in B: B[k].append(pb[k]); Cd[k].append(pc[k])
                tuned_hist.append(b); order.append(idx)
            idx=np.concatenate(order); pb={k:np.concatenate(v) for k,v in B.items()}; pc={k:np.concatenate(v) for k,v in Cd.items()}
            lb,ok=losses(fr,cat['metric'],pb,idx); lc,_=losses(fr,cat['metric'],pc,idx)
            d=(lb-lc)[ok]; cl=fr.wk[idx][ok]; n=int(ok.sum())
            p,se=boot(d,cl,seed_of(review_id,cat['id'],vname),SPEC['bootstrap'])
            blocks=[]
            for sea in sorted(set(fr.season[idx].tolist())):
                k=(fr.season[idx]==sea)&ok
                blocks.append(dict(season=sea,n=int(k.sum()),base=round(float(lb[k].mean()),4),cand=round(float(lc[k].mean()),4)))
            to=apply(cat,P,clip(cat,target),O)
            ttl=('%s %s → %s'%(cat['name'],fmt_ratio(cat,P,O),fmt_ratio(cat,to,O))) if cat['kind']=='engine_ratio' else '%s %s → %s'%(cat['name'],fmt(cat,P),fmt(cat,to))
            c=dict(res,variant=vname,title=ttl,to_params={p:to[p] for p in cat['params']},steps=round(steps(cat,cur,clip(cat,target)),2),onoff=onoff,
                   turns=('on' if is_off(cur) else 'off') if onoff else None,n=n,base=round(float(lb[ok].mean()),4),cand=round(float(lc[ok].mean()),4),
                   delta=round(float(d.mean()),4),se=round(se,5),p=round(p,5),blocks=blocks,sec=secondary(fr,idx,pb,pc),
                   tuned_spread=round(float(max(steps(cat,tuned_hist[-1],x) for x in tuned_hist[-8:])),2),
                   _evidence=dict(gid=[fr.gid[i] for i in idx],base={k:[round(float(x),4) for x in v] for k,v in pb.items()},
                                  cand={k:[round(float(x),4) for x in v] for k,v in pc.items()}))
            cands.append(c)
    return cands

def rollback_check(fr,C,cutoff,review_id):
    V=gm.current(C)
    if V['how'] not in ('auto','approved'): return None
    prev=max((x for x in C['versions'] if x['v']<V['v']),key=lambda x:x['v'])
    idx=np.where(fr.wk>gm.wk(*V['cutoff']))[0]
    if len(idx)<SPEC['rollback']['min_games']: return dict(version=V['v'],games=int(len(idx)),status='too early')
    pv=predict(fr,V['params'],idx); pp=predict(fr,prev['params'],idx)
    lv,_=losses(fr,'margin_total',pv,idx); lp,_=losses(fr,'margin_total',pp,idx)
    p,_=boot(lv-lp,fr.wk[idx],seed_of(review_id,'rollback'),SPEC['bootstrap'])
    out=dict(version=V['v'],previous=prev['v'],games=int(len(idx)),new=round(float(lv.mean()),4),old=round(float(lp.mean()),4),p=round(p,5))
    out['status']='rolled back' if p<SPEC['rollback']['alpha'] else 'kept'
    return out

# ------------------------------------------------------------------ checking and weighing, the same for both models
def judge(c,m,spec):
    S=spec; SC=S['score']; sec=c['sec']; tol=S['collateral']
    big=[b for b in c['blocks'] if b['n']>=S['min_block_games']]; better=sum(1 for b in big if b['cand']<b['base']); worse=len(big)-better
    col=[k for k in tol if k!=c['metric'] and k in sec and sec[k][1]-sec[k][0]>tol[k]]
    checks=[('enough',c['n']>=S['min_eval_games'],'%d games it never saw (need %d)'%(c['n'],S['min_eval_games'])),
            ('better',c['delta']>0,'%s %s → %s'%(MLAB[c['metric']],nf(c['base']),nf(c['cand']))),
            ('significant',c['p_adj']<S['alpha'],'%.1f%% confidence after correcting for %d idea%s tested (need %.0f%%)'%(100*(1-c['p_adj']),m,'s' if m!=1 else '',100*(1-S['alpha']))),
            ('consistent',better>=S['min_better_blocks'] and worse<=S['max_worse_blocks'],'better in %d of %d seasons with %d+ games'%(better,len(big),S['min_block_games'])),
            ('no_damage',not col,'no other measure worse beyond tolerance' if not col else 'worse on '+', '.join(MLAB.get(k,k) for k in col))]
    c['checks']=[dict(id=a,ok=bool(b),text=t) for a,b,t in checks]
    pros=[]; cons=[]
    z=c['delta']/c['se'] if c['se']>0 else 0.0
    if c['delta']>0: pros.append(('Lower %s on %d games it never saw: %s → %s'%(MLAB[c['metric']],c['n'],nf(c['base']),nf(c['cand'])),min(z,SC['z_cap'])))
    if better>S['min_better_blocks']: pros.append(('Better in %d seasons, more than the %d required'%(better,S['min_better_blocks']),SC['extra_block']*(better-S['min_better_blocks'])))
    for k in tol:
        if k==c['metric'] or k not in sec: continue
        dlt=sec[k][0]-sec[k][1]
        if dlt>tol[k]/2: pros.append(('Also improves %s (%s → %s)'%(MLAB[k],nf(sec[k][0]),nf(sec[k][1])),SC['secondary_better']))
        elif -dlt>tol[k]/4: cons.append(('Slightly worse %s (%s → %s)'%(MLAB[k],nf(sec[k][0]),nf(sec[k][1])),SC['secondary_worse']))
    if 'ats' in sec:
        if sec['ats'][1]-sec['ats'][0]>=1.0: pros.append(('Against the spread %.1f%% → %.1f%%'%tuple(sec['ats']),SC['secondary_better']))
        elif sec['ats'][0]-sec['ats'][1]>=1.0: cons.append(('Against the spread %.1f%% → %.1f%%'%tuple(sec['ats']),SC['secondary_worse']))
    if c['turns']=='off': pros.append(('Simpler: removes a factor',SC['simpler']))
    if c['turns']=='on': cons.append(('Adds a factor the model did not use before',SC['adds_factor']))
    cons.append(('Moves the weight %.1f step%s'%(c['steps'],'' if c['steps']==1 else 's'),SC['move_per_step']*c['steps']))
    if worse: cons.append(('Worse in %d season%s'%(worse,'' if worse==1 else 's'),SC['worse_block']*worse))
    if 'gap' in sec and c['metric'] in ('margin','margin_total') and sec['gap'][1]-sec['gap'][0]>0.1:
        cons.append(('Further from the closing line, which has been the more accurate number (%.2f → %.2f pts apart)'%tuple(sec['gap']),SC['further_from_market']))
    gains=[max(0.0,(b['base']-b['cand'])*b['n']) for b in c['blocks']]
    if sum(gains)>0 and max(gains)/sum(gains)>0.6: cons.append(('Most of the gain comes from one season',SC['concentrated']))
    if 0.01<=c['p_adj']<S['alpha']: cons.append(('Evidence only just clears the bar',SC['near_threshold']))
    if c['tuned_spread']>2.0: cons.append(('The best-fitting value has swung %.1f steps over the last eight weeks'%c['tuned_spread'],SC['unstable']))
    c['pros']=[dict(text=t,pts=round(v,2)) for t,v in pros]; c['cons']=[dict(text=t,pts=round(v,2)) for t,v in cons]
    c['net']=round(sum(v for _,v in pros)-sum(v for _,v in cons),2)
    hard=all(x['ok'] for x in c['checks'])
    c['status']=('watching' if c['delta']>0 else 'rejected') if not hard else ('rejected' if c['net']<=0 else 'passes')
    c['size']='small' if (not c['onoff']) and c['steps']<=1+1e-9 else 'big'
    c['summary']='%s: %s'%(c['title'],'; '.join(x['text'] for x in c['checks'][1:4]))

def flat(d):
    if d is None: return []
    if isinstance(d,dict): return [x for k in sorted(d) for x in flat(d[k])]
    if isinstance(d,list): return [x for v in d for x in flat(v)]
    return [float(d)] if isinstance(d,(int,float)) and not isinstance(d,bool) else []
def direction(c):
    a,b=flat(c['from_params']),flat(c['to_params'])
    if len(a)!=len(b): return 'on' if len(b)>len(a) else 'off'
    if len(a)>12: return 'up' if sum(b)>sum(a) else 'down'
    return ''.join('+' if y>x else '-' for x,y in zip(a,b))

def add_version(C,params,how,note,cutoff,decision):
    v=max(x['v'] for x in C['versions'])+1
    C['versions'].append(dict(v=v,date=today(),cutoff=list(cutoff),how=how,note=note,decision=decision,params=params)); C['current']=v
    return v
def evidence_path(did): return os.path.join(EDIR,did.replace(':','_'))

def adapter(model,book,cutoff,update_history=False):
    """champion, rules, candidates and rollback check for one model; None when its data is not ready"""
    if model=='pregame':
        C=gm.load_champion(); fr=Frame(book,cutoff)
        return dict(C=C,path=gm.CHAMP,spec=SPEC,games=fr.n,cats=CATS,
                    evaluate=lambda rid,only=None: evaluate(fr,C,cutoff,rid,only=only),
                    rollback=lambda rid: rollback_check(fr,C,cutoff,rid),
                    save_ev=lambda path,ev: jsave(path+'.json',ev),
                    drift=lambda cat,to: steps(cat,vec(cat,origin_params(C),origin_params(C)),vec(cat,dict(gm.current(C)['params'],**to),origin_params(C))))
    import learn_live as LL, livemodel as lm
    if not LL.plays_ready(cutoff,update=update_history): return None
    spec=LL.load_spec(); C=lm.load_champion(); P=lm.Plays(first=spec['first_season'],cutoff=cutoff,book=book)
    def drift(cat,to):
        Q=copy.deepcopy(gm.current(C)['params']); Q.update(copy.deepcopy(to))
        return LL.steps(cat,LL.get_vec(cat,origin_params(C)),LL.get_vec(cat,Q))
    return dict(C=C,path=lm.CHAMP,spec=spec,games=int(len(np.unique(P.gid))),cats={c['id']:c for c in spec['categories']},
                evaluate=lambda rid,only=None: LL.evaluate(P,C,cutoff,rid,spec,boot,seed_of,only=only),
                rollback=lambda rid: LL.rollback_check(P,C,cutoff,rid,boot,seed_of,spec),
                save_ev=lambda path,ev: LL.save_evidence(path+'.npz',ev),drift=drift)

def load_state():
    s=jload(P_STATE,{})
    if 'models' not in s: s={'models':{'pregame':s}} if s else {'models':{}}
    return s

def run_model(model,book,cutoff,rid,state,PROPS,update_history):
    A=adapter(model,book,cutoff,update_history); ms=state['models'].setdefault(model,{})
    if A is None:
        print('  %s: play-by-play through %d week %d is not in the history database yet -- its review waits'%(MNAME[model],cutoff[0],cutoff[1])); return None
    C,spec=A['C'],A['spec']; t0=datetime.datetime.now(); applied=[]; proposed=[]; did_auto=False
    info=dict(games=A['games'],champion=C['current'])
    rb=A['rollback'](rid); info['rollback']=rb
    if rb and rb['status']=='rolled back':
        prev=gm.version(C,rb['previous'])
        v=add_version(C,copy.deepcopy(prev['params']),'rollback','Version %d did worse than version %d on the %d games since it went live (%s vs %s); restored.'%(
            rb['version'],rb['previous'],rb['games'],nf(rb['new']),nf(rb['old'])),cutoff,'%s:%s:rollback'%(rid,model))
        applied.append(dict(model=model,category='rollback',version=v)); did_auto=True
        ms.setdefault('changes',{}).setdefault('rollback',[]).append(dict(seq=seq(cutoff),season=cutoff[0],how='rollback',version=v))
    cands=A['evaluate'](rid)
    for c in cands: c['model']=model
    tested=[c for c in cands if c.get('status')!='holds']
    for c,a in zip(tested,holm([c['p'] for c in tested])): c['p_adj']=round(a,5)
    for c in tested: judge(c,len(tested),spec)
    pend=ms.get('pending',{}); newpend={}; ready=[]
    for c in tested:
        if c['status']!='passes': continue
        key='%s|%s|%s'%(c['category'],c['size'],direction(c)); old=pend.get(key)
        if old and A['games']-old['games']>=spec['confirm_min_new_games']:
            c['status']='confirmed'; ready.append(c); newpend[key]=old
        else:
            c['status']='pending'; newpend[key]=old or dict(review=rid,cutoff=cutoff,games=A['games'])
            c['checks'].append(dict(id='confirmed',ok=False,text='first time it passed; must pass again in a later review with new games'))
    ms['pending']=newpend; changes=ms.setdefault('changes',{})
    for c in sorted(ready,key=lambda c:-c['net']):
        cat=A['cats'][c['category']]; hist=changes.setdefault(c['category'],[])
        last=max([x['seq'] for x in hist]+[-99]); season_steps=sum(x.get('steps',0) for x in hist if x.get('how')=='auto' and x.get('season')==cutoff[0])
        c['checks'].append(dict(id='confirmed',ok=True,text='passed in two reviews with new games in between')); did='%s:%s:%s'%(rid,model,c['category'])
        if c['size']=='small' and season_steps+c['steps']<=1+1e-9 and A['drift'](cat,c['to_params'])<=2+1e-9:
            if seq(cutoff)-last<spec['cooldown_weeks']:
                c['status']='pending'; c['checks'].append(dict(id='cooldown',ok=False,text='%s changed %d week(s) ago; waits %d'%(cat['name'],seq(cutoff)-last,spec['cooldown_weeks']))); continue
            if did_auto:
                c['status']='pending'; c['checks'].append(dict(id='one_at_a_time',ok=False,text='another change to this model applied in this review; re-tested next week against it')); continue
            P=copy.deepcopy(gm.current(C)['params']); P.update(copy.deepcopy(c['to_params']))
            v=add_version(C,P,'auto',c['summary'],cutoff,did); c['status']='applied'; c['version']=v; did_auto=True
            hist.append(dict(seq=seq(cutoff),season=cutoff[0],steps=c['steps'],how='auto',version=v))
            applied.append(dict(model=model,category=c['category'],version=v)); A['save_ev'](evidence_path(did),c['_evidence'])
        else:
            dec=ms.get('declined',{}).get(c['category'])
            if dec and seq(cutoff)<dec: c['status']='declined earlier'; continue
            c['status']='proposed'; c['proposal']=did
            reason=('switches a factor %s'%c['turns']) if c['onoff'] else ('moves %.1f steps'%c['steps'] if c['steps']>1 else 'would take this season past one step, or the weight past two steps from launch')
            PROPS[:]=[x for x in PROPS if not (x.get('model','pregame')==model and x['category']==c['category'] and x['status']=='open')]
            PROPS.append(dict(id=did,model=model,category=c['category'],name=c['name'],title=c['title'],status='open',created=today(),cutoff=cutoff,reason=reason,
                              from_params=c['from_params'],to_params=c['to_params'],summary=c['summary'],pros=c['pros'],cons=c['cons'],net=c['net'],m=len(tested)))
            proposed.append(did); A['save_ev'](evidence_path(did),c['_evidence'])
    latest={'%s|%s'%(c['category'],c['variant']):c['_evidence'] for c in tested if c['status'] in ('pending','applied','proposed')}
    if model=='pregame': jsave(os.path.join(EDIR,'latest.json'),dict(review=rid,cutoff=cutoff,candidates=latest))
    else:
        for f in os.listdir(EDIR):
            if f.startswith('latest_live'): os.remove(os.path.join(EDIR,f))
        for key,ev in latest.items(): A['save_ev'](os.path.join(EDIR,'latest_live_'+key.replace('|','_')),ev)
        jsave(os.path.join(EDIR,'latest_live.json'),dict(review=rid,cutoff=cutoff,candidates=sorted(latest)))
    ms['last_cutoff']=list(cutoff); ms['last_games']=A['games']; jsave(A['path'],C)
    info.update(tested=len(tested),champion_after=C['current'],seconds=round((datetime.datetime.now()-t0).total_seconds(),1))
    return dict(info=info,results=[{k:v for k,v in c.items() if not k.startswith('_')} for c in cands],applied=applied,proposed=proposed)

def review(force=False,update_history=False):
    book=gm.Book(); cutoff=latest_cutoff(book); state=load_state(); LOG=jload(P_LOG,[]); PROPS=jload(P_PROPS,[])
    if cutoff is None: print('no completed week yet -- nothing to learn from'); return
    rid='R%d-%02d'%tuple(cutoff)
    due=[m for m in MODELS if force or state['models'].get(m,{}).get('last_cutoff')!=list(cutoff)]
    if not due:
        print('week %d-%02d already reviewed for both models -- nothing new to learn from'%tuple(cutoff)); write_summary(LOG,PROPS,state); return
    rec=next((x for x in LOG if x['id']==rid and 'models' in x),None) or dict(id=rid,cutoff=cutoff,models={},results=[],applied=[],proposed=[])
    rec['date']=today(); new=[]
    for model in due:
        out=run_model(model,book,cutoff,rid,state,PROPS,update_history)
        if out is None: continue
        rec['models'][model]=out['info']
        rec['results']=[r for r in rec['results'] if r.get('model','pregame')!=model]+out['results']
        rec['applied']=[a for a in rec['applied'] if a.get('model','pregame')!=model]+out['applied']
        rec['proposed']=[p for p in rec['proposed'] if not p.startswith('%s:%s:'%(rid,model))]+out['proposed']; new+=out['proposed']
        counts=defaultdict(int)
        for r in out['results']: counts[r['status']]+=1
        print('review %s %s: %d games through %d week %d, %d ideas tested in %.0fs -- %s'%(rid,model,out['info']['games'],cutoff[0],cutoff[1],out['info']['tested'],out['info']['seconds'],dict(counts)))
        if out['info'].get('rollback'): print('  rollback check: %s'%out['info']['rollback'])
        for r in out['results']:
            if r['status']!='holds': print('  %-11s %-18s %s | net %+.2f'%(r['status'],r['category']+'/'+r['variant'],r['summary'][:140],r['net']))
    if not rec['models']: print('nothing reviewed'); return
    rec['tested']=sum(x.get('tested',0) for x in rec['models'].values()); rec['games']=(rec['models'].get('pregame') or {}).get('games')
    LOG=[x for x in LOG if x['id']!=rid]+[rec]; LOG=LOG[-26:]
    jsave(P_LOG,LOG); jsave(P_STATE,state); jsave(P_PROPS,PROPS); write_summary(LOG,PROPS,state)
    os.makedirs(P_NEW,exist_ok=True)
    for f in os.listdir(P_NEW): os.remove(os.path.join(P_NEW,f))
    for x in PROPS:
        if x['id'] in new: open(os.path.join(P_NEW,x['id'].replace(':','_')+'.md'),'w',encoding='utf-8').write(proposal_md(x))

def proposal_md(x):
    L=['## Model change proposal: %s (%s)'%(x['name'],MNAME[x.get('model','pregame')].lower()),'','**%s**'%x['summary'],'','Why it needs your approval: it %s.'%x['reason'],'','**Pros**']
    L+=['- %s (+%.2f)'%(p['text'],p['pts']) for p in x['pros']]+['','**Cons**']+['- %s (−%.2f)'%(p['text'],p['pts']) for p in x['cons']]
    L+=['','Net score: %+.2f'%x['net'],'','To approve: Actions → GridIron refresh → Run workflow, proposal `%s`, decision `approve`. Its evidence is re-checked on the latest games before anything changes. To decline, choose `reject`.'%x['id'],'','Proposal id: `%s`'%x['id']]
    return '\n'.join(L)

def decide(pid,approve,update_history=False):
    PROPS=jload(P_PROPS,[]); state=load_state(); LOG=jload(P_LOG,[])
    x=next((p for p in PROPS if p['id']==pid),None)
    if not x or x['status']!='open': sys.exit('no open proposal %s'%pid)
    model=x.get('model','pregame'); book=gm.Book(); cutoff=latest_cutoff(book); ms=state['models'].setdefault(model,{})
    if not approve:
        x['status']='declined'; x['closed']=today(); ms.setdefault('declined',{})[x['category']]=seq(cutoff)+8
        jsave(P_PROPS,PROPS); jsave(P_STATE,state); write_summary(LOG,PROPS,state); print('declined %s; %s will not be proposed again for 8 weeks'%(pid,x['name'])); return
    A=adapter(model,book,cutoff,update_history)
    if A is None: print('not applied: the data this proposal needs is not loaded'); return
    rid='A%d-%02d'%tuple(cutoff)
    cs=[c for c in A['evaluate'](rid,only=x['category']) if c.get('variant')=='full']; c=cs[0] if cs else None
    if c:   # re-judged with the multiple-testing count of the review that raised it
        c['model']=model; c['p_adj']=round(min(1.0,c['p']*x['m']),5); judge(c,x['m'],A['spec'])
    if c is None or not all(k['ok'] for k in c['checks']) or c['net']<=0:
        x['status']='expired'; x['closed']=today(); x['why']='the evidence no longer holds on the latest games' if c else 'the best-fitting value has moved back within the minimum change'
        jsave(P_PROPS,PROPS); write_summary(LOG,PROPS,state); print('not applied: %s'%x['why']); return
    C=A['C']; P=copy.deepcopy(gm.current(C)['params']); P.update(copy.deepcopy(c['to_params']))
    v=add_version(C,P,'approved','Approved by the owner. '+c['summary'],cutoff,pid)
    x.update(status='approved',closed=today(),version=v,applied_params=c['to_params'])
    ms.setdefault('changes',{}).setdefault(x['category'],[]).append(dict(seq=seq(cutoff),season=cutoff[0],steps=c['steps'],how='approved',version=v))
    A['save_ev'](evidence_path(pid+':approved'),c['_evidence'])
    jsave(A['path'],C); jsave(P_PROPS,PROPS); jsave(P_STATE,state); write_summary(LOG,PROPS,state)
    print('approved %s -> %s weights version %d: %s'%(pid,model,v,c['summary']))

def write_summary(LOG,PROPS,state):
    import livemodel as lm, learn_live as LL
    Cp=gm.load_champion(); Cl=lm.load_champion(); specl=LL.load_spec(); O=origin_params(Cp)
    Pp=gm.current(Cp)['params']; Pl=gm.current(Cl)['params']; last=LOG[-1] if LOG else None
    def statuses(model):
        res={}
        for r in (last or {}).get('results',[]):
            if r.get('model','pregame')==model and r.get('variant') in (None,'full'): res.setdefault(r['category'],r)
        for r in (last or {}).get('results',[]):
            if r.get('model','pregame')==model and r['status'] in ('applied','proposed','pending','confirmed'): res[r['category']]=r
        return res
    weights=[]
    for model,C,spec,P in (('pregame',Cp,SPEC,Pp),('live',Cl,specl,Pl)):
        res=statuses(model)
        for cat in spec['categories']:
            if model=='pregame':
                value=fmt_ratio(cat,P,O) if cat['kind']=='engine_ratio' else fmt(cat,P)
                changed=lambda a,b,cat=cat:any(a[p]!=b[p] for p in cat['params'])
            else:
                value=LL.fmt(cat,P); changed=lambda a,b,cat=cat:LL.get_vec(cat,a).tolist()!=LL.get_vec(cat,b).tolist()
            ch=[v for v in C['versions'] if v['v']>1 and changed(v['params'],gm.version(C,v['v']-1)['params'])]
            r=res.get(cat['id'])
            weights.append(dict(model=model,id=cat['id'],name=cat['name'],what=cat['what'],value=value,status=(r or {}).get('status','not reviewed yet'),
                                note=(r or {}).get('summary'),last_change=dict(v=ch[-1]['v'],date=ch[-1]['date'],how=ch[-1]['how']) if ch else None))
    notable=[]
    for rev in reversed(LOG):
        for r in rev.get('results',[]):
            if r['status'] in ('applied','proposed','pending','confirmed','watching') or (r['status']=='rejected' and r.get('delta',0)>0):
                notable.append(dict(review=rev['id'],date=rev['date'],model=r.get('model','pregame'),**{k:r.get(k) for k in ('category','name','variant','status','title','summary','pros','cons','net','checks','n','base','cand','delta','p_adj','blocks','metric','steps')}))
        if len(notable)>=14: break
    S=dict(updated=today(),models=MNAME,
           champion=dict(v=Cp['current'],date=gm.current(Cp)['date'],how=gm.current(Cp)['how'],versions=len(Cp['versions'])),
           live_champion=dict(v=Cl['current'],date=gm.current(Cl)['date'],how=gm.current(Cl)['how'],versions=len(Cl['versions'])),
           params=Pp,live_params=Pl,
           last_review=None if not last else dict(id=last['id'],date=last['date'],cutoff=last['cutoff'],games=last.get('games'),tested=last.get('tested',0),
               applied=last['applied'],proposed=last['proposed'],models=last.get('models',{})),
           weights=weights,decisions=notable[:14],proposals=[p for p in PROPS if p['status']=='open'],
           history=[dict(v=v['v'],date=v['date'],how=v['how'],note=v['note']) for v in Cp['versions']],
           live_history=[dict(v=v['v'],date=v['date'],how=v['how'],note=v['note']) for v in Cl['versions']],
           rules=dict(alpha=SPEC['alpha'],min_games=SPEC['min_eval_games'],better_blocks=SPEC['min_better_blocks'],cooldown=SPEC['cooldown_weeks'],seasons=SPEC['eval_last_seasons']))
    jsave(P_SUM,S)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('cmd',choices=['review','approve','reject','status']); ap.add_argument('id',nargs='?')
    ap.add_argument('--force',action='store_true'); ap.add_argument('--update-history',action='store_true')
    a=ap.parse_args()
    if a.cmd=='review': review(a.force,a.update_history)
    elif a.cmd in ('approve','reject'): decide(a.id,a.cmd=='approve',a.update_history)
    else:
        S=jload(P_SUM,None); print(json.dumps(S and dict(champion=S['champion'],live_champion=S.get('live_champion'),last_review=S['last_review'],proposals=[p['id'] for p in S['proposals']]),indent=1))
