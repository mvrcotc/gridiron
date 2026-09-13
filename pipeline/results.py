"""This week's actual stat lines for finished games. Points are nflverse's own fantasy_points_ppr, which
deducts every lost fumble (rushing, receiving, sack) and credits two-point conversions."""
import os, json, csv
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
D=json.load(open(os.path.join(DATA,'gi2.json')))
ids={g['id'] for g in D['games']}
sw=[(int(r['season']),int(r['week'])) for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'))) if (r.get('espn') or '').split('.')[0] in ids]
season,week=max(set(sw),key=sw.count)
iv=lambda v:int(round(float(v or 0)))
MAP=[('tgt','targets'),('rec','receptions'),('ry','receiving_yards'),('rtd','receiving_tds'),('car','carries'),('ru','rushing_yards'),
     ('rutd','rushing_tds'),('att','attempts'),('cmp','completions'),('py','passing_yards'),('ptd','passing_tds'),('int','passing_interceptions')]
RES={}
path=os.path.join(DATA,'stw%02d.csv'%(season%100))
for r in csv.DictReader(open(path,encoding='utf-8')):
    if r['season_type']!='REG' or int(r['week'])!=week or r['player_id'] not in D['players']: continue
    e={k:iv(r[c]) for k,c in MAP if iv(r[c])}
    fl=iv(r['rushing_fumbles_lost'])+iv(r['receiving_fumbles_lost'])+iv(r['sack_fumbles_lost'])
    if fl: e['fum']=fl
    if not e: continue
    e['pts']=round(float(r['fantasy_points_ppr'] or 0),1)
    S=(D['prod'].get(r['player_id']) or {}).get('S')
    if S:
        gp=max(1,S.get('g',1)); pg=lambda k:S.get(k,0)/gp
        exp=round(pg('rec')+0.1*pg('ry')+6*pg('rtd')+0.1*pg('ru')+6*pg('rutd')+0.04*pg('py')+4*pg('ptd'),1)
        e['exp']=exp
        if exp>=3:
            e['r']=round(e['pts']/exp,2); e['v']='beat' if e['r']>=1.25 else 'miss' if e['r']<=0.75 else 'met'
    RES[r['player_id']]=e
D['res']=RES
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('week %d actuals: %d stat lines'%(week,len(RES)))
