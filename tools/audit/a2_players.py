"""Players, depth charts, usage, production, coverage, injuries and week-1 actuals -- every number
rebuilt from the raw nflverse files, with injuries and box scores cross-checked against ESPN by ID."""
import os, json, glob, statistics
from common import num, rows, DATA, RAW, APP, nfl, roster_rows

STATUS={'Out':'O','Questionable':'Q','Doubtful':'D','Injured Reserve':'IR','Physically Unable to Perform':'PUP',
        'Suspension':'SUSP','Non-Football Injury':'NFI'}

def crosswalks():
    pfr={}; esp={}
    for r in rows(os.path.join(DATA,'rost26.csv')):
        g=(r.get('gsis_id') or '').strip()
        if not g: continue
        if (r.get('pfr_id') or '').strip(): pfr[r['pfr_id'].strip()]=g
        if (r.get('espn_id') or '').strip(): esp[r['espn_id'].split('.')[0].strip()]=g
    for r in rows(os.path.join(DATA,'players_all.csv')):
        g=(r.get('gsis_id') or '').strip()
        if not g: continue
        if (r.get('pfr_id') or '').strip(): pfr.setdefault(r['pfr_id'].strip(),g)
        if (r.get('espn_id') or '').strip(): esp.setdefault(r['espn_id'].split('.')[0].strip(),g)
    return pfr,esp

def run(A):
    A.section('players & stats'); D=A.D; PL=D['players']; PFR,ESP=crosswalks()

    ros=roster_rows(A.D)
    bad=[]
    for g,p in PL.items():
        r=ros.get(g)
        if not r: continue
        j=r.get('jersey_number') or ''
        try: j=str(int(float(j)))
        except ValueError: j=''
        for label,mine,theirs in (('name',p['n'],r['full_name'].strip()),('team',nfl(p['t']),nfl(r['team'].strip())),
                                  ('position',p['p'],r['position'].strip()),('jersey',p['j'],j)):
            if mine!=theirs: bad.append('%s %s: app "%s", roster "%s"'%(g,label,mine,theirs))
    A.check('PL1','Name, team, position and jersey match the weekly roster for the slate',bad,len(PL))
    extra=[p['n'] for g,p in PL.items() if g not in ros]
    if extra: A.warn('PL1b','Players known only from the depth chart (no roster row to verify against)',extra,len(extra))

    # ---- depth chart: starters equal the latest raw chart ----
    raw={}; latest=''
    for r in rows(os.path.join(RAW,'dc.csv')):
        if r['dt']>latest: latest=r['dt']
        if r['dt']!=D['dt'] or r['pos_rank']!='1': continue
        fam={'3WR 1TE':{'QB':'QB','RB':'RB','WR':'WR','TE':'TE'}}.get(r['pos_grp'],{}).get(r['pos_abb'])
        if fam and r.get('gsis_id'): raw.setdefault((r['team'],fam),set()).add(r['gsis_id'].strip())
    bad=[]
    for (team,fam),want in raw.items():
        have=[e['g'] for e in (D['depth'].get(team,{}).get('o',{}).get(fam) or [])][:len(want)]
        if set(have)!=want:
            bad.append('%s %s starters: app %s, depth chart %s'%(team,fam,[PL.get(x,{}).get('n',x) for x in have],
                                                                  [PL.get(x,{}).get('n',x) for x in want]))
    A.check('PL2','Offensive starters (QB, RB, WR, TE) match the depth chart they were built from',bad,len(raw))
    A.check('PL2b','Depth chart is the newest one published',[] if latest==D['dt'] else
            ['app built on %s, newest in the file is %s'%(D['dt'],latest)],warn=True)
    bad=[]
    for gm in D['games']:
        for t in (gm['a'],gm['h']):
            o=(D['depth'].get(t) or {}).get('o',{})
            for fam,need in (('QB',1),('RB',1),('WR',3),('TE',1)):
                if len(o.get(fam) or [])<need: bad.append('%s has %d %s on its chart (needs %d)'%(t,len(o.get(fam) or []),fam,need))
    A.check('PL3','Every team on the slate has a QB, RB, three WRs and a TE',bad,32)

    # ---- usage from raw snap counts ----
    wk={}
    for r in rows(os.path.join(DATA,'snaps25.csv')):
        if r['game_type']!='REG': continue
        g=PFR.get(r['pfr_player_id'].strip())
        if g: wk.setdefault(g,{})[int(r['week'])]=100*max(num(r['offense_pct']),num(r['defense_pct']))
    bad=[]
    for g,u in D['usage'].items():
        w=wk.get(g)
        if not w: bad.append('%s has usage but no raw snap rows'%PL.get(g,{}).get('n',g)); continue
        ks=sorted(w); s=statistics.mean(w[k] for k in ks); s3=statistics.mean(w[k] for k in ks[-3:])
        if abs(s-u['s'])>0.15 or abs(s3-u['s3'])>0.15 or len(ks)!=u['g']:
            bad.append('%s snap share %.1f/%.1f/%dg, raw %.1f/%.1f/%dg'%(PL.get(g,{}).get('n',g),u['s'],u['s3'],u['g'],s,s3,len(ks)))
    A.check('PL4','Snap shares (season, last 3, games) recompute from raw snap counts',bad,len(D['usage']))

    # ---- production from raw weekly stats ----
    K={'tgt':'targets','rec':'receptions','ry':'receiving_yards','car':'carries','ru':'rushing_yards','rutd':'rushing_tds',
       'att':'attempts','cmp':'completions','py':'passing_yards','ptd':'passing_tds'}
    wks={}; team_tgt={}
    for r in rows(os.path.join(DATA,'stw25.csv')):
        if r['season_type']!='REG': continue
        w=int(r['week']); wks.setdefault(r['player_id'],{})[w]=r
        team_tgt[(r['team'],w)]=team_tgt.get((r['team'],w),0)+num(r['targets'])
    bad=[]; share=[]
    for g,pr in D['prod'].items():
        W=wks.get(g)
        if not W: bad.append('%s has production but no raw rows'%PL.get(g,{}).get('n',g)); continue
        S=pr['S']
        for k,col in K.items():
            v=round(sum(num(W[w][col]) for w in W))
            if v!=int(S.get(k,0)): bad.append('%s season %s %s, raw %s'%(PL.get(g,{}).get('n',g),k,S.get(k,0),v))
        if len(W)!=S['g']: bad.append('%s games %s, raw %d'%(PL.get(g,{}).get('n',g),S['g'],len(W)))
        t=sum(num(W[w]['targets']) for w in W); tt=sum(team_tgt[(W[w]['team'],w)] for w in W)
        if S.get('ts') and t>=20 and tt:
            true=100*t/tt
            if abs(true-S['ts'])>1.0: share.append('%s shows %.1f%% target share; actual %.0f of %.0f team targets = %.1f%%'%(
                PL.get(g,{}).get('n',g),S['ts'],t,tt,true))
    A.check('PL5','Season totals recompute exactly from raw weekly stats',bad,len(D['prod']))
    share.sort(key=lambda s:-abs(float(s.split('= ')[1].rstrip('%'))-float(s.split('shows ')[1].split('%')[0])))
    A.check('PL6','Target share shown equals his targets / his team\'s targets in games he played',share,len(D['prod']))

    # ---- coverage from raw PFR advanced stats ----
    cov={}
    for r in rows(os.path.join(RAW,'cov.csv')):
        if r['season']=='2025':
            g=PFR.get(r['pfr_id'].strip())
            if g: cov[g]=r
    bad=[]
    for g,c in D['cov'].items():
        r=cov.get(g)
        if not r: bad.append('%s coverage has no raw row'%PL.get(g,{}).get('n',g)); continue
        for k in ('tgt','cmp','yds','td','int','prss'):
            if int(c[k])!=round(num(r[k])): bad.append('%s %s %s, raw %s'%(PL.get(g,{}).get('n',g),k,c[k],r[k]))
        if abs(num(c['rat'])-num(r['rat']))>0.05: bad.append('%s rating %s, raw %s'%(PL.get(g,{}).get('n',g),c['rat'],r['rat']))
        if num(r['tgt'])>0 and abs(c['cpct']-100*num(r['cmp'])/num(r['tgt']))>1.0:
            bad.append('%s completion %% shown %.1f, raw %s/%s = %.1f'%(PL.get(g,{}).get('n',g),c['cpct'],r['cmp'],r['tgt'],100*num(r['cmp'])/num(r['tgt'])))
        mt,cb=num(r.get('m_tkl')),num(r.get('comb'))
        if mt+cb>0 and abs(c['mt']-100*mt/(mt+cb))>1.5:
            bad.append('%s missed-tackle %% shown %.1f, raw %d missed / %d tackles = %.1f'%(PL.get(g,{}).get('n',g),c['mt'],mt,cb,100*mt/(mt+cb)))
    A.check('PL7','Coverage numbers (targets, completions, rating, completion %, missed tackles) match PFR',bad,len(D['cov']))

    # ---- injuries, rebuilt by ESPN athlete ID; name+team only where the crosswalk has no ID ----
    import unicodedata, re as _re
    def nrm(s):
        s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower().replace('.','').replace("'",'').replace('-',' ')
        return ' '.join(_re.sub(r'\b(jr|sr|ii|iii|iv|v)\b','',s).split())
    byname={}
    for g,p in PL.items(): byname.setdefault((nrm(p['n']),nfl(p['t'])),[]).append(g)
    files={}
    for q in sorted(glob.glob(os.path.join(RAW,'espn','s_*.json'))): files[os.path.basename(q)[2:]]=q
    for q in sorted(glob.glob(os.path.join(RAW,'espn','f_*.json'))): files[os.path.basename(q)[2:]]=q
    src={}; byname_only=[]
    for q in files.values():
        for blk in json.load(open(q)).get('injuries') or []:
            team=nfl((blk.get('team') or {}).get('abbreviation') or '')
            for it in blk.get('injuries') or []:
                a=it.get('athlete') or {}; g=ESP.get(str(a.get('id'))); how='id'
                if g not in PL:
                    c=byname.get((nrm(a.get('displayName')),team),[]); g=c[0] if len(c)==1 else None; how='name'
                if g: src[g]=dict(s=STATUS.get(it.get('status'),'?'+str(it.get('status'))),team=team,name=a.get('displayName'),raw=it.get('status'),how=how)
    bad=[]
    for g,v in D['injd'].items():
        e=src.get(g); nm=PL.get(g,{}).get('n',g)
        if not e: bad.append('%s shown %s, but no ESPN injury entry matches by ID or by name+team'%(nm,v['s'])); continue
        if e['s']!=v['s']: bad.append('%s shown %s, ESPN says "%s"'%(nm,v['s'],e['raw']))
        if e['team']!=nfl(PL.get(g,{}).get('t','')): bad.append('%s injury filed under %s but player is %s'%(nm,e['team'],PL.get(g,{}).get('t')))
        if e['how']=='name': byname_only.append('%s (%s) %s'%(nm,e['team'],v['s']))
    miss=['%s (%s) %s'%(e['name'],e['team'],e['raw']) for g,e in src.items() if g not in D['injd']]
    A.check('PL8','Every injury status matches ESPN (by player ID, or name+team where no ID exists), under the right team',bad,len(D['injd']))
    if byname_only: A.warn('PL8b','Injuries verified by name and team only (these players have no ESPN ID in the crosswalk)',byname_only,len(byname_only))
    A.check('PL9','No injured player on the slate is missing from the app',miss,len(src))

    # ---- week-1 actuals: nflverse vs ESPN box score ----
    W1={r['player_id']:r for r in rows(os.path.join(DATA,'stw26.csv')) if r['week']=='1' and r['season_type']=='REG'}
    box={}
    for p in glob.glob(os.path.join(RAW,'espn','f_*.json')):
        for tm in json.load(open(p)).get('boxscore',{}).get('players',[]):
            for grp in tm.get('statistics',[]):
                L=grp.get('labels',[])
                for a in grp.get('athletes',[]):
                    g=ESP.get(str(a['athlete']['id']))
                    if not g: continue
                    s=dict(zip(L,a.get('stats',[]))); b=box.setdefault(g,{})
                    if grp['name']=='receiving': b.update(rec=num(s.get('REC')),ry=num(s.get('YDS')),tgt=num(s.get('TGTS')))
                    if grp['name']=='rushing': b.update(car=num(s.get('CAR')),ru=num(s.get('YDS')))
                    if grp['name']=='passing':
                        ca=str(s.get('C/ATT','0/0')).split('/'); b.update(cmp=num(ca[0]),att=num(ca[-1]),py=num(s.get('YDS')))
    bad=[]; xs=[]
    col={'tgt':'targets','rec':'receptions','ry':'receiving_yards','car':'carries','ru':'rushing_yards','att':'attempts','cmp':'completions','py':'passing_yards'}
    for g,e in D['res'].items():
        r=W1.get(g); nm=PL.get(g,{}).get('n',g)
        if not r: bad.append('%s has a week-1 line but no nflverse row'%nm); continue
        for k,c in col.items():
            if int(e.get(k,0))!=round(num(r[c])): bad.append('%s %s shown %s, nflverse %s'%(nm,k,e.get(k,0),r[c]))
            if g in box and k in box[g] and round(num(r[c]))!=round(box[g][k]):
                xs.append('%s %s: nflverse %s, ESPN box score %s'%(nm,k,round(num(r[c])),round(box[g][k])))
        ppr=num(r['fantasy_points_ppr'])
        if abs(num(e.get('pts'))-ppr)>0.051: bad.append('%s PPR shown %.1f, nflverse fantasy_points_ppr %.1f'%(nm,num(e.get('pts')),ppr))
    A.check('PL10','Week-1 stat lines match nflverse, and PPR points equal its own fantasy_points_ppr',bad,len(D['res']))
    A.check('PL11','nflverse and ESPN box scores agree on every week-1 stat',xs,len(box))
    vc=open(os.path.join(APP,'app.js'),encoding='ascii').read().split('function verdictChip(')[1].split('\nfunction ')[0]
    A.check('PL12','Finished-game chips say they compare with the 2025 average, not with a GridIron projection',
            [] if 'ABOVE AVG' in vc and 'BEAT' not in vc and '2025' in vc else ['chip text reads like a grade against a projection that never existed'])
