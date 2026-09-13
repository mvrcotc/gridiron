"""Game predictions -- exactly the model the published track record measures: opponent-adjusted team
ratings (engine2), a flat fitted home edge that is zero at neutral sites, a backup-quarterback term, and
recalibrated win probability. Ingredients the backtest never tested are not used."""
import os, sys, json, math
from collections import Counter, defaultdict
HERE=os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0,HERE)
from engine2 import run, pts_box, G, DATA
HP=json.load(open('hp2.json')); WPF=json.load(open('wpfit.json')); QBK=json.load(open('qbfit.json'))['k']
GI=json.load(open(os.path.join(DATA,'gi2.json'))); PJ,PL=GI['proj'],GI['players']
E2N={'LAR':'LA','WSH':'WAS'}; nf=lambda t:E2N.get(t,t); OUT={'O','IR','D','PUP','NFI','SUSP'}; BW=0.15
E2SW={str(g['espn']).split('.')[0]:(int(g['season']),int(g['week'])) for g in G.values() if g.get('espn')}
hits=[E2SW[x['id']] for x in GI['games'] if x['id'] in E2SW]
if not hits: sys.exit('slate games not found in the nflverse schedule')
UNTIL=Counter(hits).most_common(1)[0][0]
out,ST=run(HP,ret_state=True,until=UNTIL); L=ST['L']; wB,wE,wS=HP['wB'],HP['wE'],HP['wS']
print('slate: season %d week %d -- ratings use every game before it'%UNTIL)

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
    side={}; raw={}
    for s,tm,op in (('h',nf(g['h']),nf(g['a'])),('a',nf(g['a']),nf(g['h']))):
        ypp=L['ypp']*ST['oY'].rate(tm)*ST['dY'].rate(op); pl=L['plays']*ST['oP'].rate(tm)*ST['dP'].rate(op)
        yd=ypp*pl; td=yd*L['tdpy']*ST['oT'].rate(tm)*ST['dT'].rate(op); to=pl*L['topp']*ST['oO'].rate(tm)*ST['dO'].rate(op)
        pB=pts_box(yd,td,to); pE=L['ppg']+(ST['oE'].rate(tm)+ST['dE'].rate(op))*pl; pS=L['ppg']+ST['oS'].rate(tm)+ST['dS'].rate(op)
        raw[s]=wB*pB+wE*pE+wS*pS
        pyd,men=volume(g[s],pl,(g.get(s+'_pr') or GI['lg']['pr'])/100.0)
        side[s]=dict(p0=round(raw[s],1),yd=round(yd),td=round(td,2),to=round(to,2),pl=round(pl,1),pB=round(pB,1),pE=round(pE,1),
                     pS=round(pS,1),pyd=None if pyd is None else round(pyd),men=men)
    hv=0.0 if g.get('neutral') else HP['hfa']; qb=QBK*(g['a_qbbackup']-g['h_qbbackup'])
    ph=raw['h']+hv/2+qb/2; pa=raw['a']-hv/2-qb/2; mar=ph-pa; tot=ph+pa
    steps=[{'k':'Home field','v':round(hv,2),'w':'neutral site: no home edge' if g.get('neutral') else
            'a flat %.1f-point edge -- per-venue edges made held-out predictions worse, so none is used'%HP['hfa']}]
    if qb: steps.append({'k':'Backup quarterback','v':round(qb,2),'w':'a backup under centre is worth %.1f points of margin'%QBK})
    wp=0.5*(1+math.erf((WPF['a']+WPF['b']*mar)/(WPF['sd']*math.sqrt(2))))
    sp=round(-mar*2)/2.0; gt=round(tot*2)/2.0; vs,vt=g.get('spread'),g.get('ou')
    PRED[g['id']]=dict(ph=round(ph,1),pa=round(pa,1),sp=sp,tot=gt,wp=round(100*wp),sd=round(WPF['sd'],1),hfa=round(hv,2),qbnet=round(qb,2),steps=steps,
        bsp=None if vs is None else round((BW*sp+(1-BW)*vs)*2)/2.0, btot=None if vt is None else round((BW*gt+(1-BW)*vt)*2)/2.0,
        dsp=None if vs is None else round(sp-vs,1), dtot=None if vt is None else round(gt-vt,1),
        notes=['week %d: team ratings are mostly carried over from last season'%UNTIL[1]] if UNTIL[1]<=3 else [],
        h=side['h'],a=side['a'])
GI['pred']=PRED
if os.path.exists('track.json'): GI['track']=json.load(open('track.json'))
json.dump(PRED,open('pred.json','w')); json.dump(GI,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('predictions: %d games; backup-QB flags: %s'%(len(PRED),[x['a']+'@'+x['h'] for x in GI['games'] if x['a_qbbackup'] or x['h_qbbackup']] or 'none'))
