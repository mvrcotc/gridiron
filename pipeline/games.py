"""Volatile game fields from the raw ESPN snapshot: status, final scores, the betting line, forecast weather, ESPN's win
probability and attendance.

Everything else about a game is left as built. Every ESPN value is parsed defensively: a field that changes type upstream
(ESPN began sending weather conditions as words on game day) is skipped and reported, never allowed to stop the refresh."""
import os, json, time, math
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
RAW=os.path.join(DATA,'raw','espn'); D=json.load(open(os.path.join(DATA,'gi2.json'),encoding='utf-8'))
def numf(x):
    try:
        v=float(x)
    except (TypeError,ValueError):
        return None
    if not math.isfinite(v): return None
    return int(v) if v.is_integer() else v
def load(p):
    try: return json.load(open(p,encoding='utf-8'))
    except (OSError,ValueError): return None
sb={e.get('id'):e for e in ((load(os.path.join(RAW,'sb2.json')) or {}).get('events') or [])}
KEYS=('state','date','sc','det','spread','ou','temp','gust','precip','cond','condtext','wp','att'); changed=[]; odd=[]
for g in D['games']:
    e=sb.get(g['id'])
    if not e: continue
    name='%s@%s'%(g['a'],g['h']); before={k:g.get(k) for k in KEYS}
    c=(e.get('competitions') or [{}])[0] or {}; st=((c.get('status') or {}).get('type') or {})
    state=st.get('state') or g.get('state')
    g['state']=state; g['sdesc']=st.get('description') or g.get('sdesc'); g['date']=e.get('date') or g['date']
    if state=='post':
        T={x.get('homeAway'):x for x in (c.get('competitors') or [])}
        a,h=numf((T.get('away') or {}).get('score')),numf((T.get('home') or {}).get('score'))
        if a is not None and h is not None: g['sc']={'a':int(a),'h':int(h)}
        else: odd.append('%s final score is not numeric'%name)
    s=load(os.path.join(RAW,'s_%s.json'%g['id']))
    if s:
        pc=(s.get('pickcenter') or [{}])[0] or {}
        if isinstance(pc.get('details'),str) and pc['details'].strip(): g['det']=pc['details'].strip()
        for k,src in (('spread','spread'),('ou','overUnder')):
            v=numf(pc.get(src))
            if v is not None: g[k]=float(v)
            elif pc.get(src) is not None: odd.append('%s %s is not numeric: %r'%(name,src,pc.get(src)))
    if s and state!='post':
        w=(s.get('gameInfo') or {}).get('weather') or {}
        for k,src in (('temp','temperature'),('gust','gust'),('precip','precipitation')):
            v=numf(w.get(src))
            if v is not None: g[k]=v
            elif w.get(src) is not None: odd.append('%s weather %s is not numeric: %r'%(name,src,w.get(src)))
        cid=w.get('conditionId')
        if cid is not None:
            v=numf(cid)
            if v is not None: g['cond']=int(v); g.pop('condtext',None)
            else: g.pop('cond',None); g['condtext']=str(cid).strip()[:40]
        pr=numf(((s.get('predictor') or {}).get('homeTeam') or {}).get('gameProjection'))
        if pr is not None: g['wp']=float(pr)
    if state=='post':
        f=load(os.path.join(RAW,'f_%s.json'%g['id']))
        at=numf(((f or {}).get('gameInfo') or {}).get('attendance'))
        if at: g['att']=int(at)
    after={k:g.get(k) for k in KEYS}
    if after!=before: changed.append('%s %s'%(name,{k:'%s->%s'%(before[k],after[k]) for k in KEYS if before[k]!=after[k]}))
sbp=os.path.join(RAW,'sb2.json')
D['lines_fetched']=time.strftime('%Y-%m-%dT%H:%MZ',time.gmtime(os.path.getmtime(sbp))) if os.path.exists(sbp) else D.get('lines_fetched')
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('games updated from ESPN snapshot (%s); %d changed'%(D['lines_fetched'],len(changed)))
for x in changed: print('  '+x[:180])
for x in odd: print('  note: '+x[:180])
