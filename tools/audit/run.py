#!/usr/bin/env python3
"""Run the GridIron audit.   python3 tools/audit/run.py [module ...]   (default: every a*.py)
Exit code 1 if any check FAILs -- refresh.py uses that to refuse publishing."""
import os, sys, glob, json, importlib, time, traceback
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
from common import Audit, DATA
mods=sys.argv[1:] or sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(HERE,'a[0-9]_*.py')))
mods=[m for a in mods for m in ([a] if a.startswith('a') and '_' in a else
      [os.path.basename(p)[:-3] for p in glob.glob(os.path.join(HERE,a+'_*.py'))])]
A=Audit(); t0=time.time()
for m in mods:
    try: importlib.import_module(m).run(A)
    except Exception:
        A.section(m); A._add('FAIL','CRASH','audit module %s crashed'%m,traceback.format_exc().strip().split('\n')[-4:],None)
cur=None; C={'PASS':0,'WARN':0,'FAIL':0}
for r in A.results:
    C[r['status']]+=1
    if r['section']!=cur:
        cur=r['section']; print('\n== %s =='%cur)
    n='' if r['n'] is None else '  (n=%s)'%r['n']
    print('  %-4s %-5s %s%s'%(r['status'],r['id'],r['title'],n))
    if r['status']!='PASS':
        for d in r['details']: print('         - '+d)
        if r['more']: print('         ... and %d more'%r['more'])
print('\n%d PASS   %d WARN   %d FAIL   (%.0fs)'%(C['PASS'],C['WARN'],C['FAIL'],time.time()-t0))
json.dump(dict(when=time.strftime('%Y-%m-%dT%H:%M:%S'),counts=C,results=A.results),
          open(os.path.join(DATA,'audit_report.json'),'w'),indent=1)
sys.exit(1 if C['FAIL'] else 0)
