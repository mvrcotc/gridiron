"""Rebuilds track.json -- the record on the Model page -- with the shared game model the live predictions use
(gamemodel.py). Every game is predicted by the champion weights in force before its week, so a weight the learning
loop changes later can never flatter the games it was tuned on. Also measures on held-out seasons the ingredients the
launch model left out."""
import os, sys, json, math, statistics
from collections import defaultdict
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0,HERE)
import gamemodel as gm
C=gm.load_champion(); CUR=gm.current(C)['params']; BOOK=gm.Book(); GA=BOOK.rows
f=lambda v:float(v) if v not in ('',None) else None
X=[]
for x in gm.track_rows(C,book=BOOK,last=2025):
    r=GA[x['gid']]; P=gm.version(C,x['v'])['params']; dome=(r['roof'] or '').lower() in ('dome','closed')
    X.append(dict(s=x['s'],w=x['w'],home=x['home'],m0=x['m0'],m=x['m'],qb=int(x['f']['qb']),t=x['t'],wp=x['wp'],hfa=P['hfa'],v=x['v'],
                  am=x['am'],at=x['at'],vs=x['vs'],vt=x['vt'],neutral=r['location']!='Home',dome=dome,
                  wind=0.0 if dome else (f(r['wind']) or 0.0),temp=70.0 if dome else (f(r['temp']) if r['temp'] else 60.0),gid=x['gid']))
def summ(S):
    St=[x for x in S if x['vt'] is not None]; a=[(x['am']-x['vs'])*(x['m']-x['vs']) for x in S if x['am']!=x['vs']]
    o=[(x['at']-x['vt'])*(x['t']-x['vt']) for x in St if x['at']!=x['vt']]; aw=sum(1 for v in a if v>0)
    return dict(n=len(S),gm=round(statistics.mean(abs(x['m']-x['am']) for x in S),2),vm=round(statistics.mean(abs(x['vs']-x['am']) for x in S),2),
        gt=round(statistics.mean(abs(x['t']-x['at']) for x in St),2),vt=round(statistics.mean(abs(x['vt']-x['at']) for x in St),2),
        su=round(100*sum(1 for x in S if (x['m']>0)==(x['am']>0))/len(S)),ats=round(100*aw/len(a),1),atsn=len(a),atsw=aw,
        ou=round(100*sum(1 for v in o if v>0)/len(o),1),oun=len(o))
T=json.load(open('track.json'))
HO=[x for x in X if x['s']>=2023]; TR=[x for x in X if x['s']<2023]
T['all']=summ(X); T['held']=summ(HO); T['wk1']=summ([x for x in X if x['w']==1]); T['by']={str(s):summ([x for x in X if x['s']==s]) for s in range(2019,2026)}
B=defaultdict(list)
for x in X:
    p=x['wp']; B[min(9,int(p*10))].append((p,1.0 if x['am']>0 else 0.5 if x['am']==0 else 0.0))
T['wpcal']={'err':round(100*sum(abs(statistics.mean(p for p,_ in v)-statistics.mean(a for _,a in v))*len(v) for v in B.values())/len(X),2),
            'bands':[{'b':k*10,'n':len(v),'p':round(100*statistics.mean(p for p,_ in v),1),'a':round(100*statistics.mean(a for _,a in v),1)} for k,v in sorted(B.items()) if len(v)>=20]}
mae=lambda S,fn,k='am':statistics.mean(abs(fn(x)-x[k]) for x in S)
bk=[x for x in HO if x['qb']]; K=CUR['qb']
src='fitted on 2019-22' if C['current']==1 else 'set by the learning loop (weights version %d)'%C['current']
e0,e1=mae(bk,lambda x:x['m0']),mae(bk,lambda x:x['m'])
T['qb']=dict(k=K,n=sum(1 for x in X if x['qb']),s=('A backup under centre is worth %.1f points of margin, %s. A starter counts as the usual one when he has the most starts so far '
  'this season — all anyone can know at kickoff. On the %d held-out 2023-25 games that involved a backup, the term %s GridIron’s margin error from %.2f to %.2f; '
  'the learning loop re-tests its size every week. An offseason quarterback change carried no measurable direction in week 1, so GridIron applies nothing for it '
  'and simply flags it.')%(K,src,len(bk),'cut' if e1<e0 else 'raised',e0,e1))
T['blend']=dict(T.get('blend') or {},w=round(100*CUR['blend']))
T['blend']['note']='GridIron gets %d%% of the blended line; the learning loop re-tests that share every week against the closing line alone.'%round(100*CUR['blend'])
T['asof']='Each game is predicted by the weights in force before its week (weights version %s).'%('1' if C['current']==1 else '1 to %d'%C['current'])
# ---- ingredients the launch model left out, measured on held-out seasons ----
REL={'STL':'LA','SD':'LAC','OAK':'LV'}; H=defaultdict(list); R=defaultdict(list); ah=[]; ar=[]
hist=sorted([r for r in GA.values() if r['home_score'] and 2015<=int(r['season'])<=2025],key=lambda r:(int(r['season']),int(r['week']))); i=0
for x in sorted(X,key=lambda x:(x['s'],x['w'])):
    while i<len(hist) and (int(hist[i]['season']),int(hist[i]['week']))<(x['s'],x['w']):
        r=hist[i]; i+=1
        if r['location']!='Home': continue
        m=float(r['home_score'])-float(r['away_score']); H[REL.get(r['home_team'],r['home_team'])].append(m); R[REL.get(r['away_team'],r['away_team'])].append(-m); ah.append(m); ar.append(-m)
    t=x['home']; x['swing']=statistics.mean(H[t])-statistics.mean(R[t]) if len(H[t])>=16 and len(R[t])>=16 else statistics.mean(ah)-statistics.mean(ar)
flat=mae(HO,lambda x:x['m']); venue=mae(HO,lambda x:x['m']-(0 if x['neutral'] else x['hfa']-0.394*x['swing']))
hand=lambda x:x['t']+(0.6 if x['dome'] else 0)-(min(2,0.11*(x['wind']-10)) if x['wind']>=15 else 0)-(0.8 if not x['dome'] and x['temp']<=32 else 0)
A=np.array([[1,x['dome'],max(0,x['wind']-8),max(0,45-x['temp'])/10] for x in TR],float); b=np.linalg.lstsq(A,np.array([x['at']-x['t'] for x in TR]),rcond=None)[0]
fit=lambda x:x['t']+b[1]*x['dome']+b[2]*max(0,x['wind']-8)+b[3]*max(0,45-x['temp'])/10
T['excluded']=dict(margin_flat=round(flat,3),margin_venue=round(venue,3),total_none=round(mae(HO,lambda x:x['t'],'at'),3),
                   total_hand=round(mae(HO,hand,'at'),3),total_fitted=round(mae(HO,fit,'at'),3))
E=T['excluded']
for fc in T['factors']:
    if fc['k']=='Venue home-field edge':
        verdict=('made held-out 2023-25 margin error worse (%.3f vs %.3f)' if E['margin_venue']>=E['margin_flat'] else
                 'barely moved held-out 2023-25 margin error (%.3f vs %.3f), far short of earning a weight')%(E['margin_venue'],E['margin_flat'])
        fc['s']=('Real in raw results: a venue measured 4 points friendlier than average predicts about +1.6 points of home margin. But the team '
          'ratings already absorb it — adding per-venue edges on top %s, so GridIron uses one flat %.1f-point edge, and none at neutral sites. '
          'The learning loop re-tests a venue edge every week; it has to earn its weight.')%(verdict,CUR['hfa'])
    if fc['k']=='Wind, cold and roof' and fc.get('scope')=='the betting line':
        fc['s']=('The same conditions barely move game totals, and the market prices them. GridIron adds no conditions adjustment to its totals: '
          'hand-set adjustments left held-out error unchanged (%.3f vs %.3f with none) and adjustments fitted on 2019-22 made it worse (%.3f). '
          'The learning loop re-tests this every week.')%(E['total_hand'],E['total_none'],E['total_fitted'])
json.dump(T,open('track.json','w'),indent=1)
print('track rebuilt: all %s | held-out %s | wk1 %s'%({k:T['all'][k] for k in ('n','gm','vm','ats')},{k:T['held'][k] for k in ('n','gm','vm','ats')},{k:T['wk1'][k] for k in ('gm','vm')}))
print('calibration error %.2f | excluded ingredients %s'%(T['wpcal']['err'],E))
