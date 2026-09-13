"""Players, depth charts, usage and coverage rebuilt from fresh nflverse files, so roster moves, jersey changes and
depth-chart updates reach the app without a manual rebuild. Definitions match the audited build exactly."""
import os, json, csv, statistics
from collections import defaultdict, Counter
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
rows=lambda f: csv.DictReader(open(os.path.join(DATA,f),newline='',encoding='utf-8'))
D=json.load(open(os.path.join(DATA,'gi2.json'),encoding='utf-8'))
ids={g['id'] for g in D['games']}
sw=Counter((int(r['season']),int(r['week'])) for r in rows('games_all.csv') if (r.get('espn') or '').split('.')[0] in ids)
if not sw: raise SystemExit('slate games not found in the nflverse schedule')
SEASON,WEEK=sw.most_common(1)[0][0]; PREV=SEASON-1

# ---- players: weekly roster for the slate's week, or the latest week published before it ----
R=[r for r in rows('rost%02d.csv'%(SEASON%100)) if (r.get('week') or '').isdigit()]
weeks=sorted({int(r['week']) for r in R})
use=max([w for w in weeks if w<=WEEK] or weeks[:1])
PLAYERS={}; PFR={}
for r in R:
    if int(r['week'])!=use: continue
    g=(r.get('gsis_id') or '').strip()
    if not g: continue
    j=(r.get('jersey_number') or '').strip()
    try: j=str(int(float(j)))
    except ValueError: j=''
    PLAYERS[g]={'n':r['full_name'].strip(),'j':j,'p':r['position'].strip(),'t':r['team'].strip()}
    if (r.get('pfr_id') or '').strip(): PFR[r['pfr_id'].strip()]=g
for r in rows('players_all.csv'):
    p=(r.get('pfr_id') or '').strip(); g=(r.get('gsis_id') or '').strip()
    if p and g: PFR.setdefault(p,g)

# ---- depth chart: newest snapshot, slot structure preserved ----
FAM_O={'QB':'QB','RB':'RB','WR':'WR','TE':'TE','LT':'OL','LG':'OL','C':'OL','RG':'OL','RT':'OL'}
FAM_D={'LDE':'DL','RDE':'DL','NT':'DL','LDT':'DL','RDT':'DL','WLB':'LB','MLB':'LB','SLB':'LB','LILB':'LB','RILB':'LB',
       'LCB':'CB','RCB':'CB','NB':'CB','FS':'S','SS':'S'}
SLOT_ORD={'LT':0,'LG':1,'C':2,'RG':3,'RT':4,'LDE':0,'NT':1,'LDT':1,'RDT':2,'RDE':3,'LCB':0,'NB':1,'RCB':2,'FS':0,'SS':1}
LB_ORD={'3-4':{'WLB':0,'SLB':1,'LILB':2,'RILB':3,'MLB':2},'4-3':{'WLB':0,'MLB':1,'SLB':2,'LILB':1,'RILB':2}}
latest=max(r['dt'] for r in csv.DictReader(open(os.path.join(DATA,'raw','dc.csv'),newline='',encoding='utf-8')))
raw=defaultdict(lambda:{'o':defaultdict(list),'d':defaultdict(list),'s':None}); slots=defaultdict(lambda:defaultdict(list))
for r in csv.DictReader(open(os.path.join(DATA,'raw','dc.csv'),newline='',encoding='utf-8')):
    if r['dt']!=latest: continue
    grp=r['pos_grp']
    if grp=='3WR 1TE': side,FAM='o',FAM_O
    elif grp in ('Base 3-4 D','Base 4-3 D'): side,FAM='d',FAM_D; raw[r['team']]['s']='3-4' if '3-4' in grp else '4-3'
    else: continue
    fam=FAM.get(r['pos_abb']); g=(r.get('gsis_id') or '').strip()
    if not fam or not g or not r['player_name'].strip(): continue
    sch=raw[r['team']]['s']
    so=(LB_ORD.get(sch,LB_ORD['4-3']).get(r['pos_abb'],9) if fam=='LB' else SLOT_ORD.get(r['pos_abb'],9))
    raw[r['team']][side][fam].append({'g':g,'abb':r['pos_abb'],'r':int(r['pos_rank']),'so':so})
    slots[r['team']][(side,r['pos_abb'],r['pos_slot'])].append((int(r['pos_rank']),g))
    if g not in PLAYERS: PLAYERS[g]={'n':r['player_name'].strip(),'j':'','p':r['pos_abb'],'t':r['team']}
def fam_list(lst):
    seen=set(); out=[]
    for p in sorted(lst,key=lambda p:(p['r'],p['so'])):
        if p['g'] in seen: continue
        seen.add(p['g']); out.append({'g':p['g'],'p':p['abb']})
    return out[:5]
DEPTH={}
for t,v in raw.items():
    if not v['o'] or not v['d']: continue
    DEPTH[t]={'o':{k:fam_list(x) for k,x in v['o'].items()},'d':{k:fam_list(x) for k,x in v['d'].items()},
              'sl':{s+':'+a+':'+n:[g for _,g in sorted(set(l))][:4] for (s,a,n),l in slots[t].items()},'s':v['s']}
for espn_code,nfl in {'LAR':'LA','WSH':'WAS'}.items():
    if nfl in DEPTH: DEPTH[espn_code]=DEPTH[nfl]
NEED={e['g'] for v in DEPTH.values() for s in ('o','d') for lst in v[s].values() for e in lst}

# ---- usage: prior-season snap share, joined pfr id -> gsis ----
wk=defaultdict(dict)
for r in rows('snaps%02d.csv'%(PREV%100)):
    if r['game_type']!='REG': continue
    g=PFR.get(r['pfr_player_id'].strip())
    if not g or g not in NEED: continue
    wk[g][int(r['week'])]=round(max(float(r['offense_pct'] or 0),float(r['defense_pct'] or 0))*100,1)
USAGE={}
for g,w in wk.items():
    ks=sorted(w); vals=[w[k] for k in ks]
    USAGE[g]={'s':round(statistics.mean(vals),1),'s3':round(statistics.mean([w[k] for k in ks[-3:]]),1),'g':len(vals),'sp':[int(round(w[k])) for k in ks[-8:]]}

# ---- which players carry a production line (stats.py fills the numbers) ----
KEYS=('targets','receptions','receiving_yards','receiving_tds','receiving_air_yards','attempts','completions','passing_yards','passing_tds','carries','rushing_yards','rushing_tds')
has=set()
for r in rows('stw%02d.csv'%(PREV%100)):
    if r['season_type']=='REG' and r['player_id'] in NEED and (any(abs(float(r[k] or 0))>=0.5 for k in KEYS) or float(r.get('target_share') or 0)>0):
        has.add(r['player_id'])

# ---- coverage: prior-season PFR advanced defence ----
iv=lambda v:int(round(float(v or 0))); fv=lambda v:round(float(v or 0),3)
COV={}
for r in csv.DictReader(open(os.path.join(DATA,'raw','cov.csv'),newline='',encoding='utf-8')):
    if r['season']!=str(PREV): continue
    g=PFR.get(r['pfr_id'].strip())
    if not g or g not in NEED: continue
    COV[g]={'tgt':iv(r['tgt']),'cmp':iv(r['cmp']),'cpct':round(fv(r['cmp_percent'])*100,1),'yds':iv(r['yds']),'rat':fv(r['rat']),
            'td':iv(r['td']),'int':iv(r['int']),'prss':iv(r['prss']),'mt':round(fv(r['m_tkl_percent'])*100,1)}

P={g:v for g,v in PLAYERS.items() if g in NEED}
old=D; changed=[g for g in P if g in old['players'] and P[g]!=old['players'][g]]
starters=lambda dep,t,s,f:[e['g'] for e in ((dep.get(t) or {}).get(s,{}).get(f) or [])][:3]
moved=['%s %s'%(t,f) for t in DEPTH for s,fams in (('o',('QB','RB','WR','TE')),('d',('CB','S','LB','DL'))) for f in fams
       if starters(DEPTH,t,s,f)!=starters(old['depth'],t,s,f)]
print('slate %d wk %d | roster wk %d | depth chart %s -> %s'%(SEASON,WEEK,use,old.get('dt'),latest))
print('players %d -> %d (%d added, %d removed, %d changed name/team/position/jersey)'%(
    len(old['players']),len(P),len(set(P)-set(old['players'])),len(set(old['players'])-set(P)),len(changed)))
print('depth groups whose top-3 changed: %d %s'%(len(moved),moved[:12]))
D['players']=P; D['depth']=DEPTH; D['usage']=USAGE; D['cov']=COV; D['dt']=latest
D['prod']={g:old['prod'].get(g,{}) for g in sorted(has)}
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('usage %d | production lines %d | coverage %d'%(len(USAGE),len(D['prod']),len(COV)))
