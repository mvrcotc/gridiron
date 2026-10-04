"""Play-by-play, boiled down for the blind-spot scan: each team's success rate in every regular-season game, and each
quarterback's dropback EPA in every game.

GridIron's ratings are built from weekly team box scores (yards, touchdowns, turnovers, team EPA). Play-by-play is the
data sharper models use -- success rate, garbage time down-weighted, each quarterback's own efficiency -- so it is
tested as two blind-spot candidates (pipeline/blindspots.py): play-by-play team ratings, and the quarterback actually
starting measured against the quarterbacks the team's ratings were built on. Neither enters the game model unless the
scan proves it on seasons it never saw and the owner approves.

Per season, pipeline/learning/pbp/<season>.csv holds one row per team-game (kind T) and per quarterback-game (kind Q):
  T: game_id, season, week, team, opp, success rate and EPA per play (plays with win probability outside 5-95% count a
     quarter), weight, plays
  Q: game_id, season, week, team, qb (gsis id), dropback EPA summed and its weight, dropbacks
Kneels and spikes are dropped. Finished seasons are fetched once and kept; the current season is fetched every daily run.

   python3 pipeline/pbp.py --fetch      fetch missing seasons and the current one from nflverse (daily lane)"""
import os, sys, csv, gzip, io, time, datetime, urllib.request
from collections import defaultdict
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,'learning','pbp')
URL='https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_%d.csv.gz'
FIRST=2018
REL={'STL':'LA','SD':'LAC','OAK':'LV'}
FIELDS=('kind','game_id','season','week','team','opp','qb','sr','epa','w','n')

def season_now():
    t=datetime.date.today(); return t.year if t.month>=3 else t.year-1
def fnum(v):
    try: return float(v)
    except (TypeError,ValueError): return None

def boil(rows):
    """play rows (dicts) -> team-game and quarterback-game rows"""
    T=defaultdict(lambda:[0.0,0.0,0.0,0]); Q=defaultdict(lambda:[0.0,0.0,0]); meta={}
    for r in rows:
        if r.get('season_type')!='REG' or r.get('play_type') not in ('pass','run'): continue
        e=fnum(r.get('epa')); pos=r.get('posteam'); de=r.get('defteam')
        if e is None or not pos or not de or r.get('qb_kneel')=='1' or r.get('qb_spike')=='1': continue
        wp=fnum(r.get('wp')); w=1.0 if wp is not None and 0.05<=wp<=0.95 else 0.25
        pos,de=REL.get(pos,pos),REL.get(de,de); k=(r['game_id'],pos); meta[k]=(int(r['season']),int(r['week']),de)
        t=T[k]; t[0]+=w*(fnum(r.get('success')) or 0.0); t[1]+=w*e; t[2]+=w; t[3]+=1
        if r.get('qb_dropback')=='1' and r.get('passer_player_id'):
            q=Q[(r['game_id'],pos,r['passer_player_id'])]; q[0]+=w*e; q[1]+=w; q[2]+=1
    out=[]
    for k,t in T.items():
        s,wk,de=meta[k]; out.append(dict(kind='T',game_id=k[0],season=s,week=wk,team=k[1],opp=de,qb='',sr=round(t[0]/t[2],5),epa=round(t[1]/t[2],5),w=round(t[2],2),n=t[3]))
    for k,q in Q.items():
        s,wk,_=meta[(k[0],k[1])]; out.append(dict(kind='Q',game_id=k[0],season=s,week=wk,team=k[1],opp='',qb=k[2],sr='',epa=round(q[0],4),w=round(q[1],2),n=q[2]))
    out.sort(key=lambda x:(x['week'],x['game_id'],x['kind'],x['team'],x['qb']))
    return out

def fetch(season):
    with urllib.request.urlopen(URL%season,timeout=120) as r: raw=r.read()
    rows=boil(csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(raw)),encoding='utf-8')))
    if not rows: raise ValueError('no regular-season plays in %d'%season)
    os.makedirs(OUT,exist_ok=True); p=os.path.join(OUT,'%d.csv'%season)
    with open(p+'.part','w',newline='',encoding='utf-8') as f:
        wr=csv.DictWriter(f,fieldnames=FIELDS); wr.writeheader(); wr.writerows(rows)
    os.replace(p+'.part',p); return len(rows)

def load():
    """kind -> list of rows, every season on file, in week order"""
    out={'T':[],'Q':[]}
    if not os.path.isdir(OUT): return out
    for f in sorted(os.listdir(OUT)):
        if not f.endswith('.csv'): continue
        for r in csv.DictReader(open(os.path.join(OUT,f),encoding='utf-8')):
            r['season']=int(r['season']); r['week']=int(r['week']); r['w']=float(r['w']); r['epa']=float(r['epa']); r['n']=int(r['n'])
            if r['kind']=='T': r['sr']=float(r['sr'])
            out[r['kind']].append(r)
    for v in out.values(): v.sort(key=lambda r:(r['season'],r['week']))
    return out

if __name__=='__main__':
    if '--fetch' in sys.argv:
        S=season_now(); have={int(f[:4]) for f in os.listdir(OUT) if f.endswith('.csv')} if os.path.isdir(OUT) else set()
        for y in range(FIRST,S+1):
            if y in have and y!=S: continue
            try: print('play-by-play %d: %d rows'%(y,fetch(y)))
            except Exception as e: print('play-by-play %d not fetched (%s); the scan uses what is on file'%(y,str(e)[:80]))
            time.sleep(0.3)
    L=load(); print('play-by-play on file: %d team-games, %d quarterback-games'%(len(L['T']),len(L['Q'])))
