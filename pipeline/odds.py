"""Every US sportsbook's line, from The Odds API -- off until an API key is set.

ESPN shows one book. Taking the best number across books (line shopping) is worth more than most model changes:
+3.5 instead of +3, or -105 instead of -110. With ODDS_API_KEY set (a repository secret passed to the refresh), the
daily lane takes one snapshot of spreads, totals and moneylines for the slate (3 of the free plan's 500 monthly
credits) and appends it to pipeline/learning/odds_<season>.jsonl, building the multi-book, timestamped line history
the opening-line test needs. Every lane publishes the best number on each side from the latest snapshot.

Without a key the stage does nothing and the page shows nothing extra.

   ODDS_API_KEY=... python3 pipeline/odds.py --fetch    take a snapshot (daily lane)
   python3 pipeline/odds.py                             publish the best lines from the latest snapshot"""
import os, sys, json, time, datetime, urllib.request, urllib.parse
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(ROOT,'data'); GI=os.path.join(DATA,'gi2.json')
URL='https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/?'
TEAM={'Arizona Cardinals':'ARI','Atlanta Falcons':'ATL','Baltimore Ravens':'BAL','Buffalo Bills':'BUF','Carolina Panthers':'CAR',
      'Chicago Bears':'CHI','Cincinnati Bengals':'CIN','Cleveland Browns':'CLE','Dallas Cowboys':'DAL','Denver Broncos':'DEN',
      'Detroit Lions':'DET','Green Bay Packers':'GB','Houston Texans':'HOU','Indianapolis Colts':'IND','Jacksonville Jaguars':'JAX',
      'Kansas City Chiefs':'KC','Las Vegas Raiders':'LV','Los Angeles Chargers':'LAC','Los Angeles Rams':'LAR','Miami Dolphins':'MIA',
      'Minnesota Vikings':'MIN','New England Patriots':'NE','New Orleans Saints':'NO','New York Giants':'NYG','New York Jets':'NYJ',
      'Philadelphia Eagles':'PHI','Pittsburgh Steelers':'PIT','San Francisco 49ers':'SF','Seattle Seahawks':'SEA',
      'Tampa Bay Buccaneers':'TB','Tennessee Titans':'TEN','Washington Commanders':'WSH'}

def iso(t=None): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(t))
def ts(s): return datetime.datetime.fromisoformat(str(s).replace('Z','+00:00')).timestamp()
def dec(american):
    """American odds as a decimal payout, for comparing prices"""
    a=float(american); return 1+a/100.0 if a>0 else 1+100.0/-a

def boil(events,games):
    """The Odds API events -> ESPN game id -> book -> [market, side, point, price] rows; unmatched events are skipped"""
    out={}
    for ev in events:
        h,a=TEAM.get(ev.get('home_team')),TEAM.get(ev.get('away_team'))
        try: when=ts(ev['commence_time'])
        except (KeyError,ValueError): continue
        g=next((g for g in games if g['h']==h and g['a']==a and abs(ts(g['date'])-when)<12*3600),None)
        if not g: continue
        books={}
        for b in ev.get('bookmakers') or []:
            rows=[]
            for m in b.get('markets') or []:
                for o in m.get('outcomes') or []:
                    side={ev['home_team']:'home',ev['away_team']:'away','Over':'over','Under':'under'}.get(o.get('name'))
                    if side is None or o.get('price') is None: continue
                    if m.get('key') in ('spreads','totals') and o.get('point') is None: continue
                    rows.append([m['key'],side,o.get('point'),o['price']])
            if rows: books[b.get('title') or b.get('key')]=rows
        if books: out[g['id']]=books
    return out

def better(m,side,x,y):
    """is row x a better bet than row y for this market and side?"""
    if m=='spreads' and x[2]!=y[2]: return x[2]>y[2]                     # more points (or fewer given) is better
    if m=='totals' and x[2]!=y[2]: return x[2]<y[2] if side=='over' else x[2]>y[2]
    return dec(x[3])>dec(y[3])

def best(books):
    """market -> side -> {point, price, book, n}"""
    out={}
    for book,rows in books.items():
        for m,side,pt,price in rows:
            cur=out.setdefault(m,{}).get(side); row=[m,side,pt,price]
            if cur is None or better(m,side,row,[m,side,cur['point'],cur['price']]): out[m][side]=dict(point=pt,price=price,book=book)
    return out

def log_path(season): return os.path.join(HERE,'learning','odds_%d.jsonl'%season)
def latest(season):
    last=None
    try:
        with open(log_path(season),encoding='utf-8') as f:
            for line in f:
                if line.strip(): last=line
        return json.loads(last) if last else None
    except (OSError,ValueError): return None

def season_of(D):
    d=min((g['date'] for g in D.get('games',[])),default=iso())[:10]; y,mth=int(d[:4]),int(d[5:7])
    return y if mth>=3 else y-1

def main():
    D=json.load(open(GI,encoding='utf-8')); season=season_of(D); key=os.environ.get('ODDS_API_KEY','').strip()
    if '--fetch' in sys.argv:
        if not key: print('odds: no ODDS_API_KEY set; multi-book lines are off')
        else:
            q=urllib.parse.urlencode(dict(apiKey=key,regions='us',markets='spreads,totals,h2h',oddsFormat='american'))
            try:
                with urllib.request.urlopen(URL+q,timeout=60) as r:
                    events=json.loads(r.read()); left=r.headers.get('x-requests-remaining')
                snap=dict(at=iso(),remaining=left,games=boil(events,D.get('games',[])))
                with open(log_path(season),'a',encoding='utf-8') as f: f.write(json.dumps(snap,separators=(',',':'),sort_keys=True)+'\n')
                print('odds: %d games from %d events, %s credits left'%(len(snap['games']),len(events),left))
            except Exception as e: print('odds: fetch failed (%s); keeping the last snapshot'%str(e)[:100])
    snap=latest(season)
    if not snap: D.pop('odds',None)
    else:
        G={}
        for gid,books in snap['games'].items():
            b=best(books); b['books']=len(books); G[gid]=b
        D['odds']=dict(at=snap['at'],games=G,source='The Odds API, US books')
    json.dump(D,open(GI,'w'),separators=(',',':'))
    print('odds: %s'%('best lines for %d games from the snapshot of %s'%(len(D['odds']['games']),D['odds']['at']) if snap else 'nothing published'))

if __name__=='__main__': main()
