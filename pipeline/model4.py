import csv, json, collections
import numpy as np
rng=np.random.default_rng(11)
exec(open('model.py').read().split('# ------------------------------------------------- 1.')[0])
F=json.load(open('fit1.json')); BASE=F['base']; K=json.load(open('fit_k.json')); O=json.load(open('fit_opp.json'))
DEF=O['DEF']; SLOPE=F['slope']; ICEPT=F['icept']; PLAYS=F['plays']; TDC=F['tdcurve']
BY=collections.defaultdict(list)
for p in P: BY[p['id']].append(p)
for v in BY.values(): v.sort(key=lambda x:x['w'])
POS={pid:v[0]['pos'] for pid,v in BY.items()}
TS_PRIOR={'WR':.145,'TE':.115,'RB':.085}

def td_per_target(adot):
    xs=[c[0] for c in TDC]; ys=[c[1] for c in TDC]
    return float(np.interp(adot,xs,ys))

def accumulate(hist):
    a=collections.defaultdict(float)
    for g in hist:
        for k in ('tgt','rec','ry','rtd','ay','car','ru','rutd','att','cmp','py','ptd','pint'):
            a[k]+=g[k]
        a['tatt']+=TW.get((g['w'],g['tm']),{}).get('att',0.0)
        a['tcar']+=TW.get((g['w'],g['tm']),{}).get('car',0.0)
        a['g']+=1
    return a

def project(pid, hist, spread, opp, pos):
    """Same function drives the live projection and the backtest."""
    if not hist: return None
    a=accumulate(hist)
    pr=BASE.get(pos)
    if pr is None: return None
    # --- volume ---
    prate=ICEPT+SLOPE*spread
    tatt=PLAYS*prate
    ts=(a['tgt']+K['target share']*TS_PRIOR.get(pos,.12))/(a['tatt']+K['target share']) if a['tatt']>0 else TS_PRIOR.get(pos,.12)
    tgt=tatt*ts
    # --- efficiency, regressed then opponent-adjusted ---
    cr=(a['rec']+K['catch rate']*pr['cr'])/(a['tgt']+K['catch rate'])
    ypt=(a['ry']+K['yards/target']*pr['ypt'])/(a['tgt']+K['yards/target'])
    ypt=max(2.0, ypt+DEF.get(opp,0.0))
    adot=(a['ay']+40*pr['adot'])/(a['tgt']+40) if a['tgt']+40>0 else pr['adot']
    tdpt=td_per_target(adot)
    # --- rushing ---
    cshare=(a['car']+20*0.12)/(a['tcar']+20) if a['tcar']>0 else 0.0
    car=PLAYS*(1-prate)*cshare
    ypc=(a['ru']+40*4.3)/(a['car']+40)
    rutdpc=(a['rutd']+40*0.028)/(a['car']+40)
    # --- passing ---
    pa=cr_p=py=ptd=pint=0.0
    if a['att']>=20:
        pashare=a['att']/max(1.0,a['tatt'])
        pa=tatt*min(1.0,pashare)
        cr_p=(a['cmp']+60*.655)/(a['att']+60)
        ypa=(a['py']+120*7.1)/(a['att']+120)
        py=pa*ypa
        ptd=pa*((a['ptd']+120*.045)/(a['att']+120))
        pint=pa*((a['pint']+120*.023)/(a['att']+120))
    return {'tgt':tgt,'cr':cr,'ypt':ypt,'tdpt':tdpt,'car':car,'ypc':ypc,'rutdpc':rutdpc,
            'pa':pa,'pcr':cr_p,'py':py,'ptd':ptd,'pint':pint,'n':a['tgt']+a['car']+a['att']}

def simulate(pj, N, infl):
    """infl scales parameter uncertainty; calibrated on held-out weeks."""
    def nb(mean, over):
        mean=max(1e-6,mean)
        r=max(0.05, mean/max(1e-6,(over-1.0))) if over>1.0 else 1e6
        p=r/(r+mean)
        return rng.negative_binomial(r,p,N).astype(float)
    tgt=nb(pj['tgt'], infl['vol'])
    rec=rng.binomial(np.maximum(0,tgt).astype(int), min(.99,max(.01,pj['cr'])))
    ypr=pj['ypt']/max(.05,pj['cr'])
    shp=np.maximum(0.02, rec*infl['yshape'])
    ry=rng.gamma(shp, ypr/infl['yshape'])
    rtd=rng.binomial(np.maximum(0,tgt).astype(int), min(.4,max(0.0,pj['tdpt'])))
    car=nb(pj['car'], infl['vol']) if pj['car']>0.2 else np.zeros(N)
    rsh=np.maximum(0.02, car*infl['yshape'])
    ru=rng.gamma(rsh, pj['ypc']/infl['yshape']) if pj['car']>0.2 else np.zeros(N)
    rutd=rng.binomial(np.maximum(0,car).astype(int), min(.3,max(0.0,pj['rutdpc'])))
    if pj['pa']>1:
        pa=nb(pj['pa'], infl['vol'])
        psh=np.maximum(0.02, pa*infl['yshape']*1.8)
        py=rng.gamma(psh, (pj['py']/max(1e-6,pj['pa']))/(infl['yshape']*1.8))
        ptd=rng.poisson(max(0,pj['ptd']),N); pint=rng.poisson(max(0,pj['pint']),N)
    else:
        py=np.zeros(N); ptd=np.zeros(N); pint=np.zeros(N)
    pts=rec*1.0+ry*0.1+rtd*6+ru*0.1+rutd*6+py*0.04+ptd*4-pint*2
    return {'pts':pts,'ry':ry,'rec':rec.astype(float),'ru':ru,'py':py,'tgt':tgt}

# ------------------------------------ walk-forward calibration on 2025
def backtest(infl, weeks=range(8,19), N=800):
    pit=[]
    for w in weeks:
        for pid,games in BY.items():
            pos=POS.get(pid)
            if pos not in BASE: continue
            hist=[g for g in games if g['w']<w]
            cur=[g for g in games if g['w']==w]
            if len(hist)<4 or not cur: continue
            g=cur[0]
            ctx=GM.get((w,g['tm']))
            if not ctx: continue
            pj=project(pid,hist,ctx['spread'],g['opp'],pos)
            if not pj or pj['tgt']+pj['car']+pj['pa']<2: continue
            s=simulate(pj,N,infl)
            act=g['rec']*1.0+g['ry']*.1+g['rtd']*6+g['ru']*.1+g['rutd']*6+g['py']*.04+g['ptd']*4-g['pint']*2
            pit.append(float((s['pts']<act).mean()+0.5*(s['pts']==act).mean()))
    return np.array(pit)

print('calibrating the simulator on held-out weeks (2025, weeks 8-18)\n')
best=None
for vol in (1.15,1.45,1.8):
    for ysh in (0.45,0.7,1.0):
        infl={'vol':vol,'yshape':ysh}
        pit=backtest(infl)
        h,_=np.histogram(pit,bins=10,range=(0,1))
        h=h/h.sum()
        dev=float(np.abs(h-0.1).sum())          # total variation from uniform
        if best is None or dev<best[0]: best=(dev,infl,pit,h)
        print(f'  vol x{vol:<5} yshape {ysh:<5} -> calibration error {dev:.3f}  (n={len(pit)})')
dev,infl,pit,h=best
print(f'\nbest: {infl}   calibration error {dev:.3f}')
print('\nPIT histogram — where actual results landed in the predicted distribution.')
print('A perfectly calibrated model puts 10% in every decile:\n')
for i,v in enumerate(h):
    bar='#'*int(round(v*200))
    print(f'  {i*10:>3}-{i*10+10:<3}%  {v*100:5.1f}%  {bar}')
json.dump({'infl':infl,'pit':list(map(float,h)),'n':int(len(pit))},open('fit_cal.json','w'))
