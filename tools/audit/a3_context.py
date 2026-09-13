"""Context factors: home-field edge, referee, pace, pass rate, new-QB flag, divisional, neutral site.
Definitions were matched against stored values first; checks rebuild them from raw nflverse files."""
import os, json, statistics
from collections import defaultdict, Counter
from common import num, rows, DATA, RAW, nfl

REL={'STL':'LA','SD':'LAC','OAK':'LV'}
DIV={t:d for d,ts in {'AE':'BUF MIA NE NYJ','AN':'BAL CIN CLE PIT','AS':'HOU IND JAX TEN','AW':'DEN KC LV LAC',
     'NE':'DAL NYG PHI WAS','NN':'CHI DET GB MIN','NS':'ATL CAR NO TB','NW':'ARI LA SF SEA'}.items() for t in ts.split()}

def run(A):
    A.section('context factors'); D=A.D; GA=list(rows(os.path.join(DATA,'games_all.csv')))

    # home-field edge: 2015-2025 regular season, true home games, relocated franchises mapped
    H=defaultdict(list); R=defaultdict(list); ah=[]; ar=[]
    for r in GA:
        if r['home_score']=='' or r['game_type']!='REG' or not 2015<=int(r['season'])<=2025 or r['location']!='Home': continue
        h=REL.get(r['home_team'],r['home_team']); a=REL.get(r['away_team'],r['away_team']); m=num(r['home_score'])-num(r['away_score'])
        H[h].append(m); R[a].append(-m); ah.append(m); ar.append(-m)
    lg=statistics.mean(ah)-statistics.mean(ar); bad=[]
    for g in D['games']:
        f=g.get('hfa')
        if not f: bad.append('%s@%s has no home-field record'%(g['a'],g['h'])); continue
        t=nfl(g['h']); e=statistics.mean(H[t])-statistics.mean(R[t])
        if abs(f['e']-e)>0.015 or f['n']!=len(H[t]) or abs(f['lg']-lg)>0.02 or abs(f['d']-(f['e']-f['lg']))>0.015:
            bad.append('%s stored e=%s n=%s lg=%s d=%s, recompute e=%.2f n=%d lg=%.2f'%(g['h'],f['e'],f['n'],f['lg'],f['d'],e,len(H[t]),lg))
    A.check('C1','Venue home-field edge recomputes from 2015-25 results (relocations mapped)',bad,len(D['games']))

    # referee
    old={r['old_game_id']:r for r in GA if r['home_score']}
    crew=defaultdict(list)
    for r in rows(os.path.join(DATA,'officials.csv')):
        if r['season']=='2025' and r['position'].strip()=='Referee' and r['game_id'] in old:
            g=old[r['game_id']]; crew[r['official_name'].strip()].append((g['game_type'],num(g['home_score'])+num(g['away_score'])))
    lgt=statistics.mean(num(r['home_score'])+num(r['away_score']) for r in GA if r['season']=='2025' and r['game_type']=='REG' and r['home_score'])
    bad=[]; mixed=False
    for g in D['games']:
        f=g.get('ref') or {}; c=crew.get(f.get('n'))
        if not f.get('n'): continue
        if not c: bad.append('%s has no 2025 games in officials.csv'%f['n']); continue
        allt=[t for ty,t in c if ty=='REG']
        if abs(f['avg']-statistics.mean(allt))>0.06 or f['gp']!=len(allt) or abs(f['lg']-lgt)>0.06:
            bad.append('%s stored %.1f over %d (lg %.1f), recompute %.2f over %d (lg %.2f)'%(f['n'],f['avg'],f['gp'],f['lg'],statistics.mean(allt),len(allt),lgt))
        if any(ty!='REG' for ty,_ in c): mixed=True
    A.check('C2','Referee crew averages (regular season, like-for-like with the league average) recompute from officials.csv',bad,len(D['games']))

    # pace and pass rate: (attempts + carries) per game, attempts / (attempts + carries), 2025 regular season
    T=defaultdict(lambda:defaultdict(float))
    for r in rows(os.path.join(DATA,'tw2025.csv')):
        if r['season_type']!='REG': continue
        t=T[r['team']]; t['g']+=1; t['a']+=num(r['attempts']); t['c']+=num(r['carries'])
    bad=[]
    for g in D['games']:
        for s in ('a','h'):
            t=T.get(nfl(g[s]))
            pace,pr=g.get(s+'_pace'),g.get(s+'_pr')
            if pace is None or pr is None:
                bad.append('%s pace/pass rate missing (ESPN code %s vs nflverse %s)'%(g[s],g[s],nfl(g[s]))); continue
            if abs(pace-(t['a']+t['c'])/t['g'])>0.06 or abs(pr-100*t['a']/(t['a']+t['c']))>0.06:
                bad.append('%s stored %.1f plays %.1f%%, recompute %.1f / %.1f%%'%(g[s],pace,pr,(t['a']+t['c'])/t['g'],100*t['a']/(t['a']+t['c'])))
    La=sum(t['a'] for t in T.values()); Lc=sum(t['c'] for t in T.values()); Lg=sum(t['g'] for t in T.values())
    if abs(D['lg']['plays']-(La+Lc)/Lg)>0.06 or abs(D['lg']['pr']-100*La/(La+Lc))>0.06: bad.append('league baselines %s'%D['lg'])
    if abs(D['lg']['total']-lgt)>0.06: bad.append('league total %s, recompute %.2f'%(D['lg']['total'],lgt))
    A.check('C3','Pace and pass tendency present for both teams in every game, and recompute',bad,32)

    # 2025 primary passer and the new-QB flag
    att=defaultdict(Counter)
    for r in rows(os.path.join(DATA,'stw25.csv')):
        if r['season_type']=='REG' and r['position']=='QB': att[r['team']][r['player_id']]+=num(r['attempts'])
    bad=[]
    for g in D['games']:
        for s in ('a','h'):
            tm=nfl(g[s]); prim=att[tm].most_common(1)[0][0]
            dep=(D['depth'].get(g[s]) or D['depth'].get(tm) or {}).get('o',{}).get('QB',[])
            want=int(bool(dep and dep[0]['g']!=prim))
            if int(g.get(s+'_qbnew',0))!=want:
                bad.append('%s new-QB flag %s, should be %d (2025 primary %s, week-1 QB1 %s)'%(g[s],g.get(s+'_qbnew',0),want,
                           D['players'].get(prim,{}).get('n',prim),D['players'].get(dep[0]['g'],{}).get('n') if dep else None))
    A.check('C4','"New quarterback" flag is set exactly where the week-1 QB1 differs from 2025\'s primary passer',bad,32)

    bad=['%s@%s divisional=%s, should be %s'%(g['a'],g['h'],g.get('div'),int(DIV[nfl(g['a'])]==DIV[nfl(g['h'])]))
         for g in D['games'] if int(bool(g.get('div')))!=int(DIV[nfl(g['a'])]==DIV[nfl(g['h'])])]
    A.check('C5','Divisional flag matches the NFL division table',bad,len(D['games']))

    sb=json.load(open(os.path.join(RAW,'espn','sb2.json')))
    neu={e['id']:bool(e['competitions'][0].get('neutralSite')) for e in sb['events']}
    bad=['%s@%s neutral=%s, ESPN %s'%(g['a'],g['h'],bool(g.get('neutral')),neu.get(g['id'])) for g in D['games'] if bool(g.get('neutral'))!=neu.get(g['id'])]
    A.check('C6','Neutral-site flag matches ESPN',bad,len(D['games']))
