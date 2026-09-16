"""The deployable site: what GitHub Pages serves must be exactly the audited data and code, with immutable file names,
and the refresh must refuse to publish when anything fails."""
import os, re, json, hashlib
from common import ROOT, DATA, APP

SITE=os.path.join(ROOT,'site')
def run(A):
    A.section('deployable site'); D=A.D
    vj=os.path.join(SITE,'version.json')
    if not os.path.exists(vj):
        A.check('S0','site/ has been built',['run tools/build_site.py (refresh stage "site")']); return
    V=json.load(open(vj)); code=hashlib.sha1(open(os.path.join(APP,'app.js'),'rb').read()+open(os.path.join(APP,'context.js'),'rb').read()
                     +open(os.path.join(APP,'gridiron-v2.html'),'rb').read()).hexdigest()[:10]   # the shell's CSS is part of the code a browser holds
    miss=[f for f in ('index.html','.nojekyll',V.get('data'),V.get('app'),V.get('context')) if not f or not os.path.exists(os.path.join(SITE,f))]
    S=json.load(open(os.path.join(SITE,V['data']),encoding='utf-8')) if V.get('data') and os.path.exists(os.path.join(SITE,V['data'])) else {}
    meta=S.get('meta') or {}
    if meta.get('faces') and not os.path.exists(os.path.join(SITE,'heads.webp')): miss.append('heads.webp (faces are on)')
    A.check('S1','Every file the current build names is present',miss)
    if not S: return

    body={k:v for k,v in S.items() if k!='meta'}; want=dict(D)
    if not meta.get('faces'): want['sprite']=None
    diff=sorted(k for k in set(body)|set(want) if json.dumps(body.get(k),sort_keys=True)!=json.dumps(want.get(k),sort_keys=True))
    A.check('S2','The site\'s current data file is exactly the audited dataset',['differs in: %s -- rebuild the site after the last pipeline stage'%diff] if diff else [])

    bad=[]
    for k,src in (('app','app.js'),('context','context.js')):
        if open(os.path.join(SITE,V[k]),'rb').read()!=open(os.path.join(APP,src),'rb').read(): bad.append('site/%s is not the audited app/%s'%(V[k],src))
    if (V.get('version'),V.get('code'),V.get('built'))!=(meta.get('version'),meta.get('code'),meta.get('built')): bad.append('version.json does not match the data file meta')
    if V.get('code')!=code: bad.append('site built for code %s, app code is %s'%(V.get('code'),code))
    if (V.get('data'),V.get('app'),V.get('context'))!=('data.%s.json'%V.get('version'),'app.%s.js'%code,'context.%s.js'%code): bad.append('file names are not content-versioned: %s'%V)
    idx=open(os.path.join(SITE,'index.html'),encoding='utf-8').read()
    if 'id="gi-data"' in idx: bad.append('index.html still embeds a dataset')
    if 'version.json' not in idx or 'GRIDIRON_LIVE' not in idx: bad.append('index.html does not load through version.json')
    if re.search(r'<script src="[^"]*(app|context|data)[^"]*">',idx): bad.append('index.html hard-links a script or data file (breaks when Pages serves a cached index)')
    A.check('S3','Immutable, content-versioned files and a loader that never pairs stale code with new data',bad)

    hist=V.get('history') or []; bad=[]
    if not hist or hist[0]!={k:V[k] for k in ('data','app','context')}: bad.append('history does not start with the current build')
    for h in hist:
        for k in ('data','app','context'):
            if not h.get(k) or not os.path.exists(os.path.join(SITE,h[k])): bad.append('carried-forward build is missing %s'%h.get(k))
    A.check('S5','Previous builds a cached version.json may still name are all served',bad,len(hist))

    rf=open(os.path.join(ROOT,'refresh.py'),encoding='utf-8').read()
    wf=os.path.join(ROOT,'.github','workflows','refresh.yml'); w=open(wf).read() if os.path.exists(wf) else ''
    bad=[]
    if not w: bad.append('no .github/workflows/refresh.yml')
    else:
        if w.find('refresh.py --lane')<0 or w.find('upload-pages-artifact')<w.find('refresh.py --lane'): bad.append('workflow does not refresh before uploading the site')
        if 'continue-on-error' in w: bad.append('workflow has continue-on-error, which would publish after a failed audit')
        if 'GRIDIRON_SITE_URL' not in w: bad.append('workflow does not pass the live site URL, so previous builds are not carried forward')
    for lane in ('live','daily'):
        m=re.search(r"'%s'\s*:\s*\[([^\]]*)\]"%lane,rf); order=re.findall(r"'(\w+)'",m.group(1)) if m else []
        if not order or order[-1]!='audit' or 'site' not in order or order.index('site')>order.index('audit'): bad.append('lane %s must build the site and end with the audit: %s'%(lane,order))
    if 'raise SystemExit(1)' not in rf.split('def stage_audit')[1].split('\ndef ')[0]: bad.append('stage_audit does not stop the run on failure')
    A.check('S4','The refresh builds the site, audits it last, and stops before publishing on any failure',bad)
