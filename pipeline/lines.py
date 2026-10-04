"""Line movement: when GridIron disagrees with the betting line, does the line later move its way?

The closing line beats GridIron (Model page). This asks a narrower question that needs far fewer games to answer: does
GridIron know where the line is going? A model that does would have bet into the opening number at a better price than
the close -- the edge professional bettors chase -- even while the close stays the better forecast of the score. A model
that does not is noise around the line.

The lines are one book's (ESPN's game summary keeps its opening and closing number after the game; DraftKings today), so
a move is that book changing its own price, never two books disagreeing. Each finished game is stored once in
pipeline/learning/lines.json and never rewritten.

GridIron's early opinion is measured two ways:

  rebuilt  For every stored game: the ratings as they stood a week before kickoff (after week w-2's games for a week-w
           game; weeks 1 and 2 use last season's), plus home field, the venue edge to that point and rest -- all known
           when the line opened. When a book posts its opener is not recorded, and look-ahead lines go up a week early,
           so the week of lag keeps GridIron from being credited with results the opener had not seen. The backup-QB
           flag (the actual starter), weather and the referee are left out: they arrive after the open and move the
           line too. Spreads only: a past season's league scoring averages are that season's full ones (an engine-wide
           simplification that barely touches a margin but would flatter a total).
  real     GridIron's own call at the first line it recorded for the game (the kickoff ledger's `entry`, timestamped,
           before kickoff), against the same book's close. Spreads and totals. It starts with this stage.

Disagreement d = GridIron's margin minus the line's; move = closing margin minus that line's. A game counts toward
GridIron when the move has d's sign.

The benchmark is a guess that knows nothing about the teams: home field alone. An opener set too far from the middle
drifts back, and any opinion nearer the middle gets credit for that drift without knowing anything; GridIron's moves
are judged against the benchmark's, and a significant lean that the benchmark matches is called reversion, not skill.
The money question sits beside it: GridIron's side bet at the opening number, settled on the final score.

   python3 pipeline/lines.py              measure from the stored lines (plus this slate's finished games)
   python3 pipeline/lines.py --fetch [N]  first fetch up to N (default 150) finished games' summaries not yet stored"""
import os, sys, csv, json, math, time, statistics, urllib.request
from collections import defaultdict, Counter
HERE=os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0,HERE)
from engine2 import DATA

GI=os.path.join(DATA,'gi2.json'); RAW=os.path.join(DATA,'raw','espn'); STORE=os.path.join(HERE,'learning','lines.json')
SUMMARY='https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=%s'
FIRST=2023                       # seasons from here on are fetched
NEED=50                          # moves needed before a verdict is given
BUCKETS=((0,2),(2,4),(4,7),(7,None))
ESPN2NFL={'LAR':'LA','WSH':'WAS'}

def iso(t=None): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(t))
def sign(x): return (x>0)-(x<0)

# ------------------------------------------------------------------ parsing ESPN
def num(t):
    try: v=float(t)
    except (TypeError,ValueError): return None
    return v+0.0 if math.isfinite(v) else None          # +0.0 turns ESPN's '-0' into 0
def spread_of(x):
    """an ESPN spread string ('-3.5', '+3', 'PK', 'EVEN') as the home spread"""
    if x is None: return None
    t=str(x).strip().lower()
    return 0.0 if t in ('pk','pick','even',"pick'em") else num(t)
def total_of(x):
    """an ESPN total string ('o44.5', 'u44.5', '44.5')"""
    if x is None: return None
    t=str(x).strip().lower()
    return num(t[1:] if t[:1] in ('o','u') else t)

def parse(s):
    """(book, open, close, home, final) from an ESPN game summary; open/close are dicts of spread (home) and ou"""
    c=((s.get('header') or {}).get('competitions') or [{}])[0] or {}
    st=((c.get('status') or {}).get('type') or {})
    home=next((x.get('team',{}).get('abbreviation') for x in (c.get('competitors') or []) if x.get('homeAway')=='home'),None)
    final=bool(st.get('completed')) or st.get('state')=='post'
    for pc in (s.get('pickcenter') or []):
        ps=(pc.get('pointSpread') or {}).get('home') or {}; tt=(pc.get('total') or {}).get('over') or {}
        o=dict(spread=spread_of((ps.get('open') or {}).get('line')),ou=total_of((tt.get('open') or {}).get('line')))
        if o['spread'] is None and o['ou'] is None: continue
        cl=dict(spread=spread_of((ps.get('close') or {}).get('line')),ou=total_of((tt.get('close') or {}).get('line')))
        return dict(book=(pc.get('provider') or {}).get('name'),open=o,close=cl,home=ESPN2NFL.get(home,home),final=final)
    return dict(book=None,open=None,close=None,home=ESPN2NFL.get(home,home),final=final)

# ------------------------------------------------------------------ the store
def load():
    try: S=json.load(open(STORE,encoding='utf-8'))
    except (OSError,ValueError): S={}
    S.setdefault('games',{}); S.setdefault('none',{}); return S

def save(S):
    """one game per line, so a day's additions read as a day's additions in the git history"""
    S['updated']=iso()
    S['note']=('Opening and closing lines from ESPN game summaries, one book per game (spread is the home spread: '
               'negative when the home team is favoured). A stored game is never rewritten. "none" lists games whose '
               'summary carried no usable line, so they are not fetched again.')
    out=['{"updated":%s,"note":%s,'%(json.dumps(S['updated']),json.dumps(S['note']))]
    for key in ('games','none'):
        items=sorted(S[key].items(),key=lambda kv:(-kv[1].get('s',0),-kv[1].get('w',0),kv[0]))
        out.append('"%s":{'%key+(','.join('\n %s:%s'%(json.dumps(k),json.dumps(v,separators=(',',':'),sort_keys=True)) for k,v in items))+'\n}'+(',' if key=='games' else ''))
    out.append('}')
    tmp=STORE+'.part'; open(tmp,'w',encoding='utf-8').write('\n'.join(out)+'\n'); os.replace(tmp,STORE)

def schedule():
    """ESPN id -> nflverse schedule row, regular season"""
    return {str(r.get('espn') or '').split('.')[0]:r for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'),encoding='utf-8'))
            if r.get('espn') and r['game_type']=='REG'}

def add(S,gid,r,s,src):
    """store one finished game's lines from a parsed summary; returns what happened. A slate summary must say the game
    is over (its close is then final); a fetched one is only asked for once nflverse has the score. A fetched summary
    for the wrong home team is listed under none, so a game that can never match is not fetched every day."""
    if gid in S['games']: return 'kept'
    if r['home_score'] in ('',None): return 'no nflverse score yet'      # stored games are scored games; it comes back next run
    if src=='slate' and not s['final']: return 'not final'
    base=dict(s=int(r['season']),w=int(r['week']),h=r['home_team'],a=r['away_team'],at=iso(),src=src)
    if s['home'] and s['home']!=r['home_team']:
        if src!='slate': S['none'][gid]=dict(base,why='summary home team %s, schedule %s'%(s['home'],r['home_team']))
        return 'home team mismatch'
    if not s['open'] or s['open']['spread'] is None or not s['close'] or s['close']['spread'] is None:
        S['none'][gid]=dict(base,why='no opening and closing spread in the summary'); return 'none'
    S['games'][gid]=dict(base,book=s['book'],open=s['open'],close=s['close']); S['none'].pop(gid,None); return 'added'

def from_slate(S,SC,D):
    """this slate's finished games, from the summaries the espn stage already saved"""
    n=Counter()
    for g in D.get('games',[]):
        r=SC.get(g['id'])
        if g.get('state')!='post' or not r or g['id'] in S['games']: continue
        try: s=json.load(open(os.path.join(RAW,'s_%s.json'%g['id']),encoding='utf-8'))
        except (OSError,ValueError): continue
        n[add(S,g['id'],r,parse(s),'slate')]+=1
    return n

def fetch_missing(S,SC,cap):
    """finished games from FIRST on that are neither stored nor known to have no line, newest first"""
    todo=sorted((gid for gid,r in SC.items() if int(r['season'])>=FIRST and r['home_score'] not in ('',None)
                 and gid not in S['games'] and gid not in S['none']),
                key=lambda g:(-int(SC[g]['season']),-int(SC[g]['week']),g))
    n=Counter(); fails=0
    for gid in todo[:cap]:
        try:
            with urllib.request.urlopen(urllib.request.Request(SUMMARY%gid),timeout=60) as resp: s=json.loads(resp.read())
            fails=0
        except Exception as e:
            n['fetch failed']+=1; fails+=1
            if fails>=5: print('  five fetches in a row failed (%s); stopping for this run'%str(e)[:60]); break
            continue
        n[add(S,gid,SC[gid],parse(s),'fetch')]+=1
        time.sleep(0.15)
    return n,max(0,len(todo)-cap)

# ------------------------------------------------------------------ GridIron's early opinion
def rebuilt(SC,ids):
    """ESPN id -> (GridIron's ratings-only margin a week before kickoff, home field alone) -- see the module note"""
    import gamemodel as gm
    from review import side, snapshot
    C=gm.load_champion(); book=gm.Book(); out={}
    for gid in ids:
        r=SC.get(gid)
        if not r: continue
        s,w=int(r['season']),int(r['week']); lw=max(w-1,1)
        P=gm.in_force(C,s,lw)['params']; snap=snapshot(P,s,lw); h,a=r['home_team'],r['away_team']
        H,A=side(snap,P,s,h,a),side(snap,P,s,a,h)
        f=book.features(r); neutral=f['neutral']>0
        hf=0.0 if neutral else P['hfa']
        out[gid]=(H['p']-A['p']+hf+(0.0 if neutral else P['venue']*book.venue(h,s,lw))+P['rest']*f['rest'],hf)
    return out

# ------------------------------------------------------------------ the measurement
def binom_p(k,n):
    """two-sided exact binomial p of k successes in n at one half"""
    if not n: return None
    pk=[math.comb(n,i)/2**n for i in range(n+1)]
    return min(1.0,sum(p for p in pk if p<=pk[k]*(1+1e-9)))

def stats(X):
    """X: (disagreement, move[, actual margin minus the line, minus the close]) per game"""
    P=[x for x in X if x[0]]; M=[x for x in P if x[1]]
    tw=sum(1 for x in M if sign(x[0])==sign(x[1]))
    out=dict(n=len(X),moved=len(M),toward=tw,away=len(M)-tw,flat=len(P)-len(M),
             pts=round(statistics.mean(x[1]*sign(x[0]) for x in P),3) if P else None,
             p=round(binom_p(tw,len(M)),4) if M else None)
    if len(X)>=3:
        d=[x[0] for x in X]; m=[x[1] for x in X]; db,mb=statistics.mean(d),statistics.mean(m)
        sxx=sum((v-db)**2 for v in d)
        if sxx>0:
            b=sum((u-db)*(v-mb) for u,v in zip(d,m))/sxx; res=[v-mb-b*(u-db) for u,v in zip(d,m)]
            out.update(slope=round(b,4),se=round(math.sqrt(sum(e*e for e in res)/(len(X)-2)/sxx),4))
    out['verdict']='early' if len(M)<NEED else ('signal' if tw>len(M)-tw else 'against') if out['p']<0.05 else 'none'
    return out

def ats(X,k):
    """GridIron's side against a line: X[i][k] is the result against that line, X[i][k+1] GridIron against it"""
    w=l=p=0
    for x in X:
        if not x[k+1]: continue
        if not x[k]: p+=1
        elif sign(x[k])==sign(x[k+1]): w+=1
        else: l+=1
    return [w,l,p]

def measure(S,SC,E):
    G=S['games']; ids=[g for g in G if g in SC and SC[g]['home_score'] not in ('',None)]
    M=rebuilt(SC,ids); X=[]; B=[]; by=defaultdict(list); err=[]
    for gid in ids:
        if gid not in M: continue
        g=G[gid]; r=SC[gid]; om,cm=-g['open']['spread'],-g['close']['spread']
        am=float(r['home_score'])-float(r['away_score']); gmg,hf=M[gid]
        x=(gmg-om,cm-om,am-om,gmg-om,am-cm,gmg-cm); X.append(x); by[g['s']].append(x); B.append((hf-om,cm-om))
        err.append((abs(om-am),abs(cm-am),abs(gmg-am)))
    R=stats([x[:2] for x in X])
    R.update(seasons={str(s):{k:v for k,v in stats([x[:2] for x in by[s]]).items() if k in ('n','moved','toward','pts')} for s in sorted(by)},
             buckets=[dict(lo=lo,hi=hi,**{k:v for k,v in stats([x[:2] for x in X if abs(x[0])>=lo and (hi is None or abs(x[0])<hi)]).items() if k in ('n','moved','toward','pts')})
                      for lo,hi in BUCKETS],
             ats_open=ats(X,2),ats_close=ats(X,4),
             # the benchmark: a "model" that knows nothing about the teams. Openers that sit far from the middle drift
             # back, and any opinion closer to the middle than the opener gets credit for that; GridIron has to beat it.
             base={k:v for k,v in stats(B).items() if k in ('n','moved','toward','away','pts','p','slope')},
             err=dict(open=round(statistics.mean(e[0] for e in err),3),close=round(statistics.mean(e[1] for e in err),3),gi=round(statistics.mean(e[2] for e in err),3)) if err else None)
    rate=lambda x:x['toward']/x['moved'] if x.get('moved') else 0.0
    if R['verdict']=='signal' and rate(R['base'])>=rate(R): R['verdict']='reversion'
    # real calls: the ledger's first recorded call, against the same book's close
    Xs=[]; Xt=[]; pend=0
    for gid,e in E.items():
        en=e.get('entry')
        if not en or en.get('ph') is None: continue
        g=G.get(gid)
        if not g: pend+=1; continue
        if en.get('spread') is not None: Xs.append(((en['ph']-en['pa'])+en['spread'],en['spread']-g['close']['spread']))
        if en.get('ou') is not None and g['close'].get('ou') is not None: Xt.append(((en['ph']+en['pa'])-en['ou'],g['close']['ou']-en['ou']))
    books=Counter(g.get('book') for g in G.values())
    return dict(book=books.most_common(1)[0][0] if books else None,books=dict(books),rebuilt=R,
                real=dict(spread=stats(Xs),total=stats(Xt),pending=pend,recorded=sum(1 for e in E.values() if e.get('entry'))),
                store=dict(games=len(G),none=len(S['none']),seasons=dict(sorted(Counter(str(g['s']) for g in G.values()).items()))),
                need=NEED,lag='a week',first=FIRST)

def main():
    a=sys.argv[1:]; D=json.load(open(GI,encoding='utf-8')); SC=schedule(); S=load()
    n=from_slate(S,SC,D)
    if n: print('slate: %s'%dict(n))
    if '--fetch' in a:
        i=a.index('--fetch'); cap=int(a[i+1]) if len(a)>i+1 and a[i+1].isdigit() else 150
        f,left=fetch_missing(S,SC,cap); print('fetched: %s; %d games still to fetch'%(dict(f),left))
    save(S)
    R=measure(S,SC,(D.get('ledger') or {}).get('entries') or {})
    D['moves']=R; json.dump(D,open(GI,'w'),separators=(',',':'))
    rb,rs=R['rebuilt'],R['real']['spread']
    print('lines: %d games stored (%s), %d without a line | rebuilt: %d of %d moves toward GridIron, %+s pts, p=%s, %s | real calls: %d of %d'%(
        R['store']['games'],R['store']['seasons'],R['store']['none'],rb['toward'],rb['moved'],rb['pts'],rb['p'],rb['verdict'],rs['toward'],rs['moved']))

if __name__=='__main__': main()
