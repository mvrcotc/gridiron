import csv, json, collections, sys, io

def gj(p): return json.load(open(p))
sb=gj('gi/sb.json')
games=[]
for e in sb['events']:
    c=e['competitions'][0]
    a=next(t for t in c['competitors'] if t['homeAway']=='away')
    h=next(t for t in c['competitors'] if t['homeAway']=='home')
    b=(c.get('broadcasts') or [])
    net=(b[0].get('names') or ['TBD'])[0] if b else 'TBD'
    v=c.get('venue',{}); ad=v.get('address') or {}
    g={'id':e['id'],'a':a['team']['abbreviation'],'h':h['team']['abbreviation'],
       'an':a['team']['shortDisplayName'],'hn':h['team']['shortDisplayName'],
       'ac':'#'+a['team'].get('color','666666'),'hc':'#'+h['team'].get('color','666666'),
       'aa':'#'+a['team'].get('alternateColor','ffffff'),'ha':'#'+h['team'].get('alternateColor','ffffff'),
       'date':e['date'],'net':net,'venue':v.get('fullName',''),
       'city':ad.get('city',''),'st':ad.get('state',''),'indoor':bool(v.get('indoor')),
       'state':c['status']['type']['state']}
    try:
        s=gj(f"gi/s_{e['id']}.json")
        w=((s.get('gameInfo') or {}).get('weather')) or {}
        if w.get('temperature') is not None: g['temp']=w['temperature']
        if w.get('gust') is not None: g['gust']=w['gust']
        if w.get('precipitation') is not None: g['precip']=w['precipitation']
        pc=(s.get('pickcenter') or [])
        if pc:
            p=pc[0]
            if p.get('spread') is not None: g['spread']=p['spread']
            if p.get('overUnder') is not None: g['ou']=p['overUnder']
            if p.get('details'): g['det']=p['details']
        pr=s.get('predictor') or {}
        if pr.get('homeTeam'): g['wp']=float(pr['homeTeam'].get('gameProjection') or 0)
        inj=s.get('injuries') or []
        im={}
        for blk in inj:
            ab=blk.get('team',{}).get('abbreviation')
            for it in (blk.get('injuries') or []):
                nm=(it.get('athlete') or {}).get('displayName')
                stt=it.get('status')
                if nm and stt: im[nm]=stt[0].upper() if stt[0].upper() in 'OQD' else stt[:1].upper()
        if im: g['inj']=im
    except Exception as ex: print('warn',e['id'],ex,file=sys.stderr)
    games.append(g)

rows=list(csv.DictReader(open('dc.csv')))
latest=max(r['dt'] for r in rows)
rows=[r for r in rows if r['dt']==latest]
depth={}
for r in rows:
    if r['pos_rank']!='1': continue
    d=depth.setdefault(r['team'],{'off':{},'def':{},'scheme':None})
    if r['pos_grp']=='3WR 1TE':
        d['off'].setdefault(r['pos_abb'],set()).add((int(r['pos_slot']),r['player_name']))
    elif r['pos_grp'] in ('Base 3-4 D','Base 4-3 D'):
        d['scheme']='3-4' if '3-4' in r['pos_grp'] else '4-3'
        d['def'].setdefault(r['pos_abb'],set()).add((int(r['pos_slot']),r['player_name']))
def flat(gr):
    out={}
    for abb,st in gr.items():
        lst=sorted(st)
        if abb=='WR':
            for i,(s,n) in enumerate(lst[:3]): out['WR%d'%(i+1)]=n
        else: out[abb]=lst[0][1]
    return out
DEPTH={}
for t,d in depth.items():
    o,df=flat(d['off']),flat(d['def'])
    if len(o)>=9 and len(df)>=10: DEPTH[t]={'o':o,'d':df,'s':d['scheme']}

need=set()
for d in DEPTH.values(): need|=set(d['o'].values())|set(d['d'].values())
def f(v,i=False):
    try: return int(round(float(v))) if i else round(float(v),3)
    except: return 0
STATS={}
for r in csv.DictReader(open('st25.csv')):
    n=r['player_display_name']
    if n not in need: continue
    s={'g':f(r['games'],1)}
    if f(r['attempts'],1): s.update(att=f(r['attempts'],1),cmp=f(r['completions'],1),py=f(r['passing_yards'],1),ptd=f(r['passing_tds'],1))
    if f(r['targets'],1): s.update(tgt=f(r['targets'],1),rec=f(r['receptions'],1),ry=f(r['receiving_yards'],1),rtd=f(r['receiving_tds'],1),ay=f(r['receiving_air_yards'],1),ts=round(f(r['target_share'])*100,1))
    if f(r['carries'],1): s.update(car=f(r['carries'],1),ru=f(r['rushing_yards'],1),rutd=f(r['rushing_tds'],1))
    if len(s)>1: STATS[n]=s
COV={}
for r in csv.DictReader(open('gi/cov.csv')):
    if r['season']!='2025': continue
    n=r['player']
    if n not in need: continue
    COV[n]={'tgt':f(r['tgt'],1),'cmp':f(r['cmp'],1),'cpct':round(f(r['cmp_percent'])*100,1),
            'yds':f(r['yds'],1),'rat':f(r['rat']),'td':f(r['td'],1),'int':f(r['int'],1),
            'prss':f(r['prss'],1),'mt':round(f(r['m_tkl_percent'])*100,1)}
out={'games':games,'depth':DEPTH,'stats':STATS,'cov':COV,'dt':latest}
open('gi.json','w').write(json.dumps(out,separators=(',',':')))
print('games',len(games),'teams',len(DEPTH),'stats',len(STATS),'cov',len(COV),'bytes',len(open('gi.json').read()))
print('CIN off:',json.dumps(DEPTH.get('CIN',{}).get('o')))
print('TB def :',json.dumps(DEPTH.get('TB',{}).get('d')),DEPTH.get('TB',{}).get('s'))
print('Chase  :',json.dumps(STATS.get("Ja'Marr Chase")))
print('McColl :',json.dumps(COV.get('Zyon McCollum')))
print('game0  :',json.dumps({k:v for k,v in games[2].items() if k!='inj'}))
