import csv, json, collections, statistics, re, sys

# ---------------- players, from the roster (gsis_id is the key) ----------------
PLAYERS={}; PFR2GSIS={}
for r in csv.DictReader(open('rost26.csv')):
    if r['week']!='1': continue
    g=r['gsis_id'].strip()
    if not g: continue
    j=(r.get('jersey_number') or '').strip()
    try: j=str(int(float(j)))
    except Exception: j=''
    PLAYERS[g]={'n':r['full_name'].strip(),'j':j,'p':r['position'].strip(),'t':r['team'].strip()}
    if r.get('pfr_id','').strip(): PFR2GSIS[r['pfr_id'].strip()]=g

# the weekly roster only carries a pfr_id for ~2/3 of players; the league-wide
# players file fills the rest of the crosswalk so every join stays ID-based
for r in csv.DictReader(open('players_all.csv')):
    p=(r.get('pfr_id') or '').strip(); g=(r.get('gsis_id') or '').strip()
    if p and g: PFR2GSIS.setdefault(p,g)

# ---------------- depth chart, slot structure preserved ----------------
FAM_O={'QB':'QB','RB':'RB','WR':'WR','TE':'TE','LT':'OL','LG':'OL','C':'OL','RG':'OL','RT':'OL'}
FAM_D={'LDE':'DL','RDE':'DL','NT':'DL','LDT':'DL','RDT':'DL',
       'WLB':'LB','MLB':'LB','SLB':'LB','LILB':'LB','RILB':'LB',
       'LCB':'CB','RCB':'CB','NB':'CB','FS':'S','SS':'S'}
SLOT_ORD={'LT':0,'LG':1,'C':2,'RG':3,'RT':4,'LDE':0,'NT':1,'LDT':1,'RDT':2,'RDE':3,
          'LCB':0,'NB':1,'RCB':2,'FS':0,'SS':1}
LB_ORD={'3-4':{'WLB':0,'SLB':1,'LILB':2,'RILB':3,'MLB':2},
        '4-3':{'WLB':0,'MLB':1,'SLB':2,'LILB':1,'RILB':2}}

rows=list(csv.DictReader(open('dc.csv')))
latest=max(r['dt'] for r in rows)
rows=[r for r in rows if r['dt']==latest]

raw=collections.defaultdict(lambda:{'o':collections.defaultdict(list),'d':collections.defaultdict(list),'s':None})
slots=collections.defaultdict(lambda: collections.defaultdict(list))   # team -> slot key -> [(rank,gsis)]
for r in rows:
    grp=r['pos_grp']
    if grp=='3WR 1TE': side,FAM=('o',FAM_O)
    elif grp in ('Base 3-4 D','Base 4-3 D'):
        side,FAM=('d',FAM_D); raw[r['team']]['s']='3-4' if '3-4' in grp else '4-3'
    else: continue
    fam=FAM.get(r['pos_abb']); g=r.get('gsis_id','').strip()
    if not fam or not g or not r['player_name'].strip(): continue
    sch=raw[r['team']]['s']
    so=(LB_ORD.get(sch,LB_ORD['4-3']).get(r['pos_abb'],9) if fam=='LB' else SLOT_ORD.get(r['pos_abb'],9))
    raw[r['team']][side][fam].append({'g':g,'abb':r['pos_abb'],'r':int(r['pos_rank']),'so':so})
    slots[r['team']][(side,r['pos_abb'],r['pos_slot'])].append((int(r['pos_rank']),g))
    if g not in PLAYERS:
        PLAYERS[g]={'n':r['player_name'].strip(),'j':'','p':r['pos_abb'],'t':r['team']}

def fam_list(lst):
    seen=set(); out=[]
    for p in sorted(lst,key=lambda p:(p['r'],p['so'])):
        if p['g'] in seen: continue
        seen.add(p['g']); out.append({'g':p['g'],'p':p['abb']})
    return out[:5]

DEPTH={}
for t,v in raw.items():
    if not v['o'] or not v['d']: continue
    sl={}
    for (side,abb,snum),lst in slots[t].items():
        key=side+':'+abb+':'+snum
        sl[key]=[g for _,g in sorted(set(lst))][:4]
    DEPTH[t]={'o':{k:fam_list(x) for k,x in v['o'].items()},
              'd':{k:fam_list(x) for k,x in v['d'].items()},
              'sl':sl,'s':v['s']}
for espn,nfl in {'LAR':'LA','WSH':'WAS'}.items():
    if nfl in DEPTH: DEPTH[espn]=DEPTH[nfl]

NEED=set()
for v in DEPTH.values():
    for side in ('o','d'):
        for lst in v[side].values():
            for e in lst: NEED.add(e['g'])

# ---------------- usage, weekly (snaps join by pfr id -> gsis) ----------------
wk=collections.defaultdict(dict)
for r in csv.DictReader(open('snaps25.csv')):
    if r['game_type']!='REG': continue
    g=PFR2GSIS.get(r['pfr_player_id'].strip())
    if not g or g not in NEED: continue
    try: w=int(r['week'])
    except Exception: continue
    o=float(r['offense_pct'] or 0); d=float(r['defense_pct'] or 0)
    wk[g][w]=round(max(o,d)*100,1)
USAGE={}
for g,weeks in wk.items():
    ks=sorted(weeks)
    vals=[weeks[k] for k in ks]
    last3=[weeks[k] for k in ks[-3:]]
    USAGE[g]={'s':round(statistics.mean(vals),1),
              's3':round(statistics.mean(last3),1),
              'g':len(vals),
              'sp':[int(round(weeks[k])) for k in ks[-8:]]}

# ---------------- production, weekly (player_id IS gsis) ----------------
def f(v,i=False):
    try: return int(round(float(v))) if i else round(float(v),3)
    except Exception: return 0
prod=collections.defaultdict(lambda: collections.defaultdict(dict))
for r in csv.DictReader(open('stw25.csv')):
    if r['season_type']!='REG': continue
    g=r['player_id'].strip()
    if g not in NEED: continue
    try: w=int(r['week'])
    except Exception: continue
    prod[g][w]={'tgt':f(r['targets'],1),'rec':f(r['receptions'],1),'ry':f(r['receiving_yards'],1),
                'rtd':f(r['receiving_tds'],1),'ay':f(r['receiving_air_yards'],1),
                'ts':round(f(r['target_share'])*100,1),
                'att':f(r['attempts'],1),'cmp':f(r['completions'],1),'py':f(r['passing_yards'],1),
                'ptd':f(r['passing_tds'],1),'car':f(r['carries'],1),'ru':f(r['rushing_yards'],1),
                'rutd':f(r['rushing_tds'],1)}
SUMK=['tgt','rec','ry','rtd','ay','att','cmp','py','ptd','car','ru','rutd']
PROD={}
for g,weeks in prod.items():
    ks=sorted(weeks)
    if not ks: continue
    def agg(keys):
        o={}
        for k in SUMK:
            v=sum(weeks[w].get(k,0) for w in keys)
            if v: o[k]=v
        ts=[weeks[w].get('ts',0) for w in keys if weeks[w].get('ts')]
        if ts: o['ts']=round(statistics.mean(ts),1)
        o['g']=len(keys)
        return o
    season=agg(ks); last3=agg(ks[-3:])
    if len(season)<=1: continue
    e={'S':season,'L3':last3}
    tg=[weeks[w].get('tgt',0) for w in ks[-8:]]
    if any(tg): e['tsp']=tg
    PROD[g]=e

# ---------------- coverage (pfr id -> gsis) ----------------
COV={}
for r in csv.DictReader(open('gi/cov.csv')):
    if r['season']!='2025': continue
    g=PFR2GSIS.get(r['pfr_id'].strip())
    if not g or g not in NEED: continue
    COV[g]={'tgt':f(r['tgt'],1),'cmp':f(r['cmp'],1),'cpct':round(f(r['cmp_percent'])*100,1),
            'yds':f(r['yds'],1),'rat':f(r['rat']),'td':f(r['td'],1),'int':f(r['int'],1),
            'prss':f(r['prss'],1),'mt':round(f(r['m_tkl_percent'])*100,1)}

P={g:v for g,v in PLAYERS.items() if g in NEED}
old=json.load(open('gi.json'))

# ESPN reports injuries by display name; resolve them to ids once, here,
# so nothing downstream has to match on a name.
def nrm(n):
    n=n.lower().replace('.','').replace("'",'').replace('-',' ')
    n=re.sub(r'\b(jr|sr|ii|iii|iv|v)\b','',n)
    return ' '.join(n.split())
byname=collections.defaultdict(list)
for g,v in P.items(): byname[nrm(v['n'])].append(g)
games=old['games']; matched=0; unmatched=0
for gm in games:
    im=gm.pop('inj',None) or {}
    out={}
    for nm,st in im.items():
        c=byname.get(nrm(nm),[])
        if len(c)==1: out[c[0]]=st; matched+=1
        else: unmatched+=1
    if out: gm['inj']=out
print(f'injuries resolved to ids: {matched} (unmatched/ambiguous: {unmatched})')

out={'games':games,'players':P,'depth':DEPTH,'usage':USAGE,'prod':PROD,'cov':COV,'dt':latest}
json.dump(out,open('gi2.json','w'),separators=(',',':'))

print(f'players referenced : {len(NEED)}')
print(f'  with profile     : {len(P)} ({len(P)/len(NEED)*100:.0f}%)')
print(f'  with usage       : {len(USAGE)} ({len(USAGE)/len(NEED)*100:.0f}%)   [was 81% by name]')
print(f'  with production  : {len(PROD)} ({len(PROD)/len(NEED)*100:.0f}%)')
print(f'  with coverage    : {len(COV)} ({len(COV)/len(NEED)*100:.0f}%)')
print(f'bytes: {len(open("gi2.json").read()):,}')
