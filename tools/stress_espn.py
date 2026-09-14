#!/usr/bin/env python3
"""Schema-drift stress test: copy the inputs, corrupt ESPN's payloads the way upstream changes have (numbers turned into
words, fields missing, empty values), and confirm every ESPN-reading stage still finishes.   python3 tools/stress_espn.py DIR"""
import os, sys, json, glob, shutil, subprocess
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); SRC=os.path.join(ROOT,'data'); OUT=sys.argv[1]
def fresh():
    if os.path.isdir(OUT): shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT,'raw','espn'))
    for f in ('gi2.json','games_all.csv','rost26.csv','players_all.csv'): shutil.copy(os.path.join(SRC,f),os.path.join(OUT,f))
    for f in glob.glob(os.path.join(SRC,'raw','espn','*.json')): shutil.copy(f,os.path.join(OUT,'raw','espn'))
def corrupt():
    for p in glob.glob(os.path.join(OUT,'raw','espn','s_*.json'))+glob.glob(os.path.join(OUT,'raw','espn','f_*.json')):
        s=json.load(open(p)); w=(s.get('gameInfo') or {}).get('weather')
        if isinstance(w,dict): w['conditionId']='Sunny'; w['temperature']='N/A'; w.pop('gust',None); w['precipitation']=None
        if s.get('pickcenter'): s['pickcenter'][0]['spread']='EVEN'; s['pickcenter'][0].pop('overUnder',None); s['pickcenter'][0]['details']=None
        if s.get('predictor'): s['predictor']['homeTeam']={'gameProjection':'--'}
        for blk in s.get('injuries') or []:
            for i,it in enumerate(blk.get('injuries') or []):
                if i%3==0: (it.get('athlete') or {}).pop('id',None)
                if i%4==0: it['status']='Day-To-Day'
        if (s.get('gameInfo') or {}).get('attendance') is not None: s['gameInfo']['attendance']='sold out'
        json.dump(s,open(p,'w'))
    p=os.path.join(OUT,'raw','espn','sb2.json'); sb=json.load(open(p))
    for k,e in enumerate(sb['events']):
        c=e['competitions'][0]
        if k==0: c['competitors'][0]['score']=''; c['broadcasts']=[]; c['venue']={}
        if k==1: c['competitors'][1]['team'].pop('color',None); c['status']['type'].pop('description',None)
    json.dump(sb,open(p,'w'))
fails=0
for label,mut in (('real ESPN payloads',False),('corrupted ESPN payloads',True)):
    fresh()
    if mut: corrupt()
    for stage in ('slate.py','games.py','injuries.py'):
        r=subprocess.run([sys.executable,os.path.join(ROOT,'pipeline',stage)],capture_output=True,text=True,env=dict(os.environ,GRIDIRON_DATA=OUT))
        ok=r.returncode==0; fails+=0 if ok else 1
        print('  %-24s %-12s %s'%(label,stage,'ok' if ok else 'CRASH: '+(r.stderr.strip().split('\n')[-1])[:150]))
        if ok and stage=='games.py':
            for line in r.stdout.strip().split('\n'):
                if 'note:' in line or 'updated' in line: print('      '+line.strip()[:150])
sys.exit(1 if fails else 0)
