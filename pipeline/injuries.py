"""Injury report from the raw ESPN game summaries. Players are matched by ESPN athlete ID first; only when
the crosswalk has no ID do we fall back to an accent-insensitive name AND team match, and we record which."""
import os, re, json, csv, glob, unicodedata
from collections import defaultdict
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
E2N={'LAR':'LA','WSH':'WAS'}; nf=lambda t:E2N.get(t,t)
D=json.load(open(os.path.join(DATA,'gi2.json'))); PL=D['players']
esp={}
for f in ('rost26.csv','players_all.csv'):
    for r in csv.DictReader(open(os.path.join(DATA,f),encoding='utf-8')):
        e=(r.get('espn_id') or '').split('.')[0].strip(); g=(r.get('gsis_id') or '').strip()
        if e and g: esp.setdefault(e,g)
def nrm(n):
    n=unicodedata.normalize('NFKD',n).encode('ascii','ignore').decode().lower().replace('.','').replace("'",'').replace('-',' ')
    return ' '.join(re.sub(r'\b(jr|sr|ii|iii|iv|v)\b','',n).split())
byname=defaultdict(list)
for g,p in PL.items(): byname[(nrm(p['n']),nf(p['t']))].append(g)
RAW=os.path.join(DATA,'raw','espn'); files={}
for p in sorted(glob.glob(os.path.join(RAW,'s_*.json'))): files[os.path.basename(p)[2:]]=p
for p in sorted(glob.glob(os.path.join(RAW,'f_*.json'))): files[os.path.basename(p)[2:]]=p     # a final summary supersedes the pre-game one
INJ={}; how={'id':0,'name':0}; unmatched=[]
for p in files.values():
    for blk in json.load(open(p)).get('injuries') or []:
        team=nf((blk.get('team') or {}).get('abbreviation') or '')
        for it in blk.get('injuries') or []:
            a=it.get('athlete') or {}; g=esp.get(str(a.get('id'))); m='id'
            if g not in PL:
                c=byname.get((nrm(a.get('displayName') or ''),team),[]); g=c[0] if len(c)==1 else None; m='name'
            if not g: unmatched.append('%s (%s)'%(a.get('displayName'),team)); continue
            det=it.get('details') or {}
            rec={'s':((it.get('type') or {}).get('abbreviation') or (it.get('status') or '?')[:1]).upper(),'m':m}
            if it.get('status'): rec['sl']=it['status']
            for k,src in (('bp','type'),('loc','location'),('side','side')):
                if det.get(src) and det[src]!='Not Specified': rec[k]=det[src]
            if det.get('returnDate'): rec['ret']=det['returnDate']
            INJ[g]=rec; how[m]+=1
D['injd']=INJ
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('injuries: %d (%d by ESPN id, %d by name+team); not on any app roster: %d'%(len(INJ),how['id'],how['name'],len(unmatched)))
