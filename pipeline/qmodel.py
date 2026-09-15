"""Questionable players in one place: how often a player listed Questionable on the final injury report plays offense, and
how much less he plays when he does. fit_questionable.py fits it (qfit.json) on every season from 2019 to last season;
project.py applies it. Played = at least one offensive snap in nflverse snap counts.

    P(plays) = shrunk share by practice status (DNP / limited / full / none) and role (regular = 50%+ of offensive snaps
               over his previous four games, or the end of last season in the first weeks), shrunk toward the practice
               status, which is shrunk toward all questionable reports (m = 20 reports each level)
    usage    = offensive-snap share when he plays / his previous four games, relative to the same ratio for every regular
               (regression to the mean), by practice status; regulars only, part-time players 1.0"""
import os, csv, json
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); QFIT=os.path.join(HERE,'qfit.json')
M=20.0; PRACS=('DNP','LP','FP','none')
POS={'QB':'QB','RB':'RB','FB':'RB','WR':'WR','TE':'TE'}

def load_fit(path=QFIT): return json.load(open(path,encoding='utf-8')) if os.path.exists(path) else None
def prac(s):
    s=(s or '').lower()
    return 'DNP' if 'did not' in s else 'LP' if 'limited' in s else 'FP' if 'full' in s else 'none'
def key(pr,reg): return '%s|%d'%(pr,int(bool(reg)))
def crosswalk(path):
    """pfr id -> gsis id from nflverse players.csv"""
    return {r['pfr_id']:r['gsis_id'] for r in csv.DictReader(open(path,encoding='utf-8')) if r.get('pfr_id') and r.get('gsis_id')}
def read_snaps(path,X,season,into,seen=None):
    """(season, week, gsis id) -> offensive snap share for every regular-season game with an offensive snap"""
    for r in csv.DictReader(open(path,encoding='utf-8')):
        if r.get('game_type')!='REG': continue
        g=X.get(r.get('pfr_player_id'))
        if not g: continue
        if seen is not None: seen.add((season,g))
        try: off=float(r.get('offense_snaps') or 0)
        except ValueError: off=0.0
        if off>0: into[(season,int(r['week']),g)]=float(r.get('offense_pct') or 0)
def practice(path,week):
    """gsis id -> practice status on this week's final report (nflverse injuries file), {} when not published yet"""
    if not os.path.exists(path): return {}
    return {r['gsis_id']:prac(r.get('practice_status')) for r in csv.DictReader(open(path,encoding='utf-8'))
            if r.get('game_type')=='REG' and r.get('gsis_id') and str(r.get('week'))==str(week)}
def recent_share(snap,season,week,g):
    prev=[snap[(season,k,g)] for k in range(max(1,week-4),week) if (season,k,g) in snap]
    if not prev: prev=[snap[(season-1,k,g)] for k in range(15,19) if (season-1,k,g) in snap]
    return float(np.mean(prev)) if prev else None
def regular(share): return share is not None and share>=0.5

def fit(rows,snap,seasons):
    """rows: questionable reports with played / pct / prev / pr / reg; snap: the snap-share map; seasons: fit seasons"""
    T={}
    def add(k,x): t=T.setdefault(k,[0,0]); t[0]+=int(bool(x)); t[1]+=1
    for r in rows: add('all',r['played']); add(r['pr'],r['played']); add(key(r['pr'],r['reg']),r['played'])
    num=den=0.0
    for (y,w,g),pct in snap.items():
        if y in seasons and w>=5:
            pv=[snap[(y,k,g)] for k in range(w-4,w) if (y,k,g) in snap]
            if len(pv)>=3 and np.mean(pv)>=0.5: num+=pct; den+=float(np.mean(pv))
    cr=num/den
    act=[r for r in rows if r['played'] and r['reg']]
    ratio=lambda z: sum(r['pct'] for r in z)/sum(r['prev'] for r in z)/cr
    allu=min(1.0,ratio(act)); U={'all':round(allu,4)}
    for pr in PRACS:
        z=[r for r in act if r['pr']==pr]
        U[pr]=round(allu if len(z)<30 else min(1.0,(len(z)*ratio(z)+50*allu)/(len(z)+50)),4)
    return dict(T=T,U=U,control=round(cr,4),m=M)

def play_prob(F,pr,reg):
    m=F['m']; a,n=F['T']['all']; base=a/n
    a,n=F['T'].get(pr,[0,0]); c1=(a+m*base)/(n+m)
    a,n=F['T'].get(key(pr,reg),[0,0]); return (a+m*c1)/(n+m)
def usage(F,pr,reg): return F['U'].get(pr,F['U']['all']) if reg else 1.0
