"""Fits qfit.json: the chance a Questionable skill player plays and his usage when he does (qmodel.py), from nflverse
injury reports and snap counts, every season from 2019 through last season. Downloads what it needs into data/raw/nflverse/.

   python3 pipeline/fit_questionable.py          refit, keep the stored held-out test
   python3 pipeline/fit_questionable.py --test   also re-run the held-out test: for each season from 2023, fit only on
                                                 earlier seasons and score the player model's own projections for every
                                                 questionable player-week against what he scored (0 when he sat)"""
import os, sys, csv, json, datetime, urllib.request
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
import qmodel as qm, gamemodel as gm, playermodel as pm
ROOT=os.path.dirname(HERE); DATA=os.path.join(ROOT,'data'); RAW=os.path.join(DATA,'raw','nflverse')
NFLV='https://github.com/nflverse/nflverse-data/releases/download'; FIRST=2019; FIRST_TEST=2023

def season_now():
    t=datetime.date.today(); return t.year if t.month>=3 else t.year-1
def get(tag,name,refresh=False):
    dest=os.path.join(RAW,name)
    if os.path.exists(dest) and not refresh: return dest
    os.makedirs(RAW,exist_ok=True)
    with urllib.request.urlopen('%s/%s/%s'%(NFLV,tag,name),timeout=120) as r: b=r.read()
    open(dest+'.part','wb').write(b); os.replace(dest+'.part',dest); return dest

def load(last):
    X=qm.crosswalk(os.path.join(DATA,'players_all.csv')); snap={}; seen=set(); rows=[]
    for y in range(FIRST-1,last+1): qm.read_snaps(get('snap_counts','snap_counts_%d.csv'%y,refresh=y==last),X,y,snap,seen)
    for y in range(FIRST,last+1):
        for r in csv.DictReader(open(get('injuries','injuries_%d.csv'%y,refresh=y==last),encoding='utf-8')):
            g=r.get('gsis_id')
            if r.get('game_type')!='REG' or r.get('report_status')!='Questionable' or r.get('position') not in qm.POS or (y,g) not in seen: continue
            w=int(r['week']); sh=qm.recent_share(snap,y,w,g)
            rows.append(dict(y=y,w=w,g=g,team=r['team'],pr=qm.prac(r.get('practice_status')),played=(y,w,g) in snap,
                             pct=snap.get((y,w,g)),prev=sh,reg=qm.regular(sh)))
    return rows,snap

def held_out(rows,snap,last):
    P=gm.current(pm.load_champion())['params']; panel=pm.Panel.from_db(FIRST_TEST-1); SP={}; OPP={}
    for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'),encoding='utf-8')):
        if r['game_type']!='REG' or gm.fnum(r['spread_line']) is None: continue
        k=(int(r['season']),int(r['week'])); sp=float(r['spread_line'])
        SP[k+(r['home_team'],)]=-sp; SP[k+(r['away_team'],)]=sp; OPP[k+(r['home_team'],)]=r['away_team']; OPP[k+(r['away_team'],)]=r['home_team']
    out=[]
    for y in range(FIRST_TEST,last+1):
        F=qm.fit([r for r in rows if r['y']<y],snap,set(range(FIRST,y)))
        for r in rows:
            if r['y']!=y: continue
            pos=panel.POS.get(r['g']); k=(y,r['w'],r['team'])
            if pos not in pm.BASE or k not in SP: continue
            pj=pm.project_one(panel,r['g'],y,r['w'],SP[k],OPP[k],pos,P)
            if not pj: continue
            E=max(0.0,float(pm.expected_points(pj))); act=next((pm.actual_points(g) for g in panel.BY.get(r['g'],[]) if g['s']==y and g['w']==r['w']),0.0)
            out.append((y*100+r['w'],y,E,E*qm.play_prob(F,r['pr'],r['reg'])*qm.usage(F,r['pr'],r['reg']),act,r['played']))
    wk=np.array([o[0] for o in out]); sea=np.array([o[1] for o in out]); E=np.array([o[2] for o in out]); Q=np.array([o[3] for o in out]); A=np.array([o[4] for o in out])
    d=(E-A)**2-(Q-A)**2; u,inv=np.unique(wk,return_inverse=True); s=np.bincount(inv,weights=d); n=np.bincount(inv).astype(float)
    ix=np.random.default_rng(11).integers(0,len(u),size=(4000,len(u))); p=float((1+np.sum(s[ix].sum(1)/n[ix].sum(1)<=0))/4001)
    r2=lambda v:round(float(v),3)
    return dict(seasons=[FIRST_TEST,last],player_weeks=len(out),played=r2(np.mean([o[5] for o in out])),mean_scored=r2(A.mean()),
                mean_projected=[r2(E.mean()),r2(Q.mean())],mse=[r2(((E-A)**2).mean()),r2(((Q-A)**2).mean())],mae=[r2(np.abs(E-A).mean()),r2(np.abs(Q-A).mean())],
                p=round(p,4),by_season={int(y):[r2(((E-A)**2)[sea==y].mean()),r2(((Q-A)**2)[sea==y].mean())] for y in np.unique(sea)},
                how='each season fitted only on earlier seasons; [certain to play, with the discount]; p = week-clustered bootstrap share with no improvement')

if __name__=='__main__':
    last=season_now()-1; rows,snap=load(last)
    F=qm.fit(rows,snap,set(range(FIRST,last+1))); old=qm.load_fit() or {}
    out=dict(fitted=datetime.date.today().isoformat(),seasons=[FIRST,last],reports=len(rows),played=round(float(np.mean([r['played'] for r in rows])),4),**F)
    out['test']=held_out(rows,snap,last) if '--test' in sys.argv else old.get('test')
    json.dump(out,open(qm.QFIT,'w',encoding='utf-8'),indent=1)
    print('qfit: %d questionable reports %d-%d, %.0f%% played; usage %s'%(len(rows),FIRST,last,100*out['played'],F['U']))
    for k in sorted(F['T']): print('  %-8s played %5.1f%% of %d'%(k,100*F['T'][k][0]/F['T'][k][1],F['T'][k][1]))
    if out.get('test'): print('held-out:',json.dumps(out['test']))
