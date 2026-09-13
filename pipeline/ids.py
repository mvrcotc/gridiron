"""ESPN athlete id -> gsis id for every player the app knows, so the page can map live ESPN box scores by ID."""
import os, json, csv
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.environ.get('GRIDIRON_DATA') or os.path.join(os.path.dirname(HERE),'data')
D=json.load(open(os.path.join(DATA,'gi2.json'))); season=int(D['games'][0]['date'][:4])
M={}; dup=set()
for f in ('rost%02d.csv'%(season%100),'players_all.csv'):
    for r in csv.DictReader(open(os.path.join(DATA,f),encoding='utf-8')):
        e=(r.get('espn_id') or '').split('.')[0].strip(); g=(r.get('gsis_id') or '').strip()
        if not e or g not in D['players']: continue
        if e in M and M[e]!=g: dup.add(e)
        M.setdefault(e,g)
for e in dup: M.pop(e,None)          # an ESPN id claimed by two players is not trusted
D['espn']=M
json.dump(D,open(os.path.join(DATA,'gi2.json'),'w'),separators=(',',':'))
print('espn id map: %d of %d players (%d ambiguous ids dropped)'%(len(set(M.values())),len(D['players']),len(dup)))
