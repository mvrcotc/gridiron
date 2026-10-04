"""The brain: post-game reviews, the blind-spot scan and the accuracy badge -- every number rebuilt with code written only
for the audit. Box scores come straight from nflverse's team-week files, the points conversion is refitted here, the
repeatability figures are recomputed, the starters-out feature is rebuilt from the raw injury and snap files, and the
walk-forward residuals behind the blind-spot test are rebuilt the way a7 rebuilds the track record. Like a7, the only
pipeline code imported is engine2, for the ratings' own per-game expectations."""
import os, sys, re, csv, json, math, statistics, subprocess
from collections import defaultdict, Counter
import numpy as np
from common import num, rows, DATA, PIPE, ROOT

REL={'STL':'LA','SD':'LAC','OAK':'LV'}    # team-week files use today's codes, the schedule the codes of the day
RK=('kY','cY','kP','cP','kT','cT','kO','cO','kE','cE','kS','cS','decay')
PARTS=('yards','finish','turnovers','nonoff')
def jsr(x): return int(math.floor(x+0.5))          # the page rounds with toFixed (halves up), not Python's half-to-even
def lead(t):
    m=re.match(r'\s*(-?[\d.]+)',t or ''); return float(m.group(1)) if m else None

def box_rows():
    """(season, game_id) -> team -> box score, parsed here from every tw<season>.csv"""
    out=defaultdict(dict)
    for f in sorted(os.listdir(DATA)):
        if not re.fullmatch(r'tw\d{4}\.csv',f): continue
        for r in rows(os.path.join(DATA,f)):
            if r.get('season_type')!='REG': continue
            out[(int(r['season']),r['game_id'])][r['team']]=dict(w=int(r['week']),
                yds=num(r['passing_yards'])+num(r['rushing_yards']),td=num(r['passing_tds'])+num(r['rushing_tds']),
                to=num(r['passing_interceptions'])+num(r['rushing_fumbles_lost'])+num(r['receiving_fumbles_lost'])+num(r['sack_fumbles_lost']),
                plays=num(r['attempts'])+num(r['carries'])+num(r['sacks_suffered']))
    return out

def pbp_rebuild(GA):
    """game_id -> (play-by-play edge, quarterback-value edge), rebuilt from the play-by-play season files with running
    decayed sums -- a different construction from the pipeline's, which re-weights every past game each week"""
    src=open(os.path.join(PIPE,'blindspots.py'),encoding='utf-8').read()
    m=re.search(r"PBP=dict\(decay=([\d.]+),trust=([\d.]+),carry=([\d.]+),qb_trust=([\d.]+),qb_carry=([\d.]+)\)",src)
    d=os.path.join(PIPE,'learning','pbp')
    if not m or not os.path.isdir(d): return {}
    lam,k,carry,qk,qc=(float(x) for x in m.groups())
    SR=defaultdict(dict); QB=defaultdict(list); first=None
    for f in sorted(os.listdir(d)):
        if not f.endswith('.csv'): continue
        first=int(f[:4]) if first is None else min(first,int(f[:4]))
        for r in rows(os.path.join(d,f)):
            if r['kind']=='T': SR[r['game_id']][r['team']]=float(r['sr'])
            else: QB[(r['game_id'],r['team'])].append((r['qb'],float(r['epa']),float(r['w'])))
    o=defaultdict(lambda:[0.0,0.0]); df=defaultdict(lambda:[0.0,0.0]); po=defaultdict(float); pdf=defaultdict(float)
    qs=defaultdict(lambda:[0.0,0.0]); tw=defaultdict(lambda:defaultdict(float)); past=[]; out={}
    rt=lambda acc,pr:(k*pr+acc[0])/(k+acc[1])
    def qr(q): return qs[q][0]/(qs[q][1]+qk) if q in qs else 0.0
    def tq(tm):
        W=tw.get(tm); den=sum(W.values()) if W else 0.0
        return sum(w*qr(q) for q,w in W.items())/den if den else None
    wk=defaultdict(list)
    for r in GA.values():
        if int(r['season'])>=first: wk[(int(r['season']),int(r['week']))].append(r)
    cur=None
    for (s,w) in sorted(wk):
        if s!=cur:
            if cur is not None:
                for tm in set(o)|set(po): po[tm]=carry*rt(o[tm],po[tm]); pdf[tm]=carry*rt(df[tm],pdf[tm])
                for q in qs: qs[q][0]*=qc; qs[q][1]*=qc
            o.clear(); df.clear(); tw.clear(); cur=s
            prev=[v for ss,v in past if ss<s]
            base=statistics.mean(prev) if prev else statistics.mean([v for g,dd in SR.items() if g.startswith('%d_'%s) for v in dd.values()] or [0.0])
        for r in wk[(s,w)]:
            h,a=REL.get(r['home_team'],r['home_team']),REL.get(r['away_team'],r['away_team'])
            qv=[]
            for side,tm in (('home',h),('away',a)):
                st=r.get(side+'_qb_id'); t0=tq(tm); qv.append(qr(st)-t0 if st and t0 is not None else 0.0)
            out[r['game_id']]=((rt(o[h],po[h])+rt(df[a],pdf[a]))-(rt(o[a],po[a])+rt(df[h],pdf[h])),qv[0]-qv[1])
        upd=[]
        for r in wk[(s,w)]:
            g=SR.get(r['game_id']) or {}; h,a=REL.get(r['home_team'],r['home_team']),REL.get(r['away_team'],r['away_team'])
            if h not in g or a not in g: continue
            past.extend([(s,g[h]),(s,g[a])])
            oh,dh,oa,da=rt(o[h],po[h]),rt(df[h],pdf[h]),rt(o[a],po[a]),rt(df[a],pdf[a])
            upd.append((o[h],g[h]-base-da)); upd.append((df[a],g[h]-base-oh)); upd.append((o[a],g[a]-base-dh)); upd.append((df[h],g[a]-base-oa))
            for tm in (h,a):
                for q,e,ww in QB.get((r['game_id'],tm),[]): qs[q][0]+=e; qs[q][1]+=ww; tw[tm][q]+=ww
        for acc,v in upd: acc[0]+=v; acc[1]+=1.0
        for acc in list(o.values())+list(df.values()): acc[0]*=lam; acc[1]*=lam      # a week passes
        for W in tw.values():
            for q in W: W[q]*=lam
    return out

def run(A):
    A.section('the brain: reviews, blind spots, accuracy badge'); D=A.D
    RV=D.get('review'); BS=D.get('blindspots'); LG=D.get('ledger') or {}; E=LG.get('entries') or {}
    if not RV or not BS:
        A.check('RV1','The review and blind-spot data exist',['missing from data/gi2.json: '+', '.join(k for k,v in (('review',RV),('blindspots',BS)) if not v)]); return
    sys.path.insert(0,PIPE); import engine2
    GA={r['game_id']:r for r in rows(os.path.join(DATA,'games_all.csv')) if r['game_type']=='REG'}
    BYESPN={str(r.get('espn') or '').split('.')[0]:r for r in GA.values() if r.get('espn')}
    BOX=box_rows()
    CH=json.load(open(os.path.join(PIPE,'champion.json'))); VS={v['v']:v for v in CH['versions']}

    # ---------- RV1: one review per settled frozen call, tied to the ledger's own numbers ----------
    G=RV.get('games') or {}; bad=[]
    for gid,e in E.items():
        if not (e.get('frozen') and e.get('final') and (e.get('call') or {}).get('ph') is not None): continue
        r=BYESPN.get(gid); have=r and len(BOX.get((int(r['season']),r['game_id']),{}))==2
        g=G.get(gid); n='%s@%s'%(e['a'],e['h'])
        if not g:
            if have: bad.append('%s has a frozen call, a final score and a box score but no review'%n)
            continue
        call=e['call']['ph']-e['call']['pa']; am=e['final']['h']-e['final']['a']
        if abs(g['call']-call)>0.006: bad.append('%s review starts from %+.2f, the frozen call is %+.2f'%(n,g['call'],call))
        if g['final']!=am: bad.append('%s review final %+d, ledger %+d'%(n,g['final'],am))
        if abs(g['miss']-(am-call))>0.006: bad.append('%s miss %+.2f, should be %+.2f'%(n,g['miss'],am-call))
        if g['right']!=(((call>0)==(am>0)) if am else None): bad.append('%s marked %s, the call and the result say otherwise'%(n,'right' if g['right'] else 'wrong'))
    for gid in G:
        if not (E.get(gid) or {}).get('frozen'): bad.append('review for %s has no frozen ledger call'%gid)
    A.check('RV1','Every settled frozen call is reviewed, starting from exactly its frozen call and final score',bad,len(G))

    # ---------- RV2: the decomposition, rebuilt from the raw box score and a conversion refitted here ----------
    conv={}
    def conv_for(s):
        if s not in conv:
            prev=sorted({k[0] for k in BOX if k[0]<s and sum(1 for kk in BOX if kk[0]==k[0])>=100})
            fit=prev[-1] if prev else s; X=[];Y=[]
            for (ss,gid),d in BOX.items():
                if ss!=fit or gid not in GA or not GA[gid]['home_score']: continue
                hc=REL.get(GA[gid]['home_team'],GA[gid]['home_team'])
                for t,b in d.items():
                    X.append([1.0,b['yds'],b['td'],b['to']]); Y.append(num(GA[gid]['home_score'] if t==hc else GA[gid]['away_score']))
            conv[s]=np.linalg.lstsq(np.array(X),np.array(Y),rcond=None)[0]
        return conv[s]
    runs={}
    def eng(P):
        key=tuple(P[k] for k in RK)
        if key not in runs: runs[key]={o['gid']:o for o in engine2.run({**P})}
        return runs[key]
    bad=[]; nb=0
    for gid,g in G.items():
        r=GA.get(g['gid']); s=int(r['season']); d=BOX.get((s,g['gid']),{}); P=VS[g['v']]['params']; o=eng(P).get(g['gid'])
        h,a=r['home_team'],r['away_team']
        if len(d)!=2 or not o: bad.append('%s: cannot rebuild (box score or engine row missing)'%g['gid']); continue
        c=conv_for(s); ah,aa=d[h],d[a]; eh,ea=o['hd'],o['ad']
        def part(ex,ac):
            rate=ex['td']/ex['yd'] if ex['yd'] else 0.0; dy=ac['yds']-ex['yd']
            return c[1]*dy+c[2]*rate*dy, c[2]*(ac['td']-rate*ac['yds']), c[3]*(ac['to']-ex['to'])
        ph,pa=part(eh,ah),part(ea,aa); am=g['final']
        ab=sum(c[i]*(ah[k]-aa[k]) for i,k in ((1,'yds'),(2,'td'),(3,'to'))); eb=sum(c[i]*(eh[k]-ea[k]) for i,k in ((1,'yd'),(2,'td'),(3,'to')))
        want=dict(yards=ph[0]-pa[0],finish=ph[1]-pa[1],turnovers=ph[2]-pa[2],nonoff=am-ab,blend=eb-g['call'])
        for k,v in want.items():
            if abs(g['parts'].get(k,1e9)-v)>0.02: bad.append('%s %s %+.2f, rebuilt %+.2f'%(g['gid'],k,g['parts'].get(k,float('nan')),v))
        for sd,act in (('h',ah),('a',aa)):
            st=g['stats'][sd]['act']
            if (st['yd'],st['td'],st['to'])!=(act['yds'],act['td'],act['to']): bad.append('%s %s box %s, nflverse %s'%(g['gid'],sd,st,act))
        if abs(sum(g['parts'].values())-g['miss'])>0.02: bad.append('%s parts sum to %+.2f, the miss is %+.2f'%(g['gid'],sum(g['parts'].values()),g['miss']))
        nb+=1
    A.check('RV2','Each miss splits into yardage, finishing, turnovers, other scores and blend exactly as rebuilt from nflverse\'s box score, and the parts add up',bad,nb)

    # ---------- RV3: what repeats -- split-half reliability, recomputed ----------
    per=defaultdict(list)
    for (s,gid),d in BOX.items():
        if not 2019<=s<=2025 or len(d)!=2 or gid not in GA or not GA[gid]['home_score']: continue
        c=conv_for(s); r=GA[gid]; hc=REL.get(r['home_team'],r['home_team']); t1,t2=d.keys()
        for me,op in ((t1,t2),(t2,t1)):
            m,o=d[me],d[op]; pm=num(r['home_score'] if me==hc else r['away_score']); po=num(r['away_score'] if me==hc else r['home_score'])
            bx=lambda b:c[0]+c[1]*b['yds']+c[2]*b['td']+c[3]*b['to']
            per[(s,me)].append(dict(w=m['w'],yards=m['yds']-o['yds'],finish=m['td']/m['yds']*100 if m['yds'] else 0.0,turnovers=o['to']-m['to'],nonoff=(pm-bx(m))-(po-bx(o))))
    bad=[]; Pst=RV.get('persist') or {}; th=RV.get('thresholds') or {}
    for k in PARTS:
        x=[];y=[]
        for L in per.values():
            if len(L)<14: continue
            L=sorted(L,key=lambda z:z['w']); x.append(statistics.mean(z[k] for z in L[0::2])); y.append(statistics.mean(z[k] for z in L[1::2]))
        rr=statistics.correlation(x,y); p=Pst.get(k) or {}
        if abs(num(p.get('r'),9)-rr)>0.005 or p.get('n')!=len(x): bad.append('%s r %s over %s, rebuilt %.3f over %d'%(k,p.get('r'),p.get('n'),rr,len(x)))
        cls='trait' if rr>=th.get('trait',0.35) else 'chance' if rr<th.get('chance',0.25) else 'mixed'
        if p.get('cls')!=cls: bad.append('%s classed %s, its r says %s'%(k,p.get('cls'),cls))
    A.check('RV3','What repeats: split-half reliability of each part over every team-season 2019-25, and the chance/trait class it implies',bad,len(PARTS))

    # ---------- RV4: verdicts follow the stated rule ----------
    bad=[]; w8={'chance':1.0,'mixed':0.5,'trait':0.0}
    for gid,g in G.items():
        push={k:v for k,v in g['parts'].items() if k!='blend' and v*g['miss']>0}; tot=sum(abs(v) for v in push.values())
        sh=sum(abs(v)*w8[Pst[k]['cls']] for k,v in push.items())/tot if tot else 0.0
        vd='right' if g['right'] else 'tie' if g['right'] is None else ('chance' if sh>=0.6 else 'misjudged' if sh<=0.4 else 'both')
        if abs(g['chance_share']-sh)>0.002 or g['verdict']!=vd: bad.append('%s verdict %s (chance share %.3f), rule gives %s (%.3f)'%(gid,g['verdict'],g['chance_share'],vd,sh))
        if g['close']!=(abs(g['final'])<=3): bad.append('%s close-game flag wrong'%gid)
    S=RV.get('summary') or {}; W=[g for g in G.values() if g['right'] is False]
    want=dict(reviewed=len(G),right=sum(1 for g in G.values() if g['right']),wrong=len(W))
    for k,v in want.items():
        if S.get(k)!=v: bad.append('summary %s %s, recount %s'%(k,S.get(k),v))
    for k in ('chance','both','misjudged'):
        if (S.get('verdicts') or {}).get(k)!=sum(1 for g in W if g['verdict']==k): bad.append('summary verdict count for %s is off'%k)
    A.check('RV4','Each wrong call\'s verdict -- mostly chance, misjudged, or both -- follows the published rule from its parts',bad,len(G))

    # ---------- RV5: what it learned is the engine's own before-and-after ----------
    bad=[]
    for gid,g in G.items():
        o=eng(VS[g['v']]['params']).get(g['gid'])
        if o and abs(g['learned']['before']-o['margin'])>0.006: bad.append('%s rematch before %+.2f, the engine had %+.2f for this game'%(gid,g['learned']['before'],o['margin']))
        if abs(g['learned']['shift']-(g['learned']['after']-g['learned']['before']))>0.011: bad.append('%s shift does not equal after minus before'%gid)
    if G and abs(num(S.get('shift'))-statistics.mean(abs(g['learned']['shift']) for g in G.values()))>0.006: bad.append('summary rating shift %s does not recompute'%S.get('shift'))
    A.check('RV5','"What it learned" starts from the ratings\' own margin for the game, and the shift and its average recompute',bad,len(G))

    # ---------- BS1: blind-spot verdicts, the multiple-testing correction and proposals ----------
    C=BS.get('candidates') or []; M=BS.get('method') or {}; bad=[]
    o=sorted(range(len(C)),key=lambda i:C[i]['p']); runmax=0.0; adj={}
    for j,i in enumerate(o): runmax=max(runmax,min(1.0,(len(C)-j)*C[i]['p'])); adj[i]=runmax
    for i,c in enumerate(C):
        if abs(c['p_adj']-adj[i])>0.0002: bad.append('%s corrected p %s, Holm gives %.4f'%(c['id'],c['p_adj'],adj[i]))
        n=len(c['by_season']); pos=sum(1 for v in c['by_season'].values() if v>0)
        vd=('blind_spot' if adj[i]<M['alpha'] and c['gain']>=M['min_gain'] and pos>=math.ceil(M['most']*n) else 'watch' if c['p']<M['watch'] and c['gain']>0 else 'clear')
        if c['verdict']!=vd or c['pos']!=pos: bad.append('%s verdict %s, its numbers say %s'%(c['id'],c['verdict'],vd))
        if BS.get('proposing') and c['verdict']=='blind_spot' and c['id'] not in (BS.get('proposed') or {}): bad.append('%s is a blind spot but was never proposed to the owner'%c['id'])
    for v in ('blind_spot','watch','clear'):
        if (BS.get('counts') or {}).get(v)!=sum(1 for c in C if c['verdict']==v): bad.append('count of %s is off'%v)
    A.check('BS1','Blind-spot verdicts follow the stated bar, the Holm correction recomputes, and every blind spot was proposed',bad,len(C))

    # ---------- BS2: starters ruled out, rebuilt from the raw injury and snap files ----------
    pfr={r['gsis_id'].strip():r['pfr_id'].strip() for r in rows(os.path.join(DATA,'players_all.csv')) if r.get('gsis_id') and r.get('pfr_id')}
    snaps=defaultdict(list)
    for f in sorted(os.listdir(DATA)):
        if re.fullmatch(r'snaps\d\d\.csv',f):
            for r in rows(os.path.join(DATA,f)):
                if r.get('game_type')=='REG' and r.get('pfr_player_id'):
                    snaps[r['pfr_player_id']].append((int(r['season']),int(r['week']),min(1.0,num(r['offense_pct'])+num(r['defense_pct']))))
    for v in snaps.values(): v.sort()
    OUT=defaultdict(float); seen=set()
    for f in sorted(os.listdir(DATA)):
        if not re.fullmatch(r'injuries\d\d\.csv',f): continue
        for r in rows(os.path.join(DATA,f)):
            if r.get('game_type')!='REG' or r.get('report_status') not in ('Out','Doubtful') or r.get('position')=='QB': continue
            k=(int(r['season']),int(r['week']),r['team'],r.get('gsis_id'))
            if k in seen: continue
            seen.add(k); L=snaps.get(pfr.get((r.get('gsis_id') or '').strip()),[])
            prev=[x[2] for x in L if (x[0],x[1])<k[:2]][-3:]
            OUT[k[:3]]+=statistics.mean(prev) if prev else 0.0
    bad=[]; FL=BS.get('flags') or {}
    for gidx,f in FL.items():
        r=GA.get(gidx)
        if not r: bad.append('flagged game %s is not on the schedule'%gidx); continue
        s,w=int(r['season']),int(r['week']); x=OUT.get((s,w,r['away_team']),0.0)-OUT.get((s,w,r['home_team']),0.0)
        if abs(f.get('starters_out',0.0)-round(x,2))>0.011: bad.append('%s starters out %s, rebuilt %+.2f'%(gidx,f.get('starters_out',0.0),x))
    A.check('BS2','Starters ruled out (snap-weighted, quarterbacks aside) rebuilt from nflverse\'s injury reports and snap counts for every game shown',bad,len(FL))

    # ---------- BS3: the held-out test itself, rebuilt for every candidate not cleared, plus schedule-only ones ----------
    starts=defaultdict(Counter); weeks=defaultdict(list); G2=[]
    for r in GA.values(): weeks[(int(r['season']),int(r['week']))].append(r)
    def force(s,w):
        ok=[v for v in sorted(VS.values(),key=lambda v:v['v']) if v['cutoff'][0]*100+v['cutoff'][1]<s*100+w]
        return ok[-1] if ok else VS[min(VS)]
    zero_ok=True
    for (s,w) in sorted(weeks):
        for r in weeks[(s,w)]:
            if s<2019 or not r['home_score'] or not r['spread_line']: continue
            P=force(s,w)['params']; o2=eng({**P}).get(r['game_id'])
            if not o2: continue
            if any(P.get(k) for k in ('venue','rest','wx_dome','wx_wind','wx_cold','ref')): zero_ok=False
            bk=lambda t,q:int(bool(starts[(s,t)] and q and q!=starts[(s,t)].most_common(1)[0][0]))
            m=o2['margin']+P['qb']*(bk(r['away_team'],r['away_qb_id'])-bk(r['home_team'],r['home_qb_id']))
            G2.append(dict(s=s,w=w,gid=r['game_id'],m=m,res=num(r['home_score'])-num(r['away_score'])-m,r=r))
        for r in weeks[(s,w)]:
            if not r['home_score']: continue
            if r['home_qb_id']: starts[(s,r['home_team'])][r['home_qb_id']]+=1
            if r['away_qb_id']: starts[(s,r['away_team'])][r['away_qb_id']]+=1
    PBF=pbp_rebuild(GA)
    feats={'starters_out':lambda x:OUT.get((x['s'],x['w'],x['r']['away_team']),0.0)-OUT.get((x['s'],x['w'],x['r']['home_team']),0.0),
           'pbp':lambda x:PBF.get(x['gid'],(0.0,0.0))[0],
           'qb_value':lambda x:PBF.get(x['gid'],(0.0,0.0))[1],
           'early':lambda x:x['m'] if 2<=x['w']<=4 else 0.0,
           'divisional':lambda x:x['m'] if x['r'].get('div_game')=='1' else 0.0,
           'short_week':lambda x:x['m'] if num(x['r'].get('home_rest'),9)<=5 and num(x['r'].get('away_rest'),9)<=5 else 0.0,
           'primetime':lambda x:1.0 if x['r']['location']=='Home' and (x['r'].get('gametime') or '')>='19:00' else 0.0}
    bad=[] if zero_ok else ['a weight version in force has a non-zero venue/rest/weather/referee weight; this rebuild models only home edge and backup QB']
    for gidx,f in (BS.get('flags') or {}).items():          # the play-by-play values carried into each reviewed game
        for i,cid in ((0,'pbp'),(1,'qb_value')):
            want=round(PBF.get(gidx,(0.0,0.0))[i],2)
            if abs(num(f.get(cid,0.0))-want)>0.011: bad.append('%s %s %s, rebuilt %+.2f'%(gidx,cid,f.get(cid,0.0),want))
    Ss=np.array([x['s'] for x in G2]); Rs=np.array([x['res'] for x in G2]); nchk=0
    for c in C:
        if c['id'] not in feats:
            if c['verdict']!='clear': bad.append('%s is %s but the audit has no independent rebuild of its feature'%(c['id'],c['verdict']))
            continue
        X=np.array([feats[c['id']](x) for x in G2],dtype=float); gains=[]; by={}
        for s in BS.get('test_seasons') or []:
            tr=Ss<s; te=Ss==s
            if tr.sum()<200 or te.sum()<32: continue
            a0=Rs[tr].mean(); co=np.linalg.lstsq(np.column_stack([np.ones(tr.sum()),X[tr]]),Rs[tr],rcond=None)[0]
            g=np.abs(Rs[te]-a0)-np.abs(Rs[te]-co[0]-co[1]*X[te]); gains.extend(g.tolist()); by[s]=float(g.mean())
        gain=float(np.mean(gains)) if gains else float('nan'); nchk+=1
        if abs(gain-c['gain'])>0.002: bad.append('%s held-out gain %+.3f, rebuilt %+.3f'%(c['id'],c['gain'],gain))
        for s,v in by.items():
            if abs(v-num((c['by_season'] or {}).get(str(s)),9))>0.002: bad.append('%s %d gain %s, rebuilt %+.3f'%(c['id'],s,(c['by_season'] or {}).get(str(s)),v))
    A.check('BS3','The held-out test rebuilt from fresh walk-forward residuals for every candidate not cleared (and the schedule-only ones)',bad,nchk)

    # ---------- the page ----------
    out='/tmp/gi_audit_brain.json'
    r=subprocess.run(['node',os.path.join(os.path.dirname(__file__),'render_dump.js'),out],capture_output=True,text=True,timeout=180)
    if r.returncode or not os.path.exists(out):
        A.check('U18','The page renders for the brain checks',['render failed: '+(r.stderr or r.stdout)[-300:]]); return
    Rn=json.load(open(out)); LR=LG.get('record') or {}
    bad=[]; acc=Rn.get('acc') or {}; su=LR.get('su'); fav=LR.get('fav')
    if su and sum(su[:2]):
        p=jsr(100*su[0]/(su[0]+su[1])); t=acc.get('text') or ''
        if acc.get('hidden'): bad.append('the badge is hidden although %d calls have settled'%(su[0]+su[1]))
        if '%d%%'%p not in t or '%d–%d'%(su[0],su[1]) not in t: bad.append('badge shows "%s", the ledger gives %d%% (%d-%d)'%(t,p,su[0],su[1]))
        if fav and sum(fav[:2]):
            pf=jsr(100*fav[0]/(fav[0]+fav[1]))
            if 'Vegas favourite %d%%'%pf not in t: bad.append('badge should show the closing favourite\'s %d%% beside GridIron\'s'%pf)
            if 'won %d of %d'%(fav[0],fav[0]+fav[1]) not in (acc.get('title') or ''): bad.append('badge explanation does not state the favourite\'s %d of %d'%(fav[0],fav[0]+fav[1]))
    elif not acc.get('hidden'): bad.append('the badge shows a record with nothing settled')
    A.check('U18','The header badge shows the since-launch straight-up record from the ledger, beside the closing favourite\'s record on the same games',bad)

    bad=[]; MR=(Rn.get('model') or {}).get('reviews') or {}
    tl={x[0].lower():' '.join(x) for x in MR.get('tiles') or []}
    for k,want in (('reviewed','%d calls'%S['reviewed']),('mostly chance',str(S['verdicts']['chance'])),('misjudged a team',str(S['verdicts']['misjudged'])),
                   ('part of each',str(S['verdicts']['both'])),('ratings move','%.1f pts'%(jsr(num(S['shift'])*10)/10))):
        if want not in tl.get(k,''): bad.append('review tile "%s" should show %s, shows "%s"'%(k,want,tl.get(k)))
    rws=MR.get('rows') or []
    if len(rws)!=S['wrong']: bad.append('%d wrong calls listed, the reviews have %d'%(len(rws),S['wrong']))
    lab={'chance':'Mostly chance','misjudged':'Misjudged','both':'Part of each'}
    for row,g in zip(rws,sorted(W,key=lambda g:(-g['w'],-abs(g['miss'])))):
        tail=re.findall(r'([\d.]+)\s*$',row['head'])
        if '%s at %s'%(g['a'],g['h']) not in row['head'] or lab[g['verdict']] not in row['head'] or not tail or abs(float(tail[0])-abs(g['miss']))>0.051:
            bad.append('wrong-call row "%s" does not match %s at %s (%s, %.1f)'%(row['head'][:80],g['a'],g['h'],g['verdict'],abs(g['miss'])))
        for (k,v),pk in zip(row['parts'],('yards','finish','turnovers','nonoff','blend')):
            pv=g['parts'][pk]; got=lead(v)
            if got is None or abs(got-(0.0 if abs(pv)<0.05 else abs(pv)))>0.051: bad.append('%s at %s %s shows "%s", data %+.2f'%(g['a'],g['h'],pk,v,pv))
    for x,k in zip(MR.get('repeat') or [],PARTS):
        rr=re.findall(r'r\s*=\s*(-?[\d.]+)',x)
        if not rr or abs(float(rr[0])-num(Pst[k]['r']))>0.0051: bad.append('repeatability row "%s" should show r = %.2f'%(x[:60],num(Pst[k]['r'])))
    A.check('U19','Model page review card: tiles, every wrong call with its verdict, miss and parts, and the repeatability table match the reviews',bad,len(rws))

    bad=[]; MB=(Rn.get('model') or {}).get('blind') or {}
    VL={'blind_spot':'Blind spot','watch':'Watch','clear':'Clear'}
    for row,c in zip(MB.get('rows') or [],sorted(C,key=lambda c:c['p'])):
        if c['name'] not in row['head'] or row['verdict'].lower()!=VL[c['verdict']].lower() or ('better in %d of %d'%(c['pos'],len(c['by_season']))) not in row['head']:
            bad.append('blind-spot row "%s" does not match %s (%s)'%(row['head'][:70],c['name'],c['verdict']))
    if len(MB.get('rows') or [])!=len(C): bad.append('%d candidates shown, %d tested'%(len(MB.get('rows') or []),len(C)))
    tb={x[0].lower():x[1] for x in MB.get('tiles') or []}
    for k,v in (('blind spots',BS['counts']['blind_spot']),('on watch',BS['counts']['watch']),('clear',BS['counts']['clear'])):
        if tb.get(k)!=str(v): bad.append('blind-spot tile "%s" shows %s, data %s'%(k,tb.get(k),v))
    A.check('U20','Model page blind-spot card: every candidate with its verdict and held-out record, and the counts, match the scan',bad,len(C))
