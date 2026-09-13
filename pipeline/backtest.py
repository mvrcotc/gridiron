"""Rebuilds track.json -- the record on the Model page -- from the same engine and terms the live predictions use,
and measures on held-out seasons the ingredients the live model deliberately leaves out."""
import os, sys, json, math, csv, statistics
from collections import defaultdict, Counter
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0,HERE)
import engine2
from engine2 import DATA
HP=json.load(open('hp2.json')); K=json.load(open('qbfit.json'))['k']; WP=json.load(open('wpfit.json'))
GA={r['game_id']:r for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'))) if r['game_type']=='REG'}
f=lambda v:float(v) if v not in ('',None) else None
st=defaultdict(Counter)
for r in GA.values():
    if r['home_score'] and r['home_qb_id']:
        st[(r['season'],r['home_team'])][r['home_qb_id']]+=1; st[(r['season'],r['away_team'])][r['away_qb_id']]+=1
prim={k:c.most_common(1)[0][0] for k,c in st.items()}
X=[]
for o in engine2.run(HP):
    r=GA[o['gid']]
    if o['season']>2025 or not r['spread_line']: continue
    qb=int(bool(r['away_qb_id']) and prim.get((r['season'],r['away_team']))!=r['away_qb_id'])-int(bool(r['home_qb_id']) and prim.get((r['season'],r['home_team']))!=r['home_qb_id'])
    dome=(r['roof'] or '').lower() in ('dome','closed')
    X.append(dict(s=o['season'],w=o['week'],home=o['home'],m0=o['margin'],m=o['margin']+K*qb,qb=qb,t=o['total'],am=o['amargin'],at=o['atotal'],
                  vs=f(r['spread_line']),vt=f(r['total_line']),neutral=r['location']!='Home',dome=dome,
                  wind=0.0 if dome else (f(r['wind']) or 0.0),temp=70.0 if dome else (f(r['temp']) if r['temp'] else 60.0),gid=o['gid']))
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
    p=0.5*(1+math.erf((WP['a']+WP['b']*x['m'])/(WP['sd']*math.sqrt(2)))); B[min(9,int(p*10))].append((p,1.0 if x['am']>0 else 0.5 if x['am']==0 else 0.0))
T['wpcal']={'err':round(100*sum(abs(statistics.mean(p for p,_ in v)-statistics.mean(a for _,a in v))*len(v) for v in B.values())/len(X),2),
            'bands':[{'b':k*10,'n':len(v),'p':round(100*statistics.mean(p for p,_ in v),1),'a':round(100*statistics.mean(a for _,a in v),1)} for k,v in sorted(B.items()) if len(v)>=20]}
mae=lambda S,fn,k='am':statistics.mean(abs(fn(x)-x[k]) for x in S)
bk=[x for x in HO if x['qb']]
T['qb']=dict(k=K,n=sum(1 for x in X if x['qb']),s=('A backup under centre is worth %.1f points of margin, fitted on 2019-22. On the %d held-out 2023-25 games that '
  'involved one, it cut GridIron’s margin error from %.2f to %.2f. An offseason quarterback change carried no measurable direction in week 1, '
  'so GridIron applies nothing for it and simply flags it.')%(K,len(bk),mae(bk,lambda x:x['m0']),mae(bk,lambda x:x['m'])))
# ---- ingredients deliberately left out, measured on held-out seasons ----
REL={'STL':'LA','SD':'LAC','OAK':'LV'}; H=defaultdict(list); R=defaultdict(list); ah=[]; ar=[]
hist=sorted([r for r in GA.values() if r['home_score'] and 2015<=int(r['season'])<=2025],key=lambda r:(int(r['season']),int(r['week']))); i=0
for x in sorted(X,key=lambda x:(x['s'],x['w'])):
    while i<len(hist) and (int(hist[i]['season']),int(hist[i]['week']))<(x['s'],x['w']):
        r=hist[i]; i+=1
        if r['location']!='Home': continue
        m=float(r['home_score'])-float(r['away_score']); H[REL.get(r['home_team'],r['home_team'])].append(m); R[REL.get(r['away_team'],r['away_team'])].append(-m); ah.append(m); ar.append(-m)
    t=x['home']; x['swing']=statistics.mean(H[t])-statistics.mean(R[t]) if len(H[t])>=16 and len(R[t])>=16 else statistics.mean(ah)-statistics.mean(ar)
flat=mae(HO,lambda x:x['m']); venue=mae(HO,lambda x:x['m']-(0 if x['neutral'] else HP['hfa']-0.394*x['swing']))
hand=lambda x:x['t']+(0.6 if x['dome'] else 0)-(min(2,0.11*(x['wind']-10)) if x['wind']>=15 else 0)-(0.8 if not x['dome'] and x['temp']<=32 else 0)
A=np.array([[1,x['dome'],max(0,x['wind']-8),max(0,45-x['temp'])/10] for x in TR],float); b=np.linalg.lstsq(A,np.array([x['at']-x['t'] for x in TR]),rcond=None)[0]
fit=lambda x:x['t']+b[1]*x['dome']+b[2]*max(0,x['wind']-8)+b[3]*max(0,45-x['temp'])/10
T['excluded']=dict(margin_flat=round(flat,3),margin_venue=round(venue,3),total_none=round(mae(HO,lambda x:x['t'],'at'),3),
                   total_hand=round(mae(HO,hand,'at'),3),total_fitted=round(mae(HO,fit,'at'),3))
E=T['excluded']
for fc in T['factors']:
    if fc['k']=='Venue home-field edge':
        fc['s']=('Real in raw results: a venue measured 4 points friendlier than average predicts about +1.6 points of home margin. But the team '
          'ratings already absorb it — adding per-venue edges on top made held-out 2023-25 margin error worse (%.3f vs %.3f), so GridIron uses '
          'one flat %.1f-point edge, and none at neutral sites. The venue edge on each card is context, not an input.')%(E['margin_venue'],E['margin_flat'],HP['hfa'])
    if fc['k']=='Wind, cold and roof' and fc.get('scope')=='the betting line':
        fc['s']=('The same conditions barely move game totals, and the market prices them. GridIron adds no conditions adjustment to its totals: '
          'hand-set adjustments left held-out error unchanged (%.3f vs %.3f with none) and adjustments fitted on 2019-22 made it worse (%.3f).')%(E['total_hand'],E['total_none'],E['total_fitted'])
json.dump(T,open('track.json','w'),indent=1)
print('track rebuilt: all %s | held-out %s | wk1 %s'%({k:T['all'][k] for k in ('n','gm','vm','ats')},{k:T['held'][k] for k in ('n','gm','vm','ats')},{k:T['wk1'][k] for k in ('gm','vm')}))
print('calibration error %.2f | excluded ingredients %s'%(T['wpcal']['err'],E))
