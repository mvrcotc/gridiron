"""Post-game review: every frozen GridIron call that has a final score, taken apart honestly.

For each game it answers four questions, using only the model's own numbers and nflverse's box score:

  1. What did GridIron consider?  Each side's expected yards, touchdowns and turnovers from the ratings in force that
     week, the home edge, the backup-quarterback term, the blend with Vegas, and the factors it tested and gave no weight.
  2. What swung the game?         The miss (actual margin minus the frozen call) split into parts that add up exactly:
       yardage    -- yards gained beyond or short of expectation, in points at the season's own conversion
       finishing  -- touchdowns beyond what the yards implied
       turnovers  -- giveaways and takeaways beyond expectation
       non-offense-- points the box score does not explain: field goals, return and defensive scores, safeties
       blend      -- how far GridIron's full rating blend sat from its yardage path alone (a property of the model)
  3. Chance or misjudgement?      Each part is classed by MEASURED repeatability: how well a team's average on that stat
     in one half of a season predicts the other half, over every team-season 2019-25. A part that barely repeats
     (turnovers, non-offensive scoring) is chance no model sees coming; one that repeats (yardage, finishing) means the
     teams played differently from how GridIron rated them.
  4. What did it learn?           The same matchup re-predicted with the ratings after that week against the ratings
     before it -- how far the game actually moved GridIron's view of these two teams.

It changes no weight. Learning a weight is the learning loop's job (learn.py); finding a factor the model does not
have is blindspots.py's. This stage only explains, and its numbers are rebuilt independently by the audit.

   python3 pipeline/review.py"""
import os, sys, csv, json, statistics, datetime
from collections import defaultdict
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0,HERE)
import engine2, gamemodel as gm
from engine2 import DATA

GI=os.path.join(DATA,'gi2.json')
TRAIT,CHANCE=0.35,0.25          # split-half r: at or above TRAIT a stat is a team trait, below CHANCE it is chance
PARTS=('yards','finish','turnovers','nonoff')
ESPN={'LA':'LAR','WAS':'WSH'}

def persistence(first=2019,last=2025):
    """split-half reliability of each part's stat across team-seasons: odd games against even games, in week order.

    Points come from the schedule with relocated teams' codes mapped (the team-week files call the 2019 Raiders LV, the
    schedule OAK), and the box-score conversion is refitted here on those points -- engine2 matches the raw codes, which
    hands the 2019 Raiders their opponents' score at home."""
    SC={r['game_id']:r for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'),encoding='utf-8')) if r['game_type']=='REG' and r['home_score']}
    by=defaultdict(dict)
    for t in engine2.TW:
        r=SC.get(t['gid'])
        if not r or t['plays']<=0: continue
        home=gm.REL.get(r['home_team'],r['home_team'])==t['team']
        by[(t['season'],t['gid'])][t['team']]=dict(t,pts=float(r['home_score'] if home else r['away_score']))
    fits={}
    def conv(s):
        """the season before's fit (a season's own when none is earlier), as engine2.conv_for -- on the right points"""
        if s not in fits:
            have=sorted({k[0] for k,d in by.items() if len(d)==2}); prev=[x for x in have if x<s]; f=prev[-1] if prev else s
            R=[t for k,d in by.items() if k[0]==f and len(d)==2 for t in d.values()]
            fits[s]=[float(x) for x in np.linalg.lstsq(np.array([[1.0,t['yds'],t['td'],t['to']] for t in R]),np.array([t['pts'] for t in R]),rcond=None)[0]]
        return fits[s]
    G=defaultdict(list)
    for (s,gid),d in by.items():
        if len(d)!=2 or not first<=s<=last: continue
        cv=conv(s); box=lambda t:cv[0]+cv[1]*t['yds']+cv[2]*t['td']+cv[3]*t['to']
        a,b=d.values()
        for me,op in ((a,b),(b,a)):
            G[(s,me['team'])].append(dict(w=me['week'],yards=me['yds']-op['yds'],finish=me['td']/me['yds']*100 if me['yds'] else 0.0,
                                          turnovers=op['to']-me['to'],nonoff=(me['pts']-box(me))-(op['pts']-box(op))))
    out={}
    for k in PARTS:
        x=[];y=[]
        for L in G.values():
            if len(L)<14: continue
            L=sorted(L,key=lambda g:g['w']); x.append(statistics.mean(g[k] for g in L[0::2])); y.append(statistics.mean(g[k] for g in L[1::2]))
        r=statistics.correlation(x,y)
        out[k]=dict(r=round(r,3),n=len(x),cls='trait' if r>=TRAIT else 'chance' if r<CHANCE else 'mixed')
    return out

def side(snap,P,s,tm,op):
    """one side's expected box score and points from a ratings snapshot -- engine2.run's own per-game formula"""
    L=engine2.LG.get(s) or snap['L']; R=lambda k,t:snap[k].rate(t)     # run()'s loop uses LG[s], not the _lg_for fallback
    ypp=L['ypp']*R('oY',tm)*R('dY',op); pl=L['plays']*R('oP',tm)*R('dP',op); yd=ypp*pl
    td=yd*L['tdpy']*R('oT',tm)*R('dT',op); to=pl*L['topp']*R('oO',tm)*R('dO',op)
    pB=engine2.pts_box(yd,td,to,s); pE=L['ppg']+(R('oE',tm)+R('dE',op))*pl; pS=L['ppg']+R('oS',tm)+R('dS',op)
    return dict(yd=yd,td=td,to=to,p=P['wB']*pB+P['wE']*pE+P['wS']*pS)

_SNAP={}
def snapshot(P,s,w):
    """the ratings as they stood at the start of week w (so after every game before it)"""
    key=(tuple(round(float(P[k]),8) for k in gm.RATING_KEYS),s,w)
    if key not in _SNAP: _SNAP[key]=engine2.run({**P},ret_state=True,until=(s,w))[1]
    return _SNAP[key]

def review_game(e,r,o,box):
    """o: engine2.run's own row for the game, so the expectations are exactly the ones the prediction was built on"""
    s,w=int(r['season']),int(r['week']); h,a=r['home_team'],r['away_team']; neutral=r['location']!='Home'
    act={t['team']:t for t in box}
    if h not in act or a not in act or not o: return None
    eh,ea=o['hd'],o['ad']
    cv=engine2.conv_for(s); A=act[h],act[a]
    gmg=e['call']['ph']-e['call']['pa']; am=e['final']['h']-e['final']['a']; miss=am-gmg
    # Yardage owns the touchdowns its extra yards would normally bring at that side's expected rate per yard; finishing
    # is only the touchdowns beyond that rate. Otherwise the conversion's basis -- a yard is worth little once touchdowns
    # are counted -- hands "moved the ball at will" to "finished unusually well". The two still sum to the plain
    # yards-plus-touchdowns difference, since rate*expected yards is the expected touchdowns.
    def sd(ex,ac):
        rate=ex['td']/ex['yd'] if ex['yd'] else 0.0; dy=ac['yds']-ex['yd']
        return cv[1]*dy+cv[2]*rate*dy, cv[2]*(ac['td']-rate*ac['yds']), cv[3]*(ac['to']-ex['to'])
    yh,fh,th=sd(eh,A[0]); ya,fa,ta=sd(ea,A[1])
    parts=dict(yards=yh-ya,finish=fh-fa,turnovers=th-ta)
    ab=sum(cv[i]*(A[0][k]-A[1][k]) for i,k in ((1,'yds'),(2,'td'),(3,'to')))   # the margin the box score implies
    eb=sum(cv[i]*(eh[k]-ea[k]) for i,k in ((1,'yd'),(2,'td'),(3,'to')))
    parts['nonoff']=am-ab; parts['blend']=eb-gmg                          # yards+finish+turnovers == ab-eb, so the five sum to miss
    right=(gmg>0)==(am>0) if am else None
    return dict(h=ESPN.get(h,h),a=ESPN.get(a,a),s=s,w=w,gid=r['game_id'],right=right,call=round(gmg,2),final=am,miss=round(miss,2),
                parts={k:round(v,2) for k,v in parts.items()},neutral=neutral,
                stats={'h':dict(exp={k:round(eh[k],2) for k in ('yd','td','to')},act=dict(yd=A[0]['yds'],td=A[0]['td'],to=A[0]['to'])),
                       'a':dict(exp={k:round(ea[k],2) for k in ('yd','td','to')},act=dict(yd=A[1]['yds'],td=A[1]['td'],to=A[1]['to']))})

def classify(g,per):
    """chance share of the parts that pushed the result away from the call, and the verdict it implies"""
    m=g['miss']; push={k:v for k,v in g['parts'].items() if k!='blend' and v*m>0}
    tot=sum(abs(v) for v in push.values())
    w={'chance':1.0,'mixed':0.5,'trait':0.0}
    share=sum(abs(v)*w[per[k]['cls']] for k,v in push.items())/tot if tot else 0.0
    g['chance_share']=round(share,3); g['close']=abs(g['final'])<=3
    g['verdict']='right' if g['right'] else 'tie' if g['right'] is None else ('chance' if share>=0.6 else 'misjudged' if share<=0.4 else 'both')
    g['top']=max(push,key=lambda k:abs(push[k])) if push else None

def learned(g,P):
    """the same matchup on the ratings before and after the game's week -- ratings only, both sides alike"""
    s,w=g['s'],g['w']; H,A=g['_h'],g['_a']; hv=0.0 if g['neutral'] else P['hfa']
    m=lambda snap:side(snap,P,s,H,A)['p']-side(snap,P,s,A,H)['p']+hv
    b,af=m(snapshot(P,s,w)),m(snapshot(P,s,w+1))
    g['learned']=dict(before=round(b,2),after=round(af,2),shift=round(af-b,2))

def considered(g,e,r,P,book):
    f=book.features(r)
    g['considered']=dict(hfa=0.0 if g['neutral'] else P['hfa'],qb=round(P['qb']*f['qb'],2),blend=P['blend'],bsp=e['call'].get('bsp'),
                         zero=[k for k in ('venue','rest','wx_dome','wx_wind','wx_cold','ref') if not P.get(k)])

def main():
    D=json.load(open(GI,encoding='utf-8')); E=(D.get('ledger') or {}).get('entries') or {}
    C=gm.load_champion(); book=gm.Book(); per=persistence()
    GA={str(r.get('espn') or '').split('.')[0]:r for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'),encoding='utf-8')) if r.get('espn')}
    BOX=defaultdict(list)
    for t in engine2.TW: BOX[t['gid']].append(t)
    out={}; skipped=[]; RUNS={}
    for gid,e in E.items():
        if not (e.get('frozen') and e.get('final') and (e.get('call') or {}).get('ph') is not None): continue
        r=GA.get(gid)
        if not r: skipped.append('%s@%s not in the schedule'%(e.get('a'),e.get('h'))); continue
        v=((e['call'].get('v') or {}).get('pregame')) or gm.in_force(C,int(r['season']),int(r['week']))['v']
        P=gm.version(C,v)['params']
        if v not in RUNS: RUNS[v]={x['gid']:x for x in engine2.run({**P})}
        g=review_game(e,r,RUNS[v].get(r['game_id']),BOX.get(r['game_id'],[]))
        if not g: skipped.append('%s@%s week %s: nflverse has no box score yet'%(e['a'],e['h'],r['week'])); continue
        g['_h'],g['_a']=r['home_team'],r['away_team']
        classify(g,per); learned(g,P); considered(g,e,r,P,book); g['v']=v
        del g['_h'],g['_a']; out[gid]=g
    W=[g for g in out.values() if g['right'] is False]
    summ=dict(reviewed=len(out),right=sum(1 for g in out.values() if g['right']),wrong=len(W),
              verdicts={k:sum(1 for g in W if g['verdict']==k) for k in ('chance','both','misjudged')},close=sum(1 for g in W if g['close']),
              shift=round(statistics.mean(abs(g['learned']['shift']) for g in out.values()),2) if out else None,
              top={k:sum(1 for g in W if g['top']==k) for k in PARTS})
    D['review']=dict(asof=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),persist=per,
                     thresholds=dict(trait=TRAIT,chance=CHANCE),summary=summ,games=out,skipped=skipped)
    json.dump(D,open(GI,'w'),separators=(',',':'))
    print('review: %d calls reviewed, %d wrong (%d mostly chance, %d both, %d misjudged; %d decided by 3 or fewer); ratings moved %.2f pts a game'%(
        summ['reviewed'],summ['wrong'],summ['verdicts']['chance'],summ['verdicts']['both'],summ['verdicts']['misjudged'],summ['close'],summ['shift'] or 0))
    print('  repeatability (split-half r): '+', '.join('%s %+.2f (%s)'%(k,per[k]['r'],per[k]['cls']) for k in PARTS))
    for m in skipped: print('  !! not reviewed: '+m)

if __name__=='__main__': main()
