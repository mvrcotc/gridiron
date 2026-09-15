"""Game facts against the raw ESPN snapshot the app was built from, cross-checked with nflverse."""
import os, json
from collections import defaultdict
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

    bad=[]; odd=[]
    for g in D['games']:
        pc=(S[g['id']].get('pickcenter') or [{}])[0] or {}; n=g['a']+'@'+g['h']
        for k,src in (('det','details'),('spread','spread'),('ou','overUnder')):
            ev=pc.get(src)
            if ev is None or (k=='det' and not (isinstance(ev,str) and ev.strip())): continue
            if k!='det' and num(ev,None) is None: odd.append('%s %s from DraftKings is not a number: %r'%(n,src,ev)); continue
            if (g.get(k)!=ev.strip()) if k=='det' else abs(num(g.get(k),99)-num(ev))>0.01:
                bad.append('%s %s: app %r, DraftKings %r'%(n,k,g.get(k),ev))
    A.check('G2','Spread, total and line text match the DraftKings pick centre',bad,len(D['games']))
    if odd: A.warn('G2b','DraftKings sent a non-numeric line; the last good line was kept',odd,len(odd))

    bad=[]; odd=[]
    for g in D['games']:
        if g.get('state')=='post': continue
        w=S[g['id']].get('gameInfo',{}).get('weather') or {}; n=g['a']+'@'+g['h']
        for k,src in (('temp','temperature'),('gust','gust'),('precip','precipitation')):
            ev=w.get(src); en=num(ev,None) if ev is not None else None
            if ev is None and g.get(k) is None: continue
            if ev is not None and en is None: odd.append('%s %s from ESPN is not a number: %r'%(n,k,ev)); continue
            if num(g.get(k),-99)!=en: bad.append('%s %s: app %r, ESPN %r'%(n,k,g.get(k),ev))
        ev=w.get('conditionId')
        if ev is not None:
            en=num(ev,None)
            if en is None and (g.get('cond') is not None or g.get('condtext')!=str(ev).strip()[:40]): bad.append('%s condition: app %r/%r, ESPN text %r'%(n,g.get('cond'),g.get('condtext'),ev))
            if en is not None and g.get('cond')!=int(en): bad.append('%s condition: app %r, ESPN %r'%(n,g.get('cond'),ev))
    A.check('G3','Forecast temperature, gust, precipitation and condition match ESPN (numbers or text, as sent)',bad)
    if odd: A.warn('G3b','ESPN sent a non-numeric weather value; it was skipped rather than shown',odd,len(odd))

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
        if g.get('state')!='post' and g.get('wp') is not None and num(hp,None) is not None and abs(num(g['wp'])-num(hp))>0.05:
            bad.append('%s@%s ESPN win prob app %s, ESPN %s'%(g['a'],g['h'],g['wp'],hp))
        if g.get('state')=='post':
            f=os.path.join(RAW,'espn','f_%s.json'%g['id'])
            at=json.load(open(f)).get('gameInfo',{}).get('attendance') if os.path.exists(f) else None
            if at is not None and int(num(g.get('att')))!=int(at): bad.append('%s@%s attendance app %s, ESPN %s'%(g['a'],g['h'],g.get('att'),at))
    A.check('G6','ESPN win probability and attendance match',bad)

    # ---- team standings, rebuilt from the raw schedule and ESPN's finals; division games use nflverse's own flag ----
    TD=D.get('teams'); bad=[]
    if not TD:
        A.check('G7','Team standings recompute from the raw schedule',['no team standings in the data']); return
    allg=[r for r in rows(os.path.join(DATA,'games_all.csv')) if r['game_type']=='REG']; fin={}
    for eid,e in sb.items():
        c=e['competitions'][0]
        if c['status']['type']['state']!='post': continue
        T2={x['homeAway']:x for x in c['competitors']}
        try: fin[eid]=(float(T2['away']['score']),float(T2['home']['score']))
        except (KeyError,TypeError,ValueError): pass
    AFC=set('BUF MIA NE NYJ BAL CIN CLE PIT HOU IND JAX TEN DEN KC LAC LV'.split())
    for season in TD['seasons']:
        B=TD['by'][str(season)]; games=[]
        for r in allg:
            if int(r['season'])!=season: continue
            e=str(r.get('espn') or '').split('.')[0]
            if r['home_score']: games.append((r,num(r['away_score']),num(r['home_score'])))
            elif e in fin: games.append((r,fin[e][0],fin[e][1]))
        games.sort(key=lambda x:(int(x[0]['week']),x[0]['gameday'] or '',x[0]['game_id']))
        BX={}; twp=os.path.join(DATA,'tw%d.csv'%season)
        if os.path.exists(twp):
            for r in rows(twp):
                if r['season_type']=='REG':
                    BX[(r['game_id'],r['team'])]=(num(r['passing_yards'])+num(r['rushing_yards']),
                        num(r['passing_interceptions'])+num(r['rushing_fumbles_lost'])+num(r['receiving_fumbles_lost'])+num(r['sack_fumbles_lost']))
        S=defaultdict(lambda:dict(w=0,l=0,t=0,pf=0.0,pa=0.0,div=[0,0,0],conf=[0,0,0],home=[0,0,0],away=[0,0,0],ats=[0,0,0],ou=[0,0,0],seq='',y=[0.0,0.0,0.0,0.0,0]))
        for r,as_,hs_ in games:
            for team,opp,pf,pa,home in ((r['home_team'],r['away_team'],hs_,as_,True),(r['away_team'],r['home_team'],as_,hs_,False)):
                x=S[team]; k=0 if pf>pa else (1 if pf<pa else 2)
                x['wlt'[k]]+=1; x['pf']+=pf; x['pa']+=pa; x['seq']+='WLT'[k]
                if r['location']=='Home': x['home' if home else 'away'][k]+=1
                if str(r.get('div_game'))=='1': x['div'][k]+=1
                if (team in AFC)==(opp in AFC): x['conf'][k]+=1
                if r['spread_line']:
                    m=(hs_-as_)-num(r['spread_line']); m=m if home else -m; x['ats'][0 if m>0 else (1 if m<0 else 2)]+=1
                if r['total_line']:
                    o=hs_+as_-num(r['total_line']); x['ou'][0 if o>0 else (1 if o<0 else 2)]+=1
                if (r['game_id'],team) in BX and (r['game_id'],opp) in BX:
                    y=x['y']; y[0]+=BX[(r['game_id'],team)][0]; y[1]+=BX[(r['game_id'],opp)][0]; y[2]+=BX[(r['game_id'],team)][1]; y[3]+=BX[(r['game_id'],opp)][1]; y[4]+=1
        if len(B['rows'])!=32: bad.append('%d standings have %d teams'%(season,len(B['rows'])))
        if B['final_games']!=len(games): bad.append('%d standings count %d final games, the schedule and ESPN give %d'%(season,B['final_games'],len(games)))
        for code,z in B['rows'].items():
            x=S[code]; seq=x['seq']; y=x['y']
            streak='%s%d'%(seq[-1],len(seq)-len(seq.rstrip(seq[-1]))) if seq else ''
            want=dict(w=x['w'],l=x['l'],t=x['t'],pf=int(x['pf']),pa=int(x['pa']),diff=int(x['pf']-x['pa']),div=x['div'],conf=x['conf'],home=x['home'],
                      away=x['away'],ats=x['ats'],ou=x['ou'],streak=streak,last5=seq[-5:],ypg=round(y[0]/y[4],1) if y[4] else None,
                      ypga=round(y[1]/y[4],1) if y[4] else None,to=int(y[3]-y[2]) if y[4] else None)
            for k,v in want.items():
                if z.get(k)!=v: bad.append('%d %s %s: data %r, schedule gives %r'%(season,z['ab'],k,z.get(k),v))
    A.check('G7','Team standings (records, splits, points, ATS, O/U, streaks, yards, turnovers) recompute from the raw schedule and ESPN finals, with division games from nflverse\'s own flag',bad,32*len(TD['seasons']))

