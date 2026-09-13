#!/usr/bin/env python3
"""Build the static website in site/ for GitHub Pages.

GitHub Pages caches every file for up to 10 minutes and ignores query strings, so every build writes uniquely
named, immutable files (data.<version>.json, app.<code>.js, context.<code>.js). Only index.html and version.json
change in place; version.json names the current files, and the previous two builds' files are carried forward so a
browser holding a stale version.json never requests a file that no longer exists.
   python3 tools/build_site.py [--no-faces]        GRIDIRON_SITE_URL=https://... carries the live site's builds forward"""
import os, re, sys, json, hashlib, shutil, time, urllib.request
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP=os.path.join(ROOT,'app'); DATA=os.path.join(ROOT,'data'); SITE=os.path.join(ROOT,'site')
faces='--no-faces' not in sys.argv; SITE_URL=os.environ.get('GRIDIRON_SITE_URL','').rstrip('/')
html=open(os.path.join(APP,'gridiron-v2.html'),encoding='utf-8').read()
html=re.sub(r'<script id="gi-data" type="application/json">.*?</script>\n?','',html,count=1,flags=re.S)
assert 'id="gi-data"' not in html and '<script src="app.js"></script>' in html and '<script src="context.js"></script>' in html
code=hashlib.sha1(open(os.path.join(APP,'app.js'),'rb').read()+open(os.path.join(APP,'context.js'),'rb').read()).hexdigest()[:10]
cut=html.index('<div class="shell">'); head,body=html[:cut],html[cut:]
loader=('<script>\n(function(){\n'
 '  window.GRIDIRON_LIVE=true;\n'
 '  var box=document.getElementById("games"); if(box) box.textContent="Loading the latest data\\u2026";\n'
 '  function load(src){ return new Promise(function(ok,no){ var s=document.createElement("script"); s.src=src;'
 ' s.onload=ok; s.onerror=function(){ no(new Error("could not load "+src)); }; document.body.appendChild(s); }); }\n'
 '  function get(u){ return fetch(u,{cache:"no-store"}).then(function(r){ if(!r.ok) throw new Error(u+" HTTP "+r.status); return r.json(); }); }\n'
 '  get("version.json?t="+Date.now())\n'
 '    .then(function(v){ window.GRIDIRON_CODE=v.code; return get(v.data).then(function(d){ window.GRIDIRON_DATA=d; return load(v.context); })'
 '.then(function(){ return load(v.app); }); })\n'
 '    .catch(function(e){ if(box) box.textContent="Could not load GridIron ("+e.message+"). Refresh to try again."; });\n'
 '})();\n</script>')
body=body.replace('<script src="context.js"></script>\n','').replace('<script src="context.js"></script>','').replace('<script src="app.js"></script>',loader)
doc=('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n'
     '<meta name="robots" content="noindex">\n'+head+'</head>\n<body>\n'+body+'\n</body>\n</html>\n')
if os.path.isdir(SITE): shutil.rmtree(SITE)
os.makedirs(SITE)
D=json.load(open(os.path.join(DATA,'gi2.json'),encoding='utf-8'))
if not faces: D['sprite']=None
rep=os.path.join(DATA,'audit_report.json'); audit=json.load(open(rep))['counts'] if os.path.exists(rep) else None
version=hashlib.sha1((json.dumps(D,separators=(',',':'),sort_keys=True)+code).encode()).hexdigest()[:12]
built=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
D['meta']={'version':version,'code':code,'built':built,'audit':audit,'faces':faces}
names={'data':'data.%s.json'%version,'app':'app.%s.js'%code,'context':'context.%s.js'%code}
text=json.dumps(D,separators=(',',':'))
assert '</script' not in text.lower()
open(os.path.join(SITE,'index.html'),'w',encoding='utf-8').write(doc)
open(os.path.join(SITE,names['data']),'w',encoding='utf-8').write(text)
shutil.copy(os.path.join(APP,'app.js'),os.path.join(SITE,names['app'])); shutil.copy(os.path.join(APP,'context.js'),os.path.join(SITE,names['context']))
if faces: shutil.copy(os.path.join(APP,'heads.webp'),os.path.join(SITE,'heads.webp'))
open(os.path.join(SITE,'.nojekyll'),'w').close()
history=[names]
if SITE_URL:
    try: prev=json.load(urllib.request.urlopen(SITE_URL+'/version.json',timeout=20))
    except Exception as e: prev=None; print('no previous build to carry forward (%s)'%str(e)[:80])
    if prev:
        for h in [{k:prev.get(k) for k in ('data','app','context')}]+list(prev.get('history') or []):
            if len(history)>=3: break
            if not all(h.get(k) for k in ('data','app','context')) or h in history: continue
            try:
                for k in ('data','app','context'):
                    dest=os.path.join(SITE,h[k])
                    if not os.path.exists(dest): open(dest,'wb').write(urllib.request.urlopen(SITE_URL+'/'+h[k],timeout=30).read())
                history.append(h)
            except Exception as e: print('could not carry %s forward (%s)'%(h['data'],str(e)[:60]))
V=dict(version=version,code=code,built=built,history=history,**names)
open(os.path.join(SITE,'version.json'),'w').write(json.dumps(V))
print('site/ built: version %s, code %s, faces %s, %d build(s) available'%(version,code,faces,len(history)))
for f in sorted(os.listdir(SITE)): print('  %-28s %8.1f KB'%(f,os.path.getsize(os.path.join(SITE,f))/1024))
