"""Markets: the prop-line archive and the multi-book odds feed, rebuilt with code written only for the audit. Archive
entries are checked against kickoff, against the last committed archive (a recorded line never changes after it is
first seen) and against nflverse's player stats; the summary and the page are recomputed from the archive; the best
number on each side is re-picked from the latest odds snapshot."""
import os, re, json, math, datetime, subprocess
from collections import defaultdict
from common import num, rows, DATA, PIPE, ROOT

COL={'qry':'receiving_yards','qrec':'receptions','qru':'rushing_yards','qpy':'passing_yards'}
def t(s): return datetime.datetime.fromisoformat(str(s).replace('Z','+00:00'))
def jsr1(x): return math.floor(x*10+0.5)/10
def figs(s): return [float(x) for x in re.findall(r'\d+(?:\.\d+)?',s or '')]

def run(A):
    A.section('markets: prop archive and odds'); D=A.D
    L=os.path.join(PIPE,'learning')
    files=sorted(f for f in os.listdir(L) if re.fullmatch(r'props_\d{4}\.json',f))
    bad=[]; allE=[]
    for f in files:
        s=int(f[6:10]); E=(json.load(open(os.path.join(L,f),encoding='utf-8')).get('entries') or {})
        prev=subprocess.run(['git','-C',ROOT,'show','HEAD:pipeline/learning/'+f],capture_output=True,text=True)
        H=(json.loads(prev.stdout).get('entries') or {}) if prev.returncode==0 else {}
        p=os.path.join(DATA,'stw%02d.csv'%(s%100)); ST={}; pub=set()
        if os.path.exists(p):
            for r in rows(p):
                if r.get('season_type')=='REG': ST[(r['player_id'],r['game_id'])]=r; pub.add(r['game_id'])
        for key,e in E.items():
            allE.append(e)
            if key!='%s|%s|%s'%(e.get('g'),e.get('gs'),e.get('k')) or e.get('k') not in COL: bad.append('%s is malformed'%key); continue
            for snap in ('first','last'):
                x=e.get(snap)
                if x and t(x['at'])>=t(e['kickoff']): bad.append('%s %s line recorded at %s, kickoff %s'%(key,snap,x['at'],e['kickoff']))
            if e.get('last') and e.get('first') and t(e['last']['at'])<t(e['first']['at']): bad.append('%s last line is older than its first'%key)
            if key in H and H[key].get('first')!=e.get('first'): bad.append('%s first line changed after it was recorded'%key)
            if key in H and 'actual' in H[key] and H[key]['actual']!=e.get('actual'): bad.append('%s settled result changed'%key)
            if 'actual' in e:
                if e.get('nfl') not in pub: bad.append('%s settled before nflverse published its game'%key)
                else:
                    r=ST.get((e['gs'],e['nfl'])); want=num(r[COL[e['k']]],None) if r else None
                    if e['actual']!=want: bad.append('%s settled at %s, nflverse says %s'%(key,e['actual'],want))
            elif e.get('nfl') in pub: bad.append('%s is unsettled although nflverse has published its game'%key)
    A.check('PA1','Prop archive: every line recorded before kickoff, never changed once kept, and settled on nflverse\'s own stat line',bad,len(allE))

    bad=[]; P=D.get('propsarc')
    S=[e for e in allE if e.get('actual') is not None and e.get('last')]
    gi=[0,0,0]; un=[0,0,0]; by=defaultdict(lambda:[0,0,0])
    for e in S:
        d=e['actual']-e['last']['line']; un[2 if d==0 else 0 if d<0 else 1]+=1
        if e['last']['p']==0.5: continue
        win=(d>0) if e['last']['p']>0.5 else (d<0)
        k=2 if d==0 else 0 if win else 1; gi[k]+=1; by[e['k']][k]+=1
    pc=lambda x:round(100.0*x[0]/(x[0]+x[1]),1) if x[0]+x[1] else None
    if P is None: bad.append('data/gi2.json has no prop-archive summary')
    else:
        want=dict(settled=len(S),void=sum(1 for e in allE if 'actual' in e and e['actual'] is None),pending=sum(1 for e in allE if 'actual' not in e),
                  gi=gi,under=un,gi_pct=pc(gi),under_pct=pc(un),entries=len(allE))
        for k,v in want.items():
            if P.get(k)!=v: bad.append('summary %s %s, recompute %s'%(k,P.get(k),v))
        for k,v in by.items():
            if (P.get('by') or {}).get(k,{}).get('rec')!=v: bad.append('%s record %s, recompute %s'%(k,(P.get('by') or {}).get(k,{}).get('rec'),v))
    A.check('PA2','The prop-archive record recomputes: GridIron\'s side, every under, void and pending',bad,len(S))

    # ---------- the odds feed ----------
    bad=[]; O=D.get('odds'); n=0
    if O:
        logs=sorted(f for f in os.listdir(L) if re.fullmatch(r'odds_\d{4}\.jsonl',f)); snap=None
        for f in logs:
            for line in open(os.path.join(L,f),encoding='utf-8'):
                if line.strip():
                    x=json.loads(line)
                    if snap is None or x['at']>snap['at']: snap=x
        if not snap or snap['at']!=O.get('at'): bad.append('published odds from %s, latest snapshot %s'%(O.get('at'),snap and snap['at']))
        else:
            dec=lambda a:1+a/100.0 if a>0 else 1+100.0/-a
            for gid,books in snap['games'].items():
                n+=1; got=(O.get('games') or {}).get(gid) or {}
                if got.get('books')!=len(books): bad.append('%s shows %s books, snapshot has %d'%(gid,got.get('books'),len(books)))
                for m,sides in (('spreads',('home','away')),('totals',('over','under')),('h2h',('home','away'))):
                    for sd in sides:
                        rs=[(b,r[2],r[3]) for b,R in books.items() for r in R if r[0]==m and r[1]==sd]
                        if not rs: continue
                        if m=='spreads': top=max(rs,key=lambda x:(x[1],dec(x[2])))
                        elif m=='totals': top=max(rs,key=lambda x:((-x[1]) if sd=='over' else x[1],dec(x[2])))
                        else: top=max(rs,key=lambda x:dec(x[2]))
                        g=(got.get(m) or {}).get(sd) or {}
                        if (g.get('point'),g.get('price'))!=(top[1],top[2]): bad.append('%s %s %s shows %s %s, best is %s %s (%s)'%(gid,m,sd,g.get('point'),g.get('price'),top[1],top[2],top[0]))
    A.check('OD1','Multi-book odds: the best number on each side re-picked from the latest snapshot (off until a key is set)',bad,n)

    # ---------- the page ----------
    out='/tmp/gi_audit_market.json'
    r=subprocess.run(['node',os.path.join(os.path.dirname(__file__),'render_dump.js'),out],capture_output=True,text=True,timeout=180)
    if r.returncode or not os.path.exists(out):
        A.check('U22','The page renders for the market checks',['render failed: '+(r.stderr or r.stdout)[-300:]]); return
    R=json.load(open(out)); C=(R.get('model') or {}).get('propsarc') or {}; bad=[]
    if P is not None:
        if not S:
            if 'Collecting' not in (C.get('text') or ''): bad.append('nothing settled, but the card does not say it is collecting')
        else:
            tl={x[0]:x for x in C.get('tiles') or []}
            for key,rec,p in (('gi',gi,pc(gi)),('under',un,pc(un))):
                x=tl.get(key) or [None,'','']
                if p is not None and not any(abs(v-jsr1(p))<0.051 for v in figs(x[1])): bad.append('tile %s shows %s, recompute %.1f%%'%(key,x[1],p))
                if not x[2].startswith('%d-%d'%(rec[0],rec[1])): bad.append('tile %s should give %d-%d'%(key,rec[0],rec[1]))
    G={g['id']:g for g in D.get('games',[])}
    for c in R.get('cards') or []:
        ob=((O or {}).get('games') or {}).get(c['id']); g=G.get(c['id']) or {}
        mt={k:v for k,v in (c.get('metrics') or [])}
        if not ob or g.get('state')!='pre':
            if 'Best spread' in mt: bad.append('%s shows a best spread with no odds for it'%c['id'])
            continue
        sp=(ob.get('spreads') or {}).get('home')
        if sp and (sp['book'] not in (mt.get('Best spread') or '') or ('%s'%abs(sp['point'])).rstrip('0').rstrip('.') not in (mt.get('Best spread') or '')):
            bad.append('%s best spread tile "%s" does not carry %s %s'%(c['id'],mt.get('Best spread'),sp['point'],sp['book']))
    A.check('U22','Model page prop-archive card and each game\'s best-line tiles match the archive and the odds snapshot',bad,len(R.get('cards') or []))
