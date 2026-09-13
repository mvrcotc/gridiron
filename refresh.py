#!/usr/bin/env python3
"""
GridIron weekly refresh.

  python3 refresh.py              rebuild everything for the current week
  python3 refresh.py --stage wx   run one stage
  python3 refresh.py --list       show the stages

Every stage writes into data/ and is safe to re-run: the weather and injury passes refuse
to apply twice to the same projections. Nothing here is hand-tuned per week:
the fitted constants in pipeline/*.json were fitted once on historical seasons and are
reused, so a refresh cannot quietly re-tune the model to flatter the current slate.
"""
import os,sys,json,subprocess,time,urllib.request,datetime,shutil,re,glob
LANE=None

ROOT=os.path.dirname(os.path.abspath(__file__))
DATA=os.path.join(ROOT,'data'); PIPE=os.path.join(ROOT,'pipeline'); APP=os.path.join(ROOT,'app')
os.makedirs(DATA,exist_ok=True)
GI=os.path.join(DATA,'gi2.json')
UA={}   # ESPN's site API returns 403 to browser-style User-Agents; urllib's default is accepted

def say(m): print('  '+m,flush=True)
def head(m): print('\n\033[1m%s\033[0m'%m,flush=True)
def fetch(url,dest=None,tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=60) as r:
                b=r.read()
            if dest:
                os.makedirs(os.path.dirname(dest),exist_ok=True); tmp=dest+'.part'
                open(tmp,'wb').write(b); os.replace(tmp,dest); return dest        # never leave a half-written file
            return json.loads(b)
        except Exception as e:
            if i==tries-1: raise
            time.sleep(1.2)

NFLVERSE='https://github.com/nflverse/nflverse-data/releases/download'
def season_now():
    t=datetime.date.today()
    return t.year if t.month>=3 else t.year-1

# ------------------------------------------------------------------ stages
def SOURCES(S):
    """every nflverse file the pipeline and the audit read: (release path, local name under data/)"""
    return ([('stats_team/stats_team_week_%d.csv'%y,'tw%d.csv'%y) for y in range(S-7,S+1)]+
            [('schedules/games.csv','games_all.csv'),
             ('weekly_rosters/roster_weekly_%d.csv'%S,'rost%02d.csv'%(S%100)),
             ('depth_charts/depth_charts_%d.csv'%S,'raw/dc.csv'),
             ('snap_counts/snap_counts_%d.csv'%(S-1),'snaps%02d.csv'%((S-1)%100)),
             ('snap_counts/snap_counts_%d.csv'%S,'snaps%02d.csv'%(S%100)),
             ('stats_player/stats_player_week_%d.csv'%S,'stw%02d.csv'%(S%100)),
             ('stats_player/stats_player_week_%d.csv'%(S-1),'stw%02d.csv'%((S-1)%100)),
             ('officials/officials.csv','officials.csv'),
             ('players_components/players.csv','players_all.csv'),
             ('pfr_advstats/advstats_season_def.csv','raw/cov.csv')])

def stage_sources():
    """nflverse releases; every file is required, validated and written atomically"""
    want=SOURCES(season_now())
    if LANE=='live' and os.environ.get('SOURCES_CACHED')=='true' and all(os.path.exists(os.path.join(DATA,n)) for _,n in want):
        say("restored from this 6-hour window's cache (%d files)"%len(want)); return
    fails=[]
    for path,name in want:
        dest=os.path.join(DATA,name)
        try:
            fetch('%s/%s'%(NFLVERSE,path),dest)
            with open(dest,encoding='utf-8') as f: hdr=f.readline()
            if hdr.count(',')<3: raise ValueError('not a CSV header: %r'%hdr[:50])
            say('%-22s %9.1f KB'%(name,os.path.getsize(dest)/1024))
        except Exception as e:
            fails.append('%s (%s)'%(name,str(e)[:70]))
    if fails: raise SystemExit('sources failed: '+'; '.join(fails))

def stage_espn():
    """this week's scoreboard and per-game summaries, written in the raw layout the stages and audit read"""
    raw=os.path.join(DATA,'raw','espn'); os.makedirs(raw,exist_ok=True)
    sb=fetch('https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard')
    json.dump(sb,open(os.path.join(raw,'sb2.json'),'w'))
    say('scoreboard: %d games, week %s'%(len(sb.get('events',[])),(sb.get('week') or {}).get('number')))
    n=0
    for e in sb.get('events',[]):
        try:
            s=fetch('https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=%s'%e['id'])
            json.dump(s,open(os.path.join(raw,'s_%s.json'%e['id']),'w')); n+=1
            if e['competitions'][0]['status']['type']['state']=='post':
                json.dump(s,open(os.path.join(raw,'f_%s.json'%e['id']),'w'))
            time.sleep(0.2)
        except Exception as ex: say('summary %s failed: %s'%(e['id'],str(ex)[:60]))
    say('summaries saved for %d games'%n)
    if n<len(sb.get('events',[])): raise SystemExit('only %d of %d game summaries fetched'%(n,len(sb.get('events',[]))))

def stage_weather():
    """Open-Meteo at each venue: sustained 10m wind at kickoff for every game, and the recorded conditions for games
    already played. A kickoff hour outside the forecast window is reported, never silently replaced by another hour."""
    src=open(os.path.join(APP,'context.js'),encoding='utf-8').read()
    STAD={m.group(1):(float(m.group(2)),float(m.group(3))) for m in re.finditer(r"([A-Z]{2,3}):\{v:'[^']*',la:(-?[\d.]+),lo:(-?[\d.]+)",src)}
    NEU={m.group(1):(float(m.group(2)),float(m.group(3))) for m in re.finditer(r"'([^']+)':\{la:(-?[\d.]+),lo:(-?[\d.]+)",src)}
    def wmo(c):
        c=int(c or 0)
        for codes,fam,label in (((0,1),'sun','Clear'),((2,),'cloud','Partly cloudy'),((3,),'cloud','Overcast'),((45,48),'cloud','Fog'),
                                (tuple(range(51,58)),'rain','Drizzle'),(tuple(range(61,68))+(80,81,82),'rain','Rain'),
                                (tuple(range(71,78))+(85,86),'snow','Snow'),((95,96,99),'storm','Thunderstorm')):
            if c in codes: return fam,label
        return 'cloud','Cloudy'
    D=json.load(open(GI)); n=rec=0; missing=[]
    for g in D['games']:
        name='%s@%s'%(g['a'],g['h'])
        site=NEU.get(g.get('venue')) if g.get('neutral') else STAD.get(g['h'])
        if not site: missing.append('%s: no coordinates for %s'%(name,g.get('venue'))); continue
        kick=datetime.datetime.fromisoformat(g['date'].replace('Z','+00:00'))
        u=('https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&hourly=wind_speed_10m,wind_gusts_10m,temperature_2m,precipitation,weather_code'
           '&wind_speed_unit=mph&temperature_unit=fahrenheit&timezone=UTC&past_days=7&forecast_days=16')%site
        try: H=fetch(u)['hourly']
        except Exception as e: missing.append('%s: %s'%(name,str(e)[:60])); continue
        want=kick.strftime('%Y-%m-%dT%H:00')
        if want not in H['time']: missing.append('%s: kickoff hour %s outside the forecast window'%(name,want)); continue
        i=H['time'].index(want)
        g['wsus']=round(H['wind_speed_10m'][i],1); g['wgust2']=round(H['wind_gusts_10m'][i],1); n+=1
        if g.get('state')=='post' and g.get('rtemp') is None:
            g['rtemp']=round(H['temperature_2m'][i]); g['rwind']=round(H['wind_speed_10m'][i]); g['rgust']=round(H['wind_gusts_10m'][i])
            g['rprecip']=round(sum(x or 0 for x in H['precipitation'][i:i+3]),2); g['rfam'],g['rlabel']=wmo(H['weather_code'][i]); rec+=1
        time.sleep(0.2)
    json.dump(D,open(GI,'w'),separators=(',',':'))
    say('sustained wind for %d of %d venues; recorded conditions added for %d finished games'%(n,len(D['games']),rec))
    for m in missing: say('!! no weather: '+m)

def run(script,label):
    r=subprocess.run([sys.executable,os.path.join(PIPE,script)],capture_output=True,text=True,cwd=PIPE)
    tail=(r.stdout or r.stderr).strip().split('\n')[-3:]
    for t in tail: say(t[:150])
    if r.returncode:
        say('!! %s exited %d'%(label,r.returncode))
        for x in (r.stderr or '').strip().split('\n')[-6:]: say('   '+x[:160])
        raise SystemExit(1)
    return r.returncode==0

def stage_slate():    run('slate.py','slate')
def stage_roster():   run('roster.py','roster')
def stage_games():    run('games.py','games')
def stage_context():  run('context.py','context')
def stage_stats():    run('stats.py','stats')
def stage_results():  run('results.py','results')
def stage_injuries(): run('injuries.py','injuries')
def stage_project(): run('project.py','project')
def stage_backtest(): run('backtest.py','backtest')
def stage_predict(): run('predict.py','predict')
def stage_props():   run('props.py','props')

def stage_embed():
    """drop the fresh dataset into the page"""
    p=os.path.join(APP,'gridiron-v2.html')
    lines=open(p,encoding='utf-8').read().split('\n')
    i=[k for k,l in enumerate(lines) if l.startswith('<script id="gi-data"')]
    if not i: say('!! no gi-data script tag found'); return
    data=open(GI,encoding='utf-8').read()
    if '</script' in data.lower(): say('!! dataset contains a closing script tag'); return
    lines[i[0]]='<script id="gi-data" type="application/json">'+data+'</script>'
    open(p,'w',encoding='utf-8').write('\n'.join(lines))
    say('embedded %.1f KB into app/gridiron-v2.html'%(len(data)/1024))
    bad=sum(1 for b in open(os.path.join(APP,'app.js'),'rb').read() if b>127)
    say('app.js non-ascii bytes: %d %s'%(bad,'' if bad==0 else '<- convert to \\uXXXX before publishing'))

def stage_audit():
    """independent audit; any FAIL stops the run before anything is published"""
    mods=[] if LANE in (None,'daily') else [os.path.basename(p)[:-3] for p in sorted(glob.glob(os.path.join(ROOT,'tools','audit','a[0-8]_*.py')))]
    r=subprocess.run([sys.executable,os.path.join(ROOT,'tools','audit','run.py')]+mods,capture_output=True,text=True)
    for line in (r.stdout or '').strip().split('\n'):
        if line.startswith(('  FAIL','         -')) or line[:1].isdigit(): say(line[:170])
    if r.returncode:
        say('!! AUDIT FAILED -- nothing is published. Full report: data/audit_report.json'); raise SystemExit(1)
    say('audit clean')

def stage_ids(): run('ids.py','ids')

def stage_site():
    """static website for GitHub Pages"""
    r=subprocess.run([sys.executable,os.path.join(ROOT,'tools','build_site.py')],capture_output=True,text=True)
    for t in ((r.stdout or '')+(r.stderr or '')).strip().split('\n')[-9:]: say(t[:150])
    if r.returncode: raise SystemExit(1)

def stage_check():
    D=json.load(open(GI))
    g=D['games']; pr=D.get('pred',{})
    say('games %d | predictions %d | projections %d | props %d lines'
        %(len(g),len(pr),len(D.get('proj',{})),(D.get('props') or {}).get('n',0)))
    miss=[x['a']+'@'+x['h'] for x in g if x['id'] not in pr]
    if miss: say('!! no prediction for: '+', '.join(miss))
    out=[k for k,v in D.get('proj',{}).items() if v.get('out')]
    say('ruled out and zeroed: %d players across %d teams'%(len(out),len(D.get('redist',{}))))
    say('OK' if not miss else 'INCOMPLETE')

STAGES=[('sources', stage_sources, 'nflverse releases: schedule, rosters, depth charts, stats, snaps, officials, PFR'),
        ('espn',    stage_espn,    'scoreboard and per-game summaries'),
        ('slate',   stage_slate,   'the game list from ESPN; a new week replaces it'),
        ('roster',  stage_roster,  'players, depth charts, usage and coverage from fresh nflverse files'),
        ('weather', stage_weather, 'sustained wind at kickoff, recorded conditions for finished games'),
        ('games',   stage_games,   'status, scores, betting line, forecast weather from the ESPN snapshot'),
        ('context', stage_context, 'pace, pass rate, new QB, home edge, referee, two-source badges'),
        ('stats',   stage_stats,   'season and last-3 production, true target share'),
        ('results', stage_results, 'finished-game stat lines and PPR points'),
        ('injuries',stage_injuries,'injury report matched by ESPN id'),
        ('project', stage_project, 'player projections: model inputs -> weather -> injury fallout -> simulate'),
        ('backtest',stage_backtest,'track record from the exact live model'),
        ('predict', stage_predict, 'game predictions from the backtested model'),
        ('props',   stage_props,   'DraftKings prop lines'),
        ('ids',     stage_ids,     'ESPN athlete id -> gsis map for live box scores'),
        ('site',    stage_site,    'build site/ for GitHub Pages'),
        ('embed',   stage_embed,   'write the dataset into the claude.ai artifact page (legacy)'),
        ('audit',   stage_audit,   'independent audit -- stops the run on any failure'),
        ('check',   stage_check,   'sanity report')]
LANES={'live': ['sources','espn','slate','roster','weather','games','context','stats','results','injuries','project','predict','props','ids','site','audit'],
       'daily':['sources','espn','slate','roster','weather','games','context','stats','results','injuries','project','backtest','predict','props','ids','site','audit']}

if __name__=='__main__':
    a=sys.argv[1:]
    if '--list' in a:
        for n,_,d in STAGES: print('  %-9s %s'%(n,d))
        for k,v in LANES.items(): print('\n  lane %-6s %s'%(k,' > '.join(v)))
        sys.exit(0)
    names=[n for n,_,_ in STAGES]
    if '--lane' in a:
        LANE=a[a.index('--lane')+1]
        if LANE not in LANES: sys.exit('unknown lane %r (live, daily)'%LANE)
        todo=LANES[LANE]
    elif '--stage' in a: todo=[a[a.index('--stage')+1]]
    else: LANE='daily'; todo=LANES['daily']
    unknown=[x for x in todo if x not in names]
    if unknown: sys.exit('unknown stage(s): %s'%unknown)
    fns={n:(fn,d) for n,fn,d in STAGES}; t0=time.time()
    for name in todo:
        fn,desc=fns[name]; head('%s - %s'%(name,desc))
        try: fn()
        except SystemExit as e:
            if e.code not in (0,None):
                if not isinstance(e.code,int): say('!! '+str(e.code)[:300])
                say('!! stage %s failed -- stopping, nothing is published'%name); raise SystemExit(1)
        except Exception as e:
            say('!! stage %s crashed: %r -- stopping, nothing is published'%(name,e)); raise SystemExit(1)
    print('\ndone in %.0fs'%(time.time()-t0))
