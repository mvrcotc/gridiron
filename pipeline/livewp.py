"""Live model report: how the live weights perform on held-out seasons, against nflfastR's win probability with and without
the betting line and against the line faded with the clock. The constants themselves live in champion_live.json and
are governed by the weekly review (learn.py); every play here is predicted by the live weights in force at its week,
from the pregame numbers GridIron actually showed. Writes pipeline/livefit.json for the page and the README."""
import os, sys, json, time
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0,HERE)
import gamemodel as gm, livemodel as lm
t0=time.time(); TEST=(2023,2025)
C=lm.load_champion(); V=gm.current(C); P=lm.Plays(first=2019)
print('plays: %d from %d games'%(P.n,len(np.unique(P.gid))),flush=True)
pred={k:np.full(P.n,np.nan) for k in ('wp','mm','tt')}
for w in sorted(set(P.wk.tolist())):
    i,j=P.before(w),P.before(w+1); S=P.view(i,j); pr=lm.predict(S,gm.in_force(C,w//100,w%100)['params'])
    for k in pred: pred[k][i:j]=pr[k]
te=(P.season>=TEST[0])&(P.season<=TEST[1])
def scores(m,p):
    ok=m&P.decided&~np.isnan(p); pc=np.clip(p[ok],1e-6,1-1e-6); y=P.y[ok]
    return dict(n=int(ok.sum()),brier=round(float(np.mean((pc-y)**2)),5),logloss=round(float(-np.mean(y*np.log(pc)+(1-y)*np.log(1-pc))),5))
common=te&~np.isnan(P.NFW)&~np.isnan(P.VEG); REP={}
REP['wp_all']={'gridiron':scores(common,pred['wp']),'nflfastr':scores(common,P.NFW),'nflfastr_with_line':scores(common,P.VEG)}
q=np.floor((1-P.frac)*4).clip(0,3).astype(int)
REP['wp_by_quarter']=[{'q':k+1,'gridiron':scores(common&(q==k),pred['wp']),'nflfastr_with_line':scores(common&(q==k),P.VEG)} for k in range(4)]
bands=[]
for k in range(10):
    m=te&P.decided&(pred['wp']>=k/10)&((pred['wp']<(k+1)/10) if k<9 else (pred['wp']<=1.0))
    if m.sum()>=200: bands.append({'b':k*10,'n':int(m.sum()),'p':round(100*float(np.mean(pred['wp'][m])),1),'a':round(100*float(np.mean(P.RES[m]>0)),1)})
REP['wp_calibration']=bands
mg=te&~np.isnan(P.SPR); tt=te&~np.isnan(P.TLN)
REP['final_margin_mae']={'gridiron_live':round(float(np.mean(np.abs(P.RES[mg]-pred['mm'][mg]))),3),'market_faded':round(float(np.mean(np.abs(P.RES[mg]-(P.D[mg]+P.SPR[mg]*P.frac[mg])))),3),'n':int(mg.sum())}
REP['final_total_mae']={'gridiron_live':round(float(np.mean(np.abs(P.TOT[tt]-pred['tt'][tt]))),3),'market_faded':round(float(np.mean(np.abs(P.TOT[tt]-(P.CUR[tt]+P.TLN[tt]*P.frac[tt])))),3),'n':int(tt.sum())}
O=min(C['versions'],key=lambda v:v['v'])
OUT=dict(fit='2019-%d'%O['cutoff'][0],test='%d-%d'%TEST,version=V['v'],n_test_plays=int(te.sum()),report=REP,built=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
         note='every play predicted by the live weights in force at its week, from the pregame numbers GridIron showed',**{k:V['params'][k] for k in ('ep','margin','platt','total')})
json.dump(OUT,open('livefit.json','w'),indent=1)
print('live weights version %d, held out %s: %s'%(V['v'],OUT['test'],json.dumps(REP['wp_all'])))
print('final margin MAE:',REP['final_margin_mae'],'| final total MAE:',REP['final_total_mae'])
print('calibration bands:',bands); print('done in %.0fs'%(time.time()-t0))
