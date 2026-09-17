"""Team standings and season statistics for the Teams page and each game's "Season so far" panel.

Results come from the nflverse schedule (games_all.csv); a slate game ESPN already lists as final counts before
nflverse catches up. Yards and turnovers come from nflverse team box scores (tw<season>.csv) for the games they
cover. Teams are ordered by win percentage, then division win percentage, then point differential -- simpler than
the NFL's full tiebreakers, and the page says so."""
import os, csv, json, time
from collections import defaultdict, Counter
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
DIVS=[('AFC East','AFC','BUF MIA NE NYJ'),('AFC North','AFC','BAL CIN CLE PIT'),('AFC South','AFC','HOU IND JAX TEN'),('AFC West','AFC','DEN KC LAC LV'),
      ('NFC East','NFC','DAL NYG PHI WAS'),('NFC North','NFC','CHI DET GB MIN'),('NFC South','NFC','ATL CAR NO TB'),('NFC West','NFC','ARI LA SEA SF')]
NAMES=dict(BUF='Bills',MIA='Dolphins',NE='Patriots',NYJ='Jets',BAL='Ravens',CIN='Bengals',CLE='Browns',PIT='Steelers',HOU='Texans',IND='Colts',
           JAX='Jaguars',TEN='Titans',DEN='Broncos',KC='Chiefs',LAC='Chargers',LV='Raiders',DAL='Cowboys',NYG='Giants',PHI='Eagles',WAS='Commanders',
           CHI='Bears',DET='Lions',GB='Packers',MIN='Vikings',ATL='Falcons',CAR='Panthers',NO='Saints',TB='Buccaneers',ARI='Cardinals',LA='Rams',
           SEA='Seahawks',SF='49ers')
DIVOF={t:d for d,_,ts in DIVS for t in ts.split()}; CONF={t:c for _,c,ts in DIVS for t in ts.split()}
N2E={'LA':'LAR','WAS':'WSH'}; E2N={v:k for k,v in N2E.items()}
fnum=lambda v:float(v) if v not in ('',None,'NA') else None

D=json.load(open(os.path.join(DATA,'gi2.json'),encoding='utf-8'))
ROWS=[r for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'),encoding='utf-8')) if r['game_type']=='REG']
BY_ESPN={str(r.get('espn') or '').split('.')[0]:r for r in ROWS if r.get('espn')}
ESPN_FINAL={g['id']:(g['sc']['a'],g['sc']['h']) for g in D['games'] if g.get('state')=='post' and g.get('sc')}
slate=[(int(BY_ESPN[g['id']]['season']),int(BY_ESPN[g['id']]['week'])) for g in D['games'] if g['id'] in BY_ESPN]
CURRENT=Counter(slate).most_common(1)[0][0][0] if slate else max(int(r['season']) for r in ROWS if r['home_score'])

def final(r):
    if r['home_score'] not in ('',None): return float(r['away_score']),float(r['home_score']),'nflverse'
    e=str(r.get('espn') or '').split('.')[0]
    if e in ESPN_FINAL: return float(ESPN_FINAL[e][0]),float(ESPN_FINAL[e][1]),'espn'
    return None

def box(season):
    """(game_id, team) -> (yards, giveaways) from nflverse team box scores"""
    p=os.path.join(DATA,'tw%d.csv'%season); out={}
    if not os.path.exists(p): return out
    for r in csv.DictReader(open(p,encoding='utf-8')):
        if r.get('season_type')!='REG': continue
        n=lambda k:fnum(r.get(k)) or 0.0
        out[(r['game_id'],r['team'])]=(n('passing_yards')+n('rushing_yards'),
                                       n('passing_interceptions')+n('rushing_fumbles_lost')+n('receiving_fumbles_lost')+n('sack_fumbles_lost'))
    return out

def season_table(season):
    sched=[r for r in ROWS if int(r['season'])==season]
    games=sorted([(r,final(r)) for r in sched if final(r)],key=lambda x:(int(x[0]['week']),x[0]['gameday'] or '',x[0]['game_id']))
    B=box(season)
    T={t:dict(w=0,l=0,t=0,gp=0,pf=0.0,pa=0.0,div=[0,0,0],conf=[0,0,0],home=[0,0,0],away=[0,0,0],ats=[0,0,0],ou=[0,0,0],seq=[],
              yds=0.0,ydsa=0.0,ygp=0,give=0.0,take=0.0) for t in NAMES}
    src=Counter()
    for r,(asc,hsc,how) in games:
        src[how]+=1; h,a=r['home_team'],r['away_team']
        if h not in T or a not in T: continue
        sl,tl=fnum(r.get('spread_line')),fnum(r.get('total_line'))
        for team,opp,pf,pa,side in ((h,a,hsc,asc,'home'),(a,h,asc,hsc,'away')):
            x=T[team]; k=0 if pf>pa else (1 if pf<pa else 2)
            x['wlt'[k]]+=1; x['gp']+=1; x['pf']+=pf; x['pa']+=pa; x['seq'].append('WLT'[k])
            if r['location']=='Home': x[side][k]+=1
            if DIVOF[team]==DIVOF[opp]: x['div'][k]+=1
            if CONF[team]==CONF[opp]: x['conf'][k]+=1
            if sl is not None:                                   # spread_line is positive when the home team is favoured
                cov=(hsc-asc-sl)*(1 if side=='home' else -1); x['ats'][0 if cov>0 else (1 if cov<0 else 2)]+=1
            if tl is not None:
                ov=hsc+asc-tl; x['ou'][0 if ov>0 else (1 if ov<0 else 2)]+=1
            mine,theirs=B.get((r['game_id'],team)),B.get((r['game_id'],opp))
            if mine and theirs: x['yds']+=mine[0]; x['ydsa']+=theirs[0]; x['give']+=mine[1]; x['take']+=theirs[1]; x['ygp']+=1
    out={}
    for t,x in T.items():
        gp=x['gp']; seq=x['seq']; streak=''
        if seq:
            n=1
            while n<len(seq) and seq[-1-n]==seq[-1]: n+=1
            streak='%s%d'%(seq[-1],n)
        out[t]=dict(ab=N2E.get(t,t),w=x['w'],l=x['l'],t=x['t'],gp=gp,pct=round((x['w']+0.5*x['t'])/gp,3) if gp else None,
                    div=x['div'],conf=x['conf'],home=x['home'],away=x['away'],pf=int(x['pf']),pa=int(x['pa']),diff=int(x['pf']-x['pa']),
                    pfg=round(x['pf']/gp,1) if gp else None,pag=round(x['pa']/gp,1) if gp else None,streak=streak,last5=''.join(seq[-5:]),
                    ats=x['ats'],ou=x['ou'],ypg=round(x['yds']/x['ygp'],1) if x['ygp'] else None,ypga=round(x['ydsa']/x['ygp'],1) if x['ygp'] else None,
                    to=int(x['take']-x['give']) if x['ygp'] else None,boxgp=x['ygp'])
    def key(t):
        r=out[t]; dp=(r['div'][0]+0.5*r['div'][2])/max(1,sum(r['div']))
        return (-(r['pct'] if r['pct'] is not None else -1),-dp,-r['diff'],t)
    for d,_,ts in DIVS:
        for i,t in enumerate(sorted(ts.split(),key=key)): out[t]['rank']=i+1
    weeks=[int(r['week']) for r,_ in games]
    return dict(through=max(weeks) if weeks else 0,final_games=len(games),scheduled=len(sched),from_espn=src.get('espn',0),rows=out)

def schedule(season):
    """every regular-season game as [week, date, away, home, away pts, home pts, closing spread_line, closing total_line, espn id,
    overtime, where the score came from]; scores are null until final. spread_line is the home margin the line expects"""
    out=[]
    for r in sorted((r for r in ROWS if int(r['season'])==season),key=lambda r:(int(r['week']),r['gameday'] or '',r['gametime'] or '',r['game_id'])):
        f=final(r); sl,tl=fnum(r.get('spread_line')),fnum(r.get('total_line'))
        out.append([int(r['week']),r['gameday'],r['away_team'],r['home_team'],int(f[0]) if f else None,int(f[1]) if f else None,
                    sl,tl,str(r.get('espn') or '').split('.')[0] or None,1 if r.get('overtime')=='1' and f else 0,f[2] if f else None])
    return out

meta=((D.get('teams') or {}).get('meta')) or {}
for t in NAMES: meta.setdefault(t,{})
for g in D['games']:                                   # ESPN colours and names for teams on the slate; kept for teams on a bye
    for s in ('a','h'):
        t=E2N.get(g[s],g[s])
        if t in meta: meta[t].update(color=g[s+'c'],alt=g.get(s+'a'),full=g.get(s+'n'))
for t in NAMES: meta[t].update(ab=N2E.get(t,t),name=NAMES[t],div=DIVOF[t],conf=CONF[t])
seasons=[CURRENT,CURRENT-1]
D['teams']=dict(current=CURRENT,seasons=seasons,divisions=[dict(name=d,conf=c,teams=ts.split()) for d,c,ts in DIVS],meta=meta,
                by={str(s):season_table(s) for s in seasons},games={str(s):schedule(s) for s in seasons},updated=time.strftime('%Y-%m-%dT%H:%MZ',time.gmtime()),
                note='Teams are ordered by win percentage, then division record, then point differential; the NFL’s official tiebreakers go further.')
# the slate's week, from the schedule (every game type, so playoff rounds get their names); the page labels itself with this
ALLG={str(r.get('espn') or '').split('.')[0]:r for r in csv.DictReader(open(os.path.join(DATA,'games_all.csv'),encoding='utf-8')) if r.get('espn')}
SW=[(int(ALLG[g['id']]['season']),int(ALLG[g['id']]['week']),ALLG[g['id']]['game_type']) for g in D['games'] if g['id'] in ALLG]
ROUND={'WC':'Wild Card round','DIV':'Divisional round','CON':'Conference championships','SB':'Super Bowl'}
if SW:
    s_,w_,t_=Counter(SW).most_common(1)[0][0]
    D['slate']=dict(season=s_,week=w_,type=t_,label=ROUND.get(t_,'Week %d'%w_))
else: D['slate']=dict(season=CURRENT,week=None,type=None,label='%d season'%CURRENT)
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
for s in seasons:
    b=D['teams']['by'][str(s)]
    lead=sorted(b['rows'].items(),key=lambda kv:(-(kv[1]['pct'] or -1),-kv[1]['diff']))[0]
    print('%d: %d of %d games final through week %d (%d from ESPN ahead of nflverse); best record %s %d-%d-%d'%(
        s,b['final_games'],b['scheduled'],b['through'],b['from_espn'],lead[1]['ab'],lead[1]['w'],lead[1]['l'],lead[1]['t']))
