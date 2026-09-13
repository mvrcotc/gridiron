"""Season and last-3 production from raw weekly stats. Target share is the player's targets over his
team's targets in the games he played -- NOT an average of weekly shares that skips his zero-target weeks."""
import os, json, csv
from collections import defaultdict
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
D=json.load(open(os.path.join(DATA,'gi2.json'))); prev=int(D['games'][0]['date'][:4])-1
iv=lambda v:int(round(float(v or 0)))
K={'tgt':'targets','rec':'receptions','ry':'receiving_yards','rtd':'receiving_tds','ay':'receiving_air_yards','att':'attempts',
   'cmp':'completions','py':'passing_yards','ptd':'passing_tds','car':'carries','ru':'rushing_yards','rutd':'rushing_tds'}
W=defaultdict(dict); TT=defaultdict(float)
for r in csv.DictReader(open(os.path.join(DATA,'stw%02d.csv'%(prev%100)),encoding='utf-8')):
    if r['season_type']!='REG': continue
    w=int(r['week']); TT[(r['team'],w)]+=float(r['targets'] or 0); W[r['player_id']][w]=r
def agg(g,weeks):
    o={k:sum(iv(W[g][w][c]) for w in weeks) for k,c in K.items()}; o={k:v for k,v in o.items() if v}
    tt=sum(TT[(W[g][w]['team'],w)] for w in weeks)
    if o.get('tgt') and tt: o['ts']=round(100*o['tgt']/tt,1)
    o['g']=len(weeks); return o
changed=0
for g,e in D['prod'].items():
    if g not in W: continue
    ks=sorted(W[g]); new={'S':agg(g,ks),'L3':agg(g,ks[-3:])}
    tg=[iv(W[g][w]['targets']) for w in ks[-8:]]
    if any(tg): new['tsp']=tg
    if new!=e: changed+=1
    D['prod'][g]=new
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('production rebuilt for %d players (%d changed)'%(len(D['prod']),changed))
