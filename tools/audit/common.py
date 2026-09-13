"""Shared harness for the GridIron audit.

Every check rebuilds a number from RAW sources with code written for the audit, never by
importing the pipeline that produced it -- the same code checking itself catches nothing.

  FAIL  a displayed number is wrong or an invariant is broken  -> blocks publishing
  WARN  cannot be independently verified, or a method concern   -> listed, does not block
  PASS
"""
import os, json, csv, math
HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(os.path.dirname(HERE))
DATA=os.path.join(ROOT,'data'); RAW=os.path.join(DATA,'raw'); APP=os.path.join(ROOT,'app'); PIPE=os.path.join(ROOT,'pipeline')

def num(v, fb=0.0):
    try:
        x=float(v)
        return x if math.isfinite(x) else fb
    except (TypeError, ValueError):
        return fb

def rows(path):
    with open(path, newline='', encoding='utf-8') as f:
        yield from csv.DictReader(f)

ESPN2NFL={'LAR':'LA','WSH':'WAS'}
NFL2ESPN={v:k for k,v in ESPN2NFL.items()}
def nfl(t): return ESPN2NFL.get(t,t)
def espn(t): return NFL2ESPN.get(t,t)

class Audit:
    def __init__(self):
        self.D=json.load(open(os.path.join(DATA,'gi2.json'), encoding='utf-8'))
        self.results=[]
        self._section='general'
    def section(self, name): self._section=name
    def _add(self, status, cid, title, details, n):
        self.results.append(dict(section=self._section, id=cid, status=status, title=title,
                                 details=[str(d) for d in (details or [])][:12],
                                 more=max(0,len(details or [])-12), n=n))
    def check(self, cid, title, bad, n=None, warn=False):
        """bad: list of human-readable problems. Empty list = PASS."""
        st='PASS' if not bad else ('WARN' if warn else 'FAIL')
        self._add(st, cid, title, bad, n)
        return not bad
    def warn(self, cid, title, details, n=None): self._add('WARN', cid, title, details, n)
    def close(a, b, tol): return abs(num(a)-num(b))<=tol


def slate_week(D):
    """(season, week) of the slate, from nflverse's schedule by ESPN game id"""
    from collections import Counter
    ids={g['id'] for g in D['games']}
    c=Counter((int(r['season']),int(r['week'])) for r in rows(os.path.join(DATA,'games_all.csv')) if (r.get('espn') or '').split('.')[0] in ids)
    return c.most_common(1)[0][0]

def roster_rows(D):
    """gsis -> weekly roster row for the slate's week, or the latest week published before it"""
    season,week=slate_week(D)
    R=[r for r in rows(os.path.join(DATA,'rost%02d.csv'%(season%100))) if (r.get('week') or '').isdigit() and r.get('gsis_id')]
    wks=sorted({int(r['week']) for r in R}); use=max([w for w in wks if w<=week] or wks[:1])
    return {r['gsis_id'].strip():r for r in R if int(r['week'])==use}
