"""Track record: every headline number on the Model page rebuilt from the raw schedule and the
engine's walk-forward predictions, with fresh code for the QB term, ATS, calibration and factor slopes."""
import os, sys, json, math, statistics
from collections import defaultdict, Counter
from common import num, rows, DATA, PIPE, APP

def run(A):
    A.section('track record'); T=A.D['track']
    sys.path.insert(0,PIPE); import engine2
    HP=json.load(open(os.path.join(PIPE,'hp2.json'))); K=json.load(open(os.path.join(PIPE,'qbfit.json')))['k']
    WP=json.load(open(os.path.join(PIPE,'wpfit.json')))
    GA={r['game_id']:r for r in rows(os.path.join(DATA,'games_all.csv')) if r['game_type']=='REG'}
    starts=defaultdict(Counter)
    for r in GA.values():
        if r['home_score'] and r['home_qb_id']:
            starts[(r['season'],r['home_team'])][r['home_qb_id']]+=1; starts[(r['season'],r['away_team'])][r['away_qb_id']]+=1
    prim={k:c.most_common(1)[0][0] for k,c in starts.items()}
    G=[]
    for o in engine2.run(HP):
        if o['season']>2025: continue          # the published record covers 2019-2025
        r=GA[o['gid']]
        if not r['spread_line']: continue
        hb=int(bool(r['home_qb_id']) and prim.get((r['season'],r['home_team']))!=r['home_qb_id'])
        ab=int(bool(r['away_qb_id']) and prim.get((r['season'],r['away_team']))!=r['away_qb_id'])
        G.append(dict(s=int(r['season']),w=int(r['week']),m=o['margin']+K*(ab-hb),t=o['total'],
                      am=num(r['home_score'])-num(r['away_score']),at=num(r['home_score'])+num(r['away_score']),
                      vs=num(r['spread_line']),vt=num(r['total_line']) if r['total_line'] else None))
    def summ(X):
        Xt=[x for x in X if x['vt'] is not None]
        ats=[(x['am']-x['vs'])*(x['m']-x['vs']) for x in X if x['am']!=x['vs']]
        ou=[(x['at']-x['vt'])*(x['t']-x['vt']) for x in Xt if x['at']!=x['vt']]
        return dict(n=len(X),gm=statistics.mean(abs(x['m']-x['am']) for x in X),vm=statistics.mean(abs(x['vs']-x['am']) for x in X),
                    gt=statistics.mean(abs(x['t']-x['at']) for x in Xt),vt=statistics.mean(abs(x['vt']-x['at']) for x in Xt),
                    su=100*sum(1 for x in X if (x['m']>0)==(x['am']>0))/len(X),
                    ats=100*sum(1 for v in ats if v>0)/len(ats),atsn=len(ats),ou=100*sum(1 for v in ou if v>0)/len(ou))
    bad=[]
    for key,X in (('all',G),('held',[x for x in G if x['s']>=2023]),('wk1',[x for x in G if x['w']==1]))+tuple((str(s),[x for x in G if x['s']==s]) for s in range(2019,2026)):
        st=T['all'] if key=='all' else T['held'] if key=='held' else T['wk1'] if key=='wk1' else T['by'].get(key)
        if not st: bad.append('track has no %s block'%key); continue
        m=summ(X)
        for k,tol in (('n',0),('gm',0.006),('vm',0.006),('gt',0.006),('vt',0.006),('su',0.6),('ats',0.06),('atsn',0),('ou',0.06)):
            if abs(num(st.get(k))-m[k])>tol: bad.append('%s %s: shown %s, recompute %.3f'%(key,k,st.get(k),m[k]))
    A.check('T1','Every backtest headline (errors, ATS, O/U, straight-up) recomputes, by season and overall',bad,len(G))

    bad=[]; B=defaultdict(list)
    for x in G:
        p=0.5*(1+math.erf((WP['a']+WP['b']*x['m'])/(WP['sd']*math.sqrt(2))))
        B[min(9,int(p*10))].append((p,1.0 if x['am']>0 else 0.5 if x['am']==0 else 0.0))
    err=sum(abs(statistics.mean(p for p,_ in v)-statistics.mean(a for _,a in v))*len(v) for v in B.values())/len(G)
    if abs(100*err-T['wpcal']['err'])>0.02: bad.append('calibration error shown %.2f, recompute %.2f'%(T['wpcal']['err'],100*err))
    for b in T['wpcal']['bands']:
        v=B.get(b['b']//10,[])
        if len(v)!=b['n'] or abs(100*statistics.mean(p for p,_ in v)-b['p'])>0.06 or abs(100*statistics.mean(a for _,a in v)-b['a'])>0.06:
            bad.append('band %d%%: shown n=%d %.1f/%.1f, recompute n=%d'%(b['b'],b['n'],b['p'],b['a'],len(v)))
    A.check('T2','Win-probability calibration bands and error recompute',bad,len(T['wpcal']['bands']))

    js=open(os.path.join(APP,'app.js'),encoding='ascii').read()
    A.check('T3','Model page headline figures come from held-out 2023-25, not the years the calibration and QB term were fitted on',
            [] if 'T.held||T.all' in js and T.get('held') else ['headline tiles read the all-seasons block, which includes the 2019-22 fitting years'])