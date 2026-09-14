"""GridIron's live in-game model in one place: play features, each fitting step, and the formula the page runs.

    final margin ~ Normal(mean, sd)
    mean = D + a*EP_home + b*M0*frac + c*frac        D = home lead now, M0 = GridIron's pregame margin, frac = regulation left
    sd   = sqrt(sigma^2*frac + eps^2)
    home win probability = Phi(mean/sd), then an optional Platt tail calibration on the logit
    final total = current total + t1*T0*frac + t2*frac + t3*|EP_home|

The pregame margin M0 and total T0 for every game come from the pregame weights in force that week (gamemodel.py), so
the live model is fitted and tested on the same pregame numbers the page showed. livewp.py (the report), learn_live.py
(the weekly review) and predict.py (the constants the page uses) all go through this module."""
import os, sys, json, math, sqlite3
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0,HERE)
import gamemodel as gm

DB=os.path.join(gm.DATA,'history','history.sqlite'); CHAMP=os.path.join(HERE,'champion_live.json')
YB=[1,11,21,31,41,51,61,71,81,91,100]; DD=[1,4,8,13,100]
def load_champion(path=CHAMP): return json.load(open(path,encoding='utf-8'))

def ncdf(x):
    """standard normal CDF via Abramowitz-Stegun 7.1.26 (error below 1.5e-7) -- the same approximation the page runs"""
    x=np.asarray(x,float); z=np.abs(x)/math.sqrt(2); t=1/(1+0.3275911*z)
    e=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*np.exp(-z*z)
    return 0.5*(1+np.sign(x)*e)

def bands(v,edges):
    out=np.searchsorted(np.array(edges[1:-1],float),np.nan_to_num(np.asarray(v,float),nan=edges[0]),side='right')
    return np.clip(out,0,len(edges)-2)

def plays_through():
    """latest (season*100+week) with regular-season plays in the history database, or None"""
    if not os.path.exists(DB): return None
    con=sqlite3.connect(DB)
    try: r=con.execute("SELECT MAX(season*100+week) FROM plays WHERE season_type='REG'").fetchone()
    except sqlite3.Error: r=(None,)
    con.close(); return r[0]

class Plays:
    """regular-season plays in quarters 1-4 from `first` through the cutoff week, in time order, with GridIron's pregame numbers"""
    ARR=('gid','season','week','wk','frac','down','dist','yl','sign','D','CUR','RES','TOT','ep','NFW','VEG','SPR','TLN','M0','T0','pv','yb','db','has_down','key','y','decided')
    def __init__(s,first=2019,cutoff=None,C=None,book=None):
        C=C or gm.load_champion(); book=book or gm.Book()
        prior={x['gid']:(x['m'],x['t'],x['v']) for x in gm.track_rows(C,first=first,last=cutoff[0] if cutoff else None,book=book)}
        con=sqlite3.connect(DB)
        rows=con.execute("SELECT game_id,season,week,game_seconds_remaining,down,ydstogo,yardline_100,posteam,home_team,away_team,"
                         "total_home_score,total_away_score,result,total,ep,home_wp,vegas_home_wp,spread_line,total_line FROM plays "
                         "WHERE season>=? AND season_type='REG' AND qtr<=4 AND game_seconds_remaining IS NOT NULL "
                         "AND total_home_score IS NOT NULL AND total_away_score IS NOT NULL AND result IS NOT NULL "
                         "ORDER BY season,week,game_id,play_id",(first,)).fetchall()
        con.close()
        cw=gm.wk(*cutoff) if cutoff else 10**9
        rows=[r for r in rows if r[0] in prior and r[1]*100+r[2]<=cw]
        f=lambda i,fb=np.nan:np.array([fb if r[i] is None else float(r[i]) for r in rows])
        s.n=len(rows); s.gid=np.array([r[0] for r in rows]); s.season=f(1).astype(int); s.week=f(2).astype(int); s.wk=s.season*100+s.week
        s.frac=np.clip(f(3),0,3600)/3600.0; s.down=f(4,0).astype(int); s.dist=f(5,10.0); s.yl=f(6)
        s.sign=np.array([1.0 if r[7]==r[8] else (-1.0 if r[7]==r[9] else 0.0) for r in rows])
        s.D=f(10)-f(11); s.CUR=f(10)+f(11); s.RES=f(12); s.TOT=f(13); s.ep=f(14); s.NFW=f(15); s.VEG=f(16); s.SPR=f(17); s.TLN=f(18)
        s.M0=np.array([prior[r[0]][0] for r in rows]); s.T0=np.array([prior[r[0]][1] for r in rows]); s.pv=np.array([prior[r[0]][2] for r in rows])
        s.yb=bands(s.yl,YB); s.db=bands(np.where(np.isnan(s.dist)|(s.dist<=0),10,s.dist),DD)
        s.has_down=(s.down>=1)&(s.down<=4)&~np.isnan(s.yl)
        s.key=(s.yb*4+np.clip(s.down-1,0,3))*(len(DD)-1)+s.db
        s.y=(s.RES>0).astype(float); s.decided=s.RES!=0
    def before(s,w): return int(np.searchsorted(s.wk,w,'left'))
    def view(s,i,j):
        """plays i..j-1 as a lightweight view (numpy slices, no copies)"""
        o=object.__new__(Plays)
        for k in s.ARR: setattr(o,k,getattr(s,k)[i:j])
        o.n=max(0,min(j,s.n)-i); return o

def _m(P,m,a): return a if m is None else a[m]

# ------------------------------------------------------------------ fitting steps; m is a mask of plays or None for all
def fit_ep(P,m=None):
    ok=P.has_down&~np.isnan(P.ep)
    if m is not None: ok=ok&m
    nb=(len(YB)-1)*4*(len(DD)-1); nd=len(DD)-1
    s=np.bincount(P.key[ok],weights=P.ep[ok],minlength=nb); n=np.bincount(P.key[ok],minlength=nb)
    k2=P.key//nd; s2=np.bincount(k2[ok],weights=P.ep[ok],minlength=nb//nd); n2=np.bincount(k2[ok],minlength=nb//nd)
    flat=np.where(n>=30,s/np.maximum(n,1),np.repeat(np.where(n2>0,s2/np.maximum(n2,1),0.0),nd))
    return np.round(flat,3).reshape(len(YB)-1,4,nd).tolist()
def ep_home(P,table):
    t=np.array(table,float).reshape(-1)
    return np.where(P.has_down,P.sign*t[P.key],0.0)
def fit_margin(P,m,EPH):
    X=np.column_stack([_m(P,m,EPH),_m(P,m,P.M0)*_m(P,m,P.frac),_m(P,m,P.frac)]); b=np.linalg.lstsq(X,_m(P,m,P.RES-P.D),rcond=None)[0]
    return dict(a_ep=round(float(b[0]),4),b_prior=round(float(b[1]),4),c_frac=round(float(b[2]),4))
def mean_margin(P,M,EPH): return P.D+M['a_ep']*EPH+M['b_prior']*P.M0*P.frac+M['c_frac']*P.frac
def fit_spread(P,m,resid,start=(13.0,2.0)):
    """maximum likelihood by coarse then fine grid search"""
    fr=_m(P,m,P.frac); r2=_m(P,m,resid)**2; sig,eps=start
    def nll(sg,ep):
        v=sg*sg*fr+ep*ep; return float(np.sum(0.5*np.log(v)+r2/(2*v)))
    for step,span in ((0.25,None),(0.05,0.5)):
        for _ in range(2):
            gs=np.arange(6.0,20.0+1e-9,step) if span is None else np.arange(max(6.0,sig-span),min(20.0,sig+span)+1e-9,step)
            sig=min(gs,key=lambda x:nll(x,eps))
            ge=np.arange(0.25,8.0+1e-9,step) if span is None else np.arange(max(0.25,eps-span),min(8.0,eps+span)+1e-9,step)
            eps=min(ge,key=lambda x:nll(sig,x))
    return dict(sigma=round(float(sig),3),eps=round(float(eps),3))
def raw_wp(P,M,EPH):
    return ncdf(mean_margin(P,M,EPH)/np.sqrt(M['sigma']**2*P.frac+M['eps']**2))
def logit(p): p=np.clip(p,1e-6,1-1e-6); return np.log(p/(1-p))
def fit_platt(P,m,raw):
    k=P.decided if m is None else (m&P.decided); z=logit(raw[k]); lab=P.y[k]; A=np.column_stack([np.ones_like(z),z]); w=np.array([0.0,1.0])
    for _ in range(50):
        pp=1/(1+np.exp(-(A@w))); g=A.T@(lab-pp); H=(A*(pp*(1-pp))[:,None]).T@A
        st=np.linalg.solve(H,g); w=w+st
        if np.max(np.abs(st))<1e-9: break
    return dict(alpha=round(float(w[0]),5),beta=round(float(w[1]),5))
def apply_platt(raw,pl): return raw if not pl else 1/(1+np.exp(-(pl['alpha']+pl['beta']*logit(raw))))
def fit_total(P,m,EPH):
    X=np.column_stack([_m(P,m,P.T0)*_m(P,m,P.frac),_m(P,m,P.frac),np.abs(_m(P,m,EPH))]); b=np.linalg.lstsq(X,_m(P,m,P.TOT-P.CUR),rcond=None)[0]
    return dict(t_prior=round(float(b[0]),4),t_frac=round(float(b[1]),4),t_ep=round(float(b[2]),4))
def total_pred(P,T,EPH): return P.CUR+T['t_prior']*P.T0*P.frac+T['t_frac']*P.frac+T['t_ep']*np.abs(EPH)

def predict(P,prm):
    """win probability, final-margin mean and final total for every play under one parameter set"""
    EPH=ep_home(P,prm['ep']['table']); M=prm['margin']
    return dict(wp=apply_platt(raw_wp(P,M,EPH),prm.get('platt')),mm=mean_margin(P,M,EPH),tt=total_pred(P,prm['total'],EPH))

def fit_all(P,m=None,platt=True):
    """every step, in order, on the masked plays"""
    table=fit_ep(P,m); EPH=ep_home(P,table); M=fit_margin(P,m,EPH)
    M.update(fit_spread(P,m,P.RES-mean_margin(P,M,EPH)))
    pl=fit_platt(P,m,raw_wp(P,M,EPH)) if platt else None
    return dict(ep=dict(yard_bands=YB,dist_bands=DD,table=table),margin=M,platt=pl,total=fit_total(P,m,EPH))
