"""Prop-line archive: every DraftKings player prop GridIron reads, kept with GridIron's call on it and later settled on
the player's real stat line -- the history needed to find out whether GridIron's prop reads beat the book.

The props stage reads the current lines and GridIron's chance of the over for each. Without a record of past lines
there is no way to prove anything (the Model page says so); this builds that record. Per season,
pipeline/learning/props_<season>.json holds one entry per game, player and market:
  first  the line, DraftKings' opening line and GridIron's median and P(over) the first time the archive saw it
  last   the same at the latest daily run before kickoff -- the number a bettor could have taken
  actual the player's stat from nflverse once the week's stats are out; a player with no stat line is void
Entries are recorded only before kickoff and never rewritten after it; only the daily lane records (it commits
pipeline/learning), every lane settles and summarises.

GridIron's side is the over when P(over) > 50%, the under when below. The benchmark is taking every under: books are
known to shade overs, so a model that leans under can look good for that reason alone. No prices come with these
lines, so 52.4% (-110) is taken as break-even.

   python3 pipeline/propsarc.py            settle and summarise
   python3 pipeline/propsarc.py --record   first record this run's pre-kickoff lines (daily lane)"""
import os, sys, csv, json, time, datetime, statistics
from collections import defaultdict
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(ROOT,'data'); GI=os.path.join(DATA,'gi2.json')
STAT={'qry':'receiving_yards','qrec':'receptions','qru':'rushing_yards','qpy':'passing_yards'}
BREAK=52.4

def iso(t=None): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(t))
def ts(s): return datetime.datetime.fromisoformat(str(s).replace('Z','+00:00')).timestamp()
def path(season): return os.path.join(HERE,'learning','props_%d.json'%season)
def load(season):
    try: return json.load(open(path(season),encoding='utf-8')).get('entries') or {}
    except (OSError,ValueError): return {}
def save(season,E):
    items=sorted(E.items(),key=lambda kv:(kv[1]['w'],kv[0]))
    body=',\n'.join(' %s:%s'%(json.dumps(k),json.dumps(v,separators=(',',':'),sort_keys=True)) for k,v in items)
    out='{"updated":%s,"entries":{\n%s\n}}\n'%(json.dumps(iso()),body)
    p=path(season); open(p+'.part','w',encoding='utf-8').write(out); os.replace(p+'.part',p)

def seasons_on_file():
    d=os.path.join(HERE,'learning')
    return sorted(int(f[6:10]) for f in os.listdir(d) if f.startswith('props_') and f.endswith('.json') and f[6:10].isdigit())

def schedule():
    """ESPN id -> nflverse schedule row, regular season"""
    return {str(r.get('espn') or '').split('.')[0]:r for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'),encoding='utf-8'))
            if r.get('espn') and r['game_type']=='REG'}

def record(D,now,SC):
    """this run's lines for games still before kickoff"""
    try: rows=json.load(open(os.path.join(HERE,'props.json'),encoding='utf-8'))
    except (OSError,ValueError): return 0
    games={g['id']:g for g in D.get('games',[])}; book={}; n=0; seen=set()
    for r in rows:
        g=games.get(r.get('g')); sc=SC.get(r.get('g'))
        if not g or not sc or g.get('state')!='pre' or now>=ts(g['date']) or r.get('line') is None: continue
        season=int(sc['season'])
        if season not in book: book[season]=load(season)
        E=book[season]
        key='%s|%s|%s'%(r['g'],r['gs'],r['k'])
        if key in seen: continue                                 # one line per player and market per run
        seen.add(key)
        snap=dict(at=iso(now),line=r['line'],p=r['p'],mine=r.get('mine'))
        e=E.get(key)
        if e is None:
            E[key]=e=dict(g=r['g'],gs=r['gs'],k=r['k'],lab=r.get('lab'),w=int(sc['week']),nfl=sc['game_id'],kickoff=g['date'],
                          first=dict(snap,open=r.get('open')))
        e['kickoff']=g['date']                                   # a kickoff can still move before the game
        if now<ts(e['kickoff']): e['last']=snap; n+=1
    for season,E in book.items(): save(season,E)
    return n

def stats(season):
    """(gsis id, week) -> nflverse stat row, regular season"""
    p=os.path.join(DATA,'stw%02d.csv'%(season%100))
    if not os.path.exists(p): return None
    return {(r['player_id'],int(r['week'])):r for r in csv.DictReader(open(p,encoding='utf-8')) if r.get('season_type')=='REG'}

def settle(season,E,ST,games_done):
    """attach the actual stat for every entry whose game nflverse has published stats for"""
    n=0
    for e in E.values():
        if 'actual' in e or e.get('nfl') not in games_done: continue
        r=ST.get((e['gs'],e['w']))
        try: e['actual']=float(r[STAT[e['k']]]) if r else None
        except (TypeError,ValueError,KeyError): e['actual']=None
        n+=1
    return n

def summary(entries):
    S=[e for e in entries if e.get('actual') is not None and e.get('last')]
    gi=[0,0,0]; un=[0,0,0]; by=defaultdict(lambda:[0,0,0])
    for e in S:
        line=e['last']['line']; a=e['actual']; p=e['last']['p']; res=(a>line)-(a<line)
        un[2 if res==0 else 0 if res<0 else 1]+=1
        if p==0.5: continue
        side=1 if p>0.5 else -1; o=2 if res==0 else 0 if res==side else 1
        gi[o]+=1; by[e['k']][o]+=1
    pct=lambda x:round(100.0*x[0]/(x[0]+x[1]),1) if x[0]+x[1] else None
    return dict(settled=len(S),void=sum(1 for e in entries if 'actual' in e and e['actual'] is None),
                pending=sum(1 for e in entries if 'actual' not in e),gi=gi,gi_pct=pct(gi),under=un,under_pct=pct(un),
                by={k:dict(rec=v,pct=pct(v)) for k,v in sorted(by.items())},break_even=BREAK,
                lean_under=round(100.0*sum(1 for e in S if e['last']['p']<0.5)/len(S),1) if S else None)

def main():
    D=json.load(open(GI,encoding='utf-8')); now=time.time()
    if '--record' in sys.argv: print('props archive: %d lines recorded before kickoff'%record(D,now,schedule()))
    allE=[]
    for s in seasons_on_file():
        E=load(s); ST=stats(s)
        if ST is not None:
            done={r['game_id'] for r in ST.values()}
            if settle(s,E,ST,done): save(s,E)
        allE.extend(E.values())
    R=summary(allE); R.update(entries=len(allE),seasons=seasons_on_file())
    D['propsarc']=R; json.dump(D,open(GI,'w'),separators=(',',':'))
    print('props archive: %d entries, %d settled (%d void, %d pending) | GridIron side %s, all unders %s'%(
        len(allE),R['settled'],R['void'],R['pending'],R['gi_pct'],R['under_pct']))

if __name__=='__main__': main()
