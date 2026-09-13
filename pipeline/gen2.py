import csv, json, collections, statistics

old=json.load(open('gi.json'))

# ---------- snap share, aggregated per player ----------
snap=collections.defaultdict(lambda:{'o':[], 'd':[], 'g':0, 'pos':''})
for r in csv.DictReader(open('snaps25.csv')):
    if r['game_type']!='REG': continue
    s=snap[r['player']]
    s['g']+=1
    if r['position']: s['pos']=r['position']
    try: s['o'].append(float(r['offense_pct'] or 0))
    except: pass
    try: s['d'].append(float(r['defense_pct'] or 0))
    except: pass
SNAP={}
for n,s in snap.items():
    o=round(statistics.mean(s['o'])*100,1) if s['o'] else 0
    d=round(statistics.mean(s['d'])*100,1) if s['d'] else 0
    SNAP[n]={'o':o,'d':d,'g':s['g'],'pos':s.get('pos','')}

# Names differ in format between sources ("Yaya"/"YaYa", "Jr."/"", "A.J."/"AJ").
# Normalise for a fallback match, but only accept it when the normalised key is
# unambiguous AND the position family agrees -- "Byron Murphy II" (tackle) and
# "Byron Murphy Jr." (corner) collide otherwise.
import re as _re
def _norm(n):
    n=n.lower().replace('.','').replace("'",'').replace('-',' ')
    n=_re.sub(r'\b(jr|sr|ii|iii|iv|v)\b','',n)
    return ' '.join(n.split())
POSFAM={'T':'OL','OT':'OL','G':'OL','OG':'OL','C':'OL','QB':'QB','RB':'RB','FB':'RB',
        'WR':'WR','TE':'TE','DE':'DL','DT':'DL','NT':'DL','DL':'DL','EDGE':'DL',
        'LB':'LB','OLB':'LB','ILB':'LB','MLB':'LB','CB':'CB','DB':'CB',
        'S':'S','FS':'S','SS':'S'}
_byNorm={}
for n in SNAP: _byNorm.setdefault(_norm(n),[]).append(n)
def lookup(name, fam):
    if name in SNAP: return SNAP[name]
    cands=_byNorm.get(_norm(name),[])
    if len(cands)==1:
        c=SNAP[cands[0]]
        if not fam or POSFAM.get(c.get('pos','').upper())in(None,fam): return c
        return None
    for c in cands:
        if POSFAM.get(SNAP[c].get('pos','').upper())==fam: return SNAP[c]
    return None

# ---------- depth chart, full position families ----------
FAM_O={'QB':'QB','RB':'RB','WR':'WR','TE':'TE','LT':'OL','LG':'OL','C':'OL','RG':'OL','RT':'OL'}
FAM_D={'LDE':'DL','RDE':'DL','NT':'DL','LDT':'DL','RDT':'DL',
       'WLB':'LB','MLB':'LB','SLB':'LB','LILB':'LB','RILB':'LB',
       'LCB':'CB','RCB':'CB','NB':'CB','FS':'S','SS':'S'}
# Order within a family decides who is "on the field" in base personnel.
# Linebackers differ by scheme: in a 3-4 both outside backers are starting
# edge rushers and one INSIDE backer comes off in nickel; in a 4-3 the SAM
# is the one who leaves.
SLOT_ORD={'LT':0,'LG':1,'C':2,'RG':3,'RT':4,
          'LDE':0,'NT':1,'LDT':1,'RDT':2,'RDE':3,
          'LCB':0,'NB':1,'RCB':2,'FS':0,'SS':1}
LB_ORD={'3-4':{'WLB':0,'SLB':1,'LILB':2,'RILB':3,'MLB':2},
        '4-3':{'WLB':0,'MLB':1,'SLB':2,'LILB':1,'RILB':2}}

rows=list(csv.DictReader(open('dc.csv')))
latest=max(r['dt'] for r in rows)
rows=[r for r in rows if r['dt']==latest]

raw=collections.defaultdict(lambda:{'o':collections.defaultdict(list),
                                    'd':collections.defaultdict(list),'s':None})
for r in rows:
    g=r['pos_grp']
    if g=='3WR 1TE': side,FAM='o',FAM_O
    elif g in ('Base 3-4 D','Base 4-3 D'):
        side,FAM='d',FAM_D
        raw[r['team']]['s']='3-4' if '3-4' in g else '4-3'
    else: continue
    fam=FAM.get(r['pos_abb'])
    if not fam or not r['player_name'].strip(): continue
    sch=raw[r['team']]['s']
    so=(LB_ORD.get(sch,LB_ORD['4-3']).get(r['pos_abb'],9) if fam=='LB'
        else SLOT_ORD.get(r['pos_abb'],9))
    raw[r['team']][side][fam].append({
        'n':r['player_name'].strip(),'abb':r['pos_abb'],'gsis':r.get('gsis_id','').strip(),
        'r':int(r['pos_rank']),'so':so})

def build(fams, side):
    out={}
    for fam,lst in fams.items():
        seen=set(); ordered=[]
        for p in sorted(lst, key=lambda p:(p['r'], p['so'])):
            if p['n'] in seen: continue
            seen.add(p['n'])
            sn=lookup(p['n'], fam)
            e={'n':p['n'],'p':p['abb']}
            jn=JERSEY.get(p.get('gsis','')) or JERSEY_N.get(_norm(p['n']))
            if jn: e['j']=jn
            if sn:
                pct = sn['o'] if side=='o' else sn['d']
                if pct>0: e['s']=pct
                if sn['g']: e['g']=sn['g']
            ordered.append(e)
        out[fam]=ordered[:5]
    return out

JERSEY={}; JERSEY_N={}
for r in csv.DictReader(open('rost26.csv')):
    j=(r.get('jersey_number') or '').strip()
    if not j: continue
    try: j=str(int(float(j)))
    except Exception: continue
    if r.get('gsis_id'): JERSEY[r['gsis_id'].strip()]=j
    JERSEY_N.setdefault(_norm(r.get('full_name','')), j)

DEPTH={}
for t,v in raw.items():
    if not v['o'] or not v['d']: continue
    DEPTH[t]={'o':build(v['o'],'o'),'d':build(v['d'],'d'),'s':v['s']}
for espn,nfl in {'LAR':'LA','WSH':'WAS'}.items():
    if nfl in DEPTH: DEPTH[espn]=DEPTH[nfl]

# ---------- keep stats/cov only for players we now reference ----------
need=set()
for d in DEPTH.values():
    for side in ('o','d'):
        for lst in d[side].values():
            for e in lst: need.add(e['n'])
STATS={k:v for k,v in old['stats'].items() if k in need}
COV={k:v for k,v in old['cov'].items() if k in need}

# top up stats for newly-included backups
def f(v,i=False):
    try: return int(round(float(v))) if i else round(float(v),3)
    except: return 0
for r in csv.DictReader(open('st25.csv')):
    n=r['player_display_name']
    if n not in need or n in STATS: continue
    s={'g':f(r['games'],1)}
    if f(r['attempts'],1): s.update(att=f(r['attempts'],1),cmp=f(r['completions'],1),py=f(r['passing_yards'],1),ptd=f(r['passing_tds'],1))
    if f(r['targets'],1): s.update(tgt=f(r['targets'],1),rec=f(r['receptions'],1),ry=f(r['receiving_yards'],1),rtd=f(r['receiving_tds'],1),ay=f(r['receiving_air_yards'],1),ts=round(f(r['target_share'])*100,1))
    if f(r['carries'],1): s.update(car=f(r['carries'],1),ru=f(r['rushing_yards'],1),rutd=f(r['rushing_tds'],1))
    if len(s)>1: STATS[n]=s
for r in csv.DictReader(open('gi/cov.csv')):
    if r['season']!='2025': continue
    n=r['player']
    if n not in need or n in COV: continue
    COV[n]={'tgt':f(r['tgt'],1),'cmp':f(r['cmp'],1),'cpct':round(f(r['cmp_percent'])*100,1),
            'yds':f(r['yds'],1),'rat':f(r['rat']),'td':f(r['td'],1),'int':f(r['int'],1),
            'prss':f(r['prss'],1),'mt':round(f(r['m_tkl_percent'])*100,1)}

out={'games':old['games'],'depth':DEPTH,'stats':STATS,'cov':COV,'dt':latest}
json.dump(out,open('gi.json','w'),separators=(',',':'))

matched=sum(1 for n in need if n in SNAP)
print('teams',len(DEPTH),'| players referenced',len(need),'| snap matched',matched,
      f'({matched/len(need)*100:.0f}%)','| stats',len(STATS),'| cov',len(COV))
print('bytes',len(open('gi.json').read()))
print()
print('CIN WR:',json.dumps(DEPTH['CIN']['o']['WR'],indent=None))
print('CIN RB:',json.dumps(DEPTH['CIN']['o']['RB']))
print('CIN QB:',json.dumps(DEPTH['CIN']['o']['QB']))
print('TB  CB:',json.dumps(DEPTH['TB']['d']['CB']))
