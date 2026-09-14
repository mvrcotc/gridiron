"""Track record: every headline number on the Model page rebuilt from the raw schedule and the engine's walk-forward
ratings, with fresh code for the champion version in force at each week, the real-time backup-QB flag, every weighted
factor, ATS and calibration."""
import os, sys, json, math, statistics
from collections import defaultdict, Counter
from common import num, rows, DATA, PIPE, APP
REL={'STL':'LA','SD':'LAC','OAK':'LV'}
RK=('kY','cY','kP','cP','kT','cT','kO','cO','kE','cE','kS','cS','decay')

def run(A):
    A.section('track record'); T=A.D['track']
    sys.path.insert(0,PIPE); import engine2
    CH=json.load(open(os.path.join(PIPE,'champion.json'))); VS=sorted(CH['versions'],key=lambda v:v['v'])
    def force(s,w):
        ok=[v for v in VS if v['cutoff'][0]*100+v['cutoff'][1]<s*100+w]
        return ok[-1] if ok else VS[0]
    runs={}
    def ratings(P):
        key=tuple(P[k] for k in RK)
        if key not in runs:
            hp={k:P[k] for k in RK}; hp.update(hfa=0.0,wB=1.0,wE=0.0,wS=0.0); runs[key]={o['gid']:o for o in engine2.run(hp)}
        return runs[key]
    GA=[r for r in rows(os.path.join(DATA,'games_all.csv')) if r['game_type']=='REG']
    weeks=defaultdict(list)
    for r in GA: weeks[(int(r['season']),int(r['week']))].append(r)
    starts=defaultdict(Counter); H=defaultdict(lambda:[0.0,0]); R=defaultdict(lambda:[0.0,0]); LG=[0.0,0]; REF=defaultdict(list); G=[]
    for (s,w) in sorted(weeks):
        for r in weeks[(s,w)]:
            if not (2019<=s<=2025) or not r['home_score'] or not r['spread_line']: continue
            V=force(s,w); P=V['params']; o=ratings(P).get(r['game_id'])
            if not o: continue
            pts=lambda d:P['wB']*d['pB']+P['wE']*d['pE']+P['wS']*d['pS']
            def backup(team,q):
                c=starts[(s,team)]
                return int(bool(c and q and q!=c.most_common(1)[0][0]))
            qb=backup(r['away_team'],r['away_qb_id'])-backup(r['home_team'],r['home_qb_id'])
            neutral=r['location']!='Home'
            hr,ar=num(r['home_rest'],None),num(r['away_rest'],None); rest=max(-7.0,min(7.0,hr-ar)) if hr is not None and ar is not None else 0.0
            dome=(r['roof'] or '').lower() in ('dome','closed')
            wind=0.0 if dome else num(r['wind'],0.0); temp=70.0 if dome else num(r['temp'],60.0)
            t=REL.get(r['home_team'],r['home_team'])
            venue=0.0
            if not neutral and LG[1] and H[t][1]>=16 and R[t][1]>=16: venue=H[t][0]/H[t][1]-R[t][0]/R[t][1]-2*LG[0]/LG[1]
            rv=[x for sea,x in REF[(r['referee'] or '').strip()] if sea>=s-2] if (r['referee'] or '').strip() else []
            ref=statistics.mean(rv) if len(rv)>=16 else 0.0
            m=pts(o['hd'])-pts(o['ad'])+(0.0 if neutral else P['hfa']+P['venue']*venue)+P['qb']*qb+P['rest']*rest
            tt=pts(o['hd'])+pts(o['ad'])+P['wx_dome']*dome+P['wx_wind']*max(0.0,wind-8)+P['wx_cold']*max(0.0,45-temp)/10+P['ref']*ref
            G.append(dict(s=s,w=w,m=m,t=tt,wp=0.5*(1+math.erf((P['wp_a']+P['wp_b']*m)/(P['wp_sd']*math.sqrt(2)))),
                          am=num(r['home_score'])-num(r['away_score']),at=num(r['home_score'])+num(r['away_score']),
                          vs=num(r['spread_line']),vt=num(r['total_line']) if r['total_line'] else None))
        for r in weeks[(s,w)]:          # only now does this week become history
            if not r['home_score']: continue
            if r['home_qb_id']: starts[(s,r['home_team'])][r['home_qb_id']]+=1
            if r['away_qb_id']: starts[(s,r['away_team'])][r['away_qb_id']]+=1
            mm=num(r['home_score'])-num(r['away_score'])
            if r['location']=='Home' and s>=2015:
                h=H[REL.get(r['home_team'],r['home_team'])]; h[0]+=mm; h[1]+=1
                a=R[REL.get(r['away_team'],r['away_team'])]; a[0]-=mm; a[1]+=1
                LG[0]+=mm; LG[1]+=1
            if (r['referee'] or '').strip() and num(r['total_line'],None) is not None:
                REF[r['referee'].strip()].append((s,num(r['home_score'])+num(r['away_score'])-num(r['total_line'])))
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
    A.check('T1','Every backtest headline (errors, ATS, O/U, straight-up) recomputes with the weights in force at each week',bad,len(G))

    bad=[]; B=defaultdict(list)
    for x in G: B[min(9,int(x['wp']*10))].append((x['wp'],1.0 if x['am']>0 else 0.5 if x['am']==0 else 0.0))
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
