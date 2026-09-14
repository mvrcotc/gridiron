"""Game predictions from the shared game model (gamemodel.py) with the champion weights in force -- exactly what the
published track record measures and what the learning loop re-tests every week. A factor at zero weight adds nothing
and is not shown as a step."""
import os, sys, json, math
from collections import Counter, defaultdict
HERE=os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0,HERE)
import gamemodel as gm
from engine2 import run, pts_box, G, DATA
C=gm.load_champion(); V=gm.current(C); P=V['params']; BOOK=gm.Book()
GI=json.load(open(os.path.join(DATA,'gi2.json'))); PJ,PL=GI['proj'],GI['players']
E2N={'LAR':'LA','WSH':'WAS'}; nf=lambda t:E2N.get(t,t); OUT={'O','IR','D','PUP','NFI','SUSP'}
E2SW={str(g['espn']).split('.')[0]:(int(g['season']),int(g['week'])) for g in G.values() if g.get('espn')}
hits=[E2SW[x['id']] for x in GI['games'] if x['id'] in E2SW]
if not hits: sys.exit('slate games not found in the nflverse schedule')
UNTIL=Counter(hits).most_common(1)[0][0]
out,ST=run(P,ret_state=True,until=UNTIL); L=ST['L']
print('slate: season %d week %d -- ratings use every game before it; weights version %d'%(UNTIL[0],UNTIL[1],V['v']))

cnt=defaultdict(Counter)
for g in G.values():
    if int(g['season'])!=UNTIL[0] or not g['home_score'] or int(g['week'])>=UNTIL[1]: continue
    if g.get('home_qb_id'): cnt[g['home_team']][g['home_qb_id']]+=1
    if g.get('away_qb_id'): cnt[g['away_team']][g['away_qb_id']]+=1
PRIMARY={t:c.most_common(1)[0][0] for t,c in cnt.items()}; IJ=GI.get('injd',{})
def expected_qb(code):
    for e in (GI['depth'].get(code) or GI['depth'].get(nf(code)) or {}).get('o',{}).get('QB',[]):
        if (IJ.get(e['g']) or {}).get('s') not in OUT: return e['g']
def volume(code,plays,prate):
    """display only: how the projected starters' volume and efficiency add up, normalised to team plays"""
    men=[]; tg=ty=tc=cy=0.0
    for k,p in PJ.items():
        pl=PL.get(k)
        if not pl or nf(pl['t'])!=nf(code) or p.get('out'): continue
        x=p.get('x') or {}; t=x.get('tgt') or 0.0; c=x.get('car') or 0.0; ry=t*(x.get('ypt') or 0.0); uy=c*(x.get('ypc') or 0.0)
        tg+=t; ty+=ry; tc+=c; cy+=uy
        men.append(dict(g=k,n=pl['n'],p=pl['p'],j=pl.get('j'),tgt=round(t,1),car=round(c,1),y=round(ry+uy,1)))
    if tg<8 or tc<6: return None,[]
    return plays*prate*ty/tg+plays*(1-prate)*cy/tc, sorted(men,key=lambda m:-m['y'])[:8]

PRED={}
for g in GI['games']:
    for s in ('a','h'):
        p=PRIMARY.get(nf(g[s])); e=expected_qb(g[s]); g[s+'_qbbackup']=int(bool(p and e and e!=p))
    side={}; comp={}
    for s,tm,op in (('h',nf(g['h']),nf(g['a'])),('a',nf(g['a']),nf(g['h']))):
        ypp=L['ypp']*ST['oY'].rate(tm)*ST['dY'].rate(op); pl=L['plays']*ST['oP'].rate(tm)*ST['dP'].rate(op)
        yd=ypp*pl; td=yd*L['tdpy']*ST['oT'].rate(tm)*ST['dT'].rate(op); to=pl*L['topp']*ST['oO'].rate(tm)*ST['dO'].rate(op)
        pB=pts_box(yd,td,to); pE=L['ppg']+(ST['oE'].rate(tm)+ST['dE'].rate(op))*pl; pS=L['ppg']+ST['oS'].rate(tm)+ST['dS'].rate(op)
        comp[s]=(pB,pE,pS)
        pyd,men=volume(g[s],pl,(g.get(s+'_pr') or GI['lg']['pr'])/100.0)
        side[s]=dict(p0=round(P['wB']*pB+P['wE']*pE+P['wS']*pS,1),yd=round(yd),td=round(td,2),to=round(to,2),pl=round(pl,1),pB=round(pB,1),pE=round(pE,1),
                     pS=round(pS,1),pyd=None if pyd is None else round(pyd),men=men)
    ref_name=(g.get('ref') or {}).get('n')
    row=BOOK.rows.get(BOOK.by_espn.get(g['id'],'')) or dict(season=UNTIL[0],week=UNTIL[1],location='Neutral' if g.get('neutral') else 'Home',
        home_team=nf(g['h']),away_team=nf(g['a']),home_rest='',away_rest='',roof='',wind='',temp='',referee='')
    f=BOOK.features(row,dict(neutral=bool(g.get('neutral')),qb=g['a_qbbackup']-g['h_qbbackup'],dome=bool(g.get('indoor')),
                             wind=g.get('wsus'),temp=g.get('temp'),ref=ref_name))
    ph,pa=gm.score(P,comp['h']+comp['a'],f); mar=ph-pa; tot=ph+pa
    sh,ta=gm.shifts(P,f); SH=dict(sh); TA=dict(ta)
    steps=[{'k':'Home field','v':round(SH['hfa'],2),'w':'neutral site: no home edge' if f['neutral'] else
            'a flat %.1f-point edge%s'%(P['hfa'],' -- per-venue edges are re-tested every week and have not earned any weight' if P['venue']==0 else '')}]
    if abs(SH['venue'])>=0.005:
        steps.append({'k':'Venue edge','v':round(SH['venue'],2),'w':'this venue has measured %.1f points %s than the average home edge, at a learned weight of %.2f'%(
            abs(f['venue']),'friendlier' if f['venue']>0 else 'tougher',P['venue'])})
    if abs(SH['qb'])>=0.005: steps.append({'k':'Backup quarterback','v':round(SH['qb'],2),'w':'a backup under centre is worth %.1f points of margin'%P['qb']})
    if abs(SH['rest'])>=0.005:
        steps.append({'k':'Rest','v':round(SH['rest'],2),'w':'%s has %d more day%s of rest, at %.2f points a day'%(g['h'] if f['rest']>0 else g['a'],abs(f['rest']),
            '' if abs(f['rest'])==1 else 's',abs(P['rest']))})
    tsteps=[]
    if abs(TA['weather'])>=0.005:
        tsteps.append({'k':'Wind, cold and roof','v':round(TA['weather'],2),'w':'learned effect of %s on the game total'%(
            'the roof' if f['dome'] else '%.0f mph sustained wind%s'%(f['windx']+8,', %.0f°F'%(45-10*f['coldx']) if f['coldx']>0 else ''))})
    if abs(TA['ref'])>=0.005:
        tsteps.append({'k':'Referee crew','v':round(TA['ref'],2),'w':"%s's recent games ran %+.1f points against the total line, at a learned weight of %.2f"%(ref_name or 'the referee',f['ref'],P['ref'])})
    wp=gm.win_prob(P,mar)
    sp=round(-mar*2)/2.0; gt=round(tot*2)/2.0; vs,vt=g.get('spread'),g.get('ou'); bw=P['blend']
    PRED[g['id']]=dict(ph=round(ph,1),pa=round(pa,1),sp=sp,tot=gt,wp=round(100*wp),sd=round(P['wp_sd'],1),hfa=round(SH['hfa'],2),qbnet=round(SH['qb'],2),
        steps=steps,tsteps=tsteps,v=V['v'],
        bsp=None if vs is None else round((bw*sp+(1-bw)*vs)*2)/2.0, btot=None if vt is None else round((bw*gt+(1-bw)*vt)*2)/2.0,
        dsp=None if vs is None else round(sp-vs,1), dtot=None if vt is None else round(gt-vt,1),
        notes=['week %d: team ratings are mostly carried over from last season'%UNTIL[1]] if UNTIL[1]<=3 else [],
        h=side['h'],a=side['a'])
GI['pred']=PRED
LS=os.path.join(HERE,'learning','summary.json')
GI['learn']=json.load(open(LS,encoding='utf-8')) if os.path.exists(LS) else {}
GI['learn']['params']=P; GI['learn']['version']=V['v']
import livemodel as lm
LV=gm.current(lm.load_champion())
GI['live']=dict({k:LV['params'][k] for k in ('ep','margin','total','platt')},version=LV['v'])
if os.path.exists('livefit.json'):
    LF=json.load(open('livefit.json')); GI['live'].update({k:LF[k] for k in ('fit','test','n_test_plays','report','built','note') if k in LF})
GI['learn']['live_params']=LV['params']; GI['learn']['live_version']=LV['v']
if os.path.exists('track.json'): GI['track']=json.load(open('track.json'))
json.dump(PRED,open('pred.json','w')); json.dump(GI,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('predictions: %d games with weights version %d; backup-QB flags: %s'%(len(PRED),V['v'],[x['a']+'@'+x['h'] for x in GI['games'] if x['a_qbbackup'] or x['h_qbbackup']] or 'none'))
