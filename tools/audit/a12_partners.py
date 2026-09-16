"""Partner ads: what the data publishes comes only from a switched-on partners.json with real https links and carries the
required fine print (sportsbooks: 21+ and the problem-gambling helpline); the page shows nothing when ads are off and
otherwise one small labeled card in the sidebar, refusing unsafe or incomplete entries even if the data contained them."""
import os, re, json, subprocess, tempfile
from common import ROOT

HELP='1-800-GAMBLER'
def norm(v): return ' '.join(str(v or '').split())
def allowed(cfg):
    """an independent reading of partners.json: (id, kind, name, url) the page may show"""
    if not isinstance(cfg,dict) or cfg.get('enabled') is not True: return []
    out=[]; ids=set()
    for p in cfg.get('partners') or []:
        if not isinstance(p,dict) or p.get('enabled') is not True: continue
        pid=norm(p.get('id')) or '(no id)'; kind=norm(p.get('kind')); name=norm(p.get('name')); url=str(p.get('url') or '').strip()
        ok=(kind in ('dfs','sportsbook') and name and re.match(r'^https://[^\s"\'<>]+$',url) and pid not in ids and len(name)<=40
            and len(norm(p.get('headline')))<=90 and len(norm(p.get('cta')) or 'Visit')<=24 and len(norm(p.get('terms')))<=160)
        ids.add(pid)
        if ok: out.append((pid,kind,name,url))
    return out

def render(partners):
    with tempfile.TemporaryDirectory() as td:
        fx=os.path.join(td,'partners.json'); out=os.path.join(td,'ad.json'); json.dump(partners,open(fx,'w'))
        env=dict(os.environ,GRIDIRON_PARTNERS_FILE=fx)
        r=subprocess.run(['node',os.path.join(os.path.dirname(__file__),'render_dump.js'),out],capture_output=True,text=True,timeout=180,env=env)
        if r.returncode or not os.path.exists(out): return None,((r.stderr or r.stdout) or 'no output')[-240:]
        return json.load(open(out)),None

def run(A):
    A.section('partner ads'); D=A.D; P=D.get('partners'); bad=[]
    try: cfg=json.load(open(os.path.join(ROOT,'partners.json'),encoding='utf-8'))
    except (OSError,ValueError): cfg=None
    if not isinstance(P,dict): bad.append('the data carries no partners block (run the partners stage)')
    else:
        want=allowed(cfg); got=[(x.get('id'),x.get('kind'),x.get('name'),x.get('url')) for x in P.get('items') or []]
        if got!=want: bad.append('published %s, partners.json allows %s'%(got,want))
        if P.get('on')!=bool(want): bad.append('"on" is %s but %d partner(s) are allowed'%(P.get('on'),len(want)))
        if 'commission' not in (P.get('disclosure') or ''): bad.append('no commission disclosure')
        for x in P.get('items') or []:
            f=x.get('fine') or ''
            if x.get('kind')=='sportsbook' and not ('21+' in f and HELP in f): bad.append('%s: sportsbook fine print lacks 21+ or %s'%(x.get('id'),HELP))
            if x.get('kind')=='dfs' and 'eligibility' not in f: bad.append('%s: fantasy fine print lacks the eligibility note'%x.get('id'))
    A.check('AD1','Partner ads are published only from a switched-on partners.json with real https links, with the required fine print',bad,len((P or {}).get('items') or []))

    bad=[]; disc='GridIron may earn a commission from partner links.'
    off,err=render({'on':False,'items':[],'disclosure':disc})
    if err: bad.append('render with ads off failed: %s'%err)
    elif off['ad']['count'] or not off['ad']['hidden'] or off['adsTeams'][0]: bad.append('ads are off but the page shows %s'%off['ad'])
    SB=dict(id='sb',kind='sportsbook',name='Test Book',headline='Test headline',cta='Visit',url='https://example.com/sb?aff=1',
            fine='21+ and present in an eligible state. Gambling problem? Call 1-800-GAMBLER.')
    DF=dict(id='df',kind='dfs',name='Test Fantasy',headline='',cta='Play',url='https://example.com/df',fine='Age and location eligibility vary by state.')
    UNSAFE=[dict(SB,id='script',url='javascript:alert(1)'),dict(SB,id='nohelpline',fine='21+.'),dict(DF,id='plainhttp',url='http://example.com/x'),dict(DF,id='noname',name='')]
    for label,item in (('sportsbook',SB),('fantasy',DF)):
        R,err=render({'on':True,'items':UNSAFE+[item],'disclosure':disc})
        if err: bad.append('%s render failed: %s'%(label,err)); continue
        ad=R['ad']; L=ad['links']
        if ad['hidden'] or ad['count']!=1 or len(L)!=1: bad.append('%s: expected one card with one link, got %s'%(label,ad)); continue
        l=L[0]; rel=(l.get('rel') or '').split()
        if l['href']!=item['url']: bad.append('%s: the page showed %s -- an unsafe or incomplete entry got through'%(label,l['href']))
        if 'sponsored' not in rel or 'noopener' not in rel or l.get('target')!='_blank': bad.append('%s link rel=%r target=%r'%(label,l.get('rel'),l.get('target')))
        if ad['tag']!='Ad': bad.append('%s card is not labeled Ad (%r)'%(label,ad['tag']))
        if 'commission' not in (ad['fine'] or ''): bad.append('%s card has no commission disclosure'%label)
        if label=='sportsbook' and not ('21+' in (ad['fine'] or '') and HELP in (ad['fine'] or '')): bad.append('sportsbook card lacks 21+ or %s'%HELP)
        if R['adsTeams'][1]: bad.append('%s: a partner link appears outside the sidebar card'%label)
    A.check('AD2','Nothing shows when ads are off; otherwise one card labeled Ad with a sponsored, safe link and its fine print, refusing unsafe or incomplete entries',bad,3)
