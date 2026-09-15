"""The kickoff ledger: nothing is frozen that was recorded after kickoff, a frozen call never changes, scores and closing
lines match the raw schedule, the since-launch record recomputes, and the page shows exactly that."""
import os, json, datetime, subprocess, statistics
from common import num, rows, DATA, PIPE, ROOT

def t(s): return datetime.datetime.fromisoformat(str(s).replace('Z','+00:00'))
def sg(x): return (x>0)-(x<0)

def run(A):
    A.section('kickoff ledger'); D=A.D; path=os.path.join(PIPE,'ledger.json')
    if not os.path.exists(path):
        A.check('K1','The kickoff ledger exists',['pipeline/ledger.json is missing']); return
    L=json.load(open(path,encoding='utf-8')); E=L.get('entries') or {}

    A.check('K1','The published data carries exactly the ledger the pipeline wrote',[] if D.get('ledger')==L else ['data/gi2.json ledger differs from pipeline/ledger.json'])

    bad=[]; state={g['id']:g.get('state') for g in D['games']}
    for gid,e in E.items():
        n='%s@%s'%(e.get('a'),e.get('h'))
        if e.get('frozen'):
            c=e.get('call') or {}
            if not c.get('at') or t(c['at'])>=t(e['kickoff']): bad.append('%s frozen with a call recorded at %s, kickoff %s'%(n,c.get('at'),e.get('kickoff')))
            if not e.get('frozen_at') or t(e['frozen_at'])<t(e['kickoff']): bad.append('%s marked frozen at %s, before its kickoff'%(n,e.get('frozen_at')))
            if e.get('first') and t(e['first']['at'])>t(c.get('at') or e['kickoff']): bad.append('%s first line was recorded after the frozen call'%n)
            if c.get('ph') is None or c.get('pa') is None: bad.append('%s frozen without a projected score'%n)
        elif state.get(gid) in ('in','post') and not e.get('missed'): bad.append('%s kicked off but is neither frozen nor marked as missed'%n)
    A.check('K2','Only calls recorded before kickoff are frozen, and every game that kicked off is frozen or marked as missed',bad,len(E))

    bad=[]; prev=subprocess.run(['git','-C',ROOT,'show','HEAD:pipeline/ledger.json'],capture_output=True,text=True)
    if prev.returncode==0:
        try: P=(json.loads(prev.stdout).get('entries') or {})
        except ValueError: P={}
        for gid,e in P.items():
            if not e.get('frozen'): continue
            cur=E.get(gid)
            if not cur or not cur.get('frozen'): bad.append('%s@%s was frozen in the committed ledger and no longer is'%(e.get('a'),e.get('h'))); continue
            for k in ('call','kickoff','frozen_at'):
                if cur.get(k)!=e.get(k): bad.append('%s@%s frozen %s changed after the fact'%(e.get('a'),e.get('h'),k))
    A.check('K3','A frozen call never changes after kickoff (compared with the last committed ledger)',bad)

    bad=[]; GA={str(r.get('espn') or '').split('.')[0]:r for r in rows(os.path.join(DATA,'games_all.csv')) if r.get('espn') and r['game_type']=='REG'}
    for gid,e in E.items():
        r=GA.get(gid); n='%s@%s'%(e.get('a'),e.get('h'))
        if not r or r['home_score'] in ('',None): continue
        want=dict(a=int(num(r['away_score'])),h=int(num(r['home_score'])))
        f=e.get('final') or {}
        if (f.get('a'),f.get('h'))!=(want['a'],want['h']): bad.append('%s final %s, schedule %s'%(n,f,want))
        if r['spread_line'] not in ('',None):
            c=e.get('close') or {}
            if c.get('spread')!=-num(r['spread_line']) or (r['total_line'] and c.get('ou')!=num(r['total_line'])): bad.append('%s close %s, schedule spread %s total %s'%(n,c,r['spread_line'],r['total_line']))
    A.check('K4','Final scores and closing lines match the nflverse schedule',bad,len(E))

    bad=[]; R=L.get('record') or {}
    X=[e for e in E.values() if e.get('frozen') and e.get('final') and e.get('close') and (e.get('call') or {}).get('ph') is not None]
    ge=[]; ce=[]; ats=[0,0,0]; su=[0,0]; mv=[]
    for e in X:
        am=e['final']['h']-e['final']['a']; gm=e['call']['ph']-e['call']['pa']; cm=-e['close']['spread']
        ge.append(abs(gm-am)); ce.append(abs(cm-am))
        if sg(gm-cm): ats[2 if sg(am-cm)==0 else (0 if sg(gm-cm)==sg(am-cm) else 1)]+=1
        if am: su[0 if sg(gm)==sg(am) else 1]+=1
        fs=(e.get('first') or {}).get('spread')
        if fs is not None and (cm+fs) and (gm+fs): mv.append((cm+fs)*sg(gm+fs))
    if R.get('settled')!=len(X): bad.append('record says %s settled, ledger has %d'%(R.get('settled'),len(X)))
    if X:
        if abs(num(R.get('gm'))-statistics.mean(ge))>0.006 or abs(num(R.get('vm'))-statistics.mean(ce))>0.006: bad.append('margin errors %s / %s, recompute %.3f / %.3f'%(R.get('gm'),R.get('vm'),statistics.mean(ge),statistics.mean(ce)))
        if R.get('ats')!=ats: bad.append('against the close %s, recompute %s'%(R.get('ats'),ats))
        if R.get('su')!=su: bad.append('straight up %s, recompute %s'%(R.get('su'),su))
        c=R.get('clv') or {}
        if c.get('n')!=len(mv) or c.get('toward')!=sum(1 for x in mv if x>0): bad.append('line movement %s, recompute %d moves, %d toward'%(c,len(mv),sum(1 for x in mv if x>0)))
    A.check('K5','The since-launch record recomputes from the frozen calls, closing lines and scores',bad,len(X))
