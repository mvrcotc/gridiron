"""Live cross-checks against independent services: stadium coordinates and elevation (Open-Meteo
geodata vs each team's ESPN home city), plus drift in lines and wind since the dataset was built."""
import os, re, json, math, time, datetime, urllib.request, urllib.parse
from common import num, APP, ROOT

def get(u):
    for i in range(3):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u),timeout=25))   # ESPN's site API 403s browser UAs
        except Exception:
            if i==2: raise
            time.sleep(1)
def miles(a,b):
    t=math.pi/180; h=math.sin((b[0]-a[0])*t/2)**2+math.cos(a[0]*t)*math.cos(b[0]*t)*math.sin((b[1]-a[1])*t/2)**2
    return 2*3958.8*math.asin(math.sqrt(h))

def run(A):
    A.section('live cross-checks'); D=A.D
    ua=re.search(r"UA=\{'User-Agent':'([^']*)'\}",open(os.path.join(os.path.dirname(APP),'refresh.py')).read())
    try:
        hdr={'User-Agent':ua.group(1)} if ua else {}
        code=urllib.request.urlopen(urllib.request.Request('https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',headers=hdr),timeout=25).status
        A.check('L00','refresh.py\'s request header is accepted by ESPN\'s site API',[] if code==200 else ['HTTP %s'%code])
    except Exception as e:
        A.check('L00','refresh.py\'s request header is accepted by ESPN\'s site API',['scoreboard fetch with User-Agent %r fails: %r -- the espn refresh stage cannot run'%(hdr.get('User-Agent'),e)])
    src=open(os.path.join(APP,'context.js'),encoding='utf-8').read()
    ST={m.group(1):(float(m.group(2)),float(m.group(3)),int(m.group(4)),m.group(5)) for m in
        re.finditer(r"([A-Z]{2,3}):\{v:'[^']*',la:(-?[\d.]+),lo:(-?[\d.]+),el:(-?\d+),tz:'([^']*)'",src)}
    try: teams=get('https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams')['sports'][0]['leagues'][0]['teams']
    except Exception as e:
        A.warn('L0','Live checks skipped: ESPN unreachable',[repr(e)]); return
    loc=[]; elev=[]; n=0
    for t in teams:
        ab=t['team']['abbreviation']; s=ST.get(ab)
        if not s: loc.append('%s has no stadium coordinates in context.js'%ab); continue
        try:
            ad=((get('https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/%s'%ab)['team'].get('franchise') or {}).get('venue') or {}).get('address') or {}
            geo=get('https://geocoding-api.open-meteo.com/v1/search?'+urllib.parse.urlencode(dict(name=ad.get('city',''),count=10,countryCode='US'))).get('results') or []
            dem=get('https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&current=temperature_2m'%(s[0],s[1])).get('elevation')
        except Exception as e:
            loc.append('%s lookup failed: %r'%(ab,e)); continue
        n+=1
        if geo:
            dmin=min(miles((s[0],s[1]),(r['latitude'],r['longitude'])) for r in geo)
            if dmin>40: loc.append('%s stadium sits %.0f mi from its home city %s, %s'%(ab,dmin,ad.get('city'),ad.get('state')))
        if dem is not None:
            ft=dem*3.28084
            if abs(ft-s[2])>max(200,0.12*ft): elev.append('%s elevation %d ft in app, terrain model %.0f ft'%(ab,s[2],ft))
        time.sleep(0.05)
    A.check('L1','Every team\'s stadium coordinates lie within 40 miles of its ESPN home city (drives travel miles)',loc,n)
    A.check('L2','Stadium elevations agree with Open-Meteo terrain data',elev,n)

    try: sb={e['id']:e for e in get('https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard')['events']}
    except Exception as e: sb={}; A.warn('L3','Could not refetch the scoreboard',[repr(e)])
    drift=[]
    for g in D['games']:
        o=((sb.get(g['id']) or {}).get('competitions') or [{}])[0].get('odds') or []
        if not o or g.get('state')=='post': continue
        if o[0].get('details')!=g.get('det') or abs(num(o[0].get('overUnder'),0)-num(g.get('ou'),0))>0.01:
            drift.append('%s@%s built with %s / %s, now %s / %s'%(g['a'],g['h'],g.get('det'),g.get('ou'),o[0].get('details'),o[0].get('overUnder')))
    if sb: A.check('L3','Lines unchanged since the dataset was built',drift,len(D['games']),warn=True)

    wd=[]
    for g in D['games']:
        if g.get('indoor') or g.get('state')=='post' or g.get('wsus') is None: continue
        s=ST.get('MCG') if g.get('neutral') else ST.get(g['h'])
        if not s: continue
        try:
            H=get('https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&hourly=wind_speed_10m&wind_speed_unit=mph&timezone=UTC&forecast_days=7'%(s[0],s[1]))['hourly']
            k=datetime.datetime.fromisoformat(g['date'].replace('Z','+00:00')).strftime('%Y-%m-%dT%H:00')
            now=H['wind_speed_10m'][H['time'].index(k)]
            if abs(now-g['wsus'])>4: wd.append('%s@%s sustained wind built %.1f mph, forecast now %.1f'%(g['a'],g['h'],g['wsus'],now))
        except Exception: continue
    A.check('L4','Sustained-wind forecast within 4 mph of the value projections were built on',wd,warn=True)

    import importlib.util
    spec=importlib.util.spec_from_file_location('gridiron_refresh',os.path.join(ROOT,'refresh.py')); R=importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
    bad=[]; want=R.SOURCES(R.season_now())
    for path,name in want:
        u='%s/%s'%(R.NFLVERSE,path)
        try:
            code=urllib.request.urlopen(urllib.request.Request(u,headers={'Range':'bytes=0-0'}),timeout=30).status
            if code not in (200,206): bad.append('%s -> HTTP %s'%(path,code))
        except Exception as e: bad.append('%s -> %r'%(path,e))
    A.check('L5','Every nflverse source the refresh downloads still exists at its URL',bad,len(want))
