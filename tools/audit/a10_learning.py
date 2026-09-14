"""The learning loop: the weights registry, the rules every change since launch had to follow, the internal logic of
the latest review, and the evidence behind its decisions recomputed from raw final scores."""
import os, json, math, zlib
from collections import defaultdict
import numpy as np
from common import num, rows, DATA, PIPE

def holm(ps):
    order=sorted(range(len(ps)),key=lambda i:ps[i]); m=len(ps); adj=[1.0]*m; run=0.0
    for rank,i in enumerate(order):
        run=max(run,min(1.0,(m-rank)*ps[i])); adj[i]=run
    return adj
def jl(p,fb):
    return json.load(open(p,encoding='utf-8')) if os.path.exists(p) else fb

def run(A):
    A.section('learning loop'); D=A.D
    L=os.path.join(PIPE,'learning'); SPEC=jl(os.path.join(L,'spec.json'),None); CH=jl(os.path.join(PIPE,'champion.json'),None)
    if not SPEC or not CH:
        A.check('LG1','The weights registry and learning rules exist',['pipeline/champion.json or pipeline/learning/spec.json is missing']); return
    LOG=jl(os.path.join(L,'log.json'),[]); PROPS=jl(os.path.join(L,'proposals.json'),[])
    VS=sorted(CH['versions'],key=lambda v:v['v']); O=VS[0]['params']; allp=[p for c in SPEC['categories'] for p in c['params']]
    cur=next((v for v in VS if v['v']==CH['current']),None)

    bad=[]
    if [v['v'] for v in VS]!=list(range(1,len(VS)+1)): bad.append('versions are not numbered 1..%d'%len(VS))
    if not cur: bad.append('current version %s is not in the registry'%CH['current'])
    for v in VS:
        P=v['params']; miss=[p for p in allp if p not in P]
        if miss: bad.append('version %d lacks %s'%(v['v'],miss)); continue
        for c in SPEC['categories']:
            if c['kind']=='mix':
                if abs(sum(P[p] for p in c['params'])-1)>0.011 or any(not 0<=P[p]<=1 for p in c['params']): bad.append('version %d rating mix %s does not sum to 1'%(v['v'],[P[p] for p in c['params']]))
            elif c['kind']=='engine_ratio':
                lo,hi=c['ratio_bounds']
                for p in c['params']:
                    if not lo-1e-6<=P[p]/O[p]<=hi+1e-6: bad.append('version %d %s is %.2fx its launch value (allowed %s-%s)'%(v['v'],p,P[p]/O[p],lo,hi))
            else:
                for p,(lo,hi) in (c.get('bounds') or {}).items():
                    if not lo-1e-9<=P[p]<=hi+1e-9: bad.append('version %d %s=%s outside [%s, %s]'%(v['v'],p,P[p],lo,hi))
    A.check('LG1','The weights registry is complete, numbered in order, and every weight sits inside its allowed range',bad,len(VS))

    bad=[]; tested={}
    for rev in LOG:
        for r in rev.get('results',[]):
            if r.get('status') in ('applied','proposed'): tested['%s:%s'%(rev['id'],r['category'])]=(rev,r)
    autos=defaultdict(list); per_cut=defaultdict(int)
    for v in VS[1:]:
        prev=VS[v['v']-2]; changed=[p for p in allp if v['params'][p]!=prev['params'][p]]
        cats={c['id'] for c in SPEC['categories'] if any(p in c['params'] for p in changed)}
        if v['how']=='auto':
            rr=tested.get(v.get('decision'))
            if not rr: bad.append('version %d: automatic change %s has no review record'%(v['v'],v.get('decision'))); continue
            rev,r=rr
            if cats!={r['category']}: bad.append('version %d changed %s but the review tested %s'%(v['v'],sorted(cats),r['category']))
            if r.get('size')!='small' or r.get('steps',9)>1+1e-9: bad.append('version %d: automatic change was not small (%s steps)'%(v['v'],r.get('steps')))
            if not all(c['ok'] for c in r.get('checks',[])) or not any(c['id']=='confirmed' and c['ok'] for c in r.get('checks',[])): bad.append('version %d: applied without passing and confirming every check'%v['v'])
            if r.get('net',0)<=0 or r.get('p_adj',1)>=SPEC['alpha']: bad.append('version %d: net %s, corrected p %s'%(v['v'],r.get('net'),r.get('p_adj')))
            if any(abs(v['params'][p]-x)>1e-9 for p,x in r['to_params'].items()): bad.append('version %d: applied values differ from the values tested'%v['v'])
            autos[r['category']].append((v['cutoff'][0]*18+min(v['cutoff'][1],18),v['cutoff'][0],r['steps'])); per_cut[tuple(v['cutoff'])]+=1
        elif v['how']=='approved':
            pr=next((x for x in PROPS if x['id']==v.get('decision')),None)
            if not pr or pr['status']!='approved' or pr.get('version')!=v['v']: bad.append('version %d: approval %s is not on record'%(v['v'],v.get('decision')))
        elif v['how']=='rollback':
            if not any(x['params']==v['params'] for x in VS if x['v']<v['v']-1): bad.append('version %d: a rollback must restore an earlier version exactly'%v['v'])
        else: bad.append('version %d: unknown change type %r'%(v['v'],v['how']))
    for cat,xs in autos.items():
        xs.sort()
        if any(b[0]-a[0]<SPEC['cooldown_weeks'] for a,b in zip(xs,xs[1:])): bad.append('%s changed automatically inside the %d-week cooldown'%(cat,SPEC['cooldown_weeks']))
        by=defaultdict(float)
        for _,sea,st in xs: by[sea]+=st
        if any(v>1+1e-9 for v in by.values()): bad.append('%s moved more than one step automatically in a season %s'%(cat,dict(by)))
    if any(n>1 for n in per_cut.values()): bad.append('more than one automatic change in a single review')
    A.check('LG2','Every change since launch followed the rules: small moves confirmed in two reviews with every check passed, one at a time, big ones approved by the owner',bad,len(VS)-1)

    rev=LOG[-1] if LOG else None
    if not rev:
        A.warn('LG3','No model review has run yet',['the loop has not reviewed a completed week'],1); return
    bad=[]; T=[r for r in rev['results'] if r['status']!='holds']
    for r,a in zip(T,holm([r['p'] for r in T])):
        n='%s/%s'%(r['category'],r.get('variant'))
        if abs(a-r['p_adj'])>1e-4: bad.append('%s corrected p %s, recompute %.5f'%(n,r['p_adj'],a))
        ck={c['id']:c['ok'] for c in r['checks']}
        big=[b for b in r['blocks'] if b['n']>=SPEC['min_block_games']]; better=sum(1 for b in big if b['cand']<b['base'])
        want=dict(enough=r['n']>=SPEC['min_eval_games'],better=r['delta']>0,significant=a<SPEC['alpha'],
                  consistent=better>=SPEC['min_better_blocks'] and len(big)-better<=SPEC['max_worse_blocks'])
        for k,v in want.items():
            if ck.get(k)!=v: bad.append('%s check %s says %s, the numbers say %s'%(n,k,ck.get(k),v))
        if abs(round(sum(x['pts'] for x in r['pros'])-sum(x['pts'] for x in r['cons']),2)-r['net'])>0.021: bad.append('%s pros minus cons is not the net score %s'%(n,r['net']))
        if abs((r['base']-r['cand'])-r['delta'])>0.0011: bad.append('%s delta %s != %s - %s'%(n,r['delta'],r['base'],r['cand']))
        nb=sum(b['n'] for b in r['blocks'])
        if nb!=r['n'] or abs(sum(b['base']*b['n'] for b in r['blocks'])/max(nb,1)-r['base'])>0.002: bad.append('%s season blocks do not add up to the pooled result'%n)
        if any(b['season']<=VS[0]['cutoff'][0] or b['season']>rev['cutoff'][0] for b in r['blocks']): bad.append('%s was judged on seasons the launch weights were fitted on, or after the cutoff'%n)
        hard=all(ck.get(k) for k in ('enough','better','significant','consistent','no_damage')); st=r['status']
        if not hard and st not in ('watching','rejected'): bad.append('%s failed a check but is %s'%(n,st))
        if hard and r['net']<=0 and st!='rejected': bad.append('%s has more cons than pros but is %s'%(n,st))
        if hard and r['net']>0 and st not in ('pending','confirmed','applied','proposed','declined earlier'): bad.append('%s passed everything but is %s'%(n,st))
        if st=='watching' and r['delta']<=0: bad.append('%s is watched although it did worse'%n)
    A.check('LG3','The latest review is internally consistent: multiple-testing corrections, each check, pros minus cons, and every verdict',bad,len(T))

    GA={r['game_id']:r for r in rows(os.path.join(DATA,'games_all.csv')) if r['game_type']=='REG'}
    E=jl(os.path.join(L,'evidence','latest.json'),{}); bad=[]; cnt=0
    if E and E.get('review')==rev['id']:
        for key,ev in E.get('candidates',{}).items():
            cat,variant=key.split('|'); r=next((x for x in rev['results'] if x['category']==cat and x.get('variant')==variant),None)
            if not r: bad.append('evidence for %s has no review result'%key); continue
            cnt+=1; g=[GA[x] for x in ev['gid']]
            if any((int(x['season']),int(x['week']))>tuple(rev['cutoff']) or int(x['season'])<=VS[0]['cutoff'][0] for x in g): bad.append('%s evidence includes games outside the evaluation window'%key)
            am=np.array([num(x['home_score'])-num(x['away_score']) for x in g]); at=np.array([num(x['home_score'])+num(x['away_score']) for x in g])
            def loss(pr):
                P={k:np.array(v,float) for k,v in pr.items()}; met=r['metric']; ok=np.ones(len(am),bool)
                if met=='margin': return np.abs(P['m']-am),ok
                if met=='total': return np.abs(P['t']-at),ok
                if met=='margin_total': return (np.abs(P['m']-am)+np.abs(P['t']-at))/2,ok
                if met=='logloss':
                    p=np.clip(P['wp'],1e-6,1-1e-6); y=(am>0).astype(float); ok=am!=0; return np.where(ok,-(y*np.log(p)+(1-y)*np.log(1-p)),0),ok
                ok=~np.isnan(P['bt']); return np.where(ok,(np.abs(P['bm']-am)+np.abs(np.nan_to_num(P['bt'])-at))/2,0),ok
            lb,ok=loss(ev['base']); lc,_=loss(ev['cand']); d=(lb-lc)[ok]
            if abs(lb[ok].mean()-r['base'])>0.003 or abs(lc[ok].mean()-r['cand'])>0.003: bad.append('%s: recorded %.4f -> %.4f, raw scores give %.4f -> %.4f'%(key,r['base'],r['cand'],lb[ok].mean(),lc[ok].mean()))
            cl=np.array([int(x['season'])*100+int(x['week']) for x in g])[ok]; u,inv=np.unique(cl,return_inverse=True)
            sums=np.bincount(inv,weights=d); cn=np.bincount(inv).astype(float)
            ix=np.random.default_rng(zlib.crc32(('%s|%s|%s'%(rev['id'],cat,variant)).encode())).integers(0,len(u),size=(SPEC['bootstrap'],len(u)))
            p=(1+np.sum(sums[ix].sum(1)/cn[ix].sum(1)<=0))/(SPEC['bootstrap']+1)
            if abs(p-r['p'])>0.005: bad.append('%s: recorded p %.4f, recompute %.4f'%(key,r['p'],p))
    A.check('LG4','Evidence behind every pending, applied or proposed change in the latest review recomputes from raw final scores',bad,cnt)

    bad=[]; Lp=D.get('learn') or {}
    if cur and Lp.get('params')!=cur['params']: bad.append('the published data carries different weights from the current champion')
    if Lp.get('version')!=CH['current']: bad.append('published weights version %s, champion %s'%(Lp.get('version'),CH['current']))
    if (Lp.get('last_review') or {}).get('id')!=rev['id']: bad.append('page reports review %s, latest is %s'%((Lp.get('last_review') or {}).get('id'),rev['id']))
    if sorted(w['id'] for w in Lp.get('weights',[]))!=sorted(c['id'] for c in SPEC['categories']): bad.append('page weight list does not cover every weight group')
    if sorted(p['id'] for p in Lp.get('proposals',[]))!=sorted(p['id'] for p in PROPS if p['status']=='open'): bad.append('page proposals differ from the open proposals on record')
    A.check('LG5','The published data carries the current weights, the latest review and every open proposal',bad)
