"""What the reader sees: every rendered number, label and direction on the board, drawers and Model
page compared with the data it came from -- plus code-level regressions from earlier bugs."""
import os, re, json, math, glob, subprocess
from common import num, APP, PIPE, ROOT, nfl

M='−'
def nums(s): return [float(x.replace(M,'-').replace(',','')) for x in re.findall(r'[+%s-]?\d[\d,]*\.?\d*'%M,s or '')]
def miles(a,b):
    t=math.pi/180; h=math.sin((b[0]-a[0])*t/2)**2+math.cos(a[0]*t)*math.cos(b[0]*t)*math.sin((b[1]-a[1])*t/2)**2
    return round(2*3958.8*math.asin(math.sqrt(h)))

def run(A):
    A.section('what the reader sees'); D=A.D; G={g['id']:g for g in D['games']}
    out='/tmp/gi_audit_render.json'
    r=subprocess.run(['node',os.path.join(os.path.dirname(__file__),'render_dump.js'),out],capture_output=True,text=True,timeout=120)
    if r.returncode or not os.path.exists(out):
        A.check('U0','Page renders headlessly',['render failed: '+(r.stderr or r.stdout)[-300:]]); return
    R=json.load(open(out))
    txt=' '.join(c['text'] for c in R['cards'])+' '+(R['model'].get('text') or '')+' '+json.dumps(R['drawers'])+' '+(R.get('teamsText') or '')
    junk=sorted({m for m in re.findall(r'undefined|NaN|\[object|\bnull\b|Infinity',txt)})
    A.check('U0','Page renders with no script errors and no undefined / NaN / null text',R['errors']+junk)

    def splab(g,v):
        return 'PK' if abs(v)<0.05 else (g['h'] if v<0 else g['a']), abs(v)
    bad=[]
    for c in R['cards']:
        g=G[c['id']]; p=D['pred'][c['id']]; n=g['a']+'@'+g['h']
        sp,tot,wpc=c['pred'][0],c['pred'][1],c['pred'][2]
        for (label,shown),val in zip(sp['rows'],(p['sp'],p['bsp'],g.get('spread'))):
            if val is None: continue
            team,mag=splab(g,val); got=nums(shown)
            if (team=='PK' and shown!='PK') or (team!='PK' and (not shown.startswith(team) or not got or abs(abs(got[-1])-mag)>0.051)):
                bad.append('%s %s spread shows "%s", data %s -> %s %s'%(n,label,shown,val,team,mag))
        for (label,shown),val in zip(tot['rows'],(p['tot'],p['btot'],g.get('ou'))):
            if val is not None and abs(nums(shown)[0]-val)>0.051: bad.append('%s %s total shows "%s", data %s'%(n,label,shown,val))
        d=p['dsp']; want='agrees with the market' if abs(d)<0.25 else '%s pts toward %s'%(('%.1f'%abs(d)).rstrip('0').rstrip('.'),g['a'] if d>0 else g['h'])
        if sp['lean']!=want: bad.append('%s spread lean "%s", data says "%s"'%(n,sp['lean'],want))
        d=p['dtot']; want='agrees with the market' if abs(d)<0.25 else '%s pts toward the %s'%(('%.1f'%abs(d)).rstrip('0').rstrip('.'),'over' if d>0 else 'under')
        if tot['lean']!=want: bad.append('%s total lean "%s", data says "%s"'%(n,tot['lean'],want))
        if wpc['wpl']!=['%s %d%%'%(g['a'],100-p['wp']),'%s %d%%'%(g['h'],p['wp'])]: bad.append('%s win prob shows %s, data home %d%%'%(n,wpc['wpl'],p['wp']))
        im=(g['ou']/2+g['spread']/2, g['ou']/2-g['spread']/2) if g.get('ou') is not None and g.get('spread') is not None else None
        MT={k:v for k,v in (c.get('metrics') or [])}
        if im:
            got=[nums(MT.get('Implied '+g['a'],'')),nums(MT.get('Implied '+g['h'],''))]
            if not got[0] or not got[1] or abs(got[0][0]-im[0])>0.051 or abs(got[1][0]-im[1])>0.051:
                bad.append('%s implied tiles show %s / %s, expected %.2f / %.2f'%(n,MT.get('Implied '+g['a']),MT.get('Implied '+g['h']),im[0],im[1]))
    A.check('U1','Prediction cells, lean text, win probability and implied totals match the data on every card',bad,len(R['cards']))

    bad=[]
    for c in R['cards']:
        g=G[c['id']]; p=D['pred'][c['id']]; n=g['a']+'@'+g['h']; W={w['k']:w for w in c['wf']}
        for key,val in (('%s offense vs %s defense'%(g['an'],g['hn']),p['a']['p0']),('%s offense vs %s defense'%(g['hn'],g['an']),p['h']['p0'])):
            if key not in W or abs(nums(W[key]['v'])[0]-val)>0.051: bad.append('%s row "%s" shows %s, data %.1f'%(n,key,W.get(key,{}).get('v'),val))
        tot=W.get('Projected score')
        if not tot or nums(tot['v'])[:2]!=[round(p['pa'],1),round(p['ph'],1)]: bad.append('%s projected score shows %s, data %.1f-%.1f'%(n,tot and tot['v'],p['pa'],p['ph']))
        for s in p.get('steps',[]):
            if abs(s['v'])<0.05 and not g.get('neutral'):
                if s['k'] in W: bad.append('%s shows a zero "%s" row'%(n,s['k']))
                continue
            v=nums(W.get(s['k'],{}).get('v'))
            if s['k'] not in W or (abs(s['v'])>=0.05 and (len(v)<2 or abs(v[0]-s['v']/2)>0.051 or abs(v[1]+s['v']/2)>0.051)):
                bad.append('%s shift row "%s" shows %s, data moves %.2f toward %s'%(n,s['k'],W.get(s['k'],{}).get('v'),s['v']/2,g['h']))
    A.check('U2','Breakdown rows and the projected score show exactly the prediction data',bad,len(R['cards']))

    bad=[]
    for c in R['cards']:
        for row in c['inj']:
            rd=D['redist'].get(nfl(row['t'])) or D['redist'].get(row['t']) or {}
            to={m['n']:m for m in rd.get('to',[])}
            for s in row['to']:
                nm,vals=re.split(r' (?=[\d.]+→)',s)[0],nums(s.replace('→',' '))
                m=to.get(nm)
                if not m or abs(vals[-2]-m['b'])>0.051 or abs(vals[-1]-m['a'])>0.051: bad.append('%s "%s", data %s'%(row['t'],s,m and (m['b'],m['a'])))
    for c in R['cards']:
        g=G[c['id']]
        for row in c['rows']:
            pj=D['proj'].get(row['oid']); rs=D['res'].get(row['oid'])
            if row['med'] and pj and abs(float(row['med'])-pj['med'])>0.051: bad.append('%s median shows %s, data %s'%(D['players'][row['oid']]['n'],row['med'],pj['med']))
            if row['act'] and rs and abs(float(row['act'])-num(rs.get('pts')))>0.051: bad.append('%s actual shows %s, data %s'%(D['players'][row['oid']]['n'],row['act'],rs.get('pts')))
    A.check('U3','Injury panel before/after values and every matchup-row projection or actual match the data',bad)

    src=open(os.path.join(APP,'context.js'),encoding='utf-8').read()
    ST={m.group(1):(float(m.group(2)),float(m.group(3)),int(m.group(4))) for m in re.finditer(r"([A-Z]{2,3}):\{v:'[^']*',la:(-?[\d.]+),lo:(-?[\d.]+),el:(-?\d+)",src)}
    NV={m.group(1):(float(m.group(2)),float(m.group(3)),int(m.group(4))) for m in re.finditer(r"'([^']+)':\{la:(-?[\d.]+),lo:(-?[\d.]+),el:(-?\d+)",src)}
    bad=[]
    for c in R['cards']:
        g=G[c['id']]; n=g['a']+'@'+g['h']; C={x['k']:x for x in c['cells']}
        ven=NV.get(g.get('venue')) if g.get('neutral') else ST.get(g['h'])
        if ven and 'Elevation' in C and int(nums(C['Elevation']['v'])[0])!=ven[2]: bad.append('%s elevation shows %s, venue %d'%(n,C['Elevation']['v'],ven[2]))
        if ven and ST.get(g['a']) and 'Visitor travel' in C and abs(nums(C['Visitor travel']['v'])[0]-miles(ST[g['a']][:2],ven[:2]))>1:
            bad.append('%s travel shows %s, great-circle %d mi'%(n,C['Visitor travel']['v'],miles(ST[g['a']][:2],ven[:2])))
        f=g.get('hfa')
        if f and not g.get('neutral') and ('Venue edge' not in C or abs(nums(C['Venue edge']['v'])[0]-f['e'])>0.051): bad.append('%s venue edge shows %s, data %s'%(n,C.get('Venue edge',{}).get('v'),f['e']))
        rf=g.get('ref') or {}
        if rf.get('n') and ('Referee' not in C or abs(nums(C['Referee']['meta'])[0]-(rf['avg']-rf['lg']))>0.051): bad.append('%s referee delta shows %s, data %.1f'%(n,C.get('Referee',{}).get('meta'),rf.get('avg',0)-rf.get('lg',0)))
        if g.get('h_pace') is not None and g.get('a_pace') is not None:
            comb=(g['h_pace']+g['a_pace'])/2
            if 'Pace' not in C or abs(nums(C['Pace']['v'])[0]-comb)>0.051: bad.append('%s pace shows %s, data %.2f'%(n,C.get('Pace',{}).get('v'),comb))
        elif 'Pace' not in C: bad.append('%s shows no pace factor (a team is missing pace data)'%n)
        for flag,label in (('div','Divisional'),('neutral','Neutral site')):
            if bool(g.get(flag))!=(label in C): bad.append('%s %s cell %s but flag is %s'%(n,label,'shown' if label in C else 'missing',g.get(flag)))
        for s in ('a','h'):
            has=any(x['k']=='New quarterback' and x['v']==g[s] for x in c['cells'])
            if bool(g.get(s+'_qbnew'))!=has: bad.append('%s new-QB cell for %s %s but flag is %s'%(n,g[s],'shown' if has else 'missing',g.get(s+'_qbnew')))
    A.check('U4','Context cells (elevation, travel, venue edge, referee, pace, divisional, neutral, new QB) match the data',bad,len(R['cards']))

    bad=[]
    KEYS={'Receiving yards':'qry','Receptions':'qrec','Rushing yards':'qru','Passing yards':'qpy'}
    for dr in R['drawers']:
        p=D['proj'][dr['oid']]; nm=D['players'][dr['oid']]['n']
        CH={}
        for k,v in dr['chain']:
            for lab in ('Conditions','Someone else is out'):
                if k and k.startswith(lab): CH[lab]=v
        if abs(float(dr['big'])-p['med'])>0.051: bad.append('%s headline %s, data %s'%(nm,dr['big'],p['med']))
        if p.get('wx') and abs(p['wx']['m']-1)>=0.005:
            v=nums((CH.get('Conditions') or '').replace(chr(0x2192),' '))
            if len(v)<3 or abs(v[0]-100*(p['wx']['m']-1))>0.051 or abs(v[1]-p['wx']['b'])>0.051 or abs(v[2]-p['wx'].get('a',p['med']))>0.051:
                bad.append('%s conditions row "%s", data %+.1f%% %s -> %s'%(nm,CH.get('Conditions'),100*(p['wx']['m']-1),p['wx']['b'],p['med']))
        if p.get('inj') and abs(p['inj']['m']-1)>=0.005:
            v=nums((CH.get('Someone else is out') or '').split('%')[-1].replace(chr(0x2192),' '))
            if len(v)<2 or abs(v[-2]-p['inj']['b'])>0.051 or abs(v[-1]-p['inj'].get('a',p['med']))>0.051:
                bad.append('%s injury row "%s", data %s -> %s'%(nm,CH.get('Someone else is out'),p['inj']['b'],p['med']))
        mk=(D.get('props') or {}).get('by',{}).get(dr['oid'],{})
        for lab,line,read in dr['market']:
            v=mk.get(KEYS[lab]); L2=nums(line); pct=int(nums(read)[0]); side=read.split()[0]
            want_side='over' if v['rel']>0.5 else 'under'; want_pct=round(100*max(v['rel'],1-v['rel']))
            mv=None if v['open'] in (None,v['line']) else v['line']-v['open']
            if abs(L2[0]-v['line'])>0.01 or (mv is not None and (len(L2)<2 or abs(L2[1]-mv)>0.051)) or side!=want_side or abs(pct-want_pct)>1:
                bad.append('%s %s shows %s / %s, data line %s open %s rel %.3f'%(nm,lab,line,read,v['line'],v['open'],v['rel']))
        if mk and dr['line'] is not None and not any(abs(float(dr['line'])-x['line'])<0.01 for x in mk.values()):
            bad.append('%s calculator opens on %s, not a DraftKings line %s'%(nm,dr['line'],[x['line'] for x in mk.values()]))
    A.check('U5','Player drawers: headline, conditions row, DraftKings lines, movement and reads match the data',bad,len(R['drawers']))

    T=D['track'].get('held') or D['track']['all']; tiles={t[0]:t for t in R['model']['tiles']}; bad=[]
    for k,want in (('Margin error',T['gm']),('Total error',T['gt']),('Against the spread',T['ats']),('Picks the winner',T['su'])):
        if k not in tiles or abs(nums(tiles[k][1])[0]-want)>0.051: bad.append('tile %s shows %s, data %s'%(k,tiles.get(k),want))
    if len(R['model']['wprows'])!=len(D['track']['wpcal']['bands']): bad.append('calibration rows %d, bands %d'%(len(R['model']['wprows']),len(D['track']['wpcal']['bands'])))
    if len(R['model']['frows'])!=len(D['track']['factors']): bad.append('factor rows %d, factors %d'%(len(R['model']['frows']),len(D['track']['factors'])))
    for c in R['cards']:
        want='On %s games from 2023'%'{:,}'.format(T['atsn'])+chr(0x2013)+'25 that the model never trained on, GridIron picked %.1f%%'%T['ats']
        if want not in (c['foot'] or ''): bad.append('%s footer does not read "%s"'%(c['id'],want)); break
    A.check('U6','Model page tiles, calibration rows, factor rows and card footers match the track record',bad)

    # ---------------- code regressions from bugs already hit ----------------
    bad=[]
    for f in ('app.js','context.js'):
        b=open(os.path.join(APP,f),'rb').read(); nb=sum(1 for x in b if x>127)
        if nb: bad.append('%s has %d non-ASCII bytes (served without a charset they turn to mojibake)'%(f,nb))
        names=re.findall(r'^function\s+([A-Za-z_$][\w$]*)\s*\(',b.decode('ascii','replace'),re.M)
        dup=sorted({x for x in names if names.count(x)>1})
        if dup: bad.append('%s defines these functions more than once (the later copy silently wins): %s'%(f,dup))
    for f in glob.glob(os.path.join(PIPE,'*.py'))+[os.path.join(ROOT,'refresh.py')]:
        if os.path.basename(f).startswith(('gen','model')): continue
        for i,l in enumerate(open(f,encoding='utf-8'),1):
            if ('/tmp/' in l or 'scratchpad' in l) and not l.lstrip().startswith('#'): bad.append('%s:%d hardcoded path'%(os.path.basename(f),i))
    js=open(os.path.join(APP,'app.js'),encoding='ascii').read()
    for lit in {'{:,}'.format(T['atsn']),'%.1f%%'%T['ats'],'%.2f'%T['gm'],'%.2f'%T['vm'],'1,828','49.8%','10.28'}:
        for m in re.finditer(re.escape(lit),js): bad.append('app.js hardcodes "%s" near: %s'%(lit,js[max(0,m.start()-50):m.end()+10].replace('\n',' ')))
    if 'stalebar' not in js or 'menubtn' not in js: bad.append('app.js lost the stale-data banner or the phone games menu')
    if 'reloadForNewApp()' not in js or 'routeFromHash()' not in js: bad.append('app.js no longer reloads open tabs when a new version is published, or no longer restores the view from the address')
    A.check('U7','Code regressions: ASCII-only scripts, no duplicate functions, no hardcoded paths or stale track numbers',bad)

    Lr=R['model'].get('learn') or {}; LD=D.get('learn') or {}; bad=[]
    if not LD.get('weights'): bad.append('no learning data published')
    else:
        if len(Lr.get('rows',[]))!=len(LD['weights']): bad.append('learning table shows %d rows, data has %d weight groups'%(len(Lr.get('rows',[])),len(LD['weights'])))
        for row,w in zip(Lr.get('rows',[]),LD['weights']):
            if not (row['k'] or '').startswith(w['name']) or row['v']!=w['value']: bad.append('learning row %r shows %r; data %s = %s'%(row['k'],row['v'],w['name'],w['value']))
        LR=LD.get('last_review'); rv=Lr.get('rev') or ''
        if LR and ('%d week %d'%tuple(LR['cutoff']) not in rv or '%d ideas tested'%LR['tested'] not in rv or 'version %d'%LD['version'] not in rv): bad.append('last-review line reads %r'%rv)
        if len(LD.get('proposals',[]))>Lr.get('dec',0): bad.append('open proposals are not all shown')
    A.check('U10','Model page lists every weight group with its current value and status, and the latest review',bad,len(LD.get('weights',[])))

    # ---------------- Teams page and each game's season panel ----------------
    TD=D.get('teams') or {}; RT=R.get('teams') or {}; bad=[]
    def wl(a): return '%d-%d'%(a[0],a[1])+('-%d'%a[2] if a[2] else '')
    def sg(v): return '—' if v is None else ('+%d'%v if v>0 else ('−%d'%-v if v<0 else '0'))
    def f1(v): x='%.1f'%v; return x[:-2] if x.endswith('.0') else x
    def pc(v):
        if v is None: return '—'
        x='%.3f'%v; return x[1:] if x.startswith('0') else x
    if not TD.get('by'): bad.append('no team standings in the data')
    for season,B in (TD.get('by') or {}).items():
        V=RT.get(season)
        if not V: bad.append('Teams page has no %s season'%season); continue
        for view in ('div','league'):
            shown={r['team']:r for r in V[view]['rows']}
            if sorted(shown)!=sorted(B['rows']): bad.append('%s %s layout shows %d teams, data has %d'%(season,view,len(shown),len(B['rows']))); continue
            for code,x in B['rows'].items():
                cl=shown[code]['cells']; n='%s %s %s'%(season,view,x['ab'])
                want={'rec':wl([x['w'],x['l'],x['t']]),'pct':pc(x['pct']),'div':wl(x['div']),'conf':wl(x['conf']),'pf':str(x['pf']),'pa':str(x['pa']),
                      'diff':sg(x['diff']) if x['gp'] else '—','streak':x['streak'] or '—','last5':x['last5'] or '—'}
                if view=='league':
                    want.update(home=wl(x['home']),away=wl(x['away']),pfg=f1(x['pfg']) if x['gp'] else '—',pag=f1(x['pag']) if x['gp'] else '—',
                                ats=wl(x['ats']),ou=wl(x['ou']),ypg='—' if x['ypg'] is None else f1(x['ypg']),
                                ypga='—' if x['ypga'] is None else f1(x['ypga']),to=sg(x['to']))
                for k,v in want.items():
                    if cl.get(k)!=v: bad.append('%s %s shows %r, data %r'%(n,k,cl.get(k),v))
                if view=='div' and shown[code]['rank']!=str(x['rank']): bad.append('%s division place shows %s, data %s'%(n,shown[code]['rank'],x['rank']))
                slate=[g for g in D['games'] if x['ab'] in (g['a'],g['h'])]; wk=cl.get('wk') or ''
                if slate and (slate[0]['h'] if slate[0]['a']==x['ab'] else slate[0]['a']) not in wk: bad.append('%s this-week cell %r misses the opponent'%(n,wk))
                if not slate and wk!='Bye': bad.append('%s this-week cell %r though the team is not on the slate'%(n,wk))
        played=[k for k,x in B['rows'].items() if x['gp']]
        if played:
            top=sorted(played,key=lambda k:(-B['rows'][k]['pct'],-B['rows'][k]['diff'],k))[0]
            LD2={a:b for a,b in V['div']['leaders']}
            if not (LD2.get('Best record') or '').startswith(B['rows'][top]['ab']+' '): bad.append('%s best-record tile %r, data %s'%(season,LD2.get('Best record'),B['rows'][top]['ab']))
    A.check('U11','Teams page: every team\'s record, splits, points, streak, last five, ATS, O/U, yards, turnovers and this week\'s game match the standings, in both layouts and both seasons',bad,32*len(TD.get('by') or {}))

    bad=[]; E2N={'LAR':'LA','WSH':'WAS'}
    for c in R['cards']:
        g=G[c['id']]; n=g['a']+'@'+g['h']
        if not TD.get('by'): break
        a_,h_=E2N.get(g['a'],g['a']),E2N.get(g['h'],g['h']); cur=TD['by'][str(TD['current'])]; prev=TD['by'].get(str(TD['current']-1))
        S=cur if (cur['rows'][a_]['gp'] or cur['rows'][h_]['gp']) else prev
        rec={r[0]:r[1:] for r in c.get('records',[])}
        for label,fn in (('Record',lambda x:wl([x['w'],x['l'],x['t']])),('Point differential',lambda x:sg(x['diff']) if x['gp'] else '—'),
                         ('Against the spread',lambda x:wl(x['ats'])),('Over / under',lambda x:wl(x['ou'])),('Turnover margin',lambda x:sg(x['to']))):
            want=[fn(S['rows'][a_]),fn(S['rows'][h_])]
            if rec.get(label)!=want: bad.append('%s %s shows %s, data %s'%(n,label,rec.get(label),want))
        if len(c.get('jump') or [])<6 or not c.get('field'): bad.append('%s game page is missing its section links or its field'%n)
    A.check('U12','Every game page carries its season-so-far panel matching the standings, its section links and its field',bad,len(R['cards']))

    # ---------------- since-launch record (kickoff ledger) on the Model page and each game page ----------------
    LG=D.get('ledger') or {}; LR=LG.get('record') or {}; LE=LG.get('entries') or {}; bad=[]
    st={x[0].lower():' '.join(x) for x in (R['model'].get('since') or [])}; stx=R['model'].get('sinceText') or ''
    def shows(k,want):
        if want not in st.get(k,''): bad.append('since-launch tile "%s" should show %s, shows "%s"'%(k,want,st.get(k)))
    if not LG: bad.append('the data carries no kickoff ledger')
    elif LR.get('settled'):
        shows('margin error','%.2f pts'%LR['gm']); shows('margin error','closing line %.2f'%LR['vm'])
        at=LR['ats']; shows('against the close','%d-%d'%(at[0],at[1]))
        if at[0]+at[1]: shows('against the close','%.1f%%'%(100.0*at[0]/(at[0]+at[1])))
        cv=LR.get('clv') or {}
        if cv.get('n'): shows('line moved toward gridiron','%d of %d'%(cv['toward'],cv['n']))
        if '%d calls frozen, %d settled'%(LR['frozen'],LR['settled']) not in stx: bad.append('since-launch card does not state %d frozen, %d settled'%(LR['frozen'],LR['settled']))
    elif 'No settled games yet' not in stx: bad.append('since-launch card should say no games have settled')
    def lab(g,v):
        team,mag=splab(g,v); return 'PK' if team=='PK' else '%s −%s'%(team,('%.1f'%mag)[:-2] if ('%.1f'%mag).endswith('.0') else '%.1f'%mag)
    for c in R['cards']:
        g=G[c['id']]; e=LE.get(c['id']) or {}; note=c.get('ledger') or ''; n=g['a']+'@'+g['h']
        if e.get('frozen'):
            cl=e.get('call') or {}; fin=e.get('final'); cz=e.get('close')
            if not note.startswith('Frozen at kickoff'): bad.append('%s frozen call missing from its game page (shows "%s")'%(n,note[:60])); continue
            if cl.get('sp') is not None and 'GridIron '+lab(g,cl['sp'])+',' not in note: bad.append('%s frozen call shows "%s", ledger spread %s'%(n,note[:80],cl['sp']))
            if cz and cz.get('spread') is not None and 'closed '+lab(g,cz['spread']) not in note: bad.append('%s closing line not shown as %s'%(n,lab(g,cz['spread'])))
            if fin and cz and cz.get('spread') is not None and 'final %s %d–%s %d'%(g['a'],fin['a'],g['h'],fin['h']) not in note: bad.append('%s final score not shown in the ledger note'%n)
        elif e.get('missed') and g.get('state')!='pre' and 'Not in the since-launch record' not in note: bad.append('%s kicked off without a call but the page does not say so'%n)
    A.check('U13','Model page since-launch record and each game page\'s frozen kickoff call match the ledger',bad,len(R['cards']))

    # ---------------- team pages and the week-by-week view, recomputed from the nflverse schedule and the ledger ----------------
    from common import rows as _rows, DATA as _DATA
    GA=[r for r in _rows(os.path.join(_DATA,'games_all.csv')) if r['game_type']=='REG']
    EF={g['id']:(int(g['sc']['a']),int(g['sc']['h'])) for g in D['games'] if g.get('state')=='post' and g.get('sc')}
    LP=os.path.join(PIPE,'ledger.json'); LEDG=(json.load(open(LP)).get('entries') or {}) if os.path.exists(LP) else {}
    AB={'LA':'LAR','WAS':'WSH'}; ab=lambda t:AB.get(t,t); MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']; DASH='—'
    def fn(v):
        try: return float(v)
        except (TypeError,ValueError): return None
    def f1s(v): x='%.1f'%v; return x[:-2] if x.endswith('.0') else x
    def sgn(x): return (x>0)-(x<0)
    def eid(r): return str(r.get('espn') or '').split('.')[0]
    def score(r):
        if r['home_score'] not in ('',None): return int(float(r['away_score'])),int(float(r['home_score']))
        return EF.get(eid(r))
    def sdate(x): return '%s %d'%(MON[int(x[5:7])-1],int(x[8:10])) if x and len(x)>=10 else ''
    def tline(v): return DASH if v is None else ('PK' if abs(v)<0.05 else ('−' if v<0 else '+')+f1s(abs(v)))
    def fav(home,away,m): return 'PK' if abs(m)<0.05 else '%s −%s'%(ab(home if m>0 else away),f1s(abs(m)))
    def gcall(r,sc,sl,label):
        e=LEDG.get(eid(r)) or {}; c=e.get('call') or {}
        if not (e.get('frozen') and c.get('ph') is not None): return DASH
        gm=c['ph']-c['pa']; out=label(gm)
        if sc and sl is not None:
            pick,res=sgn(gm-sl),sgn(sc[1]-sc[0]-sl)
            if pick and res: out+=' ✓' if pick==res else ' ✗'
        return out
    TDm=D.get('teams') or {}; TP=R.get('teampages') or {}; bad=[]
    if len(TP)!=32: bad.append('%d team pages rendered, expected 32'%len(TP))
    for code,pages in TP.items():
        if sorted(pages)!=sorted(str(x) for x in TDm.get('seasons',[])): bad.append('%s team page seasons %s'%(ab(code),sorted(pages)))
        for season,pg in pages.items():
            sea=int(season); n='%s %s'%(ab(code),season); S=TDm['by'][season]['rows'][code]; cur=sea==TDm['current']
            if not pg['on'] or TDm['meta'][code]['name'] not in (pg['crumb'] or ''): bad.append('%s team page not shown or crumb %r'%(n,pg['crumb']))
            games={int(r['week']):r for r in GA if int(r['season'])==sea and code in (r['home_team'],r['away_team'])}
            maxw=max(int(r['week']) for r in GA if int(r['season'])==sea); shown={int(x['wk']):x['cells'] for x in pg['sched']}
            if sorted(shown)!=list(range(1,maxw+1)): bad.append('%s schedule shows weeks %s'%(n,sorted(shown))); continue
            if ('GridIron' in pg['heads'])!=cur: bad.append('%s GridIron column %s'%(n,'missing' if cur else 'shown for a past season'))
            for w in range(1,maxw+1):
                cl=shown[w]; r=games.get(w)
                if not r:
                    if cl.get('bye')!='Bye': bad.append('%s week %d should be a bye, shows %s'%(n,w,cl))
                    continue
                home=r['home_team']==code; opp=r['away_team'] if home else r['home_team']; sc=score(r); sl=fn(r['spread_line']); tl=fn(r['total_line'])
                exp=None if sl is None else (sl if home else -sl)
                want={'wk':str(w),'date':sdate(r['gameday']),'opp':('vs ' if home else '@ ')+ab(opp),'line':tline(None if exp is None else -exp),'tot':DASH if tl is None else f1s(tl)}
                if sc:
                    pf,pa=(sc[1],sc[0]) if home else sc; res='W' if pf>pa else 'L' if pf<pa else 'T'
                    want.update(res='%s %d–%d'%(res,pf,pa)+(' OT' if r.get('overtime')=='1' and r['home_score'] not in ('',None) else ''),
                                ats=DASH if exp is None else {1:'Covered',-1:'Missed',0:'Push'}[sgn(pf-pa-exp)],ou=DASH if tl is None else {1:'Over',-1:'Under',0:'Push'}[sgn(pf+pa-tl)])
                else: want.update(res=DASH,ats=DASH,ou=DASH)
                if cur: want['gi']=gcall(r,sc,sl,lambda gm,home=home:tline(-(gm if home else -gm)))
                for k,v in want.items():
                    if cl.get(k)!=v: bad.append('%s week %d %s shows %r, schedule gives %r'%(n,w,k,cl.get(k),v))
            if sorted(pg['bars'])!=sorted(w for w,r in games.items() if score(r)): bad.append('%s chart has bars for weeks %s'%(n,pg['bars']))
            tl_={a_:b_ for a_,b_ in pg['tiles']}
            if S['gp']:
                pl=[k for k,x in TDm['by'][season]['rows'].items() if x['gp']]
                rk=lambda f,low=False:1+sum(1 for k in pl if (TDm['by'][season]['rows'][k][f]<S[f] if low else TDm['by'][season]['rows'][k][f]>S[f]))
                for label,val in (('Record',wl([S['w'],S['l'],S['t']])),('Scored / game','%s #%d of %d'%(f1s(S['pfg']),rk('pfg'),len(pl))),
                                  ('Allowed / game','%s #%d of %d'%(f1s(S['pag']),rk('pag',True),len(pl))),('Against the spread',wl(S['ats'])),('Over / under',wl(S['ou']))):
                    if not (tl_.get(label) or '').startswith(val): bad.append('%s tile %s shows %r, standings give %r'%(n,label,tl_.get(label),val))
            want_inj=sorted(g for g in (D.get('injd') or {}) if (D['players'].get(g) or {}).get('t')==code)
            if sorted(pg['inj'])!=want_inj: bad.append('%s injury report lists %d players, data has %d'%(n,len(pg['inj']),len(want_inj)))
            ros=[g for g,p in D['players'].items() if p.get('t')==code and ((D.get('prod') or {}).get(g) or {}).get('S')]
            def top(f,k,mn): return sorted([g for g in ros if D['prod'][g]['S'].get(f,0)>=mn],key=lambda g:(-D['prod'][g]['S'].get(f,0),g))[:k]
            want_pl=[(g,'Passing') for g in top('att',1,100)]+[(g,'Receiving') for g in top('tgt',3,20)]+[(g,'Rushing') for g in top('car',2,40)]
            got_pl=[(x['id'],x['cells'].get('role')) for x in pg['players']]
            if got_pl!=want_pl: bad.append('%s key players %s, production data gives %s'%(n,got_pl,want_pl))
            for x in pg['players']:
                st=D['prod'][x['id']]['S']; g_=lambda k:st.get(k,0); role=x['cells'].get('role')
                line={'Passing':'%d/%d, %d yds, %d TD'%(g_('cmp'),g_('att'),g_('py'),g_('ptd')),'Receiving':'%d targets, %d rec, %d yds, %d TD'%(g_('tgt'),g_('rec'),g_('ry'),g_('rtd')),
                      'Rushing':'%d carries, %d yds, %d TD'%(g_('car'),g_('ru'),g_('rutd'))}.get(role)
                if x['cells'].get('line')!=line or x['cells'].get('g')!=str(g_('g')): bad.append('%s %s line %r, data %r'%(n,x['id'],x['cells'].get('line'),line))
            junk=[t for t in ('undefined','NaN','null','[object') if t in (pg.get('text') or '')]
            if junk: bad.append('%s team page shows %s'%(n,junk))
    A.check('U14','Every team page (32 teams, both seasons): schedule, results, closing lines, ATS, O/U, GridIron\'s frozen calls, chart, tiles, injuries and key players match the schedule, standings and ledger',bad,64)

    bad=[]; WK=R.get('weeks') or {}; nwk=0
    for season,weeks in WK.items():
        sea=int(season); cur=sea==TDm['current']; sched=[r for r in GA if int(r['season'])==sea]
        if sorted(int(w) for w in weeks)!=sorted({int(r['week']) for r in sched}): bad.append('%s week picker offers %s'%(season,sorted(weeks)))
        for w,V in weeks.items():
            games=[r for r in sched if int(r['week'])==int(w)]; shown={x['espn']:x['cells'] for x in V['rows']}
            if sorted(shown)!=sorted(eid(r) for r in games): bad.append('%s week %s shows %d games, schedule has %d'%(season,w,len(shown),len(games))); continue
            if ('GridIron' in V['heads'])!=cur: bad.append('%s week %s GridIron column wrong'%(season,w))
            nwk+=1
            for r in games:
                cl=shown[eid(r)]; sc=score(r); sl=fn(r['spread_line']); tl=fn(r['total_line']); n='%s week %s %s@%s'%(season,w,ab(r['away_team']),ab(r['home_team']))
                want={'date':sdate(r['gameday']),'game':'%s @ %s'%(ab(r['away_team']),ab(r['home_team'])),'close':DASH if sl is None else fav(r['home_team'],r['away_team'],sl),
                      'total':DASH if tl is None else f1s(tl)}
                if sc:
                    want.update(final='%d–%d'%sc+(' OT' if r.get('overtime')=='1' and r['home_score'] not in ('',None) else ''),
                                ats=DASH if sl is None else {1:ab(r['home_team']),-1:ab(r['away_team']),0:'Push'}[sgn(sc[1]-sc[0]-sl)],
                                ou=DASH if tl is None else {1:'Over',-1:'Under',0:'Push'}[sgn(sc[0]+sc[1]-tl)])
                else: want.update(ats=DASH,ou=DASH)
                if cur: want['gi']=gcall(r,sc,sl,lambda gm,r=r:fav(r['home_team'],r['away_team'],gm))
                for k,v in want.items():
                    if cl.get(k)!=v: bad.append('%s %s shows %r, schedule gives %r'%(n,k,cl.get(k),v))
            if not (V.get('note') or '').startswith('Week %s of %s'%(w,season)): bad.append('%s week %s note %r'%(season,w,V.get('note')))
    A.check('U15','Week-by-week view: every game of every week in both seasons shows its result, closing line, ATS and O/U winner, and GridIron\'s frozen call, matching the schedule and ledger',bad,nwk)

    # ---------------- a game in progress, rendered from a fixture built out of real ESPN payloads ----------------
    RAWE=os.path.join(ROOT,'data','raw','espn')
    fin=[g for g in D['games'] if g.get('state')=='post' and os.path.exists(os.path.join(RAWE,'f_%s.json'%g['id']))]
    pre=[g for g in D['games'] if g.get('state')=='pre']; make_pre=None
    if not pre and len(fin)>=3: pre=[fin[2]]; make_pre=fin[2]['id']      # every game has kicked off: stage a finished one as scheduled
    if not fin or not pre or not D.get('espn'):
        A.check('U8','A game in progress shows its live score, clock and box-score lines exactly',
                ['cannot build the fixture: need a finished game with a saved box score, a scheduled game and the ESPN id map']); return
    tg,pg=fin[0],pre[0]; tg2=fin[1] if len(fin)>1 else None
    sb=json.load(open(os.path.join(RAWE,'sb2.json')))
    for e in sb['events']:
        if make_pre and e['id']==make_pre:
            e['competitions'][0]['status']={'clock':0.0,'displayClock':'0:00','period':0,'type':{'id':'1','name':'STATUS_SCHEDULED','state':'pre','completed':False,
                'description':'Scheduled','detail':'Sun, Sep 20th at 1:00 PM EDT','shortDetail':'9/20 - 1:00 PM EDT'}}
            continue
        if tg2 and e['id']==tg2['id']:
            # second live game: home offense at its own 20, field position given only as yardLine (measured from the home goal line)
            c=e['competitions'][0]; hid=[x['team']['id'] for x in c['competitors'] if x['homeAway']=='home'][0]
            c['status']={'clock':195.0,'displayClock':'3:15','period':2,'type':{'id':'2','name':'STATUS_IN_PROGRESS','state':'in','completed':False,
                         'description':'In Progress','detail':'3:15 - 2nd Quarter','shortDetail':'3:15 - 2nd'}}
            for x in c['competitors']: x['score']='3' if x['homeAway']=='away' else '10'
            c['situation']={'possession':hid,'shortDownDistanceText':'1st & 10','isRedZone':False,'down':1,'distance':10,'yardLine':20}
            continue
        if e['id']!=tg['id']: continue
        c=e['competitions'][0]
        c['status']={'clock':522.0,'displayClock':'8:42','period':3,'type':{'id':'2','name':'STATUS_IN_PROGRESS','state':'in','completed':False,
                     'description':'In Progress','detail':'8:42 - 3rd Quarter','shortDetail':'8:42 - 3rd'}}
        for x in c['competitors']: x['score']='17' if x['homeAway']=='away' else '7'
        # away offense at the home team's 35, given as ESPN's "HOME 35" text
        habb=[x['team']['abbreviation'] for x in c['competitors'] if x['homeAway']=='home'][0]
        c['situation']={'possession':[x['team']['id'] for x in c['competitors'] if x['homeAway']=='away'][0],'shortDownDistanceText':'2nd & 7','isRedZone':False,
                        'down':2,'distance':7,'yardLine':35,'possessionText':'%s 35'%habb}
    box=json.load(open(os.path.join(RAWE,'f_%s.json'%tg['id'])))
    summ={tg['id']:box}
    if tg2: summ[tg2['id']]=json.load(open(os.path.join(RAWE,'f_%s.json'%tg2['id'])))
    fx='/tmp/gi_live_fixture.json'; json.dump({'scoreboard':sb,'summaries':summ},open(fx,'w'))
    out2='/tmp/gi_audit_render_live.json'
    if os.path.exists(out2): os.remove(out2)
    r=subprocess.run(['node',os.path.join(os.path.dirname(__file__),'render_dump.js'),out2],capture_output=True,text=True,timeout=180,
                     env=dict(os.environ,GRIDIRON_FIXTURE_FILE=fx))
    if r.returncode or not os.path.exists(out2):
        A.check('U8','A game in progress shows its live score, clock and box-score lines exactly',['live render failed: '+(r.stderr or r.stdout)[-300:]]); return
    RL=json.load(open(out2)); bad=list(RL['errors'])
    fnum=lambda x: float(x) if re.match(r'^-?\d+(\.\d+)?$',str(x).strip()) else 0.0
    want={}
    for tm in box.get('boxscore',{}).get('players',[]):
        for grp in tm.get('statistics',[]):
            for a in grp.get('athletes',[]):
                gs=D['espn'].get(str(a['athlete']['id']))
                if not gs: continue
                v=dict(zip(grp.get('labels',[]),a.get('stats',[]))); e=want.setdefault(gs,{})
                if grp['name']=='receiving':
                    e.update(rec=fnum(v.get('REC')),ry=fnum(v.get('YDS')),rtd=fnum(v.get('TD')))
                    if 'TGTS' in v: e['tgt']=fnum(v['TGTS'])
                if grp['name']=='rushing': e.update(car=fnum(v.get('CAR')),ru=fnum(v.get('YDS')),rutd=fnum(v.get('TD')))
                if grp['name']=='passing':
                    ca=str(v.get('C/ATT','0/0')).split('/'); e.update(cmp=fnum(ca[0]),att=fnum(ca[-1]),py=fnum(v.get('YDS')),ptd=fnum(v.get('TD')),int=fnum(v.get('INT')))
                if grp['name']=='fumbles': e['fum']=fnum(v.get('LOST'))
    f=lambda x: '%d'%x if float(x).is_integer() else repr(float(x))
    def sline(e):
        b=[]
        if e.get('tgt'): b.append('%s/%s for %s yds'%(f(e.get('rec',0)),f(e['tgt']),f(e.get('ry',0))))
        if e.get('car'): b.append('%s car, %s yds'%(f(e['car']),f(e.get('ru',0))))
        if e.get('att'): b.append('%s/%s, %s yds'%(f(e.get('cmp',0)),f(e['att']),f(e.get('py',0))))
        td=e.get('rtd',0)+e.get('rutd',0)+e.get('ptd',0)
        if td: b.append('%s TD'%f(td))
        if e.get('int'): b.append('%s INT'%f(e['int']))
        return (' '+chr(0xb7)+' ').join(b)
    ppr=lambda e: math.floor((e.get('rec',0)+0.1*e.get('ry',0)+6*e.get('rtd',0)+0.1*e.get('ru',0)+6*e.get('rutd',0)+0.04*e.get('py',0)
                              +4*e.get('ptd',0)-2*e.get('int',0)-2*e.get('fum',0))*10+0.5)/10
    card=[c for c in RL['cards'] if c['id']==tg['id']]
    if not card: bad.append('the in-progress game has no card')
    else:
        c=card[0]
        if not c['score'] or 'LIVE' not in c['score'] or nums(c['score'])[:2]!=[17.0,7.0]: bad.append('live card score shows %r, fixture is LIVE 17-7'%c['score'])
        if '8:42 - 3rd' not in (c['meta'] or ''): bad.append('live card does not show the clock: %r'%c['meta'])
        matched=0
        for row in c['rows']:
            e=want.get(row['oid'])
            if not e: continue
            matched+=1; nm=D['players'].get(row['oid'],{}).get('n',row['oid'])
            if row['n2']!=sline(e): bad.append('%s live line %r, ESPN box score gives %r'%(nm,row['n2'],sline(e)))
            if row['act'] is None or abs(float(row['act'])-ppr(e))>0.051: bad.append('%s live points %r, ESPN box score gives %.1f'%(nm,row['act'],ppr(e)))
        if matched<3: bad.append('only %d matchup rows matched box-score players, so the live-line test is not meaningful'%matched)
    side=[x for x in RL['sidebar'] if D['games'][x['gi']]['id']==tg['id']]
    if not side or '8:42 - 3rd' not in side[0]['text'] or '17-7' not in side[0]['text']: bad.append('sidebar live entry reads %r'%(side[0]['text'] if side else None))
    pc=[c for c in RL['cards'] if c['id']==pg['id']]
    if 'scores' not in (RL.get('stamp') or ''): bad.append('freshness stamp does not report live scores: %r'%RL.get('stamp'))
    if pc and ((pc[0]['score'] and 'LIVE' in pc[0]['score']) or '8:42' in (pc[0]['meta'] or '') or pc[0].get('live')): bad.append('a scheduled game picked up live styling')
    A.check('U8','A game in progress shows its live score, clock and box-score lines, computed exactly from ESPN\'s payload',bad)

    # ---------------- live win probability, projected final and live line, recomputed here from the fitted model ----------------
    bad=[]; LFp=os.path.join(PIPE,'livefit.json')
    if not os.path.exists(LFp): A.check('U9','Live win probability and projected score match the fitted live model',['pipeline/livefit.json is missing']); return
    LF=json.load(open(LFp)); LC=json.load(open(os.path.join(PIPE,'champion_live.json'))); LCUR=next(v for v in LC['versions'] if v['v']==LC['current'])['params']
    for k in ('ep','margin','total','platt'):
        if (D.get('live') or {}).get(k)!=LCUR.get(k): bad.append('published live model %s differs from the live champion in force'%k)
    LF=dict(LF,**{k:LCUR[k] for k in ('ep','margin','total','platt')})
    if not (LF.get('fit','')[:4].isdigit() and LF.get('test','')[:4].isdigit() and int(LF['test'][:4])>int(LF['fit'][-4:])): bad.append('live model test seasons %r are not after its fit seasons %r'%(LF.get('test'),LF.get('fit')))
    def band(v,edges):
        for i in range(len(edges)-1):
            if edges[i]<=v<edges[i+1]: return i
        return len(edges)-2
    def expect(g,hs,as_,per,secs,dn,dist,yl100,poss_home):
        p=D['pred'][g['id']]; frac=((4-per)*900+secs)/3600.0
        ep=poss_home*LF['ep']['table'][band(yl100,LF['ep']['yard_bands'])][dn-1][band(dist or 10,LF['ep']['dist_bands'])]
        M=LF['margin']; T=LF['total']; M0=p['ph']-p['pa']; T0=p['ph']+p['pa']
        ln=(((D.get('ledger') or {}).get('entries') or {}).get(g['id']) or {}).get('last') or {}   # the last line before kickoff
        msp=ln['spread'] if ln.get('spread') is not None else g.get('spread'); mou=ln['ou'] if ln.get('ou') is not None else g.get('ou')
        if M.get('w_market') and msp is not None: M0=(1-M['w_market'])*M0+M['w_market']*(-msp)
        if T.get('w_market') and mou is not None: T0=(1-T['w_market'])*T0+T['w_market']*mou
        mean=(hs-as_)+M['a_ep']*ep+M['b_prior']*M0*frac+M['c_frac']*frac
        sd=math.sqrt(M['sigma']**2*frac+M['eps']**2); wp=0.5*(1+math.erf(mean/(sd*math.sqrt(2))))
        if LF.get('platt'):
            q=min(1-1e-6,max(1e-6,wp)); wp=1/(1+math.exp(-(LF['platt']['alpha']+LF['platt']['beta']*math.log(q/(1-q)))))
        tot=hs+as_+T['t_prior']*T0*frac+T['t_frac']*frac+T['t_ep']*abs(ep)
        return wp,mean,tot
    MINUS=chr(0x2212)
    def check_strip(g,label,hs,as_,per,secs,dn,dist,yl100,poss_home):
        card=[c for c in RL['cards'] if c['id']==g['id']]; t=(card[0].get('live') if card else None) or ''
        if not t: bad.append('%s (%s) shows no live projection'%(g['a']+'@'+g['h'],label)); return
        wp,mean,tot=expect(g,hs,as_,per,secs,dn,dist,yl100,poss_home)
        wrong=expect(g,hs,as_,per,secs,dn,dist,100-yl100,poss_home)
        if abs(wrong[0]-wp)<0.005: bad.append('%s: field position does not move the live number, so the conversion is untested'%label)
        DOT,DASH=chr(0xb7),chr(0x2013)
        m=re.search(r'Win probability\s*(\S+) (\d+)%\s*'+DOT+r'\s*(\S+) (\d+)%',t); f=re.search(r'Projected final\s*(\S+) (-?[\d.]+)\s*'+DASH+r'\s*(\S+) (-?[\d.]+)',t)
        l=re.search(r'Live spread / total\s*(.+?)\s*'+DOT+r'\s*([\d.]+)$',t)
        if not (m and f and l): bad.append('%s live strip unreadable: %r'%(label,t)); return
        if (m.group(1),m.group(3))!=(g['a'],g['h']) or abs(int(m.group(2))-100*(1-wp))>0.51 or abs(int(m.group(4))-100*wp)>0.51:
            bad.append('%s live win probability %r, model gives %s %.1f%% / %s %.1f%%'%(label,m.group(0),g['a'],100*(1-wp),g['h'],100*wp))
        if abs(float(f.group(2))-(tot-mean)/2)>0.051 or abs(float(f.group(4))-(tot+mean)/2)>0.051:
            bad.append('%s projected final %r, model gives %s %.2f - %s %.2f'%(label,f.group(0),g['a'],(tot-mean)/2,g['h'],(tot+mean)/2))
        v=math.floor(-mean*2+0.5)/2; fxs=lambda x: ('%.1f'%x)[:-2] if ('%.1f'%x).endswith('.0') else '%.1f'%x
        want='PK' if abs(v)<0.05 else ('%s %s%s'%(g['h'],MINUS,fxs(-v)) if v<0 else '%s %s%s'%(g['a'],MINUS,fxs(v)))
        if l.group(1)!=want or abs(float(l.group(2))-math.floor(tot*2+0.5)/2)>0.01:
            bad.append('%s live line %r, model gives %s / %s'%(label,l.group(0),want,math.floor(tot*2+0.5)/2))
    check_strip(tg,'away ball at the home 35 (possession text)',7,17,3,522,2,7,35,-1)
    if tg2: check_strip(tg2,'home ball at its own 20 (yardLine only)',10,3,2,195,1,10,80,1)
    really_live={e['id'] for e in sb['events'] if (e['competitions'][0].get('status') or {}).get('type',{}).get('state')=='in'}
    for c in RL['cards']:
        if c.get('live') and c['id'] not in really_live: bad.append('%s shows a live projection but is not in progress'%c['id'])
    A.check('U9','Live win probability, projected final and live line match the fitted live model, from both ESPN field-position forms',bad)
    return

