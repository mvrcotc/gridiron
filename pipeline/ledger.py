"""Kickoff ledger: GridIron's real pregame predictions, frozen at kickoff, beside the first and last lines it saw, the
closing line and the final score -- the since-launch record, as opposed to the backtest.

Every refresh records, for each game still before kickoff, GridIron's latest call and line. The first refresh after
kickoff freezes the last record made before kickoff. A frozen entry never changes again except to gain its closing
line and final score. The published site carries the ledger and every refresh merges it back in, so records made by
refreshes that do not commit to git survive; the daily lane commits pipeline/ledger.json.

   python3 pipeline/ledger.py              update from data/gi2.json
   python3 pipeline/ledger.py --backfill   also replay pre-kickoff data snapshots from git history (run once, locally)"""
import os, sys, csv, json, time, datetime, subprocess, statistics, urllib.request
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(ROOT,'data'); LEDGER=os.path.join(HERE,'ledger.json')

def iso(ts): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(ts))
def ts(s): return datetime.datetime.fromisoformat(str(s).replace('Z','+00:00')).timestamp()
def fnum(v):
    try: return float(v)
    except (TypeError,ValueError): return None
def sign(x): return (x>0)-(x<0)

def load_local():
    try: return json.load(open(LEDGER,encoding='utf-8')).get('entries') or {}
    except (OSError,ValueError): return {}
def load_site():
    base=os.environ.get('GRIDIRON_SITE_URL')
    if not base: return {}
    try:
        v=json.load(urllib.request.urlopen(base.rstrip('/')+'/version.json?t=%d'%time.time(),timeout=20))
        d=json.load(urllib.request.urlopen(base.rstrip('/')+'/'+v['data'],timeout=60))
        return (d.get('ledger') or {}).get('entries') or {}
    except Exception as e:
        print('published ledger not available (%s); using the committed one'%str(e)[:80]); return {}

def merge(a,b):
    """frozen beats unfrozen; two frozen copies keep the earlier freeze; otherwise the later pre-kickoff record wins.
    The first line is the earliest either copy saw; closing lines and final scores are taken from whichever has them."""
    out=dict(a)
    for gid,e in b.items():
        o=out.get(gid)
        if o is None: out[gid]=e; continue
        if o.get('frozen') and e.get('frozen'): keep=o if o['frozen_at']<=e['frozen_at'] else e
        elif o.get('frozen') or e.get('frozen'): keep=o if o.get('frozen') else e
        else: keep=o if (o.get('call') or {}).get('at','')>=(e.get('call') or {}).get('at','') else e
        keep=dict(keep)
        for k in ('final','close','season','week'):
            if keep.get(k) is None and (o.get(k) is not None or e.get(k) is not None): keep[k]=o.get(k) if o.get(k) is not None else e.get(k)
        firsts=[x for x in (o.get('first'),e.get('first')) if x]
        if firsts: keep['first']=min(firsts,key=lambda x:x['at'])
        out[gid]=keep
    return out

def update(E,D,now,source):
    L=D.get('learn') or {}
    versions=dict(pregame=L.get('version') or 1,live=L.get('live_version'),players=L.get('players_version'))
    for g in D.get('games',[]):
        gid=g['id']; p=(D.get('pred') or {}).get(gid)
        e=dict(E.get(gid) or dict(id=gid,frozen=False)); e.update(a=g['a'],h=g['h'])
        if not e.get('frozen'):
            e['kickoff']=g['date']                                   # a kickoff can still move before the game starts
            if g.get('state')=='pre' and now<ts(g['date']):
                if g.get('spread') is not None or g.get('ou') is not None:
                    ln=dict(at=iso(now),spread=g.get('spread'),ou=g.get('ou'),det=g.get('det'))
                    e['last']=ln
                    if not e.get('first'): e['first']=ln
                if p:
                    e['call']=dict(at=iso(now),v=versions,sp=p.get('sp'),tot=p.get('tot'),wp=p.get('wp'),ph=p.get('ph'),pa=p.get('pa'),
                                   bsp=p.get('bsp'),btot=p.get('btot'))
                    e['source']=source; e.pop('missed',None)
            elif e.get('call') and ts(e['call']['at'])<ts(e['kickoff']):
                e['frozen']=True; e['frozen_at']=iso(now)
            else:
                e['missed']='no GridIron call was recorded before kickoff'
        if g.get('state')=='post' and g.get('sc') and not (e.get('final') or {}).get('src')=='nflverse':
            e['final']=dict(a=int(g['sc']['a']),h=int(g['sc']['h']),src='espn')
        E[gid]=e

def settle(E):
    """season, week, the closing line and the final score from the nflverse schedule"""
    rows={str(r.get('espn') or '').split('.')[0]:r for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'),encoding='utf-8')) if r.get('espn')}
    for gid,e in E.items():
        r=rows.get(gid)
        if not r: continue
        e['season'],e['week']=int(r['season']),int(r['week'])
        if r['home_score'] not in ('',None):
            e['final']=dict(a=int(float(r['away_score'])),h=int(float(r['home_score'])),src='nflverse')
            sl,tl=fnum(r['spread_line']),fnum(r['total_line'])
            if sl is not None: e['close']=dict(spread=-sl,ou=tl,src='nflverse')   # nflverse spread_line is positive when the home team is favoured

def record(E):
    """the since-launch record: frozen calls with a closing line and a final score"""
    fr=[e for e in E.values() if e.get('frozen')]
    X=[e for e in fr if e.get('final') and e.get('close') and (e.get('call') or {}).get('ph') is not None]
    out=dict(frozen=len(fr),settled=len(X),pending=sum(1 for e in fr if not (e.get('final') and e.get('close'))),
             missed=sum(1 for e in E.values() if e.get('missed') and not e.get('frozen')))
    if not X: return out
    gm_e=[]; cm_e=[]; gt_e=[]; ct_e=[]; ats=[0,0,0]; ou=[0,0,0]; su=[0,0]; brier=[]; clv=[]; clvt=[]
    for e in X:
        am=e['final']['h']-e['final']['a']; at=e['final']['h']+e['final']['a']
        gm=e['call']['ph']-e['call']['pa']; gt=e['call']['ph']+e['call']['pa']; cm=-e['close']['spread']; ct=e['close']['ou']
        gm_e.append(abs(gm-am)); cm_e.append(abs(cm-am))
        if ct is not None: gt_e.append(abs(gt-at)); ct_e.append(abs(ct-at))
        pick,res=sign(gm-cm),sign(am-cm)
        if pick: ats[2 if res==0 else (0 if pick==res else 1)]+=1
        if ct is not None:
            pick,res=sign(gt-ct),sign(at-ct)
            if pick: ou[2 if res==0 else (0 if pick==res else 1)]+=1
        if am: su[0 if sign(gm)==sign(am) else 1]+=1
        if e['call'].get('wp') is not None and am: brier.append((e['call']['wp']/100.0-(1.0 if am>0 else 0.0))**2)
        f=e.get('first') or {}
        if f.get('spread') is not None:
            fm=-f['spread']; move=cm-fm; dis=gm-fm
            if move and dis: clv.append(move*sign(dis))
        if f.get('ou') is not None and ct is not None:
            move=ct-f['ou']; dis=gt-f['ou']
            if move and dis: clvt.append(move*sign(dis))
    r=lambda v,d=2:round(v,d)
    out.update(gm=r(statistics.mean(gm_e)),vm=r(statistics.mean(cm_e)),gt=r(statistics.mean(gt_e)) if gt_e else None,vt=r(statistics.mean(ct_e)) if ct_e else None,
               ats=ats,ou=ou,su=su,brier=r(statistics.mean(brier),4) if brier else None,brier_n=len(brier),
               clv=dict(n=len(clv),toward=sum(1 for x in clv if x>0),pts=r(statistics.mean(clv)) if clv else None),
               clv_total=dict(n=len(clvt),toward=sum(1 for x in clvt if x>0),pts=r(statistics.mean(clvt)) if clvt else None))
    return out

def backfill(E):
    """replay pre-kickoff data snapshots committed before this ledger existed"""
    log=subprocess.run(['git','-C',ROOT,'log','--format=%H %ct','--','data/gi2.json'],capture_output=True,text=True).stdout.split('\n')
    snaps=sorted((int(ct),sha) for sha,ct in (l.split() for l in log if l.strip()))
    for ct,sha in snaps:
        raw=subprocess.run(['git','-C',ROOT,'show','%s:data/gi2.json'%sha],capture_output=True,text=True).stdout
        try: D=json.loads(raw)
        except ValueError: continue
        update(E,D,ct,'data snapshot %s committed %s'%(sha[:7],iso(ct)))
    print('replayed %d snapshots from git history'%len(snaps))

if __name__=='__main__':
    D=json.load(open(os.path.join(DATA,'gi2.json'),encoding='utf-8')); now=time.time()
    E=merge(load_local(),load_site())
    if '--backfill' in sys.argv: backfill(E)
    update(E,D,now,'refresh'); settle(E); R=record(E)
    L=dict(updated=iso(now),record=R,entries=dict(sorted(E.items(),key=lambda kv:(kv[1].get('kickoff',''),kv[0]))),
           note='Each call is the last GridIron prediction recorded before kickoff; the first line is the first one GridIron saw, not necessarily the opening line. Closing lines and scores come from nflverse.')
    json.dump(L,open(LEDGER+'.part','w',encoding='utf-8'),indent=1,ensure_ascii=False); os.replace(LEDGER+'.part',LEDGER)
    D['ledger']=L; json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
    print('ledger: %d games, %d frozen at kickoff, %d settled, %d without a pre-kickoff call | since launch %s'%(
        len(E),R['frozen'],R['settled'],R['missed'],{k:R[k] for k in ('gm','vm','ats','clv') if k in R}))
