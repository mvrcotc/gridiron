"""The live in-game model's part of the weekly review (learn.py runs it). Same process as the pregame model:
for every week of the evaluation seasons, re-fit one part of the live model on plays before that week, then score it
play by play against the live weights that were in force, on games neither side saw."""
import os, sys, json, math, copy, subprocess
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0,HERE)
import gamemodel as gm, livemodel as lm

SPEC_PATH=os.path.join(HERE,'learning','spec_live.json')
def load_spec(): return json.load(open(SPEC_PATH,encoding='utf-8'))
TOP={'ep':'ep','margin':'margin','spread':'margin','platt':'platt','total':'total','market':'margin','market_total':'total'}
MARKET=('market','market_total')   # switches: absent means off

def plays_ready(cutoff,update=False):
    """the history database has plays through the cutoff week; optionally load the newest play-by-play first"""
    have=lm.plays_through()
    if (have is None or have<gm.wk(*cutoff)) and update:
        r=subprocess.run([sys.executable,os.path.join(HERE,'history.py'),'--from','2019','--tables','plays,player_week'],capture_output=True,text=True)
        print('  history database update: %s'%((r.stdout or r.stderr).strip().split('\n')[-1][:140]),flush=True)
        have=lm.plays_through()
    return have is not None and have>=gm.wk(*cutoff)

# ------------------------------------------------------------------ one part of the live model as a point in a small space
def get_vec(cat,prm):
    k=cat['kind']
    if k=='ep': return np.array(prm['ep']['table'],float).reshape(-1)
    if k=='platt':
        pl=prm.get('platt'); return np.array([0.0,1.0]) if not pl else np.array([pl['alpha'],pl['beta']],float)
    return np.array([prm[TOP[k]].get(p,0.0) if k in MARKET else prm[TOP[k]][p] for p in cat['params']],float)
def set_vec(cat,prm,v):
    Q=copy.deepcopy(prm); k=cat['kind']
    if k=='ep': Q['ep']['table']=np.round(np.asarray(v,float).reshape(len(lm.YB)-1,4,len(lm.DD)-1),3).tolist()
    elif k=='platt': Q['platt']=dict(alpha=round(float(v[0]),5),beta=round(float(v[1]),5))
    else:
        for p,x in zip(cat['params'],v): Q[TOP[k]][p]=round(float(x),4)
    return Q
def steps(cat,a,b):
    if cat['kind']=='ep': return float(np.mean(np.abs(b-a)))/cat['step']
    return float(np.max(np.abs(b-a)/np.array([cat['step'][p] for p in cat['params']])))
def material(cat,a,b):
    if cat['kind']=='ep': return float(np.mean(np.abs(b-a)))>=cat['min_change']-1e-9
    return bool(np.any(np.abs(b-a)>=np.array([cat['min_change'][p] for p in cat['params']])-1e-9))
def clip(cat,v):
    if cat['kind']=='ep': return v
    return np.array([min(max(x,cat['bounds'][p][0]),cat['bounds'][p][1]) for p,x in zip(cat['params'],v)])
def toward(cat,a,b,limit=1.0):
    s=steps(cat,a,b); return b.copy() if s<=limit+1e-9 else a+(b-a)*(limit/s)
def fmt(cat,prm):
    k=cat['kind']
    if k=='ep':
        t=np.array(prm['ep']['table']); return '1st & 10 at own 25: %+.2f pts, midfield: %+.2f, opponent 20: %+.2f'%(t[7][0][2],t[4][0][2],t[1][0][2])
    if k=='margin': m=prm['margin']; return 'possession %.3f, pregame %.3f, clock %+.3f'%(m['a_ep'],m['b_prior'],m['c_frac'])
    if k=='spread': m=prm['margin']; return 'spread %.2f, floor %.2f'%(m['sigma'],m['eps'])
    if k=='platt':
        pl=prm.get('platt'); return 'off' if not pl else 'shift %+.3f, stretch %.3f'%(pl['alpha'],pl['beta'])
    if k in MARKET:
        w=prm[TOP[k]].get('w_market',0.0)
        return ('off (GridIron\'s own %s)'%('margin' if k=='market' else 'total')) if not w else 'betting line %.0f%%, GridIron %.0f%%'%(100*w,100*(1-w))
    t=prm['total']; return 'pregame %.3f, clock %.2f, possession %.3f'%(t['t_prior'],t['t_frac'],t['t_ep'])

def refit(cat,P,prm):
    """this part's best value on all plays in P, every other part held at prm"""
    k=cat['kind']
    if k=='ep': return np.array(lm.fit_ep(P),float).reshape(-1)
    EPH=lm.ep_home(P,prm['ep']['table'])
    if k in MARKET: return np.array([lm.fit_market_weight(P,None,prm,EPH,TOP[k])])
    if k=='margin': M=lm.fit_margin(P,None,EPH,w=prm['margin'].get('w_market',0.0)); return np.array([M[p] for p in cat['params']])
    if k=='spread':
        S=lm.fit_spread(P,None,P.RES-lm.mean_margin(P,prm['margin'],EPH),start=(prm['margin']['sigma'],prm['margin']['eps']))
        return np.array([S['sigma'],S['eps']])
    if k=='platt': pl=lm.fit_platt(P,None,lm.raw_wp(P,prm['margin'],EPH)); return np.array([pl['alpha'],pl['beta']])
    T=lm.fit_total(P,None,EPH,w=prm['total'].get('w_market',0.0)); return np.array([T[p] for p in cat['params']])

def losses(metric,P,pr):
    ones=np.ones(P.n,bool)
    if metric=='logloss':
        p=np.clip(pr['wp'],1e-6,1-1e-6); return np.where(P.decided,-(P.y*np.log(p)+(1-P.y)*np.log(1-p)),0.0),P.decided
    if metric=='brier': return np.where(P.decided,(pr['wp']-P.y)**2,0.0),P.decided
    if metric=='final_margin': return np.abs(pr['mm']-P.RES),ones
    if metric=='final_total': return np.abs(pr['tt']-P.TOT),ones
    raise ValueError(metric)

def evaluate(P,C,cutoff,rid,spec,boot,seed_of,only=None):
    cur=gm.current(C); prm=cur['params']
    ev_first=max(min(v['cutoff'][0] for v in C['versions'])+1,int(cutoff[0])-spec['eval_last_seasons']+1)
    weeks=sorted(set(P.wk[P.season>=ev_first].tolist())); out=[]
    i0=P.before(weeks[0]) if weeks else P.n
    S_all=P.view(i0,P.n)
    for cat in spec['categories']:
        if only and cat['id']!=only: continue
        curv=get_vec(cat,prm); off=(cat['kind']=='platt' and not prm.get('platt')) or (cat['kind'] in MARKET and not prm[TOP[cat['kind']]].get('w_market')); best=clip(cat,refit(cat,P,prm))
        res=dict(model='live',category=cat['id'],name=cat['name'],what=cat['what'],metric=cat['metric'])
        if not material(cat,curv,best) and (not off or cat['kind'] in MARKET):   # a switch whose best value is still off holds too
            res.update(status='holds',summary='%s: the best-fitting value is within the minimum meaningful change of the current one, so nothing to test.'%cat['name'])
            out.append(res); continue
        variants=[('full',best)]
        if not off and steps(cat,curv,best)>1+1e-9: variants.append(('step',toward(cat,curv,best)))
        wk_fits=[]
        for w in weeks:
            i,j=P.before(w),P.before(w+1); V=gm.in_force(C,w//100,w%100)
            b=clip(cat,refit(cat,P.view(0,i),V['params'])); wk_fits.append((i,j,V,b,get_vec(cat,V['params'])))
        for vname,target in variants:
            PB={k:[] for k in ('wp','mm','tt')}; PC={k:[] for k in PB}
            for i,j,V,b,base in wk_fits:
                if j<=i: continue
                S=P.view(i,j); tv=b if vname=='full' else toward(cat,base,b)
                pb=lm.predict(S,V['params']); pc=lm.predict(S,set_vec(cat,V['params'],tv))
                for k in PB: PB[k].append(pb[k]); PC[k].append(pc[k])
            PB={k:np.concatenate(v) for k,v in PB.items()}; PC={k:np.concatenate(v) for k,v in PC.items()}
            lb,ok=losses(cat['metric'],S_all,PB); lc,_=losses(cat['metric'],S_all,PC)
            d=(lb-lc)[ok]; p,se=boot(d,S_all.wk[ok],seed_of(rid,'live',cat['id'],vname),spec['bootstrap'])
            blocks=[]
            for sea in sorted(set(S_all.season.tolist())):
                k=(S_all.season==sea)&ok
                blocks.append(dict(season=int(sea),n=int(len(np.unique(S_all.gid[S_all.season==sea]))),base=round(float(lb[k].mean()),5),cand=round(float(lc[k].mean()),5)))
            sec={}
            for met in ('logloss','brier','final_margin','final_total'):
                a,okm=losses(met,S_all,PB); c2,_=losses(met,S_all,PC); sec[met]=(float(a[okm].mean()),float(c2[okm].mean()))
            to=set_vec(cat,prm,clip(cat,target)); top=TOP[cat['kind']]
            tuned=[x[3] for x in wk_fits]
            c=dict(res,variant=vname,title='%s %s → %s'%(cat['name'],fmt(cat,prm),fmt(cat,to)),
                   from_params={top:copy.deepcopy(prm.get(top))},to_params={top:copy.deepcopy(to[top])},
                   steps=round(steps(cat,curv,clip(cat,target)),2),onoff=off,turns='on' if off else None,
                   n=int(len(np.unique(S_all.gid))),plays=int(ok.sum()),base=round(float(lb[ok].mean()),5),cand=round(float(lc[ok].mean()),5),
                   delta=round(float(d.mean()),5),se=round(se,6),p=round(p,5),blocks=blocks,sec=sec,
                   tuned_spread=round(float(max(steps(cat,tuned[-1],x) for x in tuned[-8:])),2) if tuned else 0.0,
                   _evidence=dict(gid=S_all.gid,wk=S_all.wk,**{'base_'+k:v.astype(np.float32) for k,v in PB.items()},**{'cand_'+k:v.astype(np.float32) for k,v in PC.items()}))
            out.append(c)
    return out

def rollback_check(P,C,cutoff,rid,boot,seed_of,spec):
    V=gm.current(C)
    if V['how'] not in ('auto','approved'): return None
    prev=max((x for x in C['versions'] if x['v']<V['v']),key=lambda x:x['v'])
    i=P.before(gm.wk(*V['cutoff'])+1); S=P.view(i,P.n); games=int(len(np.unique(S.gid)))
    if games<max(1,spec['rollback']['min_games']): return dict(version=V['v'],games=games,status='too early')
    lv,ok=losses('logloss',S,lm.predict(S,V['params'])); lp,_=losses('logloss',S,lm.predict(S,prev['params']))
    p,_=boot((lv-lp)[ok],S.wk[ok],seed_of(rid,'live','rollback'),spec['bootstrap'])
    out=dict(version=V['v'],previous=prev['v'],games=games,new=round(float(lv[ok].mean()),5),old=round(float(lp[ok].mean()),5),p=round(p,5))
    out['status']='rolled back' if p<spec['rollback']['alpha'] else 'kept'
    return out

def save_evidence(path,ev): np.savez_compressed(path,**ev)
