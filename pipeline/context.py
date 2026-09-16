"""Game context from raw files, safe for ESPN vs nflverse team codes (LAR/LA, WSH/WAS):
pace, pass rate, prior-season primary passer, new-QB flag, venue home edge, referee crew, two-source badges."""
import os, sys, json, csv, statistics
from collections import defaultdict, Counter
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
E2N={'LAR':'LA','WSH':'WAS'}; nf=lambda t:E2N.get(t,t); REL={'STL':'LA','SD':'LAC','OAK':'LV'}
def num(v):
    try: return float(v)
    except (TypeError,ValueError): return None
rows=lambda f:csv.DictReader(open(os.path.join(DATA,f),newline='',encoding='utf-8'))
D=json.load(open(os.path.join(DATA,'gi2.json'))); GA=list(rows('games_all.csv'))
sw=Counter((int(r['season']),int(r['week'])) for r in GA if r.get('espn') and r['espn'].split('.')[0] in {g['id'] for g in D['games']})
SEASON,WEEK=sw.most_common(1)[0][0]; PREV=SEASON-1
print('slate %d week %d; tendencies from %d'%(SEASON,WEEK,PREV))

T=defaultdict(lambda:defaultdict(float))
for r in rows('tw%d.csv'%PREV):
    if r['season_type']=='REG':
        t=T[r['team']]; t['g']+=1; t['a']+=num(r['attempts']) or 0; t['c']+=num(r['carries']) or 0
tot_prev=[num(r['home_score'])+num(r['away_score']) for r in GA if int(r['season'])==PREV and r['game_type']=='REG' and r['home_score']]
La,Lc,Lg=(sum(t[k] for t in T.values()) for k in ('a','c','g'))
D['lg']={'plays':round((La+Lc)/Lg,1),'pr':round(100*La/(La+Lc),1),'total':round(statistics.mean(tot_prev),1)}

att=defaultdict(Counter)
for r in rows('stw%02d.csv'%(PREV%100)):
    if r['season_type']=='REG' and r['position']=='QB': att[r['team']][r['player_id']]+=num(r['attempts']) or 0
D['qb25']={t:c.most_common(1)[0][0] for t,c in att.items()}

H=defaultdict(list); R=defaultdict(list); ah=[]; ar=[]
for r in GA:
    if r['home_score']=='' or r['game_type']!='REG' or not 2015<=int(r['season'])<=PREV or r['location']!='Home': continue
    h=REL.get(r['home_team'],r['home_team']); a=REL.get(r['away_team'],r['away_team']); m=num(r['home_score'])-num(r['away_score'])
    H[h].append(m); R[a].append(-m); ah.append(m); ar.append(-m)
LGH=statistics.mean(ah)-statistics.mean(ar); D['hfa_lg']=round(LGH,2)

old={r['old_game_id']:r for r in GA if r['home_score']}; crew=defaultdict(list); this_ref={}
for r in rows('officials.csv'):
    if r['position'].strip()!='Referee': continue
    if int(r['season'])==PREV and r['game_id'] in old and old[r['game_id']]['game_type']=='REG':
        g=old[r['game_id']]; crew[r['official_name'].strip()].append(num(g['home_score'])+num(g['away_score']))
    if int(r['season'])==SEASON and int(r['week'])==WEEK: this_ref[r['game_id']]=r['official_name'].strip()
ESPN={r['espn'].split('.')[0]:r for r in GA if r.get('espn')}

missing=[]
for g in D['games']:
    nv=ESPN.get(g['id'])
    for s in ('a','h'):
        t=T.get(nf(g[s]))
        if not t: missing.append(g[s]); continue
        g[s+'_pace']=round((t['a']+t['c'])/t['g'],1); g[s+'_pr']=round(100*t['a']/(t['a']+t['c']),1)
        dep=(D['depth'].get(g[s]) or D['depth'].get(nf(g[s])) or {}).get('o',{}).get('QB',[])
        prim=D['qb25'].get(nf(g[s]))
        g[s+'_qbnew']=int(bool(dep and prim and dep[0]['g']!=prim))
    th=nf(g['h'])
    if H.get(th):
        e=statistics.mean(H[th])-statistics.mean(R[th])
        g['hfa']={'e':round(e,2),'d':round(e-LGH,2),'n':len(H[th]),'lg':round(LGH,2)}
    name=(this_ref.get(nv['old_game_id']) if nv else None) or (g.get('ref') or {}).get('n')
    if name:
        c=crew.get(name)
        g['ref']={'n':name,'avg':round(statistics.mean(c),1) if c else None,'gp':len(c) if c else 0,'lg':D['lg']['total'],
                  'src':'nflverse officials' if nv and this_ref.get(nv['old_game_id']) else 'kept from ESPN build'}
    V=D.setdefault('verify',{}).setdefault(g['id'],{})
    if nv:
        for k,val,oth in (('spread',g.get('spread'),-num(nv['spread_line']) if nv['spread_line'] else None),
                          ('total',g.get('ou'),num(nv['total_line']) if nv['total_line'] else None)):
            if val is None: continue
            x=V.setdefault(k,{}); x['v']=val
            if oth is None: x['s']='single'; x.pop('o',None); x['srcs']=['ESPN']
            else: x['o']=oth; x['s']='ok' if abs(val-oth)<0.01 else 'x'; x['srcs']=['ESPN','nflverse']   # the page names the sources in each badge
if missing: sys.exit('no prior-season team rows for: %s'%missing)
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('context rebuilt for %d games; new-QB flags: %s'%(len(D['games']),[g[s] for g in D['games'] for s in ('a','h') if g.get(s+'_qbnew')]))
