import json,math,os,sys
HERE=os.path.dirname(os.path.abspath(__file__))
DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
D=json.load(open(os.path.join(DATA,'gi2.json')))
import hashlib
def _sig(p): return hashlib.md5(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
_ps=D.get('passes') or []
if _ps and isinstance(_ps[-1],dict) and _ps[-1].get('after')==_sig(D['proj']):
    _done=[x.get('p') for x in _ps if isinstance(x,dict)]
else:
    _done=[]; D['passes']=[]      # projections were regenerated since the last pass: start clean
if 'wx' in _done:
    print('wx pass already applied to this exact projection set -- skipped, it would compound'); sys.exit(0)
F=json.load(open(os.path.join(HERE,'wxfit.json')))
CEN=json.load(open(os.path.join(HERE,'wxcentre.json')))
# league baselines the coefficients are deltas against
LG=dict(att=33.73,ypa=7.19,car=26.81,ypc=4.36)

def mults(g):
    dome = 1.0 if (g.get('indoor') or (g.get('roof') or '').lower() in ('dome','closed')) else 0.0
    if dome:
        wind, temp = 0.0, 70.0
    else:
        # sustained 10m wind - the quantity the coefficients were fitted on.
        # ESPN reports gusts, which run ~1.8x sustained and would double the penalty.
        wind = g.get('wsus')
        if wind in (None,''): wind = g.get('rwind')
        wind = 0.0 if wind in (None,'') else float(wind)
        temp = g.get('temp'); temp = g.get('rtemp') if temp in (None,'') else temp
        temp = 60.0 if temp in (None,'') else float(temp)
    w = max(0.0, wind-8.0); c = max(0.0, (45.0-temp))/10.0
    # Centred on average fitted conditions. The fitted deviations average exactly zero within each
    # team-season, so this is mathematically identical to keeping the intercept: a calm game correctly
    # sits a little above an all-weather projection. Written this way so that baseline is explicit.
    d = {k: F[k]['w']*(w-CEN['w']) + F[k]['c']*(c-CEN['c']) + F[k]['dome']*(dome-CEN['dome']) for k in F}
    m = {k: 1.0 + d[k]/LG[k] for k in d}
    return m, dict(wind=round(wind,1), temp=round(temp), dome=bool(dome),
                   d_att=round(d['att'],2), d_ypa=round(d['ypa'],2),
                   d_car=round(d['car'],2), d_ypc=round(d['ypc'],2))

TEAM2G={}
for g in D['games']:
    for t in (g['a'], g['h']): TEAM2G[t]=g
ALIAS={'LA':'LAR','WAS':'WSH'}
PL=D['players']; PJ=D['proj']
touched=0; big=[]
WX={}
for gid_team, g in ((t,g) for g in D['games'] for t in (g['a'],g['h'])):
    pass
for g in D['games']:
    m,info=mults(g)
    WX[g['id']]=dict(m={k:round(v,4) for k,v in m.items()}, **info)

def scale_list(a,f):
    return [round(v*f,1) for v in a] if isinstance(a,list) else a

for gsis,p in PJ.items():
    pl=PL.get(gsis)
    if not pl: continue
    t=pl.get('t')
    g=TEAM2G.get(t) or TEAM2G.get(ALIAS.get(t,''))
    if not g: continue
    m,_=mults(g)
    x=p.get('x') or {}
    tgt=x.get('tgt',0.0) or 0.0; cr=x.get('cr',0.0) or 0.0
    ypt=x.get('ypt',0.0) or 0.0; car=x.get('car',0.0) or 0.0; ypc=x.get('ypc',0.0) or 0.0
    m_t,m_y,m_c,m_p = m['att'],m['ypa'],m['car'],m['ypc']
    xry0=p.get('xry', tgt*cr*ypt); xrec0=p.get('xrec', tgt*cr); xru0=p.get('xru', car*ypc)
    v_rec = 0.1*xry0 + 1.0*xrec0
    v_run = 0.1*xru0
    adj_rec = 0.1*xry0*m_t*m_y + 1.0*xrec0*m_t
    adj_run = 0.1*xru0*m_c*m_p
    denom = v_rec+v_run
    mb = (adj_rec+adj_run)/denom if denom>1e-9 else 1.0
    if abs(mb-1.0) < 0.004:            # nothing worth showing
        continue
    base_med = p.get('med')
    # volumes and rates
    if 'tgt' in x: x['tgt']=round(tgt*m_t,2)
    if 'ypt' in x: x['ypt']=round(ypt*m_y,2)
    if 'car' in x: x['car']=round(car*m_c,2)
    if 'ypc' in x: x['ypc']=round(ypc*m_p,2)
    if 'xry'  in p: p['xry']=round(xry0*m_t*m_y,1)
    if 'xrec' in p: p['xrec']=round(xrec0*m_t,1)
    if 'xru'  in p: p['xru']=round(xru0*m_c*m_p,1)
    if 'qry'  in p: p['qry']=scale_list(p['qry'], m_t*m_y)
    if 'qrec' in p: p['qrec']=scale_list(p['qrec'], m_t)
    if 'qru'  in p: p['qru']=scale_list(p['qru'], m_c*m_p)
    for k in ('med','mean','flr','ceil'):
        if p.get(k) is not None: p[k]=round(p[k]*mb,1)
    if isinstance(p.get('q'),list): p['q']=scale_list(p['q'], mb)
    p['wx']=dict(m=round(mb,3), b=base_med)
    touched+=1
    big.append((abs(mb-1.0), PL[gsis]['n'], pl['p'], t, base_med, p['med'], mb))

D['wx']=WX
D['wxfit']=dict(att=F['att'],ypa=F['ypa'],car=F['car'],ypc=F['ypc'],lg=LG,
  note='Fitted on 3,424 team-games 2019-2025, each game measured against that team’s own '
       'leave-one-out season baseline so stadium and roster habits cannot masquerade as weather.')
D.setdefault('passes',[]).append({'p':'wx','after':_sig(D['proj'])})
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('projections adjusted: %d of %d'%(touched,len(PJ)))
big.sort(reverse=True)
print()
print('%-24s %-4s %-4s %7s %7s %7s'%('biggest movers','pos','tm','before','after','mult'))
for _,n,pos,t,b,a,mb in big[:12]:
    print('%-24s %-4s %-4s %7.1f %7.1f %6.3f'%(n,pos,t,b,a,mb))
print()
print('%-14s %5s %5s %6s %8s %8s'%('game','wind','temp','dome','att mult','ypa mult'))
for g in D['games']:
    w=WX[g['id']]
    print('%-14s %5.0f %5.0f %6s %8.3f %8.3f'%(g['a']+'@'+g['h'],w['wind'],w['temp'],w['dome'],w['m']['att'],w['m']['ypa']))
