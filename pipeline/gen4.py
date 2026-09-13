import csv, json, collections, glob, re

D=json.load(open('gi2.json'))
PLAYERS=D['players']

# ---------- final scores + status ----------
sb=json.load(open('gi/sb2.json'))
live={}
for e in sb['events']:
    c=e['competitions'][0]; st=c['status']['type']
    a=next(t for t in c['competitors'] if t['homeAway']=='away')
    h=next(t for t in c['competitors'] if t['homeAway']=='home')
    live[e['id']]={'state':st['state'],'desc':st['description'],
                   'a':int(a.get('score') or 0),'h':int(h.get('score') or 0)}
finals=0
for g in D['games']:
    L=live.get(g['id'])
    if not L: continue
    g['state']=L['state']; g['sdesc']=L['desc']
    if L['state']=='post':
        g['sc']={'a':L['a'],'h':L['h']}; finals+=1

# ---------- Week 1 2026 actuals (player_id IS gsis) ----------
def f(v,i=False):
    try: return int(round(float(v))) if i else round(float(v),3)
    except Exception: return 0
RES={}
for r in csv.DictReader(open('stw26.csv')):
    if r['season_type']!='REG' or r['week']!='1': continue
    g=r['player_id'].strip()
    if g not in PLAYERS: continue
    e={}
    for k,src in [('tgt','targets'),('rec','receptions'),('ry','receiving_yards'),('rtd','receiving_tds'),
                  ('car','carries'),('ru','rushing_yards'),('rutd','rushing_tds'),
                  ('att','attempts'),('cmp','completions'),('py','passing_yards'),('ptd','passing_tds'),
                  ('int','passing_interceptions'),('fum','rushing_fumbles_lost')]:
        v=f(r.get(src,0),1)
        if v: e[k]=v
    if e: RES[g]=e

# actual snap share, if the 2026 file has week 1
try:
    for r in csv.DictReader(open('snaps26.csv')):
        if r['game_type']!='REG' or r['week']!='1': continue
        # snaps key on pfr id; reuse the crosswalk built from the players file
        pass
except Exception: pass

# ---------- PPR: one comparable number ----------
def ppr(s):
    if not s: return None
    return round(s.get('rec',0)*1.0 + s.get('ry',0)*0.1 + s.get('rtd',0)*6
                 + s.get('ru',0)*0.1 + s.get('rutd',0)*6
                 + s.get('py',0)*0.04 + s.get('ptd',0)*4
                 - s.get('int',0)*2 - s.get('fum',0)*2, 1)
for g,e in RES.items():
    e['pts']=ppr(e)
    base=D['prod'].get(g)
    if base and base.get('S'):
        S=base['S']; gp=max(1,S.get('g',1))
        per={k:(S.get(k,0)/gp) for k in ('rec','ry','rtd','ru','rutd','py','ptd')}
        exp=round(per['rec']*1.0+per['ry']*0.1+per['rtd']*6+per['ru']*0.1+per['rutd']*6
                  +per['py']*0.04+per['ptd']*4,1)
        e['exp']=exp
        if exp>=3:
            ratio=e['pts']/exp
            e['v']='beat' if ratio>=1.25 else ('miss' if ratio<=0.75 else 'met')
            e['r']=round(ratio,2)

# ---------- injuries with body part + expected return ----------
INJ={}
def nrm(n):
    n=n.lower().replace('.','').replace("'",'').replace('-',' ')
    n=re.sub(r'\b(jr|sr|ii|iii|iv|v)\b','',n)
    return ' '.join(n.split())
byname=collections.defaultdict(list)
for gid,v in PLAYERS.items(): byname[nrm(v['n'])].append(gid)

matched=0
for path in glob.glob('gi/s_*.json')+glob.glob('gi/f_*.json'):
    try: s=json.load(open(path))
    except Exception: continue
    for blk in (s.get('injuries') or []):
        for it in (blk.get('injuries') or []):
            nm=(it.get('athlete') or {}).get('displayName')
            if not nm: continue
            c=byname.get(nrm(nm),[])
            if len(c)!=1: continue
            det=it.get('details') or {}
            abb=((it.get('type') or {}).get('abbreviation') or (it.get('status') or '?')[:1]).upper()
            rec={'s':abb}
            if it.get('status'): rec['sl']=it['status']
            if det.get('type') and det['type']!='Not Specified': rec['bp']=det['type']
            if det.get('location') and det['location']!='Not Specified': rec['loc']=det['location']
            if det.get('side') and det['side']!='Not Specified': rec['side']=det['side']
            if det.get('returnDate'): rec['ret']=det['returnDate']
            INJ[c[0]]=rec; matched+=1

D['res']=RES
D['injd']=INJ
for g in D['games']:
    g.pop('inj',None)
json.dump(D,open('gi2.json','w'),separators=(',',':'))

beat=sum(1 for e in RES.values() if e.get('v')=='beat')
miss=sum(1 for e in RES.values() if e.get('v')=='miss')
met=sum(1 for e in RES.values() if e.get('v')=='met')
print(f'final scores attached : {finals}')
print(f'week-1 stat lines     : {len(RES)}  (beat {beat} / met {met} / missed {miss})')
print(f'injuries with detail  : {len(INJ)}  ({sum(1 for v in INJ.values() if v.get("ret"))} with an expected return date)')
print(f'bytes                 : {len(open("gi2.json").read()):,}')
top=sorted([(e.get("pts",0),g) for g,e in RES.items()],reverse=True)[:6]
print('\ntop week-1 performers:')
for pts,g in top:
    e=RES[g]
    print(f'  {PLAYERS[g]["n"]:<22} {pts:>5} pts   expected {e.get("exp","-"):>5}   {e.get("v","n/a")}')
