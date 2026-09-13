"""The game list, from ESPN's scoreboard. When the scoreboard shows a new week the list is replaced and every
later stage recomputes its per-game data; for the same games, fields computed by later stages are kept."""
import os, sys, json, csv
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
RAW=os.path.join(DATA,'raw','espn'); E2N={'LAR':'LA','WSH':'WAS'}; nf=lambda t:E2N.get(t,t)
DIV={t:d for d,ts in {'AE':'BUF MIA NE NYJ','AN':'BAL CIN CLE PIT','AS':'HOU IND JAX TEN','AW':'DEN KC LV LAC',
     'NE':'DAL NYG PHI WAS','NN':'CHI DET GB MIN','NS':'ATL CAR NO TB','NW':'ARI LA SF SEA'}.items() for t in ts.split()}
D=json.load(open(os.path.join(DATA,'gi2.json'),encoding='utf-8'))
sb=json.load(open(os.path.join(RAW,'sb2.json'),encoding='utf-8')); ev=sb.get('events') or []
if not ev: sys.exit('ESPN scoreboard has no games')
NV={r['espn'].split('.')[0]:r for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'),encoding='utf-8')) if r.get('espn')}
old={g['id']:g for g in D['games']}; rollover=set(e['id'] for e in ev)!=set(old)
games=[]; notes=[]
for e in ev:
    c=e['competitions'][0]; T={x['homeAway']:x for x in c['competitors']}; v=c.get('venue') or {}; ad=v.get('address') or {}
    at,ht=T['away']['team'],T['home']['team']; st=c['status']['type']
    base={'id':e['id'],'a':at['abbreviation'],'h':ht['abbreviation'],'an':at.get('name') or at.get('shortDisplayName'),'hn':ht.get('name') or ht.get('shortDisplayName'),
          'ac':'#'+(at.get('color') or '666666').lower(),'hc':'#'+(ht.get('color') or '666666').lower(),
          'aa':'#'+(at.get('alternateColor') or 'ffffff').lower(),'ha':'#'+(ht.get('alternateColor') or 'ffffff').lower(),
          'date':e['date'],'net':((c.get('broadcasts') or [{}])[0].get('names') or ['TBD'])[0],'venue':v.get('fullName',''),
          'city':ad.get('city',''),'st':ad.get('state',''),'indoor':bool(v.get('indoor')),'neutral':bool(c.get('neutralSite')),
          'state':st['state'],'sdesc':st.get('description'),'div':int(DIV.get(nf(at['abbreviation']),1)==DIV.get(nf(ht['abbreviation']),2))}
    nv=NV.get(e['id'])
    if nv:
        # roof from the schedule, but ESPN's indoor flag wins where they disagree (nflverse once had the MCG as a dome)
        r=(nv.get('roof') or '').lower()
        base['roof']=(r if r in ('dome','closed') else 'dome') if base['indoor'] else (r if r in ('outdoors','open') else 'outdoors')
        if nv.get('surface'): base['surf']=nv['surface']
    else: notes.append('%s@%s not in the nflverse schedule yet'%(base['a'],base['h']))
    sp=os.path.join(RAW,'s_%s.json'%e['id'])
    if os.path.exists(sp):
        gv=(json.load(open(sp,encoding='utf-8')).get('gameInfo') or {}).get('venue') or {}
        if 'grass' in gv: base['grass']=bool(gv['grass'])
    g=dict(old.get(e['id']) or {}); g.update(base); games.append(g)
if rollover:
    keep={g['id'] for g in games}
    D['verify']={k:v for k,v in (D.get('verify') or {}).items() if k in keep}
    for k in ('pred','wx'): D[k]={}
D['games']=games
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('slate: %d games (%s)%s'%(len(games),'NEW WEEK -- per-game data will be rebuilt' if rollover else 'same games, base fields refreshed',
      ''.join('; '+n for n in notes)))
