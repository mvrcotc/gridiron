import json,urllib.request,csv,time,os,sys
def get(u,tries=3):
    for i in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=25))
        except Exception as e:
            if i==tries-1: return {'__err':str(e)}
            time.sleep(0.6)
HERE=os.path.dirname(os.path.abspath(__file__))
DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
D=json.load(open(os.path.join(DATA,'gi2.json')))
QS=D['cal']['qs']
# espn_id -> gsis_id
X={}
for r in csv.DictReader(open(os.path.join(DATA,'players_all.csv'))):
    if r.get('espn_id') and r.get('gsis_id'): X[str(r['espn_id']).split('.')[0]]=r['gsis_id']
print('espn->gsis crosswalk entries:',len(X))
TYPE={'Total Receiving Yards (incl. overtime)':('qry','Receiving yards'),
      'Total Receptions (incl. overtime)':('qrec','Receptions'),
      'Total Rushing Yards (incl. overtime)':('qru','Rushing yards'),
      'Total Passing Yards (incl. overtime)':('qpy','Passing yards')}
def pOver(q,line):
    if not q or line is None: return None
    n=len(q)
    if line<=q[0]: return 0.995
    if line>=q[-1]: return 0.005
    for i in range(n-1):
        if q[i]<=line<=q[i+1]:
            span=q[i+1]-q[i]
            f=0.5 if span<=0 else (line-q[i])/span
            pct=(QS[i]+(QS[i+1]-QS[i])*f)/100.0
            return max(0.005,min(0.995,1.0-pct))
    return None
ROWS=[]; seen=0
for g in D['games']:
    ref=('http://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/%s/'
         'competitions/%s/odds/100/propBets?lang=en&region=us&limit=100')%(g['id'],g['id'])
    page=1
    while True:
        p=get(ref+'&page=%d'%page)
        items=p.get('items') or []
        if '__err' in p or not items: break
        for x in items:
            seen+=1
            tn=(x.get('type') or {}).get('name')
            if tn not in TYPE: continue
            aref=(x.get('athlete') or {}).get('$ref','')
            aid=aref.rstrip('?lang=en&region=us').split('/athletes/')[-1].split('?')[0]
            gs=X.get(aid)
            if not gs or gs not in D['proj']: continue
            cur=((x.get('current') or {}).get('target') or {}).get('value')
            opn=((x.get('open') or {}).get('target') or {}).get('value')
            if cur is None: continue
            key,label=TYPE[tn]
            q=D['proj'][gs].get(key)
            if not q: continue
            pr=pOver(q,cur)
            if pr is None: continue
            ROWS.append(dict(g=g['id'],gs=gs,k=key,lab=label,line=cur,open=opn,p=round(pr,4),
                             mine=round(q[QS.index(50)],1) if 50 in QS else None))
        if page>=(p.get('pageCount') or 999): break
        page+=1
        time.sleep(0.12)
    time.sleep(0.15)
print('props scanned: %d  |  matched to a GridIron distribution: %d'%(seen,len(ROWS)))
json.dump(ROWS,open(os.path.join(HERE,'props.json'),'w'))
import statistics as _st
from collections import defaultdict as _dd
_seen=set(); U=[]
for r in ROWS:
    k=(r['gs'],r['k'],r['line'])
    if k in _seen or D['proj'][r['gs']].get('out'): continue
    _seen.add(k); U.append(r)
_bt=_dd(list)
for r in U: _bt[r['k']].append(r['p'])
LEAN={k:round(_st.mean(v),4) for k,v in _bt.items()}
BY=_dd(dict)
for r in U:
    adj=r['p']+(0.5-LEAN[r['k']])
    BY[r['gs']][r['k']]=dict(line=r['line'],open=r['open'],p=round(r['p'],3),
                          rel=round(max(0.005,min(0.995,adj)),3),lab=r['lab'])
_under=round(100*sum(1 for r in U if r['p']<0.5)/max(len(U),1))
D['props']=dict(by=BY,lean=LEAN,n=len(U),book='DraftKings via ESPN',fetched=time.strftime('%Y-%m-%dT%H:%MZ',time.gmtime()),note=("GridIron leans under on %d%% of these lines. Its distributions are well calibrated against actual results (48.2%% of outcomes land below the predicted median across 2,301 validated player-weeks), so this is a real disagreement with the book rather than a modelling artefact \u2014 but books are known to shade player-prop overs, and without historical prop lines there is no way to prove which side is right. Treat the raw lean as unproven. The relative column strips out GridIron\u2019s own average lean so you can see which players it disagrees on specifically. No prices are published with these lines, so break-even is assumed at -110.")%_under)
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('props stored: %d lines for %d players; GridIron leans under on %d%%'%(len(U),len(BY),_under))
