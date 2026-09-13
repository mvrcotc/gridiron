"""Game predictions: arithmetic, sign conventions, the displayed breakdown, and whether the live model is
exactly the one the published track record measured."""
import os, sys, re, json, math
from common import num, PIPE, APP

half=lambda x:round(x*2)/2.0
def run(A):
    A.section('predictions'); D=A.D; PR=D['pred']; G={g['id']:g for g in D['games']}
    HP=json.load(open(os.path.join(PIPE,'hp2.json'))); PF=json.load(open(os.path.join(PIPE,'ptsfit.json')))
    WP=json.load(open(os.path.join(PIPE,'wpfit.json'))); QK=json.load(open(os.path.join(PIPE,'qbfit.json')))['k']

    bad=[]
    for gid,p in PR.items():
        g=G[gid]; n=g['a']+'@'+g['h']; mar=p['ph']-p['pa']
        if abs(p['sp']-half(-mar))>0.51: bad.append('%s spread %.1f but -(home-away)=%.2f'%(n,p['sp'],-mar))
        if abs(p['tot']-half(p['ph']+p['pa']))>0.51: bad.append('%s total %.1f but scores sum %.2f'%(n,p['tot'],p['ph']+p['pa']))
        for mk,gk,dk,bk in (('sp','spread','dsp','bsp'),('tot','ou','dtot','btot')):
            if g.get(gk) is None: continue
            if abs(p[dk]-(p[mk]-g[gk]))>0.06: bad.append('%s %s gap %.1f, recompute %.1f'%(n,mk,p[dk],p[mk]-g[gk]))
            if abs(p[bk]-half(0.15*p[mk]+0.85*g[gk]))>0.01: bad.append('%s blended %s %.1f, recompute %.1f'%(n,mk,p[bk],half(0.15*p[mk]+0.85*g[gk])))
        wp=100*0.5*(1+math.erf((WP['a']+WP['b']*mar)/(WP['sd']*math.sqrt(2))))
        if abs(p['wp']-wp)>1.6: bad.append('%s win prob %d%%, recalibrated recompute %.1f%%'%(n,p['wp'],wp))
    A.check('R1','Spread, total, market gaps, blends and win probability recompute from the projected score',bad,len(PR))

    bad=[]
    for gid,p in PR.items():
        g=G[gid]; n=g['a']+'@'+g['h']
        for s in ('a','h'):
            x=p[s]
            if abs(x['p0']-(HP['wB']*x['pB']+HP['wE']*x['pE']+HP['wS']*x['pS']))>0.15: bad.append('%s %s ensemble %.1f != weighted parts'%(n,s,x['p0']))
            if abs(x['pB']-(PF['b0']+PF['byds']*x['yd']+PF['btd']*x['td']+PF['bto']*x['to']))>0.35: bad.append('%s %s box-score points %.1f != fitted conversion'%(n,s,x['pB']))
        want_h=0.0 if g.get('neutral') else HP['hfa']
        if abs(p['hfa']-want_h)>0.01: bad.append('%s home edge %.2f, backtested model uses %.2f'%(n,p['hfa'],want_h))
        want_q=QK*(int(g.get('a_qbbackup',0))-int(g.get('h_qbbackup',0)))
        if abs(p['qbnet']-want_q)>0.01: bad.append('%s QB term %.2f, flags imply %.2f'%(n,p['qbnet'],want_q))
        eh=p['h']['p0']+p['hfa']/2+p['qbnet']/2; ea=p['a']['p0']-p['hfa']/2-p['qbnet']/2
        if abs(eh-p['ph'])>0.15 or abs(ea-p['pa'])>0.15: bad.append('%s projected %.1f-%.1f but components give %.1f-%.1f'%(n,p['pa'],p['ph'],ea,eh))
    A.check('R2','Every projected score is reproduced from its own components and the backtested terms',bad,len(PR))

    bad=[]
    for gid,p in PR.items():
        g=G[gid]; n=g['a']+'@'+g['h']
        if abs(p['a']['p0']+p['h']['p0']-(p['pa']+p['ph']))>0.15: bad.append('%s team rows add to %.1f, projected score to %.1f'%(n,p['a']['p0']+p['h']['p0'],p['pa']+p['ph']))
        shift=sum(num(s['v']) for s in p.get('steps',[]))
        if abs(p['h']['p0']-p['a']['p0']+shift-(p['ph']-p['pa']))>0.15: bad.append('%s rows plus shifts give margin %.1f, projected %.1f'%(n,p['h']['p0']-p['a']['p0']+shift,p['ph']-p['pa']))
        extra=[s['k'] for s in p.get('steps',[]) if s['k'] not in ('Home field','Backup quarterback')]+(['tsteps'] if p.get('tsteps') else [])
        if extra: bad.append('%s breakdown carries unbacktested steps %s'%(n,extra))
    A.check('R3','The breakdown a reader sees adds up: team rows sum to the total, shifts only move points between teams',bad,len(PR))

    bad=[]
    for g in D['games']:
        det=str(g.get('det') or '').strip(); sp=g.get('spread')
        m=re.match(r'([A-Z]{2,3})\s*([+-]?\d+(\.\d+)?)',det)
        if not det or sp is None or not m: continue
        want=-abs(float(m.group(2))) if m.group(1)==g['h'] else abs(float(m.group(2)))
        if m.group(1) not in (g['a'],g['h']) or abs(num(sp)-want)>0.01: bad.append('%s@%s line "%s" but spread %s'%(g['a'],g['h'],det,sp))
    A.check('R4','Spread sign convention matches the line text for every game (negative = home favoured)',bad,len(D['games']))

    src=open(os.path.join(PIPE,'predict.py'),encoding='utf-8').read(); eng=open(os.path.join(PIPE,'engine2.py'),encoding='utf-8').read()
    bad=[]
    for pat,why in ((r"\bgust",'reads a gust value'),(r"\btadj\b",'adds a total adjustment the backtest never had'),(r"\bWPL\b",'blends an untested player-volume path'),
                    (r"HFA_SHRINK|slope_raw",'uses per-venue home edges the held-out test rejected')):
        if re.search(pat,src): bad.append('predict.py %s'%why)
    if not re.search(r"raw\[s\]\s*=\s*wB\*pB\s*\+\s*wE\*pE\s*\+\s*wS\*pS",src): bad.append('predict.py team points are not the backtested rating ensemble')
    if "!='Home'" not in eng and "=='Home' else 0.0" not in eng: bad.append('engine2 applies a home edge at neutral sites')
    A.check('R5','The live prediction code contains only ingredients the backtest measured',bad)

    js=open(os.path.join(APP,'app.js'),encoding='ascii').read()
    shown=('pr-conf' in js) or any('conf' in p for p in PR.values())
    A.check('R6','No confidence label is shown unless it has been shown to predict accuracy',
            ['a High/Medium/Low label is displayed; the backtest found no accuracy difference between tiers'] if shown else [])
