"""Game predictions: arithmetic, sign conventions, the displayed breakdown, and whether the live numbers come from
exactly the current champion weights the learning loop governs, through the shared model the track record uses."""
import os, sys, re, json, math
from common import num, PIPE, APP

half=lambda x:round(x*2)/2.0
STEP_PARAM={'Home field':('hfa',),'Venue edge':('venue',),'Backup quarterback':('qb',),'Rest':('rest',)}
TSTEP_PARAM={'Wind, cold and roof':('wx_dome','wx_wind','wx_cold'),'Referee crew':('ref',)}

def run(A):
    A.section('predictions'); D=A.D; PR=D['pred']; G={g['id']:g for g in D['games']}
    CH=json.load(open(os.path.join(PIPE,'champion.json'))); HP=next(v for v in CH['versions'] if v['v']==CH['current'])['params']
    PF=json.load(open(os.path.join(PIPE,'ptsfit.json'))); BW=HP['blend']

    bad=[]
    for gid,p in PR.items():
        g=G[gid]; n=g['a']+'@'+g['h']; mar=p['ph']-p['pa']
        if abs(p['sp']-half(-mar))>0.51: bad.append('%s spread %.1f but -(home-away)=%.2f'%(n,p['sp'],-mar))
        if abs(p['tot']-half(p['ph']+p['pa']))>0.51: bad.append('%s total %.1f but scores sum %.2f'%(n,p['tot'],p['ph']+p['pa']))
        for mk,gk,dk,bk in (('sp','spread','dsp','bsp'),('tot','ou','dtot','btot')):
            if g.get(gk) is None: continue
            if abs(p[dk]-(p[mk]-g[gk]))>0.06: bad.append('%s %s gap %.1f, recompute %.1f'%(n,mk,p[dk],p[mk]-g[gk]))
            if abs(p[bk]-half(BW*p[mk]+(1-BW)*g[gk]))>0.01: bad.append('%s blended %s %.1f, recompute %.1f at %.0f%% GridIron'%(n,mk,p[bk],half(BW*p[mk]+(1-BW)*g[gk]),100*BW))
        wp=100*0.5*(1+math.erf((HP['wp_a']+HP['wp_b']*mar)/(HP['wp_sd']*math.sqrt(2))))
        if abs(p['wp']-wp)>1.6: bad.append('%s win prob %d%%, recompute from the champion calibration %.1f%%'%(n,p['wp'],wp))
    A.check('R1','Spread, total, market gaps, blends and win probability recompute from the projected score and the champion weights',bad,len(PR))

    bad=[]
    for gid,p in PR.items():
        g=G[gid]; n=g['a']+'@'+g['h']
        if p.get('v')!=CH['current']: bad.append('%s predicted with weights version %s; the champion is version %s'%(n,p.get('v'),CH['current']))
        for s in ('a','h'):
            x=p[s]
            if abs(x['p0']-(HP['wB']*x['pB']+HP['wE']*x['pE']+HP['wS']*x['pS']))>0.15: bad.append('%s %s ensemble %.1f != weighted parts'%(n,s,x['p0']))
            if abs(x['pB']-(PF['b0']+PF['byds']*x['yd']+PF['btd']*x['td']+PF['bto']*x['to']))>0.35: bad.append('%s %s box-score points %.1f != fitted conversion'%(n,s,x['pB']))
        want_h=0.0 if g.get('neutral') else HP['hfa']
        if abs(p['hfa']-want_h)>0.01: bad.append('%s home edge %.2f, champion weights give %.2f'%(n,p['hfa'],want_h))
        want_q=HP['qb']*(int(g.get('a_qbbackup',0))-int(g.get('h_qbbackup',0)))
        if abs(p['qbnet']-want_q)>0.01: bad.append('%s QB term %.2f, flags imply %.2f'%(n,p['qbnet'],want_q))
        sh=sum(num(s['v']) for s in p.get('steps',[])); ta=sum(num(s['v']) for s in p.get('tsteps',[]))
        eh=p['h']['p0']+sh/2+ta/2; ea=p['a']['p0']-sh/2+ta/2
        if abs(eh-p['ph'])>0.15 or abs(ea-p['pa'])>0.15: bad.append('%s projected %.1f-%.1f but components give %.1f-%.1f'%(n,p['pa'],p['ph'],ea,eh))
    A.check('R2','Every projected score is reproduced from its own components and the current champion weights',bad,len(PR))

    bad=[]
    for gid,p in PR.items():
        g=G[gid]; n=g['a']+'@'+g['h']
        sh=sum(num(s['v']) for s in p.get('steps',[])); ta=sum(num(s['v']) for s in p.get('tsteps',[]))
        if abs(p['a']['p0']+p['h']['p0']+ta-(p['pa']+p['ph']))>0.15: bad.append('%s team rows plus total additions give %.1f, projected score %.1f'%(n,p['a']['p0']+p['h']['p0']+ta,p['pa']+p['ph']))
        if abs(p['h']['p0']-p['a']['p0']+sh-(p['ph']-p['pa']))>0.15: bad.append('%s rows plus shifts give margin %.1f, projected %.1f'%(n,p['h']['p0']-p['a']['p0']+sh,p['ph']-p['pa']))
        for lst,MAP,kind in ((p.get('steps',[]),STEP_PARAM,'shift'),(p.get('tsteps',[]),TSTEP_PARAM,'total step')):
            for s in lst:
                ps=MAP.get(s['k'])
                if not ps: bad.append('%s breakdown shows a %s "%s" that is not a champion weight'%(n,kind,s['k']))
                elif s['k']!='Home field' and all(HP[x]==0 for x in ps): bad.append('%s breakdown shows "%s" although its weight is zero'%(n,s['k']))
    A.check('R3','The breakdown a reader sees adds up, and shows only factors that carry weight in the champion',bad,len(PR))

    bad=[]
    for g in D['games']:
        det=str(g.get('det') or '').strip(); sp=g.get('spread')
        m=re.match(r'([A-Z]{2,3})\s*([+-]?\d+(\.\d+)?)',det)
        if not det or sp is None or not m: continue
        want=-abs(float(m.group(2))) if m.group(1)==g['h'] else abs(float(m.group(2)))
        if m.group(1) not in (g['a'],g['h']) or abs(num(sp)-want)>0.01: bad.append('%s@%s line "%s" but spread %s'%(g['a'],g['h'],det,sp))
    A.check('R4','Spread sign convention matches the line text for every game (negative = home favoured)',bad,len(D['games']))

    rd=lambda f:open(os.path.join(PIPE,f),encoding='utf-8').read()
    src,bt,gm,eng=rd('predict.py'),rd('backtest.py'),rd('gamemodel.py'),rd('engine2.py')
    bad=[]
    for name,code in (('predict.py',src),('backtest.py',bt)):
        for pat,why in ((r"\bgust",'reads a gust value'),(r"\btadj\b",'adds an untracked total adjustment'),(r"\bWPL\b",'blends an untested player-volume path'),
                        (r"HFA_SHRINK|slope_raw",'uses per-venue home edges outside the champion weights'),(r"hp2\.json|qbfit\.json|wpfit\.json",'reads launch-era weight files instead of champion.json')):
            if re.search(pat,code): bad.append('%s %s'%(name,why))
    if 'gm.score(' not in src or 'gm.current(' not in src: bad.append('predict.py does not score games with the shared model and the current champion')
    if 'gm.track_rows(' not in bt: bad.append('backtest.py does not build the record from the shared model')
    if "0.0 if f['neutral'] else P['hfa']" not in gm or "np.where(F['neutral']>0,0.0," not in gm: bad.append('gamemodel.py applies a home edge at neutral sites')
    if "!='Home'" not in eng and "=='Home' else 0.0" not in eng: bad.append('engine2 applies a home edge at neutral sites')
    A.check('R5','Live predictions and the track record run through one shared model and read weights only from the champion registry',bad)

    js=open(os.path.join(APP,'app.js'),encoding='ascii').read()
    shown=('pr-conf' in js) or any('conf' in p for p in PR.values())
    A.check('R6','No confidence label is shown unless it has been shown to predict accuracy',
            ['a High/Medium/Low label is displayed; the backtest found no accuracy difference between tiers'] if shown else [])
