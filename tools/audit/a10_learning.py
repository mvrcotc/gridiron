"""The learning loop, for both the pregame odds model and the live in-game model: the weights registries, the rules every
change since launch had to follow, the internal logic of the latest review, and the evidence behind its decisions
recomputed from raw final scores."""
import os, json, math, zlib
from collections import defaultdict
import numpy as np
from common import num, rows, DATA, PIPE

def holm(ps):
    order=sorted(range(len(ps)),key=lambda i:ps[i]); m=len(ps); adj=[1.0]*m; run=0.0
    for rank,i in enumerate(order):
        run=max(run,min(1.0,(m-rank)*ps[i])); adj[i]=run
    return adj
def jl(p,fb): return json.load(open(p,encoding='utf-8')) if os.path.exists(p) else fb
TOP={'ep':'ep','margin':'margin','spread':'margin','platt':'platt','total':'total','market':'margin','market_total':'total'}
MARKET=('market','market_total')
def cat_values(model,c,P):
    """the numbers a weight group controls, for comparing versions"""
    if model in ('pregame','players'): return [P[p] for p in c['params']]
    if c['kind']=='ep': return P['ep']['table']
    if c['kind']=='platt': return P.get('platt')
    return [P[TOP[c['kind']]].get(p,0.0) if c['kind'] in MARKET else P[TOP[c['kind']]][p] for p in c['params']]
def boot_p(d,cl,seed,B):
    u,inv=np.unique(cl,return_inverse=True); sums=np.bincount(inv,weights=d); cn=np.bincount(inv).astype(float)
    ix=np.random.default_rng(seed).integers(0,len(u),size=(B,len(u)))
    return (1+np.sum(sums[ix].sum(1)/cn[ix].sum(1)<=0))/(B+1)

def run(A):
    A.section('learning loop'); D=A.D; L=os.path.join(PIPE,'learning')
    REG=[('pregame',jl(os.path.join(PIPE,'champion.json'),None),jl(os.path.join(L,'spec.json'),None)),
         ('live',jl(os.path.join(PIPE,'champion_live.json'),None),jl(os.path.join(L,'spec_live.json'),None)),
         ('players',jl(os.path.join(PIPE,'champion_players.json'),None),jl(os.path.join(L,'spec_players.json'),None))]
    if any(C is None or S is None for _,C,S in REG):
        A.check('LG1','The weights registries and learning rules exist',['a champion_*.json registry or learning/spec_*.json rules file is missing']); return
    LOG=jl(os.path.join(L,'log.json'),[]); PROPS=jl(os.path.join(L,'proposals.json'),[])

    bad=[]; nv=0
    for model,CH,SPEC in REG:
        VS=sorted(CH['versions'],key=lambda v:v['v']); O=VS[0]['params']; nv+=len(VS)
        if [v['v'] for v in VS]!=list(range(1,len(VS)+1)): bad.append('%s versions are not numbered 1..%d'%(model,len(VS)))
        if CH['current'] not in [v['v'] for v in VS]: bad.append('%s current version %s is not in the registry'%(model,CH['current']))
        for v in VS:
            P=v['params']; tag='%s version %d'%(model,v['v'])
            if model=='pregame':
                miss=[p for c in SPEC['categories'] for p in c['params'] if p not in P]
                if miss: bad.append('%s lacks %s'%(tag,miss)); continue
                for c in SPEC['categories']:
                    if c['kind']=='mix':
                        if abs(sum(P[p] for p in c['params'])-1)>0.011 or any(not 0<=P[p]<=1 for p in c['params']): bad.append('%s rating mix does not sum to 1'%tag)
                    elif c['kind']=='engine_ratio':
                        lo,hi=c['ratio_bounds']
                        if any(not lo-1e-6<=P[p]/O[p]<=hi+1e-6 for p in c['params']): bad.append('%s %s outside %s-%s of launch values'%(tag,c['id'],lo,hi))
                    else:
                        for p,(lo,hi) in (c.get('bounds') or {}).items():
                            if not lo-1e-9<=P[p]<=hi+1e-9: bad.append('%s %s=%s outside [%s, %s]'%(tag,p,P[p],lo,hi))
            elif model=='players':
                miss=[p for c in SPEC['categories'] for p in c['params'] if p not in P]
                if miss: bad.append('%s lacks %s'%(tag,miss)); continue
                for c in SPEC['categories']:
                    if c['kind']=='ratio':
                        lo,hi=c['ratio_bounds']
                        if any(not lo-1e-6<=P[p]/O[p]<=hi+1e-6 for p in c['params']): bad.append('%s %s outside %s-%s of launch values'%(tag,c['id'],lo,hi))
                    else:
                        for p,(lo,hi) in c['bounds'].items():
                            if not lo-1e-9<=P[p]<=hi+1e-9: bad.append('%s %s=%s outside [%s, %s]'%(tag,p,P[p],lo,hi))
            else:
                if any(k not in P for k in ('ep','margin','total','platt')): bad.append('%s lacks a part of the live model'%tag); continue
                if np.array(P['ep']['table']).shape!=(10,4,4): bad.append('%s possession-value table is not 10x4x4'%tag)
                for c in SPEC['categories']:
                    if c['kind']=='ep' or (c['kind']=='platt' and not P.get('platt')): continue
                    for p,(lo,hi) in c['bounds'].items():
                        x=P[TOP[c['kind']]].get(p,0.0) if c['kind'] in MARKET else P[TOP[c['kind']]][p]
                        if not lo-1e-9<=x<=hi+1e-9: bad.append('%s %s=%s outside [%s, %s]'%(tag,p,x,lo,hi))
    A.check('LG1','Every weights registry (pregame, live, players) is complete, numbered in order, and every weight sits inside its allowed range',bad,nv)

    bad=[]; nchg=0
    tested=dict(jl(os.path.join(L,'decisions.json'),{}))     # permanent decision records; the review log only keeps recent weeks
    for rev in LOG:
        for r in rev.get('results',[]):
            if r.get('status') in ('applied','proposed'):
                tested.setdefault('%s:%s:%s'%(rev['id'],r.get('model','pregame'),r['category']),r)
    for model,CH,SPEC in REG:
        VS=sorted(CH['versions'],key=lambda v:v['v']); autos=defaultdict(list); per_cut=defaultdict(int)
        for v in VS[1:]:
            nchg+=1; prev=VS[v['v']-2]; tag='%s version %d'%(model,v['v'])
            cats={c['id'] for c in SPEC['categories'] if cat_values(model,c,v['params'])!=cat_values(model,c,prev['params'])}
            if v['how']=='auto':
                r=tested.get(v.get('decision'))
                if not r: bad.append('%s: automatic change %s has no review record'%(tag,v.get('decision'))); continue
                if cats!={r['category']}: bad.append('%s changed %s but the review tested %s'%(tag,sorted(cats),r['category']))
                if r.get('size')!='small' or r.get('steps',9)>1+1e-9: bad.append('%s: automatic change was not small (%s steps)'%(tag,r.get('steps')))
                if not all(c['ok'] for c in r.get('checks',[])) or not any(c['id']=='confirmed' and c['ok'] for c in r.get('checks',[])): bad.append('%s: applied without passing and confirming every check'%tag)
                if r.get('net',0)<=0 or r.get('p_adj',1)>=SPEC['alpha']: bad.append('%s: net %s, corrected p %s'%(tag,r.get('net'),r.get('p_adj')))
                if any(v['params'].get(k)!=x for k,x in r['to_params'].items()): bad.append('%s: applied values differ from the values tested'%tag)
                autos[r['category']].append((v['cutoff'][0]*18+min(v['cutoff'][1],18),v['cutoff'][0],r['steps'])); per_cut[tuple(v['cutoff'])]+=1
            elif v['how']=='approved':
                pr=next((x for x in PROPS if x['id']==v.get('decision')),None)
                if not pr or pr['status']!='approved' or pr.get('version')!=v['v']: bad.append('%s: approval %s is not on record'%(tag,v.get('decision')))
            elif v['how']=='rollback':
                if not any(x['params']==v['params'] for x in VS if x['v']<v['v']-1): bad.append('%s: a rollback must restore an earlier version exactly'%tag)
            else: bad.append('%s: unknown change type %r'%(tag,v['how']))
        for cat,xs in autos.items():
            xs.sort()
            if any(b[0]-a[0]<SPEC['cooldown_weeks'] for a,b in zip(xs,xs[1:])): bad.append('%s %s changed automatically inside the %d-week cooldown'%(model,cat,SPEC['cooldown_weeks']))
            by=defaultdict(float)
            for _,sea,st in xs: by[sea]+=st
            if any(x>1+1e-9 for x in by.values()): bad.append('%s %s moved more than one step automatically in a season'%(model,cat))
        if any(n>1 for n in per_cut.values()): bad.append('%s: more than one automatic change in a single review'%model)
    A.check('LG2','Every change since launch followed the rules: small moves confirmed in two reviews with every check passed, one at a time, big ones approved by the owner',bad,nchg)

    rev=LOG[-1] if LOG else None
    if not rev:
        A.warn('LG3','No model review has run yet',['the loop has not reviewed a completed week'],1); return
    bad=[]; fam=defaultdict(list)
    for r in rev['results']:
        if r['status']!='holds': fam[r.get('model','pregame')].append(r)
    specs={m:S for m,_,S in REG}; origin={m:min(C['versions'],key=lambda v:v['v'])['cutoff'][0] for m,C,_ in REG}
    for model,T in fam.items():
        S=specs[model]
        for r,a in zip(T,holm([r['p'] for r in T])):
            n='%s %s/%s'%(model,r['category'],r.get('variant'))
            if abs(a-r['p_adj'])>1e-4: bad.append('%s corrected p %s, recompute %.5f'%(n,r['p_adj'],a))
            ck={c['id']:c['ok'] for c in r['checks']}
            big=[b for b in r['blocks'] if b['n']>=S['min_block_games']]; better=sum(1 for b in big if b['cand']<b['base'])
            want=dict(enough=r['n']>=S['min_eval_games'],better=r['delta']>0,significant=a<S['alpha'],consistent=better>=S['min_better_blocks'] and len(big)-better<=S['max_worse_blocks'])
            for k,v in want.items():
                if ck.get(k)!=v: bad.append('%s check %s says %s, the numbers say %s'%(n,k,ck.get(k),v))
            if abs(round(sum(x['pts'] for x in r['pros'])-sum(x['pts'] for x in r['cons']),2)-r['net'])>0.021: bad.append('%s pros minus cons is not the net score %s'%(n,r['net']))
            if abs((r['base']-r['cand'])-r['delta'])>0.0011: bad.append('%s delta %s != %s - %s'%(n,r['delta'],r['base'],r['cand']))
            if sum(b['n'] for b in r['blocks'])!=r['n']: bad.append('%s season blocks do not add up to %d games'%(n,r['n']))
            if model!='live' and abs(sum(b['base']*b['n'] for b in r['blocks'])/max(r['n'],1)-r['base'])>0.002: bad.append('%s season blocks do not average to the pooled result'%n)
            if any(b['season']<=origin[model] or b['season']>rev['cutoff'][0] for b in r['blocks']): bad.append('%s was judged on seasons the launch weights were fitted on, or after the cutoff'%n)
            hard=all(ck.get(k) for k in ('enough','better','significant','consistent','no_damage')); st=r['status']
            if not hard and st not in ('watching','rejected'): bad.append('%s failed a check but is %s'%(n,st))
            if hard and r['net']<=0 and st!='rejected': bad.append('%s has more cons than pros but is %s'%(n,st))
            if hard and r['net']>0 and st not in ('pending','confirmed','applied','proposed','declined earlier'): bad.append('%s passed everything but is %s'%(n,st))
            if st=='watching' and r['delta']<=0: bad.append('%s is watched although it did worse'%n)
    A.check('LG3','The latest review is internally consistent for each model: multiple-testing corrections, each check, pros minus cons, and every verdict',bad,sum(len(v) for v in fam.values()))

    GA={r['game_id']:r for r in rows(os.path.join(DATA,'games_all.csv')) if r['game_type']=='REG'}
    res=lambda model,cat,var:next((x for x in rev['results'] if x.get('model','pregame')==model and x['category']==cat and x.get('variant')==var),None)
    bad=[]; cnt=0
    E=jl(os.path.join(L,'evidence','latest.json'),{})
    if E and E.get('review')==rev['id']:
        for key,ev in E.get('candidates',{}).items():
            cat,variant=key.split('|'); r=res('pregame',cat,variant)
            if not r: bad.append('pregame evidence for %s has no review result'%key); continue
            cnt+=1; g=[GA[x] for x in ev['gid']]
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
            if abs(lb[ok].mean()-r['base'])>0.003 or abs(lc[ok].mean()-r['cand'])>0.003: bad.append('pregame %s: recorded %s -> %s, raw scores give %.4f -> %.4f'%(key,r['base'],r['cand'],lb[ok].mean(),lc[ok].mean()))
            cl=np.array([int(x['season'])*100+int(x['week']) for x in g])[ok]
            p=boot_p(d,cl,zlib.crc32(('%s|%s|%s'%(rev['id'],cat,variant)).encode()),REG[0][2]['bootstrap'])
            if abs(p-r['p'])>0.005: bad.append('pregame %s: recorded p %.4f, recompute %.4f'%(key,r['p'],p))
    EL=jl(os.path.join(L,'evidence','latest_live.json'),{})
    if EL and EL.get('review')==rev['id']:
        for key in EL.get('candidates',[]):
            cat,variant=key.split('|'); r=res('live',cat,variant); f=os.path.join(L,'evidence','latest_live_%s_%s.npz'%(cat,variant))
            if not r or not os.path.exists(f): bad.append('live evidence for %s is missing its review result or file'%key); continue
            cnt+=1; Z=np.load(f); gid=Z['gid']
            fin={g:(num(GA[g]['home_score'])-num(GA[g]['away_score']),num(GA[g]['home_score'])+num(GA[g]['away_score'])) for g in set(gid.tolist())}
            RES=np.array([fin[g][0] for g in gid]); TOT=np.array([fin[g][1] for g in gid]); y=(RES>0).astype(float); dec=RES!=0
            def lossl(pre):
                met=r['metric']
                if met=='final_total': return np.abs(Z[pre+'tt'].astype(float)-TOT),np.ones(len(gid),bool)
                if met=='final_margin': return np.abs(Z[pre+'mm'].astype(float)-RES),np.ones(len(gid),bool)
                p=np.clip(Z[pre+'wp'].astype(float),1e-6,1-1e-6)
                if met=='brier': return np.where(dec,(p-y)**2,0),dec
                return np.where(dec,-(y*np.log(p)+(1-y)*np.log(1-p)),0),dec
            lb,ok=lossl('base_'); lc,_=lossl('cand_'); d=(lb-lc)[ok]
            if abs(lb[ok].mean()-r['base'])>2e-4 or abs(lc[ok].mean()-r['cand'])>2e-4: bad.append('live %s: recorded %s -> %s, raw scores give %.5f -> %.5f'%(key,r['base'],r['cand'],lb[ok].mean(),lc[ok].mean()))
            wk=Z['wk']
            if wk.min()//100<=origin['live'] or wk.max()>rev['cutoff'][0]*100+rev['cutoff'][1]: bad.append('live %s evidence includes plays outside the evaluation window'%key)
            p=boot_p(d,wk[ok],zlib.crc32(('%s|live|%s|%s'%(rev['id'],cat,variant)).encode()),REG[1][2]['bootstrap'])
            if abs(p-r['p'])>0.005: bad.append('live %s: recorded p %.4f, recompute %.4f'%(key,r['p'],p))
    EP=jl(os.path.join(L,'evidence','latest_players.json'),{}); DBP=os.path.join(DATA,'history','history.sqlite')
    if EP and EP.get('review')==rev['id'] and EP.get('candidates'):
        if not os.path.exists(DBP): A.warn('LG4b','Player evidence not recomputed: the history database is not in this run',sorted(EP['candidates']),len(EP['candidates']))
        else:
            import sqlite3
            con=sqlite3.connect(DBP); act={}
            for r in con.execute("SELECT player_id,season,week,receptions,receiving_yards,receiving_tds,rushing_yards,rushing_tds,passing_yards,passing_tds,passing_interceptions "
                                 "FROM player_week WHERE season_type='REG' AND season>?",(origin['players'],)):
                v=[num(x) for x in r[3:]]
                act[(r[0],r[1]*100+r[2])]=(v[0]+0.1*v[1]+6*v[2]+0.1*v[3]+6*v[4]+0.04*v[5]+4*v[6]-2*v[7],v[0],v[1]+v[3])
            con.close()
            for key in EP['candidates']:
                cat,variant=key.split('|'); r=res('players',cat,variant); f=os.path.join(L,'evidence','latest_players_%s_%s.npz'%(cat,variant))
                if not r or not os.path.exists(f): bad.append('player evidence for %s is missing its review result or file'%key); continue
                cnt+=1; Z=np.load(f); keys=list(zip(Z['pid'].tolist(),Z['wk'].tolist()))
                if any(k not in act for k in keys): bad.append('player %s evidence has player-weeks not in the raw stats'%key); continue
                j={'pts':0,'rec':1,'yds':2}[r['metric']]; truth=np.array([act[k][j] for k in keys])
                lb=np.abs(Z['base_'+r['metric']].astype(float)-truth); lc=np.abs(Z['cand_'+r['metric']].astype(float)-truth); d=lb-lc
                if abs(lb.mean()-r['base'])>2e-3 or abs(lc.mean()-r['cand'])>2e-3: bad.append('player %s: recorded %s -> %s, raw stats give %.4f -> %.4f'%(key,r['base'],r['cand'],lb.mean(),lc.mean()))
                wk=Z['wk']
                if wk.min()//100<=origin['players'] or wk.max()>rev['cutoff'][0]*100+rev['cutoff'][1]: bad.append('player %s evidence includes weeks outside the evaluation window'%key)
                p=boot_p(d,wk,zlib.crc32(('%s|players|%s|%s'%(rev['id'],cat,variant)).encode()),REG[2][2]['bootstrap'])
                if abs(p-r['p'])>0.005: bad.append('player %s: recorded p %.4f, recompute %.4f'%(key,r['p'],p))
    A.check('LG4','Evidence behind every pending, applied or proposed change in the latest review recomputes from raw final scores and stats',bad,cnt)

    bad=[]; Lp=D.get('learn') or {}
    cur=lambda C:next(v for v in C['versions'] if v['v']==C['current'])['params']
    if Lp.get('params')!=cur(REG[0][1]): bad.append('the published data carries different pregame weights from the current champion')
    if Lp.get('version')!=REG[0][1]['current']: bad.append('published pregame weights version %s, champion %s'%(Lp.get('version'),REG[0][1]['current']))
    if Lp.get('live_params')!=cur(REG[1][1]): bad.append('the published data carries different live weights from the current live champion')
    if Lp.get('players_params')!=cur(REG[2][1]): bad.append('the published data carries different player weights from the current player champion')
    if (D.get('live') or {}).get('margin')!=cur(REG[1][1])['margin']: bad.append('the page runs live constants that differ from the live champion')
    if (Lp.get('last_review') or {}).get('id')!=rev['id']: bad.append('page reports review %s, latest is %s'%((Lp.get('last_review') or {}).get('id'),rev['id']))
    if sorted(w['id'] for w in Lp.get('weights',[]))!=sorted(c['id'] for _,_,S in REG for c in S['categories']): bad.append('page weight list does not cover every weight group of all three models')
    if sorted(p['id'] for p in Lp.get('proposals',[]))!=sorted(p['id'] for p in PROPS if p['status']=='open'): bad.append('page proposals differ from the open proposals on record')
    A.check('LG5','The published data carries the current weights of all three models, the latest review and every open proposal',bad)
