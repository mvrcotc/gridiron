"""DraftKings prop lines: identity crosswalk, probability arithmetic against the CURRENT distributions."""
import os, json
from common import num, PIPE, nfl

QS=[2,5,10,20,25,30,40,50,60,70,75,80,85,90,95,98]
def p_over(q,line):
    """independent: piecewise-linear CDF through the stored percentiles"""
    if line<q[0]:  return 0.99
    if line>=q[-1]: return 0.01
    i=max(j for j in range(len(q)) if q[j]<=line)
    if i==len(q)-1: return 0.01
    lo,hi=q[i],q[i+1]
    cdf=QS[i]/100 if hi==lo else (QS[i]+(QS[i+1]-QS[i])*(line-lo)/(hi-lo))/100
    return min(0.995,max(0.005,1-cdf))

def run(A):
    A.section('props'); D=A.D; P=D.get('props') or {}; BY=P.get('by') or {}; PJ=D['proj']; PL=D['players']
    rawp=os.path.join(PIPE,'props.json'); RAW=json.load(open(rawp)) if os.path.exists(rawp) else []
    G={g['id']:g for g in D['games']}
    if not BY:
        upcoming=[g for g in D['games'] if g.get('state')=='pre']
        live=[k for k,v in PJ.items() if not v.get('out')]; scanned=int(P.get('scanned') or 0)
        if not upcoming or not live:
            A.check('X0','No prop lines expected: every game on the slate has kicked off, so nothing is left to match',[]); return
        if scanned>=200 and len(live)>=50:
            A.check('X0','Prop lines present',['DraftKings listed %d lines and %d players are projected, yet none matched -- the join is broken'%(scanned,len(live))]); return
        A.warn('X0','DraftKings has not posted prop lines for the games still to play',['%d lines scanned for %d upcoming games and %d projected players'%(scanned,len(upcoming),len(live))],len(upcoming)); return

    bad=[]
    for r in RAW:
        g=G.get(r['g']); pl=PL.get(r['gs'])
        if not g or not pl: bad.append('prop for unknown game/player %s %s'%(r['g'],r['gs'])); continue
        if nfl(pl['t']) not in (nfl(g['a']),nfl(g['h'])):
            bad.append('%s (%s) matched to a prop in %s@%s -- wrong player'%(pl['n'],pl['t'],g['a'],g['h']))
        if r['k'] in ('qry','qrec') and pl['p'] not in ('WR','TE','RB','FB'): bad.append('%s (%s) has a receiving prop'%(pl['n'],pl['p']))
        if r['k']=='qru' and pl['p'] not in ('RB','FB','QB','WR'): bad.append('%s (%s) has a rushing prop'%(pl['n'],pl['p']))
    A.check('X1','Every DraftKings line is attached to a player actually in that game, at a sensible position',sorted(set(bad)),len(RAW))

    lines={}
    for r in RAW: lines.setdefault((r['gs'],r['k']),set()).add(r['line'])
    multi=['%s %s: DraftKings posted %s, GridIron shows %s'%(PL[g]['n'],k,sorted(v),BY.get(g,{}).get(k,{}).get('line'))
           for (g,k),v in lines.items() if len(v)>1]
    A.check('X2','One line per player per market (no silently dropped alternate lines)',multi,len(lines),warn=True)

    bad=[]; n=0
    for g,mk in BY.items():
        for k,v in mk.items():
            q=PJ.get(g,{}).get(k); n+=1
            if not q: bad.append('%s %s has a line but no distribution'%(PL[g]['n'],k)); continue
            want=p_over(q,num(v['line']))
            if abs(want-num(v['p']))>0.025:
                bad.append('%s %s line %.1f: stored P(over) %.3f, current distribution gives %.3f'%(PL[g]['n'],k,v['line'],v['p'],want))
    A.check('X3','Every P(over) matches the projection distribution as it stands now',bad,n)

    bad=[]; by={}
    for g,mk in BY.items():
        for k,v in mk.items(): by.setdefault(k,[]).append(num(v['p']))
    for k,v in by.items():
        mean=sum(v)/len(v)
        if abs(mean-num(P['lean'].get(k)))>0.003: bad.append('%s stored lean %.4f, recompute %.4f'%(k,P['lean'].get(k),mean))
    for g,mk in BY.items():
        for k,v in mk.items():
            want=min(0.995,max(0.005,num(v['p'])+0.5-num(P['lean'].get(k))))
            if abs(want-num(v['rel']))>0.003: bad.append('%s %s relative %.3f, recompute %.3f'%(PL[g]['n'],k,v['rel'],want))
    A.check('X4','Average lean and each "net of lean" read recompute exactly',bad)

    bad=['%s is ruled out but shows a prop read'%PL[g]['n'] for g in BY if PJ.get(g,{}).get('out')]
    A.check('X5','No prop read is shown for a ruled-out player',bad)

    A.warn('X6','Prop reads assume -110 on both sides; DraftKings prices are not published with these lines',['break-even taken as 52.4%'])
    A.warn('X7','The %d%% under lean is unproven: there are no historical prop lines to test it against'%round(100*sum(1 for v in sum(by.values(),[]) if v<0.5)/max(1,sum(len(v) for v in by.values()))),
           ['books are known to shade overs; the app labels this as unproven'])
    import datetime as _dt
    f=P.get('fetched')
    if not f: A.check('X8','Prop lines carry a fetch time the page can show',['no fetch timestamp stored'])
    else:
        age=(_dt.datetime.utcnow()-_dt.datetime.strptime(f,'%Y-%m-%dT%H:%MZ')).total_seconds()/3600
        A.check('X8','Prop lines are fresh (fetched within 24 hours)',[] if age<=24 else ['lines fetched %.0f hours ago'%age],warn=True)
