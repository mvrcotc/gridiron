"""Volatile game fields from the raw ESPN snapshot: status, final scores, the betting line, forecast weather,
ESPN's win probability and attendance. Everything else about a game is left as built."""
import os, json, time
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
RAW=os.path.join(DATA,'raw','espn'); D=json.load(open(os.path.join(DATA,'gi2.json')))
sb={e['id']:e for e in json.load(open(os.path.join(RAW,'sb2.json')))['events']}
KEYS=('state','date','sc','det','spread','ou','temp','gust','precip','cond','wp','att'); changed=[]
for g in D['games']:
    e=sb.get(g['id'])
    if not e: continue
    before={k:g.get(k) for k in KEYS}; c=e['competitions'][0]; st=c['status']['type']; T={x['homeAway']:x for x in c['competitors']}
    g['state']=st['state']; g['sdesc']=st.get('description',g.get('sdesc')); g['date']=e.get('date',g['date'])
    if st['state']=='post': g['sc']={'a':int(float(T['away'].get('score') or 0)),'h':int(float(T['home'].get('score') or 0))}
    sp=os.path.join(RAW,'s_%s.json'%g['id'])
    if os.path.exists(sp):
        s=json.load(open(sp)); pc=(s.get('pickcenter') or [{}])[0]
        if pc.get('details') is not None: g['det']=pc['details']
        if pc.get('spread') is not None: g['spread']=float(pc['spread'])
        if pc.get('overUnder') is not None: g['ou']=float(pc['overUnder'])
        if st['state']!='post':
            w=(s.get('gameInfo') or {}).get('weather') or {}
            for k,src in (('temp','temperature'),('gust','gust'),('precip','precipitation')):
                if w.get(src) is not None: g[k]=w[src]
            if w.get('conditionId') is not None: g['cond']=int(w['conditionId'])
            pr=((s.get('predictor') or {}).get('homeTeam') or {}).get('gameProjection')
            if pr is not None: g['wp']=float(pr)
    fp=os.path.join(RAW,'f_%s.json'%g['id'])
    if st['state']=='post' and os.path.exists(fp):
        at=(json.load(open(fp)).get('gameInfo') or {}).get('attendance')
        if at: g['att']=int(at)
    after={k:g.get(k) for k in KEYS}
    if after!=before: changed.append('%s@%s %s'%(g['a'],g['h'],{k:'%s->%s'%(before[k],after[k]) for k in KEYS if before[k]!=after[k]}))
D['lines_fetched']=time.strftime('%Y-%m-%dT%H:%MZ',time.gmtime(os.path.getmtime(os.path.join(RAW,'sb2.json'))))
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('games updated from ESPN snapshot (%s); %d changed'%(D['lines_fetched'],len(changed)))
for x in changed: print('  '+x[:180])
