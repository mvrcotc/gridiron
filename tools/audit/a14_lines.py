"""Line movement: the stored opening and closing lines, GridIron's early calls and every number on the Line movement
card, rebuilt with code written only for the audit. Lines are re-read from the raw ESPN summaries this run saved and
tied to the nflverse schedule; the week-early ratings margin is rebuilt from engine2's own ratings snapshots (like a7 and
a13, the only pipeline code imported), with home field, venue and rest recomputed here from the schedule."""
import os, sys, re, json, math, statistics, subprocess, datetime
from collections import defaultdict
from common import num, rows, DATA, RAW, PIPE, ROOT

E2N={'LAR':'LA','WSH':'WAS'}
def jsr(x): return int(math.floor(x+0.5))
def sg(x): return (x>0)-(x<0)
def t(s): return datetime.datetime.fromisoformat(str(s).replace('Z','+00:00'))
def lnum(x,total=False):
    s=str(x if x is not None else '').strip()
    if total and s[:1] in 'oOuU': s=s[1:]
    if s.upper() in ('PK','EVEN','PICK',"PICK'EM"): return 0.0
    try: v=float(s)
    except ValueError: return None
    return v if math.isfinite(v) else None
def head(path):
    r=subprocess.run(['git','-C',ROOT,'show','HEAD:'+path],capture_output=True,text=True)
    if r.returncode: return None
    try: return json.loads(r.stdout)
    except ValueError: return None
def figs(s): return [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?',(s or '').replace('−','-'))]

def summary(X):
    """the movement figures for (disagreement, move) pairs, recomputed"""
    P=[x for x in X if x[0]]; M=[x for x in P if x[1]]; tw=sum(1 for d,m in M if sg(d)==sg(m)); n=len(M)
    out=dict(n=len(X),moved=n,toward=tw,away=n-tw,pts=statistics.mean(m*sg(d) for d,m in P) if P else None)
    if n:
        f=lambda i:math.comb(n,i)/2**n; obs=f(tw); out['p']=min(1.0,sum(f(i) for i in range(n+1) if f(i)<=obs*(1+1e-9)))
    if len(X)>=3:
        d=[x[0] for x in X]; m=[x[1] for x in X]; dm,mm=statistics.mean(d),statistics.mean(m); sxx=sum((v-dm)**2 for v in d)
        if sxx>0: out['slope']=sum((u-dm)*(v-mm) for u,v in zip(d,m))/sxx
    return out

def run(A):
    A.section('line movement'); D=A.D; MV=D.get('moves')
    SP=os.path.join(PIPE,'learning','lines.json')
    if not MV:
        A.check('LM1','The line-movement data exists',['data/gi2.json has no moves block']); return
    try: S=json.load(open(SP,encoding='utf-8'))
    except (OSError,ValueError): S={'games':{},'none':{}}
    G=S.get('games') or {}; NONE=S.get('none') or {}
    SC={str(r.get('espn') or '').split('.')[0]:r for r in rows(os.path.join(DATA,'games_all.csv')) if r.get('espn') and r['game_type']=='REG'}

    # ---------- LM1: every stored line is sane, tied to its schedule row, and matches the raw summary where one was saved ----------
    bad=[]
    for gid,g in G.items():
        r=SC.get(gid)
        if not r: bad.append('%s is not a regular-season game in the schedule'%gid); continue
        n='%s@%s %s wk%s'%(r['away_team'],r['home_team'],r['season'],r['week'])
        if (g.get('s'),g.get('w'),g.get('h'),g.get('a'))!=(int(r['season']),int(r['week']),r['home_team'],r['away_team']): bad.append('%s stored as %s@%s %s wk%s'%(n,g.get('a'),g.get('h'),g.get('s'),g.get('w')))
        if r['home_score'] in ('',None): bad.append('%s is stored but not finished'%n)
        if not g.get('book'): bad.append('%s has no book'%n)
        for k in ('open','close'):
            v=(g.get(k) or {}).get('spread'); o=(g.get(k) or {}).get('ou')
            if v is None or abs(v)>30 or abs(v*2-round(v*2))>1e-9: bad.append('%s %s spread %r is not a half-point line'%(n,k,v))
            if o is not None and not 25<=o<=75: bad.append('%s %s total %r is out of range'%(n,k,o))
        sl=num(r['spread_line'],None); cs=(g.get('close') or {}).get('spread')
        if sl is not None and cs is not None and abs(cs+sl)>3.5: bad.append('%s closed at home %+.1f, nflverse closed home %+.1f -- a side swapped?'%(n,cs,-sl))
    for gid in NONE:
        if gid not in SC: bad.append('no-line entry %s is not a regular-season game'%gid)
        if gid in G: bad.append('%s is both stored and listed as having no line'%gid)
    nraw=0
    for g in D.get('games',[]):
        if g.get('state')!='post' or g['id'] not in G: continue
        try: s=json.load(open(os.path.join(RAW,'espn','s_%s.json'%g['id']),encoding='utf-8'))
        except (OSError,ValueError): continue
        st=(((s.get('header') or {}).get('competitions') or [{}])[0].get('status') or {}).get('type') or {}
        if not st.get('completed'): continue
        pc=next((p for p in (s.get('pickcenter') or []) if (((p.get('pointSpread') or {}).get('home') or {}).get('open') or {}).get('line') is not None),None)
        if not pc or (pc.get('provider') or {}).get('name')!=G[g['id']].get('book'): continue
        nraw+=1; ps=pc['pointSpread']['home']; tt=(pc.get('total') or {}).get('over') or {}; got=G[g['id']]
        want=dict(open=dict(spread=lnum(ps['open'].get('line')),ou=lnum((tt.get('open') or {}).get('line'),True)),
                  close=dict(spread=lnum((ps.get('close') or {}).get('line')),ou=lnum((tt.get('close') or {}).get('line'),True)))
        for k in ('open','close'):
            for f in ('spread','ou'):
                if (got.get(k) or {}).get(f)!=want[k][f]: bad.append('%s@%s %s %s stored %r, the raw summary says %r'%(g['a'],g['h'],k,f,(got.get(k) or {}).get(f),want[k][f]))
    A.check('LM1','Stored opening and closing lines are sane, tied to the schedule, and match the raw ESPN summary for this slate\'s finished games',bad,len(G))

    # ---------- LM2: nothing stored is ever rewritten ----------
    bad=[]; H=head('pipeline/learning/lines.json')
    if H:
        for gid,g in (H.get('games') or {}).items():
            cur=G.get(gid)
            if not cur: bad.append('%s was stored in the committed file and has gone'%gid); continue
            for k in ('open','close','book','s','w','h','a'):
                if cur.get(k)!=g.get(k): bad.append('%s %s changed from %r to %r'%(gid,k,g.get(k),cur.get(k)))
        for gid in (H.get('none') or {}):
            if gid not in NONE and gid not in G: bad.append('%s was listed as having no line and has gone'%gid)
    A.check('LM2','A stored line never changes (compared with the last committed lines file)',bad,len((H or {}).get('games') or {}))

    # ---------- LM3: the rebuilt test, from engine2's ratings a week before kickoff ----------
    sys.path.insert(0,PIPE); import engine2
    CH=json.load(open(os.path.join(PIPE,'champion.json'))); VS=sorted(CH['versions'],key=lambda v:v['v'])
    def force(s,w):
        ok=[v for v in VS if v['cutoff'][0]*100+v['cutoff'][1]<s*100+w]; return ok[-1] if ok else VS[0]
    REL={'STL':'LA','SD':'LAC','OAK':'LV'}
    SCH=[r for r in rows(os.path.join(DATA,'games_all.csv')) if r['game_type']=='REG']
    HM=defaultdict(list); RD=defaultdict(list); LGM=[]
    for r in SCH:
        s=int(r['season'])
        if r['home_score'] in ('',None) or r['location']!='Home' or s<2015: continue
        k=s*100+int(r['week']); m=num(r['home_score'])-num(r['away_score'])
        HM[REL.get(r['home_team'],r['home_team'])].append((k,m)); RD[REL.get(r['away_team'],r['away_team'])].append((k,-m)); LGM.append((k,m))
    def before(L,k,need=1):
        v=[m for kk,m in L if kk<k]; return statistics.mean(v) if len(v)>=need else None
    snaps={}
    def snap(P,s,w):
        key=(tuple(P[k] for k in ('kY','cY','kP','cP','kT','cT','kO','cO','kE','cE','kS','cS','decay')),s,w)
        if key not in snaps: snaps[key]=engine2.run(dict(P),ret_state=True,until=(s,w))[1]
        return snaps[key]
    def pts(sn,P,s,tm,op):
        L=engine2.LG.get(s) or sn['L']; q=lambda k,x:sn[k].rate(x)
        pl=L['plays']*q('oP',tm)*q('dP',op); yd=L['ypp']*q('oY',tm)*q('dY',op)*pl
        td=yd*L['tdpy']*q('oT',tm)*q('dT',op); to=pl*L['topp']*q('oO',tm)*q('dO',op)
        return P['wB']*engine2.pts_box(yd,td,to,s)+P['wE']*(L['ppg']+(q('oE',tm)+q('dE',op))*pl)+P['wS']*(L['ppg']+q('oS',tm)+q('dS',op))
    X=[]; B=[]; by=defaultdict(list); ER=[]
    for gid,g in G.items():
        r=SC.get(gid)
        if not r or r['home_score'] in ('',None): continue
        s,w=int(r['season']),int(r['week']); lw=max(w-1,1); P=force(s,lw)['params']; sn=snap(P,s,lw); h,a=r['home_team'],r['away_team']
        neutral=r['location']!='Home'; k=s*100+lw; ht=REL.get(h,h)
        lg,hm,rd=before(LGM,k),before(HM[ht],k,16),before(RD[ht],k,16)
        venue=0.0 if (neutral or lg is None or hm is None or rd is None) else hm-rd-2*lg
        hr,ar=num(r['home_rest'],None),num(r['away_rest'],None); rest=max(-7.0,min(7.0,hr-ar)) if hr is not None and ar is not None else 0.0
        hf=0.0 if neutral else P['hfa']
        m=pts(sn,P,s,h,a)-pts(sn,P,s,a,h)+hf+P['venue']*venue+P['rest']*rest
        om,cm=-g['open']['spread'],-g['close']['spread']; am=num(r['home_score'])-num(r['away_score'])
        X.append((m-om,cm-om,am-om,am-cm,m-cm)); B.append((hf-om,cm-om)); by[s].append((m-om,cm-om)); ER.append((abs(om-am),abs(cm-am),abs(m-am)))
    RB=MV.get('rebuilt') or {}; bad=[]
    def cmp(lab,got,want):
        for k in ('n','moved','toward','away'):
            if k in want and got.get(k)!=want[k]: bad.append('%s %s shown %s, recompute %s'%(lab,k,got.get(k),want[k]))
        for k,tol in (('pts',0.0006),('p',0.00006),('slope',0.00006)):
            if want.get(k) is None: continue
            if got.get(k) is None or abs(num(got[k])-want[k])>tol: bad.append('%s %s shown %s, recompute %.4f'%(lab,k,got.get(k),want[k]))
    W=summary([x[:2] for x in X]); cmp('rebuilt',RB,W); cmp('benchmark',RB.get('base') or {},summary(B))
    for s,L in by.items(): cmp('season %s'%s,(RB.get('seasons') or {}).get(str(s)) or {},{k:v for k,v in summary(L).items() if k in ('n','moved','toward','pts')})
    for b in RB.get('buckets') or []:
        L=[x[:2] for x in X if abs(x[0])>=b['lo'] and (b['hi'] is None or abs(x[0])<b['hi'])]
        cmp('bucket %s'%b['lo'],b,{k:v for k,v in summary(L).items() if k in ('n','moved','toward','pts')})
    def ats(i,j):
        o=[0,0,0]
        for x in X:
            if not x[j]: continue
            o[2 if not x[i] else 0 if sg(x[i])==sg(x[j]) else 1]+=1
        return o
    if RB.get('ats_open')!=ats(2,0): bad.append('at the opener shown %s, recompute %s'%(RB.get('ats_open'),ats(2,0)))
    if RB.get('ats_close')!=ats(3,4): bad.append('at the close shown %s, recompute %s'%(RB.get('ats_close'),ats(3,4)))
    if ER:
        for i,k in enumerate(('open','close','gi')):
            if abs(num((RB.get('err') or {}).get(k))-statistics.mean(e[i] for e in ER))>0.0006: bad.append('error %s shown %s, recompute %.3f'%(k,(RB.get('err') or {}).get(k),statistics.mean(e[i] for e in ER)))
    need=num(MV.get('need'),50); bs=summary(B)
    want='early' if W['moved']<need else ('signal' if W['toward']>W['away'] else 'against') if W['p']<0.05 else 'none'
    if want=='signal' and (bs['toward']/bs['moved'] if bs.get('moved') else 0.0)>=W['toward']/W['moved']: want='reversion'
    if RB.get('verdict')!=want: bad.append('verdict %s, the stated rule gives %s'%(RB.get('verdict'),want))
    A.check('LM3','The rebuilt line-movement test recomputes from the stored lines and engine2\'s ratings a week before each kickoff, benchmark and verdict included',bad,len(X))

    # ---------- LM4: real early calls ----------
    bad=[]; LG=D.get('ledger') or {}; E=LG.get('entries') or {}
    HL=(head('pipeline/ledger.json') or {}).get('entries') or {}
    Xs=[]; Xt=[]; pend=0; rec=0
    for gid,e in E.items():
        en=e.get('entry')
        if not en: continue
        rec+=1; n='%s@%s'%(e.get('a'),e.get('h'))
        if not e.get('kickoff') or t(en['at'])>=t(e['kickoff']): bad.append('%s early call recorded at %s, kickoff %s'%(n,en.get('at'),e.get('kickoff')))
        if e.get('frozen') and t(en['at'])>t((e.get('call') or {}).get('at') or en['at']): bad.append('%s early call is later than its kickoff call'%n)
        if en.get('ph') is None or (en.get('spread') is None and en.get('ou') is None): bad.append('%s early call lacks a projection or a line'%n)
        old=(HL.get(gid) or {}).get('entry')
        if old and old!=en: bad.append('%s early call changed after it was recorded'%n)
        if en.get('ph') is None: continue
        g=G.get(gid)
        if not g: pend+=1; continue
        if en.get('spread') is not None: Xs.append((en['ph']-en['pa']+en['spread'],en['spread']-g['close']['spread']))
        if en.get('ou') is not None and g['close'].get('ou') is not None: Xt.append((en['ph']+en['pa']-en['ou'],g['close']['ou']-en['ou']))
    RL=MV.get('real') or {}
    cmp('real spreads',RL.get('spread') or {},summary(Xs)); cmp('real totals',RL.get('total') or {},summary(Xt))
    if RL.get('pending')!=pend or RL.get('recorded')!=rec: bad.append('real calls: %s recorded, %s pending shown; recompute %d, %d'%(RL.get('recorded'),RL.get('pending'),rec,pend))
    A.check('LM4','Every early call was recorded before kickoff beside a line and never changes, and the real-call movement recomputes',bad,rec)

    # ---------- U21: the card ----------
    out='/tmp/gi_audit_lines.json'
    r=subprocess.run(['node',os.path.join(os.path.dirname(__file__),'render_dump.js'),out],capture_output=True,text=True,timeout=180)
    if r.returncode or not os.path.exists(out):
        A.check('U21','The page renders for the line-movement check',['render failed: '+(r.stderr or r.stdout)[-300:]]); return
    C=(json.load(open(out)).get('model') or {}).get('moves') or {}; bad=[]
    tl={x[0]:x for x in C.get('tiles') or []}
    pc=lambda x:100.0*x['toward']/x['moved']
    def near(key,i,want,tol=0.051):
        got=figs((tl.get(key) or [None,'',''])[i])
        if not any(abs(v-w)<=tol for v in got for w in ([want] if not isinstance(want,list) else want)): bad.append('tile %s shows "%s", should carry %s'%(key,(tl.get(key) or [None,'',''])[i],want))
    if not RB.get('n'):
        if 'Collecting' not in (C.get('text') or ''): bad.append('no lines stored, but the card does not say it is collecting')
    else:
        if W['moved']:
            near('toward',1,jsr(pc(W)*10)/10)
            if '%d of %d moves'%(W['toward'],W['moved']) not in (tl.get('toward') or [None,'',''])[2]: bad.append('tile toward should say %d of %d moves'%(W['toward'],W['moved']))
        if W.get('pts') is not None: near('pts',1,sg(W['pts'])*jsr(abs(W['pts'])*100)/100,0.0051)
        if bs.get('moved'): near('base',1,jsr(pc(bs)*10)/10)
        ao=ats(2,0)
        if ao[0]+ao[1]:
            near('open',1,jsr(1000*ao[0]/(ao[0]+ao[1]))/10)
            if not (tl.get('open') or [None,'',''])[2].startswith('%d-%d'%(ao[0],ao[1])): bad.append('tile open should give the record %d-%d'%(ao[0],ao[1]))
        if len(C.get('buckets') or [])!=len(RB.get('buckets') or []): bad.append('%d disagreement rows shown, data has %d'%(len(C.get('buckets') or []),len(RB.get('buckets') or [])))
        for row,b in zip(C.get('buckets') or [],RB.get('buckets') or []):
            L=summary([x[:2] for x in X if abs(x[0])>=b['lo'] and (b['hi'] is None or abs(x[0])<b['hi'])])
            if str(b['lo'])!=row[0] or (L['moved'] and not any(abs(v-jsr(pc(L)*10)/10)<=0.051 for v in figs(row[2]))): bad.append('bucket row %s shows "%s"'%(row[0],row[2]))
        for y,txt in C.get('seasons') or []:
            L=summary(by.get(int(y),[]))
            if L['moved'] and not any(abs(v-jsr(pc(L)*10)/10)<=0.051 for v in figs(txt)): bad.append('season chip "%s" should show %.1f%%'%(txt,pc(L)))
        lead={'early':'Too early to say','signal':'The line does move toward GridIron','reversion':'Toward GridIron, but no more than toward a guess',
              'against':'The line moves away from GridIron','none':'No sign GridIron knows where the line is going'}[want]
        if not (C.get('verdict') or '').startswith(lead): bad.append('verdict reads "%s", should open "%s"'%((C.get('verdict') or '')[:60],lead))
        if str(rec)!=(tl.get('rpend') or [None,''])[1]: bad.append('early calls recorded tile shows %s, ledger has %d'%((tl.get('rpend') or [None,''])[1],rec))
        rs=summary(Xs)
        if rs['moved'] and '%d of %d'%(rs['toward'],rs['moved'])!=(tl.get('rspread') or [None,''])[1]: bad.append('real spreads tile shows %s, recompute %d of %d'%((tl.get('rspread') or [None,''])[1],rs['toward'],rs['moved']))
    A.check('U21','Model page line-movement card: tiles, disagreement rows, seasons, verdict and real calls match the rebuilt figures',bad,len(C.get('tiles') or []))
