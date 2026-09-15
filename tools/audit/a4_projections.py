"""Player projections: distribution integrity, stat definitions, and the weather / injury passes."""
import os, re, json, hashlib
from common import num, rows, DATA, PIPE, APP, nfl, roster_rows

OUT={'O','IR','D','PUP','NFI','SUSP'}
QS=[2,5,10,20,25,30,40,50,60,70,75,80,85,90,95,98]

def run(A):
    A.section('projections'); D=A.D; PJ=D['proj']; PL=D['players']; IJ=D.get('injd',{})
    live={p for p,v in PJ.items() if not v.get('out')}

    bad=[]
    for g in live:
        for k in ('q','qry','qrec','qru','qpy'):
            a=PJ[g].get(k)
            if isinstance(a,list) and any(a[i]>a[i+1]+1e-9 for i in range(len(a)-1)):
                bad.append('%s %s not monotone: %s'%(PL[g]['n'],k,a))
    A.check('P1','Every projection distribution rises monotonically',bad,len(live))

    bad=[]
    for g in live:
        p=PJ[g]; q=p['q']
        if abs(num(p['med'])-q[QS.index(50)])>0.15: bad.append('%s median %.1f but 50th pct %.1f'%(PL[g]['n'],p['med'],q[7]))
        if abs(num(p['flr'])-q[QS.index(25)])>0.15: bad.append('%s floor %.1f but 25th pct %.1f'%(PL[g]['n'],p['flr'],q[4]))
        if abs(num(p['ceil'])-q[QS.index(85)])>0.15: bad.append('%s ceiling %.1f but 85th pct %.1f'%(PL[g]['n'],p['ceil'],q[12]))
        if not (p['flr']<=p['med']<=p['ceil']): bad.append('%s floor/median/ceiling out of order'%PL[g]['n'])
    A.check('P2','Median, floor and ceiling agree with their own distribution',bad,len(live))

    bad=[]
    for g in live:
        p=PJ[g]; x=p.get('x',{})
        for key,expect,label in (('xry',num(x.get('tgt'))*num(x.get('ypt')),'targets x yards/target'),
                                 ('xrec',num(x.get('tgt'))*num(x.get('cr')),'targets x catch rate'),
                                 ('xru',num(x.get('car'))*num(x.get('ypc')),'carries x yards/carry')):
            if p.get(key) is None: continue
            if abs(p[key]-expect)>max(0.6,0.03*expect):
                bad.append('%s %s=%.1f, %s=%.1f'%(PL[g]['n'],key,p[key],label,expect))
    A.check('P3','Expected yards and receptions match their inputs (yds = targets x yards-per-target)',bad,len(live))

    # model.py defines ypt = receiving yards / TARGETS, so receiving yards = tgt*ypt, never tgt*cr*ypt
    bad=[]
    near=r"[\w\s\.\(\)'\",:]{0,40}"
    pat=re.compile(r"\bcr\b"+near+r"\*"+near+r"\bypt\b|\bypt\b"+near+r"\*"+near+r"\bcr\b")
    for path in [os.path.join(PIPE,f) for f in ('predict.py','project.py','props.py','playermodel.py')]+[os.path.join(APP,'app.js')]:
        for i,line in enumerate(open(path,encoding='utf-8'),1):
            if pat.search(line): bad.append('%s:%d  %s'%(os.path.basename(path),i,line.strip()[:110]))
    A.check('P4','No code computes receiving yards as targets x catch rate x yards-per-target',bad)

    bad=[]; outs=0
    for g,v in IJ.items():
        if v.get('s') in OUT and g in PJ:
            outs+=1
            if num(PJ[g].get('med'))!=0 or not PJ[g].get('out'):
                bad.append('%s is %s but still projected %.1f'%(PL.get(g,{}).get('n',g),v['s'],num(PJ[g].get('med'))))
    for g,p in PJ.items():
        if p.get('out') and (IJ.get(g) or {}).get('s') not in OUT:
            bad.append('%s zeroed but injury status is %s'%(PL[g]['n'],(IJ.get(g) or {}).get('s')))
    A.check('P5','Every ruled-out player projects to zero, and nobody else does',bad,outs)

    post={t for gm in D['games'] if gm.get('state')=='post' for t in (nfl(gm['a']),nfl(gm['h']))}
    slate={t for gm in D['games'] for t in (nfl(gm['a']),nfl(gm['h']))}
    bad=['%s (%s) projected but %s'%(PL[g]['n'],PL[g]['t'],'their game is final' if PL[g]['t'] in post else 'not on this slate')
         for g in PJ if nfl(PL[g]['t']) in post or nfl(PL[g]['t']) not in slate]
    A.check('P6','Projections exist only for games not yet played',bad,len(PJ))

    roster={g:r['team'] for g,r in roster_rows(D).items()}
    bad=['%s listed on %s, week-1 roster says %s'%(PL[g]['n'],PL[g]['t'],roster[g]) for g in PJ
         if g in roster and nfl(roster[g])!=nfl(PL[g]['t'])]
    miss=[PL[g]['n'] for g in PJ if g not in roster]
    A.check('P7','Projected players are on the team the week-1 roster says',bad,len(PJ))
    if miss: A.warn('P7b','Projected players missing from the week-1 roster file',miss,len(miss))

    bad=[]
    for g in live:
        x=PJ[g].get('x',{})
        if not 0<=num(x.get('cr'))<=1: bad.append('%s catch rate %s'%(PL[g]['n'],x.get('cr')))
        if num(x.get('tgt'))>0.5 and not 2<=num(x.get('ypt'))<=25: bad.append('%s yds/target %s'%(PL[g]['n'],x.get('ypt')))
        if num(x.get('car'))>0.5 and not 1<=num(x.get('ypc'))<=10: bad.append('%s yds/carry %s'%(PL[g]['n'],x.get('ypc')))
        if min(num(PJ[g].get('med')),num(x.get('tgt')),num(x.get('car')))<0: bad.append('%s negative value'%PL[g]['n'])
    A.check('P8','Rates sit in plausible football ranges',bad,len(live))

    # ---- weather pass, recomputed from raw game conditions ----
    F=D['wxfit']; LG=F['lg']; CEN=json.load(open(os.path.join(PIPE,'wxcentre.json')))
    def mult(g,use_gust):
        dome=1.0 if (g.get('indoor') or str(g.get('roof') or '').lower() in ('dome','closed')) else 0.0
        if dome: wind,temp=0.0,70.0
        else:
            wind=(g.get('gust') if use_gust else g.get('wsus'))
            if wind in (None,''): wind=g.get('rgust' if use_gust else 'rwind')
            wind=num(wind); temp=g.get('temp'); temp=g.get('rtemp') if temp in (None,'') else temp
            temp=60.0 if temp in (None,'') else num(temp)
        w=max(0.0,wind-8.0); c=max(0.0,45.0-temp)/10.0
        return {k:1+(F[k]['w']*(w-CEN['w'])+F[k]['c']*(c-CEN['c'])+F[k]['dome']*(dome-CEN['dome']))/LG[k] for k in ('att','ypa','car','ypc')}
    bad=[]
    for g in D['games']:
        s=(D.get('wx') or {}).get(g['id'])
        if not s: bad.append('%s@%s has no weather record'%(g['a'],g['h'])); continue
        want=mult(g,False); gust=mult(g,True)
        err=max(abs(s['m'][k]-want[k]) for k in want); gerr=max(abs(s['m'][k]-gust[k]) for k in gust)
        if err>0.002:
            bad.append('%s@%s multipliers %s, sustained-wind recompute %s%s'%(g['a'],g['h'],s['m'],
                {k:round(v,4) for k,v in want.items()},'  <- matches GUSTS' if gerr<0.002 else ''))
        if not g.get('indoor') and g.get('wsus') is None and g.get('state')!='post':
            bad.append('%s@%s outdoor with no sustained wind reading'%(g['a'],g['h']))
    A.check('P9','Weather multipliers recompute from sustained wind (not gusts) for every game',bad,len(D['games']))

    # ---- injury pass: recovered volume never exceeds the measured absorption rate ----
    CPL=json.load(open(os.path.join(PIPE,'champion_players.json'))); PP=next(v for v in CPL['versions'] if v['v']==CPL['current'])['params']
    AB={'tgt':PP['absorb_tgt'],'car':PP['absorb_car']}; bad=[]; info=[]
    for team,v in (D.get('redist') or {}).items():
        ft=sum(num(o.get('tgt')) for o in v['out']); fc=sum(num(o.get('car')) for o in v['out'])
        gt=sum(num(p['inj'].get('t')) for g,p in PJ.items() if p.get('inj') and PL[g]['t']==team)
        gc=sum(num(p['inj'].get('c')) for g,p in PJ.items() if p.get('inj') and PL[g]['t']==team)
        top=max([num(p['inj'].get('c')) for g,p in PJ.items() if p.get('inj') and PL[g]['t']==team] or [0])
        if gt>AB['tgt']*ft+0.25: bad.append('%s handed out %.1f targets from %.1f freed (cap %.0f%%)'%(team,gt,ft,100*AB['tgt']))
        if gc>AB['car']*fc+0.25: bad.append('%s handed out %.1f carries from %.1f freed (cap %.0f%%)'%(team,gc,fc,100*AB['car']))
        if fc>1 and top>AB['car']*fc+0.1: bad.append('%s one back got %.1f of %.1f freed carries'%(team,top,fc))
        info.append('%s: %.1f/%.1f tgt, %.1f/%.1f car'%(team,gt,ft,gc,fc))
        if any(PJ[g].get('out') for g,p in PJ.items() if p.get('inj') and PL[g]['t']==team):
            bad.append('%s gave volume to a player who is himself out'%team)
    A.check('P10','Injury redistribution respects the measured 75% / 54% recovery caps',bad,len(D.get('redist') or {}))

    bad=[]
    for g in live:
        for k in ('qry','qrec','qru','qpy'):
            if isinstance(PJ[g].get(k),list) and any(abs(v-round(v))>1e-9 for v in PJ[g][k]):
                bad.append('%s %s has fractional values %s -- a count distribution was rescaled instead of simulated'%(PL[g]['n'],k,PJ[g][k][:8]))
    A.check('P11','Yardage and reception distributions are whole numbers (adjustments change inputs, then simulate)',bad,len(live))
    opp={}
    for gm in D['games']: opp[nfl(gm['a'])]=nfl(gm['h']); opp[nfl(gm['h'])]=nfl(gm['a'])
    bad=['%s opponent adjustment %s, table value for %s is %s'%(PL[g]['n'],PJ[g]['x'].get('adj'),opp.get(nfl(PL[g]['t'])),D['cal']['def'].get(opp.get(nfl(PL[g]['t'])),0))
         for g in live if abs(num(PJ[g]['x'].get('adj'))-num(D['cal']['def'].get(opp.get(nfl(PL[g]['t'])),0)))>0.006]
    A.check('P14','Every projection uses its real opponent\'s pass-defence adjustment (ESPN/nflverse codes resolved)',bad,len(live))

    # questionable players: play probability and usage recomputed from qfit.json, this week's report and snap shares
    bad=[]; qf=os.path.join(PIPE,'qfit.json'); QF=json.load(open(qf)) if os.path.exists(qf) else None
    H=(D.get('cal') or {}).get('history') or {}; sea,wk=H.get('season'),H.get('week')
    qs=[g for g,v in IJ.items() if v.get('s')=='Q' and g in live]
    if qs and not (QF and sea and wk): bad.append('questionable players on the slate but no qfit.json or projection week')
    elif qs:
        pfr={r['gsis_id']:r['pfr_id'] for r in rows(os.path.join(DATA,'players_all.csv')) if r.get('gsis_id') and r.get('pfr_id')}; sn={}
        for y in (sea-1,sea):
            f=os.path.join(DATA,'snaps%02d.csv'%(y%100))
            if os.path.exists(f):
                for r in rows(f):
                    if r['game_type']=='REG' and num(r['offense_snaps'])>0: sn[(y,int(num(r['week'])),r['pfr_player_id'])]=num(r['offense_pct'])
        rep={}; f=os.path.join(DATA,'injuries%02d.csv'%(sea%100))
        if os.path.exists(f):
            for r in rows(f):
                if r['game_type']=='REG' and int(num(r['week']))==wk: rep[r['gsis_id']]=(r.get('practice_status') or '').lower()
        T=QF['T']; U=QF['U']; m=QF['m']
        for g in qs:
            n=PL[g]['n']; qp=PJ[g].get('qp')
            if not qp: bad.append('%s is questionable but projected as certain to play'%n); continue
            s=rep.get(g,''); pr='DNP' if 'did not' in s else 'LP' if 'limited' in s else 'FP' if 'full' in s else 'none'
            k=pfr.get(g); sh=[sn[(sea,w,k)] for w in range(max(1,wk-4),wk) if (sea,w,k) in sn] or [sn[(sea-1,w,k)] for w in range(15,19) if (sea-1,w,k) in sn]
            reg=bool(sh) and sum(sh)/len(sh)>=0.5
            a,nn=T['all']; c0=a/nn; a,nn=T.get(pr,[0,0]); c1=(a+m*c0)/(nn+m); a,nn=T.get('%s|%d'%(pr,int(reg)),[0,0]); p=(a+m*c1)/(nn+m)
            u=U.get(pr,U['all']) if reg else 1.0
            if (qp.get('pr'),bool(qp.get('reg')))!=(pr,reg): bad.append('%s practice/role %s/%s, the reports say %s/%s'%(n,qp.get('pr'),qp.get('reg'),pr,reg))
            if abs(num(qp.get('p'))-p)>0.0015 or abs(num(qp.get('u'))-u)>0.0015: bad.append('%s plays %s x usage %s, recomputed %.3f x %.3f'%(n,qp.get('p'),qp.get('u'),p,u))
            if num(qp.get('z'))<(1-p)-0.02: bad.append('%s scores zero in %.0f%% of simulations but sits %.0f%% of the time'%(n,100*num(qp.get('z')),100*(1-p)))
            if abs(num(PJ[g]['mean'])-p*num(qp.get('a')))>0.25: bad.append('%s mean %.1f, expected %.3f x %.1f if he plays'%(n,num(PJ[g]['mean']),p,num(qp.get('a'))))
    A.check('P12','Questionable players carry the measured chance they play and lighter use when they do (recomputed from the report, snap shares and qfit.json)',bad,len(qs))
    A.warn('P13','Weather and injury adjustments change model inputs using separately fitted rates; their effect on accuracy has not itself been backtested',
           ['the PIT calibration (48/52 around the median) was measured on 2025 projections without them'])
