"""Blind-spot scan: what GridIron's game model leaves out, and whether it should stop leaving it out.

The learning loop (learn.py) re-tunes the factors the model already has. This looks outside them. Every completed game
since 2019 is predicted walk-forward by the weights in force before its week -- gamemodel.track_rows, the same record
the Model page publishes -- and its residual is the actual home margin minus GridIron's. Each candidate is something
knowable before kickoff that the model does not use.

A candidate is a blind spot only if all of these hold:
  * fitted on earlier seasons alone, it shrinks the margin error on later seasons it never saw;
  * it helps in most of those held-out seasons, not just on average;
  * that gain survives a week-blocked bootstrap AND a Holm correction for how many candidates were tried at once.
Anything short of that is reported as "watch" (a hint, unproven) or "clear" (no measurable effect), with the evidence.
Most NFL ideas land in "clear": a margin's spread is about 13 points and the closing line already prices most of what
anyone knows. Saying so is the point.

A blind spot is not switched on here. It is written up as a proposal for the owner -- the same route learn.py uses
for switching a factor on -- once, the first time it qualifies. Results and that memory live in
pipeline/learning/blindspots.json, which the daily lane commits.

   python3 pipeline/blindspots.py [--propose]     --propose: file a newly proven blind spot for the owner (daily lane)"""
import os, sys, csv, json, re, math, statistics, datetime
from collections import defaultdict, Counter
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0,HERE)
import gamemodel as gm, engine2
from engine2 import DATA

OUT=os.path.join(HERE,'learning','blindspots.json'); NEWP=os.path.join(HERE,'learning','new_proposals')
GI=os.path.join(DATA,'gi2.json'); ROOT=os.path.dirname(HERE)
REL=gm.REL; FIRST_TEST=2021; B=2000; SEED=20260903
ALPHA,WATCH,MIN_GAIN,MOST=0.05,0.10,0.02,0.6
WEST={'America/Los_Angeles','America/Denver','America/Phoenix'}
EAST={'America/New_York','America/Detroit','America/Indiana/Indianapolis'}

def fnum(v,fb=None):
    try: return float(v)
    except (TypeError,ValueError): return fb
def rel(t): return REL.get(t,t)

CANDIDATES=[
 dict(id='early',name='Early-season overreaction',
      what='In weeks 2 to 4, does GridIron need to pull its margin back toward even?',
      why='Each season resets the yardage and plays ratings, and their trust constants are tiny next to the yards and plays '
          'they count, so a single game sets about 98% of those ratings. Its week-2 expectations spread almost twice as wide '
          'as mid-season ones.',form='scale',rel='The learning loop tunes these trust constants over whole seasons, where they barely matter.'),
 dict(id='starters_out',name='Starters ruled out (not the quarterback)',
      what='Players listed Out or Doubtful, each weighed by his share of snaps over his last three games.',
      why='The game model adjusts for a backup quarterback and nothing else; a team missing its left tackle, top receiver '
          'and best corner is rated as if all three were playing.',form='shift',rel='Only the quarterback is in the model.'),
 dict(id='new_coach',name='New head coach',
      what='A team whose head coach differs from the one who finished last season.',
      why='Ratings carry last season forward; a new staff can change a team faster than the carryover allows.',form='shift',rel='Not in the model.'),
 dict(id='new_qb',name='New starting quarterback (weeks 1-4)',
      what="This season's regular starter is not last season's most frequent one.",
      why='The backup-quarterback term only fires for a backup; a new regular starter inherits ratings built on someone else.',
      form='shift',rel='Flagged on the page, deliberately left out of the model after week-1 tests found no direction.'),
 dict(id='short_week',name='Short-week games',
      what='Both teams on five or fewer days of rest (nearly always a Thursday game): does GridIron need to pull its margin toward even?',
      why='Little time to prepare or recover may make games sloppier and closer than either team\'s ratings suggest.',form='scale',
      rel="The loop's rest factor covers a rest gap between the teams; a short week is almost never one -- of 1,920 games since 2019, "
          "both sides shared it in 123 and only one side had it in 3."),
 dict(id='body_clock',name='West-coast team, early eastern kickoff',
      what='A Pacific or Mountain team away in the Eastern time zone at 1 pm ET (10 am on its body clock).',
      why='A long-cited effect of early kickoffs on travelling western teams.',form='shift',rel='Not in the model.'),
 dict(id='primetime',name='Night games',
      what='Kickoff at 7 pm ET or later, at a home ground.',
      why='Crowds and travel differ at night; the home edge might too.',form='shift',rel='The model uses one flat home edge.'),
 dict(id='divisional',name='Division games',
      what='In a division game, does GridIron need to pull its margin toward even?',
      why='Division rivals meet twice a year and know each other; favourites may win by less.',form='scale',rel='Shown on the page, not in the model.'),
 dict(id='to_luck',name='Recent turnover luck',
      what="Each team's turnover margin over its previous three games this season.",
      why='Turnover margin barely repeats; if recent luck leaks into the ratings, lucky teams are overrated next week.',
      form='shift',rel='The ratings shrink turnovers hard already; this checks whether they shrink them enough.'),
]

# ------------------------------------------------------------------ features, all knowable before kickoff
def team_tz():
    src=open(os.path.join(ROOT,'app','context.js'),encoding='utf-8').read()
    tz={m.group(1):m.group(2) for m in re.finditer(r"([A-Z]{2,3}):\{v:'[^']*',la:[-\d.]+,lo:[-\d.]+,el:[-\d.]+,tz:'([^']+)'",src)}
    tz.setdefault('OAK',tz.get('LV')); tz.setdefault('WAS',tz.get('WSH')); return tz

def starters_out(sched):
    """(season, week, team) -> snap-weighted count of non-quarterbacks listed Out or Doubtful"""
    pfr={}
    for r in csv.DictReader(open(os.path.join(DATA,'players_all.csv'),encoding='utf-8')):
        if r.get('gsis_id') and r.get('pfr_id'): pfr[r['gsis_id'].strip()]=r['pfr_id'].strip()
    hist=defaultdict(list)                                    # pfr id -> [(season, week, share)]
    for f in sorted(os.listdir(DATA)):
        if not re.fullmatch(r'snaps\d\d\.csv',f): continue
        for r in csv.DictReader(open(os.path.join(DATA,f),encoding='utf-8')):
            if r.get('game_type')!='REG' or not r.get('pfr_player_id'): continue
            hist[r['pfr_player_id']].append((int(r['season']),int(r['week']),min(1.0,fnum(r['offense_pct'],0.0)+fnum(r['defense_pct'],0.0))))
    for v in hist.values(): v.sort()
    def share(p,s,w):
        L=hist.get(p)
        if not L: return 0.0
        i=0
        while i<len(L) and (L[i][0],L[i][1])<(s,w): i+=1
        prev=L[max(0,i-3):i]
        return statistics.mean(x[2] for x in prev) if prev else 0.0
    out=defaultdict(float); seen=set()
    for f in sorted(os.listdir(DATA)):
        if not re.fullmatch(r'injuries\d\d\.csv',f): continue
        for r in csv.DictReader(open(os.path.join(DATA,f),encoding='utf-8')):
            if r.get('game_type')!='REG' or r.get('report_status') not in ('Out','Doubtful') or r.get('position')=='QB': continue
            k=(int(r['season']),int(r['week']),r['team'],r.get('gsis_id'))
            if k in seen: continue
            seen.add(k); p=pfr.get((r.get('gsis_id') or '').strip())
            if p: out[k[:3]]+=share(p,k[0],k[1])
    return out

def build(rows,GA):
    tz=team_tz(); OUTS=starters_out(GA)
    # last season's coach and most frequent starter per team, from the schedule
    coach={}; qbs=defaultdict(Counter)
    for r in sorted(GA.values(),key=lambda r:(int(r['season']),int(r['week']))):
        if r['game_type']!='REG': continue
        s=int(r['season'])
        for side in ('home','away'):
            t=rel(r[side+'_team']); coach[(s,t)]=r.get(side+'_coach')
            if r.get(side+'_qb_id'): qbs[(s,t)][r[side+'_qb_id']]+=1
    TOM=defaultdict(list)                                     # (season, team) -> [(week, turnover margin)]
    by=defaultdict(dict)
    for t in engine2.TW: by[t['gid']][t['team']]=t
    for gid,d in by.items():
        if len(d)!=2: continue
        a,b=d.values()
        TOM[(a['season'],a['team'])].append((a['week'],b['to']-a['to'])); TOM[(b['season'],b['team'])].append((b['week'],a['to']-b['to']))
    def recent_to(s,t,w):
        L=[m for wk,m in sorted(TOM.get((s,t),[])) if wk<w][-3:]
        return statistics.mean(L) if L else 0.0
    X={c['id']:[] for c in CANDIDATES}
    for x in rows:
        r=GA[x['gid']]; s,w=x['s'],x['w']; h,a=r['home_team'],r['away_team']; H,A=rel(h),rel(a); neutral=r['location']!='Home'
        new_c=lambda T:1.0 if coach.get((s-1,T)) and r.get(('home' if T==H else 'away')+'_coach')!=coach.get((s-1,T)) else 0.0
        def new_q(T,side):
            last=qbs.get((s-1,T)); me=r.get(side+'_qb_id')
            return 1.0 if w<=4 and last and me and me!=last.most_common(1)[0][0] and qbs[(s,T)][me]>=max(qbs[(s,T)].values()) else 0.0
        hr,ar=fnum(r.get('home_rest')),fnum(r.get('away_rest'))
        X['early'].append(x['m'] if 2<=w<=4 else 0.0)
        X['starters_out'].append(OUTS.get((s,w,a),0.0)-OUTS.get((s,w,h),0.0))
        X['new_coach'].append(new_c(A)-new_c(H))
        X['new_qb'].append(new_q(A,'away')-new_q(H,'home'))
        X['short_week'].append(x['m'] if hr is not None and ar is not None and hr<=5 and ar<=5 else 0.0)
        X['body_clock'].append(1.0 if not neutral and tz.get(A) in WEST and tz.get(H) in EAST and (r.get('gametime') or '99')<'14:00' else 0.0)
        X['primetime'].append(1.0 if not neutral and (r.get('gametime') or '')>='19:00' else 0.0)
        X['divisional'].append(x['m'] if r.get('div_game')=='1' else 0.0)
        X['to_luck'].append(recent_to(s,A,w)-recent_to(s,H,w))
    return {k:np.array(v,dtype=float) for k,v in X.items()}

# ------------------------------------------------------------------ the held-out test
def ols(x,y):
    A=np.column_stack([np.ones_like(x),x]); c,*_=np.linalg.lstsq(A,y,rcond=None); return c
def test(x,res,S,W,mkt,seasons):
    """walk-forward: each test season is corrected only with a fit on the seasons before it"""
    gain=np.full(len(res),np.nan); by={}
    for s in seasons:
        tr=S<s; te=S==s
        if tr.sum()<200 or te.sum()<32: continue
        a0=res[tr].mean(); a,b=ols(x[tr],res[tr])
        g=np.abs(res[te]-a0)-np.abs(res[te]-a-b*x[te]); gain[te]=g; by[int(s)]=round(float(g.mean()),3)
    m=~np.isnan(gain); g=gain[m]; blk=(S[m]*100+W[m]).astype(int); ub=np.unique(blk)
    sums=np.array([g[blk==u].sum() for u in ub]); cnts=np.array([(blk==u).sum() for u in ub])
    rng=np.random.default_rng(SEED); idx=rng.integers(0,len(ub),size=(B,len(ub)))
    boot=sums[idx].sum(1)/cnts[idx].sum(1); p=float((np.sum(boot<=0)+1)/(B+1))
    tm=(S<=2025)&(S>=2019); beta=ols(x[tm],res[tm])[1]
    k=(S<=2025)&(S>=2019)&~np.isnan(mkt); bm=ols(x[k],mkt[k])[1]
    touched=m&(x!=0)
    return dict(gain=round(float(g.mean()),3),gain_touched=round(float(gain[touched].mean()),3) if touched.any() else None,
                n_test=int(m.sum()),n_touched=int(touched.sum()),by_season=by,pos=sum(1 for v in by.values() if v>0),
                p=round(p,4),beta=round(float(beta),3),market=round(float(bm),3),n_flag=int((x!=0).sum()))

def holm(ps):
    o=sorted(range(len(ps)),key=lambda i:ps[i]); adj=[0.0]*len(ps); run=0.0
    for j,i in enumerate(o): run=max(run,min(1.0,(len(ps)-j)*ps[i])); adj[i]=round(run,4)
    return adj

def proposal_md(c,today):
    by=', '.join('%d: %+.3f'%(k,v) for k,v in sorted(c['by_season'].items()))
    return ('## Blind spot: %s\n\n%s\n\n**Why it might matter.** %s\n\n**Evidence (held out).** Fitted on earlier seasons only and scored on later seasons it '
            'never saw, it cuts GridIron\'s average margin miss by %.3f points over %d games (%.3f on the %d games it touches), better in %d of %d seasons '
            '(%s). Week-blocked bootstrap p = %.4f; after Holm correction for %d candidates, %.4f. Fitted on 2019-25: %+.3f points per unit. The closing '
            'line moves %+.3f points per unit toward it.\n\n**Where it stands.** %s\n\n**What approving it means.** Adding it to the game model as a zero-weight '
            'factor the learning loop then sizes and re-tests every week, under the usual checks and rollback. Nothing changes until then.\n\n'
            '_Found by pipeline/blindspots.py on %s._\n')%(c['name'],c['what'],c['why'],c['gain'],c['n_test'],c['gain_touched'] or 0,c['n_touched'],c['pos'],
            len(c['by_season']),by,c['p'],len(CANDIDATES),c['p_adj'],c['beta'],c['market'],c['rel'],today)

def main():
    C=gm.load_champion(); book=gm.Book(); GA=book.rows
    rows=[x for x in gm.track_rows(C,book=book) if x['vs'] is not None]
    S=np.array([x['s'] for x in rows]); W=np.array([x['w'] for x in rows])
    res=np.array([x['am']-x['m'] for x in rows]); mkt=np.array([x['vs']-x['m'] for x in rows])
    X=build(rows,GA); seasons=sorted({int(s) for s in S if s>=FIRST_TEST})
    out=[]
    for c in CANDIDATES:
        out.append({**c,**test(X[c['id']],res,S,W,mkt,seasons)})
    for c,pa in zip(out,holm([c['p'] for c in out])): c['p_adj']=pa
    for c in out:
        n=len(c['by_season'])
        c['verdict']=('blind_spot' if c['p_adj']<ALPHA and c['gain']>=MIN_GAIN and c['pos']>=math.ceil(MOST*n) else
                      'watch' if c['p']<WATCH and c['gain']>0 else 'clear')
    try: prev=json.load(open(OUT,encoding='utf-8'))
    except (OSError,ValueError): prev={}
    # Only the daily lane files proposals (it commits pipeline/learning and opens the issues); any other run keeps the
    # memory of what was proposed as it found it, so a live refresh can neither file nor lose a proposal.
    propose='--propose' in sys.argv
    proposed=dict(prev.get('proposed') or {}); today=datetime.date.today().isoformat(); new=[]
    os.makedirs(NEWP,exist_ok=True)
    for c in out:
        if propose and c['verdict']=='blind_spot' and c['id'] not in proposed:
            open(os.path.join(NEWP,'blindspot_%s.md'%c['id']),'w',encoding='utf-8').write(proposal_md(c,today)); proposed[c['id']]=today; new.append(c['id'])
        c['proposed']=proposed.get(c['id'])
    # the reviewed 2026 calls: which candidates were live in each game, and which way they pointed
    ix={x['gid']:i for i,x in enumerate(rows)}; flags={}
    for x in rows:
        if x['s']<max(S): continue
        i=ix[x['gid']]; f={}
        for c in CANDIDATES:
            v=float(X[c['id']][i])
            if v and c['form']=='shift': f[c['id']]=round(v,2)
        flags[x['gid']]=f
    R=dict(asof=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),n=len(rows),seasons=[int(S.min()),int(S.max())],
           test_seasons=seasons,method=dict(alpha=ALPHA,watch=WATCH,min_gain=MIN_GAIN,most=MOST,bootstrap=B,correction='Holm'),
           sd=round(float(res.std()),2),candidates=out,proposed=proposed,proposing=propose,flags=flags,
           counts={v:sum(1 for c in out if c['verdict']==v) for v in ('blind_spot','watch','clear')})
    json.dump(R,open(OUT+'.part','w',encoding='utf-8'),indent=1); os.replace(OUT+'.part',OUT)
    D=json.load(open(GI,encoding='utf-8')); D['blindspots']=R; json.dump(D,open(GI,'w'),separators=(',',':'))
    print('blind spots: %d candidates over %d games (held out %s-%s): %d blind spot, %d watch, %d clear%s'%(
        len(out),len(rows),seasons[0],seasons[-1],R['counts']['blind_spot'],R['counts']['watch'],R['counts']['clear'],
        ('; new proposal: '+', '.join(new)) if new else ''))
    for c in sorted(out,key=lambda c:c['p']):
        print('  %-13s %-10s gain %+.3f (touched %+.3f, n=%d) seasons +%d/%d p=%.4f adj=%.4f beta=%+.3f market=%+.3f'%(
            c['id'],c['verdict'],c['gain'],c['gain_touched'] or 0,c['n_touched'],c['pos'],len(c['by_season']),c['p'],c['p_adj'],c['beta'],c['market']))

if __name__=='__main__': main()
