"""Live in-game model, fitted on historical play-by-play.

GridIron's pregame projection is the prior; it fades as the clock runs, while the current score and the value of the
current possession take over. Final margin is modelled as Normal:
    mean = D + a*EP_home + b*M0*frac + c*frac        (D = home lead now, frac = share of regulation left)
    sd   = sqrt(sigma^2 * frac + eps^2)
    live home win probability = Phi(mean / sd)
and final total as  current total + t1*T0*frac + t2*frac + t3*|EP_home|.
EP_home is the expected points of the possession (from a down x distance x field-position table fitted on the same
seasons), signed toward the home team. Fitted on 2019-22, tested on 2023-25 against nflfastR's win probability
(which uses the betting line) and a market-faded benchmark. Writes pipeline/livefit.json for the page."""
import os, sys, json, math, sqlite3, time
from collections import Counter, defaultdict
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0,HERE)
import engine2
from engine2 import DATA
DB=os.path.join(DATA,'history','history.sqlite')
HP=json.load(open('hp2.json')); QK=json.load(open('qbfit.json'))['k']
TRAIN=(2019,2022); TEST=(2023,2025)
t0=time.time()

# ---- pregame priors: exactly the walk-forward engine + backup-QB term the published track record uses ----
GA=engine2.G; st=defaultdict(Counter)
for r in GA.values():
    if r['home_score'] and r['home_qb_id']:
        st[(r['season'],r['home_team'])][r['home_qb_id']]+=1; st[(r['season'],r['away_team'])][r['away_qb_id']]+=1
prim={k:c.most_common(1)[0][0] for k,c in st.items()}
PRIOR={}
for o in engine2.run(HP):
    r=GA[o['gid']]
    qb=int(bool(r['away_qb_id']) and prim.get((r['season'],r['away_team']))!=r['away_qb_id'])-int(bool(r['home_qb_id']) and prim.get((r['season'],r['home_team']))!=r['home_qb_id'])
    PRIOR[o['gid']]=(o['margin']+QK*qb,o['total'])
print('pregame priors for %d games'%len(PRIOR),flush=True)

# ---- plays ----
con=sqlite3.connect(DB)
rows=con.execute("SELECT game_id,season,game_seconds_remaining,down,ydstogo,yardline_100,posteam,home_team,away_team,"
                 "total_home_score,total_away_score,ep,result,total,home_wp,vegas_home_wp,spread_line,total_line "
                 "FROM plays WHERE season BETWEEN ? AND ? AND season_type='REG' AND qtr<=4 AND game_seconds_remaining IS NOT NULL "
                 "AND total_home_score IS NOT NULL AND total_away_score IS NOT NULL AND result IS NOT NULL",(TRAIN[0],TEST[1])).fetchall()
con.close()
rows=[r for r in rows if r[0] in PRIOR]
print('plays with a prior: %d from %d games'%(len(rows),len({r[0] for r in rows})),flush=True)

# ---- expected-points table: yard-line band x down x distance band, fitted on training seasons only ----
YB=[1,11,21,31,41,51,61,71,81,91,100]; DD=[1,4,8,13,100]
def band(v,edges):
    for i in range(len(edges)-1):
        if edges[i]<=v<edges[i+1]: return i
    return len(edges)-2
acc=defaultdict(lambda:[0.0,0]); acc2=defaultdict(lambda:[0.0,0])
for r in rows:
    if not (TRAIN[0]<=r[1]<=TRAIN[1]) or r[3] is None or r[5] is None or r[11] is None or not 1<=r[3]<=4: continue
    k=(band(r[5],YB),int(r[3])-1,band(r[4] or 10,DD)); acc[k][0]+=r[11]; acc[k][1]+=1
    k2=(band(r[5],YB),int(r[3])-1); acc2[k2][0]+=r[11]; acc2[k2][1]+=1
EPT=[[[None]*(len(DD)-1) for _ in range(4)] for _ in range(len(YB)-1)]
for y in range(len(YB)-1):
    for d in range(4):
        for t in range(len(DD)-1):
            s,n=acc.get((y,d,t),(0,0)); s2,n2=acc2.get((y,d),(0,0))
            EPT[y][d][t]=round(s/n,3) if n>=30 else (round(s2/n2,3) if n2 else 0.0)
def ep_home(r):
    if r[3] is None or r[5] is None or not 1<=int(r[3])<=4: return 0.0
    sign=1.0 if r[6]==r[7] else (-1.0 if r[6]==r[8] else 0.0)
    return sign*EPT[band(r[5],YB)][int(r[3])-1][band(r[4] or 10,DD)]

N=len(rows)
season=np.array([r[1] for r in rows]); S=np.clip(np.array([float(r[2]) for r in rows]),0,3600); frac=S/3600.0
D=np.array([float(r[9]-r[10]) for r in rows]); EPH=np.array([ep_home(r) for r in rows])
M0=np.array([PRIOR[r[0]][0] for r in rows]); T0=np.array([PRIOR[r[0]][1] for r in rows])
RES=np.array([float(r[12]) for r in rows]); TOT=np.array([float(r[13]) for r in rows]); CUR=np.array([float(r[9]+r[10]) for r in rows])
NFW=np.array([np.nan if r[14] is None else float(r[14]) for r in rows]); VEG=np.array([np.nan if r[15] is None else float(r[15]) for r in rows])
SPR=np.array([np.nan if r[16] is None else float(r[16]) for r in rows]); TLN=np.array([np.nan if r[17] is None else float(r[17]) for r in rows])
tr=(season>=TRAIN[0])&(season<=TRAIN[1]); te=(season>=TEST[0])&(season<=TEST[1])

# ---- margin mean by least squares, spread by maximum likelihood ----
X=np.column_stack([EPH,M0*frac,frac]); y=RES-D
beta=np.linalg.lstsq(X[tr],y[tr],rcond=None)[0]; a,b,c=[float(v) for v in beta]
resid=y-X@beta
def nll(sig,eps,m):
    v=sig*sig*frac[m]+eps*eps; return float(np.sum(0.5*np.log(v)+resid[m]**2/(2*v)))
sig,eps=13.0,2.0
for _ in range(3):
    sig=min(np.arange(6.0,20.0,0.05),key=lambda s:nll(s,eps,tr))
    eps=min(np.arange(0.25,8.0,0.05),key=lambda e:nll(sig,e,tr))
sig,eps=round(float(sig),3),round(float(eps),3)
erf=np.frompyfunc(math.erf,1,1)
def live_wp(m):
    mu=D[m]+X[m]@beta; sd=np.sqrt(sig*sig*frac[m]+eps*eps)
    return 0.5*(1+erf(mu/(sd*math.sqrt(2))).astype(float))
Xt=np.column_stack([T0*frac,frac,np.abs(EPH)]); yt=TOT-CUR
bt=np.linalg.lstsq(Xt[tr],yt[tr],rcond=None)[0]

# ---- held-out evaluation ----
def scores(m,p):
    lab=(RES[m]>0).astype(float); pm=p[m]; ok=(RES[m]!=0)&~np.isnan(pm)
    pc=np.clip(pm[ok],1e-6,1-1e-6); l=lab[ok]
    return dict(n=int(ok.sum()),brier=round(float(np.mean((pc-l)**2)),5),logloss=round(float(-np.mean(l*np.log(pc)+(1-l)*np.log(1-pc))),5))
# ---- tail calibration: Platt scaling on the logit, fitted on training plays only ----
def logit(p):
    p=np.clip(p,1e-6,1-1e-6); return np.log(p/(1-p))
def fit_platt(m):
    z=logit(live_wp(m)); lab=(RES[m]>0).astype(float)
    A=np.column_stack([np.ones_like(z),z]); w=np.array([0.0,1.0])
    for _ in range(50):
        pp=1/(1+np.exp(-(A@w))); g=A.T@(lab-pp); H=(A*(pp*(1-pp))[:,None]).T@A
        step=np.linalg.solve(H,g); w=w+step
        if np.max(np.abs(step))<1e-9: break
    return float(w[0]),float(w[1])
def bl(p,lab):
    p=np.clip(p,1e-6,1-1e-6); return float(np.mean((p-lab)**2)),float(-np.mean(lab*np.log(p)+(1-lab)*np.log(1-p)))
# decided before touching the test seasons: fit on 2019-21, check on 2022, keep it only if Brier and log loss both improve
vm=(season==TRAIN[1])&(RES!=0); fm=tr&(season<TRAIN[1])&(RES!=0)
va,vb=fit_platt(fm); pr=live_wp(vm); lv=(RES[vm]>0).astype(float)
raw_b,raw_l=bl(pr,lv); cal_b,cal_l=bl(1/(1+np.exp(-(va+vb*logit(pr)))),lv)
VAL={'season':int(TRAIN[1]),'raw':{'brier':round(raw_b,5),'logloss':round(raw_l,5)},'calibrated':{'brier':round(cal_b,5),'logloss':round(cal_l,5)}}
if cal_b<raw_b and cal_l<raw_l:
    wa,wb=fit_platt(tr&(RES!=0)); PLATT={'alpha':round(wa,5),'beta':round(wb,5)}
else:
    PLATT=None
print('tail calibration check on %d: %s -> %s'%(TRAIN[1],VAL,'kept' if PLATT else 'not kept'),flush=True)
def cal(p): return p if PLATT is None else 1/(1+np.exp(-(PLATT['alpha']+PLATT['beta']*logit(p))))
REP={}
p_raw=np.full(N,np.nan); p_raw[te]=live_wp(te)
p_gi=np.full(N,np.nan); p_gi[te]=cal(p_raw[te])
common=te&~np.isnan(NFW)&~np.isnan(VEG)
REP['wp_all']={'gridiron':scores(common,p_gi),'gridiron_uncalibrated':scores(common,p_raw),'nflfastr':scores(common,NFW),'nflfastr_with_line':scores(common,VEG)}
q=np.floor((3600-S)/900).clip(0,3).astype(int)
REP['wp_by_quarter']=[{'q':k+1,'gridiron':scores(common&(q==k),p_gi),'nflfastr_with_line':scores(common&(q==k),VEG)} for k in range(4)]
bands=[]
for k in range(10):
    m=te&(RES!=0)&(p_gi>=k/10)&(p_gi<(k+1)/10 if k<9 else p_gi<=1.0)
    if m.sum()>=200: bands.append({'b':k*10,'n':int(m.sum()),'p':round(100*float(np.mean(p_gi[m])),1),'a':round(100*float(np.mean(RES[m]>0)),1)})
REP['wp_calibration']=bands
mg=te&~np.isnan(SPR); tt=te&~np.isnan(TLN)
REP['final_margin_mae']={'gridiron_live':round(float(np.mean(np.abs(RES[mg]-(D[mg]+X[mg]@beta)))),3),
                        'market_faded':round(float(np.mean(np.abs(RES[mg]-(D[mg]+SPR[mg]*frac[mg])))),3),'n':int(mg.sum())}
REP['final_total_mae']={'gridiron_live':round(float(np.mean(np.abs(TOT[tt]-(CUR[tt]+Xt[tt]@bt)))),3),
                       'market_faded':round(float(np.mean(np.abs(TOT[tt]-(CUR[tt]+TLN[tt]*frac[tt])))),3),'n':int(tt.sum())}
OUT={'fit':'%d-%d'%TRAIN,'test':'%d-%d'%TEST,'n_train_plays':int(tr.sum()),'n_test_plays':int(te.sum()),
     'ep':{'yard_bands':YB,'dist_bands':DD,'table':EPT},'margin':{'a_ep':round(a,4),'b_prior':round(b,4),'c_frac':round(c,4),'sigma':sig,'eps':eps},
     'platt':PLATT,'platt_validation':VAL,
     'total':{'t_prior':round(float(bt[0]),4),'t_frac':round(float(bt[1]),4),'t_ep':round(float(bt[2]),4)},'report':REP,
     'built':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
json.dump(OUT,open('livefit.json','w'),indent=1)
print(json.dumps({k:OUT[k] for k in ('margin','total')}))
print('held out %s: %s'%(OUT['test'],json.dumps(REP['wp_all'])))
print('by quarter:',json.dumps(REP['wp_by_quarter']))
print('final margin MAE:',REP['final_margin_mae'],'| final total MAE:',REP['final_total_mae'])
print('calibration bands:',bands)
print('done in %.0fs'%(time.time()-t0))
