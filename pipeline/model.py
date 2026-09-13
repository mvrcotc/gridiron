import csv, json, collections, math
import numpy as np
rng=np.random.default_rng(7)

# ---------------------------------------------------------------- panel
GM={}
for r in csv.DictReader(open('games_all.csv')):
    if r['season']!='2025' or r['game_type']!='REG': continue
    try: w=int(r['week']); sp=float(r['spread_line']); tot=float(r['total_line'])
    except Exception: continue
    # spread_line is home-relative and positive when home is favoured
    GM[(w,r['home_team'])]={'opp':r['away_team'],'spread':-sp,'total':tot,'home':1}
    GM[(w,r['away_team'])]={'opp':r['home_team'],'spread':sp,'total':tot,'home':0}
    # spread from THIS team's perspective: positive = underdog

P=[]
for r in csv.DictReader(open('stw25.csv')):
    if r['season_type']!='REG': continue
    def n(k):
        try: return float(r.get(k) or 0)
        except Exception: return 0.0
    P.append({'id':r['player_id'],'w':int(r['week']),'tm':r['team'],'opp':r['opponent_team'],
        'pos':r['position_group'],'tgt':n('targets'),'rec':n('receptions'),'ry':n('receiving_yards'),
        'rtd':n('receiving_tds'),'ay':n('receiving_air_yards'),'car':n('carries'),
        'ru':n('rushing_yards'),'rutd':n('rushing_tds'),'att':n('attempts'),'cmp':n('completions'),
        'py':n('passing_yards'),'ptd':n('passing_tds'),'pint':n('passing_interceptions')})

TW=collections.defaultdict(lambda:{'att':0.0,'car':0.0,'tgt':0.0})
for p in P:
    t=TW[(p['w'],p['tm'])]
    t['att']+=p['att']; t['car']+=p['car']; t['tgt']+=p['tgt']

# ------------------------------------------------- 1. game script, fitted
xs,ys=[],[]
for (w,tm),t in TW.items():
    g=GM.get((w,tm)); plays=t['att']+t['car']
    if not g or plays<30: continue
    xs.append(g['spread']); ys.append(t['att']/plays)
xs=np.array(xs); ys=np.array(ys)
A=np.vstack([xs,np.ones(len(xs))]).T
slope,icept=np.linalg.lstsq(A,ys,rcond=None)[0]
resid=ys-(A@np.array([slope,icept]))
r2=1-resid.var()/ys.var()
print(f'game script  : pass rate = {icept:.4f} + {slope:+.5f} x spread   (R2={r2:.3f}, n={len(xs)})')
print(f'               a 7-point underdog throws {slope*7*100:+.1f} pts more often than a pick-em')

LEAGUE_PLAYS=float(np.mean([TW[k]['att']+TW[k]['car'] for k in TW if TW[k]['att']+TW[k]['car']>=30]))
print(f'league plays/game: {LEAGUE_PLAYS:.1f}')

# ------------------------------------------------- 2. positional baselines
POSG=collections.defaultdict(lambda: collections.defaultdict(float))
for p in P:
    g=POSG[p['pos']]
    g['tgt']+=p['tgt']; g['rec']+=p['rec']; g['ry']+=p['ry']; g['rtd']+=p['rtd']; g['ay']+=p['ay']
BASE={}
for pos,g in POSG.items():
    if g['tgt']<50: continue
    BASE[pos]={'cr':g['rec']/g['tgt'],'ypt':g['ry']/g['tgt'],
               'tdpt':g['rtd']/g['tgt'],'adot':g['ay']/g['tgt']}
print('\npositional baselines (2025):')
for pos in sorted(BASE):
    b=BASE[pos]
    print(f'  {pos:<4} catch {b["cr"]*100:5.1f}%   {b["ypt"]:5.2f} yds/tgt   '
          f'{b["tdpt"]*100:4.2f}% TD/tgt   aDOT {b["adot"]:4.1f}')

# how touchdown rate actually varies with depth of target
bins=[(0,5),(5,9),(9,13),(13,100)]
print('\nTD rate by aDOT (this is why TD rate should come from depth, not from the player):')
TDCURVE=[]
for lo,hi in bins:
    tg=td=0.0
    byp=collections.defaultdict(lambda:[0.0,0.0,0.0])
    for p in P:
        if p['tgt']<1: continue
        a=p['ay']/p['tgt']
        if lo<=a<hi: tg+=p['tgt']; td+=p['rtd']
    if tg>60:
        TDCURVE.append(((lo+hi)/2 if hi<100 else 16.0, td/tg))
        print(f'  aDOT {lo:>2}-{hi if hi<100 else "+":<3}  {td/tg*100:5.2f}% per target   (n={tg:,.0f} targets)')
json.dump({'slope':slope,'icept':icept,'plays':LEAGUE_PLAYS,'base':BASE,'tdcurve':TDCURVE},
          open('fit1.json','w'))
