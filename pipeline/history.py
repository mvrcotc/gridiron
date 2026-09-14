"""GridIron's historical memory: every season nflverse publishes, in one SQLite database, for training and backtesting.

  games        schedule, final scores, closing lines, starting QBs, venue, weather   (1999 -> now)
  team_week    team box scores per game                                              (1999 -> now)
  player_week  every player's weekly stat line                                       (1999 -> now)
  plays        play-by-play: game state, down/distance, field position, EPA, win prob (1999 -> now)
  loads        what was loaded, when, and how many rows

Incremental: a season already loaded is skipped unless it is the current or previous season, which still change.
   python3 pipeline/history.py [--from 1999] [--rebuild]"""
import os, sys, io, time, sqlite3, datetime, urllib.request
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
HIST=os.path.join(DATA,'history'); os.makedirs(HIST,exist_ok=True); DB=os.path.join(HIST,'history.sqlite')
REL='https://github.com/nflverse/nflverse-data/releases/download'
today=datetime.date.today(); CUR=today.year if today.month>=3 else today.year-1
FIRST=int(sys.argv[sys.argv.index('--from')+1]) if '--from' in sys.argv else 1999
REBUILD='--rebuild' in sys.argv
PLAY_COLS=['play_id','game_id','old_game_id','season','season_type','week','game_date','home_team','away_team','posteam','defteam','posteam_type',
 'side_of_field','yardline_100','qtr','quarter_seconds_remaining','half_seconds_remaining','game_seconds_remaining','game_half','drive','down','ydstogo',
 'goal_to_go','play_type','yards_gained','shotgun','no_huddle','qb_dropback','qb_scramble','pass_attempt','rush_attempt','complete_pass','incomplete_pass',
 'interception','fumble_lost','sack','touchdown','pass_touchdown','rush_touchdown','return_touchdown','safety','field_goal_result','kick_distance',
 'extra_point_result','two_point_conv_result','penalty','posteam_timeouts_remaining','defteam_timeouts_remaining','home_timeouts_remaining',
 'away_timeouts_remaining','total_home_score','total_away_score','posteam_score','defteam_score','score_differential','posteam_score_post',
 'defteam_score_post','score_differential_post','ep','epa','wp','def_wp','home_wp','away_wp','wpa','vegas_wp','vegas_home_wp','success','cpoe',
 'air_yards','yards_after_catch','passer_player_id','receiver_player_id','rusher_player_id','fantasy_player_id','result','total','spread_line',
 'total_line','roof','surface','temp','wind','home_coach','away_coach']

def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(url,timeout=180) as r: return r.read()
        except Exception as e:
            if i==3: raise
            time.sleep(4*(i+1))

con=sqlite3.connect(DB); con.execute('PRAGMA journal_mode=WAL'); con.execute('PRAGMA synchronous=NORMAL')
con.execute('CREATE TABLE IF NOT EXISTS loads(tbl TEXT, season INTEGER, rows INTEGER, bytes INTEGER, loaded_at TEXT, PRIMARY KEY(tbl,season))')
has_table=lambda t: con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone() is not None
loaded=lambda t,s: con.execute('SELECT 1 FROM loads WHERE tbl=? AND season=?',(t,s)).fetchone() is not None
CANON={}
def store(tbl,season,df,nbytes):
    if tbl not in CANON:
        CANON[tbl]=[r[1] for r in con.execute('PRAGMA table_info(%s)'%tbl)] if has_table(tbl) else list(df.columns)
    extra=[c for c in df.columns if c not in CANON[tbl]]
    if extra and has_table(tbl):
        for c in extra: con.execute('ALTER TABLE %s ADD COLUMN "%s"'%(tbl,c))
        CANON[tbl]+=extra
    df=df.reindex(columns=CANON[tbl])
    if has_table(tbl) and season is not None: con.execute('DELETE FROM %s WHERE season=?'%tbl,(season,))
    df.to_sql(tbl,con,if_exists='append',index=False,chunksize=20000)
    con.execute('INSERT OR REPLACE INTO loads VALUES (?,?,?,?,?)',(tbl,-1 if season is None else season,len(df),nbytes,time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
    con.commit()

t0=time.time()
b=get(REL+'/schedules/games.csv'); g=pd.read_csv(io.BytesIO(b),low_memory=False)
if has_table('games'): con.execute('DROP TABLE games')
CANON.pop('games',None); store('games',None,g,len(b))
print('games       %6d rows  (%d-%d)'%(len(g),g['season'].min(),g['season'].max()),flush=True)

for season in range(FIRST,CUR+1):
    fresh=season>=CUR-1 or REBUILD
    for tbl,path,reader in (
        ('team_week','stats_team/stats_team_week_%d.csv'%season,lambda b: pd.read_csv(io.BytesIO(b),low_memory=False)),
        ('player_week','stats_player/stats_player_week_%d.csv'%season,lambda b: pd.read_csv(io.BytesIO(b),low_memory=False)),
        ('plays','pbp/play_by_play_%d.csv.gz'%season,lambda b: pd.read_csv(io.BytesIO(b),compression='gzip',low_memory=False,usecols=lambda c: c in PLAY_COLS))):
        if loaded(tbl,season) and not fresh: continue
        try: raw=get('%s/%s'%(REL,path))
        except Exception as e:
            print('%-11s %d  unavailable (%s)'%(tbl,season,str(e)[:60]),flush=True); continue
        df=reader(raw)
        if 'season' not in df.columns: df['season']=season
        store(tbl,season,df,len(raw))
        print('%-11s %d  %7d rows  %6.1f MB  %4.0fs'%(tbl,season,len(df),len(raw)/1048576,time.time()-t0),flush=True)

for sql in ('CREATE INDEX IF NOT EXISTS ix_plays_game ON plays(season,game_id)','CREATE INDEX IF NOT EXISTS ix_pw_player ON player_week(player_id,season,week)',
            'CREATE INDEX IF NOT EXISTS ix_tw_team ON team_week(team,season,week)','CREATE INDEX IF NOT EXISTS ix_games_id ON games(game_id)',
            'CREATE INDEX IF NOT EXISTS ix_games_espn ON games(espn)'):
    con.execute(sql)
con.commit()
print('\nsummary:')
for t in ('games','team_week','player_week','plays'):
    n,lo,hi=con.execute('SELECT COUNT(*),MIN(season),MAX(season) FROM %s'%t).fetchone()
    print('  %-11s %9d rows  %s-%s'%(t,n,lo,hi))
con.close()
print('  database    %.1f MB  (%s)  built in %.0fs'%(os.path.getsize(DB)/1048576,DB,time.time()-t0))
