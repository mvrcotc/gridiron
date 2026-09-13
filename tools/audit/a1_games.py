"""Game facts against the raw ESPN snapshot the app was built from, cross-checked with nflverse."""
import os, json
from common import num, rows, DATA, RAW, nfl

def run(A):
    A.section('game facts'); D=A.D
    sb={e['id']:e for e in json.load(open(os.path.join(RAW,'espn','sb2.json')))['events']}
    S={g['id']:json.load(open(os.path.join(RAW,'espn','s_%s.json'%g['id']))) for g in D['games']}
    bad=[]
    for g in D['games']:
        e=sb.get(g['id']); n=g['a']+'@'+g['h']
        if not e: bad.append('%s not on the ESPN scoreboard'%n); continue
        c=e['competitions'][0]; T={x['homeAway']:x for x in c['competitors']}; v=c.get('venue') or {}; ad=v.get('address') or {}
        net=((c.get('broadcasts') or [{}])[0].get('names') or ['TBD'])[0]
        want={'a':T['away']['team']['abbreviation'],'h':T['home']['team']['abbreviation'],
              'an':T['away']['team']['name'],'hn':T['home']['team']['name'],
              'ac':'#'+T['away']['team'].get('color','').lower(),'hc':'#'+T['home']['team'].get('color','').lower(),
              'aa':'#'+T['away']['team'].get('alternateColor','').lower(),'ha':'#'+T['home']['team'].get('alternateColor','').lower(),
              'date':e['date'],'venue':v.get('fullName'),'city':ad.get('city'),'st':ad.get('state'),'net':net,
              'state':c['status']['type']['state'],'neutral':bool(c.get('neutralSite'))}
        for k,w in want.items():
            have=g.get(k)
            if k=='neutral': have=bool(have)
            if isinstance(have,str) and k in ('ac','hc','aa','ha'): have=have.lower()
            if have!=w: bad.append('%s %s: app %r, ESPN %r'%(n,k,have,w))
        if bool(g.get('indoor'))!=bool(v.get('indoor')): bad.append('%s indoor: app %s, ESPN %s'%(n,g.get('indoor'),v.get('indoor')))
        if want['state']=='post':
            sc={'a':int(num(T['away'].get('score'))),'h':int(num(T['home'].get('score')))}
            if g.get('sc')!=sc: bad.append('%s final score: app %s, ESPN %s'%(n,g.get('sc'),sc))
    A.check('G1','Teams, names, colours, kickoff, venue, network, indoor, neutral and final scores match ESPN',bad,len(D['games']))

    bad=[]
    for g in D['games']:
        pc=(S[g['id']].get('pickcenter') or [{}])[0]; n=g['a']+'@'+g['h']
        for k,src in (('det','details'),('spread','spread'),('ou','overUnder')):
            if pc.get(src) is None: continue
            if (g.get(k)!=pc[src]) if k=='det' else abs(num(g.get(k),99)-num(pc[src]))>0.01:
                bad.append('%s %s: app %r, DraftKings %r'%(n,k,g.get(k),pc[src]))
    A.check('G2','Spread, total and line text match the DraftKings pick centre',bad,len(D['games']))

    bad=[]
    for g in D['games']:
        if g.get('state')=='post': continue
        w=S[g['id']].get('gameInfo',{}).get('weather') or {}; n=g['a']+'@'+g['h']
        for k,src in (('temp','temperature'),('gust','gust'),('precip','precipitation'),('cond','conditionId')):
            if w.get(src) is None and g.get(k) is None: continue
            if num(g.get(k),-99)!=num(w.get(src),-98): bad.append('%s %s: app %r, ESPN %r'%(n,k,g.get(k),w.get(src)))
    A.check('G3','Forecast temperature, gust, precipitation and condition match ESPN',bad)

    NV={r['espn'].split('.')[0]:r for r in rows(os.path.join(DATA,'games_all.csv')) if r.get('espn')}
    bad=[]; diff=[]
    for g in D['games']:
        r=NV.get(g['id']); n=g['a']+'@'+g['h']
        if not r: bad.append('%s missing from nflverse schedule'%n); continue
        if (nfl(g['a']),nfl(g['h']))!=(r['away_team'],r['home_team']): bad.append('%s nflverse has %s@%s'%(n,r['away_team'],r['home_team']))
        if r['spread_line'] and g.get('spread') is not None and abs(-num(r['spread_line'])-g['spread'])>0.01:
            diff.append('%s spread: DraftKings %s, nflverse %s'%(n,g['spread'],-num(r['spread_line'])))
        if r['total_line'] and g.get('ou') is not None and abs(num(r['total_line'])-g['ou'])>0.01:
            diff.append('%s total: DraftKings %s, nflverse %s'%(n,g['ou'],r['total_line']))
        V=(D.get('verify') or {}).get(g['id'],{})
        for k,val,oth in (('spread',g.get('spread'),-num(r['spread_line']) if r['spread_line'] else None),
                          ('total',g.get('ou'),num(r['total_line']) if r['total_line'] else None)):
            x=V.get(k)
            if not x or oth is None: continue
            agree=abs(num(val)-oth)<0.01
            if x.get('s')!=('ok' if agree else 'x') or abs(num(x.get('o'))-oth)>0.01:
                bad.append('%s verify badge for %s says %s (other=%s); sources %s vs %s'%(n,k,x.get('s'),x.get('o'),val,oth))
    A.check('G4','Every game is in the nflverse schedule, and the two-source badges report agreement correctly',bad,len(D['games']))
    A.check('G5','Where DraftKings and nflverse disagree on the line (expected: different books and times)',diff,len(D['games']),warn=True)

    bad=[]
    for g in D['games']:
        pr=S[g['id']].get('predictor') or {}
        hp=(pr.get('homeTeam') or {}).get('gameProjection')
        if g.get('wp') is not None and hp is not None and abs(num(g['wp'])-num(hp))>0.05:
            bad.append('%s@%s ESPN win prob app %s, ESPN %s'%(g['a'],g['h'],g['wp'],hp))
        if g.get('state')=='post':
            f=os.path.join(RAW,'espn','f_%s.json'%g['id'])
            at=json.load(open(f)).get('gameInfo',{}).get('attendance') if os.path.exists(f) else None
            if at is not None and int(num(g.get('att')))!=int(at): bad.append('%s@%s attendance app %s, ESPN %s'%(g['a'],g['h'],g.get('att'),at))
    A.check('G6','ESPN win probability and attendance match',bad)
