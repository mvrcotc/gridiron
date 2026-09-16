"""Partner ads: reads partners.json (repo root) and publishes only the partners the page may show -- one small, labeled
card at the foot of the sidebar. A partner is published only when the file is switched on AND that partner is switched on
with a real https tracking link, a name and a known kind. The fine print is written here, not taken from the file:
sportsbooks always carry 21+ and the problem-gambling helpline, fantasy apps an eligibility note, and every card says
GridIron may earn a commission. A broken or missing file turns ads off; it never stops a refresh."""
import os, re, json
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(ROOT,'data'); CONF=os.path.join(ROOT,'partners.json')
FINE={'dfs':'Age and location eligibility vary by state.',
      'sportsbook':'21+ and present in an eligible state. Gambling problem? Call 1-800-GAMBLER.'}
DISCLOSURE='GridIron may earn a commission from partner links.'
URL=re.compile(r'^https://[^\s"\'<>]+$')
LIMITS=dict(name=40,headline=90,cta=24,terms=160)

def clean(v): return ' '.join(str(v or '').split())

def build(cfg):
    out=dict(on=False,items=[],disclosure=DISCLOSURE); skipped=[]
    if not isinstance(cfg,dict): return out,['partners.json is not an object']
    seen=set()
    for p in cfg.get('partners') if isinstance(cfg.get('partners'),list) else []:
        if not isinstance(p,dict): skipped.append('an entry that is not an object'); continue
        pid=clean(p.get('id')) or '(no id)'
        if p.get('enabled') is not True: skipped.append('%s: switched off'%pid); continue
        f={k:clean(p.get(k)) for k in ('name','headline','cta','terms')}; f['cta']=f['cta'] or 'Visit'
        kind=clean(p.get('kind')); url=str(p.get('url') or '').strip(); why=[]
        if kind not in FINE: why.append('kind must be dfs or sportsbook')
        if not f['name']: why.append('no name')
        if not URL.match(url): why.append('no https tracking link')
        why+=['%s longer than %d characters'%(k,n) for k,n in LIMITS.items() if len(f[k])>n]
        if pid in seen: why.append('duplicate id')
        seen.add(pid)
        if why: skipped.append('%s: %s'%(pid,', '.join(why))); continue
        out['items'].append(dict(id=pid,kind=kind,name=f['name'],headline=f['headline'],cta=f['cta'],url=url,
                                 fine=FINE[kind]+(' '+f['terms'] if f['terms'] else '')))
    if cfg.get('enabled') is not True:
        if out['items']: skipped.append('the whole site is switched off ("enabled": false)')
        out['items']=[]
    out['on']=bool(out['items'])
    return out,skipped

if __name__=='__main__':
    pre=[]
    try: cfg=json.load(open(CONF,encoding='utf-8'))
    except FileNotFoundError: cfg={}; pre=['no partners.json']
    except ValueError as e: cfg={}; pre=['partners.json is not valid JSON (%s)'%str(e)[:60]]
    P,skipped=build(cfg)
    D=json.load(open(os.path.join(DATA,'gi2.json'),encoding='utf-8')); D['partners']=P
    json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
    shown='%d showing: %s'%(len(P['items']),', '.join(x['name'] for x in P['items'])) if P['on'] else 'off'
    print('partners: %s%s'%(shown,('; not shown -- '+'; '.join(pre+skipped)) if pre or skipped else ''))
