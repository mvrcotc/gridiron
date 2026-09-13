# GridIron

An NFL matchup board for betting and fantasy decisions: every game's conditions, GridIron's own
prediction beside the Vegas line, injury fallout, weather-adjusted player projections, DraftKings prop
lines, and a backtested track record that says plainly what the model can and cannot do.

## Layout

```
app/           the published page: gridiron-v2.html (dataset embedded), app.js, context.js, heads.webp
data/          inputs, the built dataset gi2.json, audit_report.json
data/raw/      raw sources exactly as fetched (depth charts, PFR coverage, ESPN summaries and box scores)
pipeline/      stages, the model, fitted constants (*.json); retired/ holds superseded scripts
tools/audit/   the independent audit -- run.py plus one module per area
refresh.py     the weekly rebuild
```

## Weekly refresh

```bash
python3 refresh.py                 # every stage, in order; stops before publishing if the audit fails
python3 refresh.py --list
python3 refresh.py --stage props
```

| Stage | What it does |
|---|---|
| `sources` | nflverse weekly releases |
| `espn` | scoreboard and per-game summaries into `data/raw/espn/` |
| `weather` | **sustained** 10m wind per venue (Open-Meteo) |
| `context` | pace, pass rate, new-QB flag, venue home edge, referee crew, two-source line badges |
| `stats` | season and last-3 production; target share = his targets / his team's targets |
| `results` | finished-game stat lines; points are nflverse's own `fantasy_points_ppr` |
| `injuries` | injury report matched by ESPN athlete ID, name+team only when no ID exists |
| `project` | player projections: model inputs -> weather -> injury fallout -> simulate |
| `backtest` | track record from the exact live model, plus held-out tests of excluded ingredients |
| `predict` | game predictions from that same model |
| `props` | DraftKings lines, de-duplicated, fetch time stamped |
| `embed` | dataset into `app/gridiron-v2.html` |
| `audit` | independent audit; **any FAIL stops here** |

`project` changes the model's *inputs* (volume, efficiency) for weather and injuries and then simulates,
so count stats stay whole numbers and before/after figures share a per-player seed. Nothing rescales a
finished distribution.

`predict` uses only what `backtest` measured: team ratings, a flat home edge (zero at neutral sites), the
backup-QB term, and recalibrated win probability. Per-venue home edges and conditions adjustments to game
totals were tested on held-out seasons, did not help, and are not used.

## The audit -- run it before every publish

```bash
python3 tools/audit/run.py          # exit code 1 on any FAIL
```

Every check rebuilds a displayed number from raw sources with code written only for the audit, never by
calling the pipeline. It covers game facts against ESPN and nflverse, every player and stat, context
factors, projections, predictions, props, the track record, the rendered page itself (every number, label
and direction a reader sees), code regressions, and live geodata and line drift.

**Rule: never publish with a FAIL.** WARNs are disclosed limits (e.g. prop prices are not published, the
under lean is unproven) and do not block.

Bug classes it now guards against: ESPN/nflverse team codes (LAR/LA, WSH/WAS); gusts used as sustained
wind; receiving yards scaled by catch rate twice; averaged weekly target shares; lost fumbles missed in
PPR; name-based joins (accents, suffixes); rescaled count distributions; stale two-source badges; a live
model that differs from its backtest; breakdown rows that do not add up; non-ASCII scripts; duplicate
function definitions; hardcoded paths and stale track numbers.

## Still not automated

`refresh.py` does not yet rebuild the game list, venues and broadcasts (`pipeline/gen.py`) or the
players, depth charts, usage and coverage tables (`pipeline/gen3.py`). Those read bare filenames from the
working directory. `model.py` and `injuries.py` still name the 2025 / 2026 season files directly.

## Fitted constants

Fitted once and reused, so a refresh cannot tune the model to flatter the current slate.

| File | What it holds |
|---|---|
| `ptsfit.json` | points from a box score (2025, R² 0.81): TD 5.1, 100 yds 2.3, turnover −1.2 |
| `hp2.json` | rating shrinkage, decay, ensemble weights and the flat home edge, tuned on 2019–22 |
| `wpfit.json` | win-probability recalibration, fitted on 2019–22 |
| `qbfit.json` | a backup quarterback is worth 3.9 points of margin |
| `fit1.json`, `fit_k.json`, `fit_opp.json`, `fit_cal.json` | player model: game script, regression constants, pass-defence adjustments, simulator calibration |
| `wxfit.json`, `wxcentre.json` | weather coefficients (sustained wind) and the average conditions they are centred on |
| `absorb.json` | teammates recover 75% of a missing starter's targets and 54% of his carries |
| `hfafit.json`, `reffit.json` | venue edge and referee crew studies shown on the Model page |
| `track.json` | the backtest record, rebuilt by `backtest.py` |

## Track record

Held out, 2023–25, 816 games the model never trained on: margin error **10.16** vs the closing line's
**9.74**; **49.7%** against the spread. All seasons 2019–25: 10.15 vs 9.83, 51.1%. Break-even is 52.4%.
It does not beat the market. Its value is explaining why a line sits where it does, and player detail.

## Data gotchas

- ESPN's weather field is **gusts** (~1.8× sustained). Weather coefficients are fitted on sustained wind.
- ESPN's `site.api` returns **403 to browser-style User-Agents**; send none.
- ESPN team codes `LAR`/`WSH` are nflverse's `LA`/`WAS` -- resolve before every join and lookup.
- Join players on `gsis_id`; ESPN athlete ids map through `espn_id`. Several players have no ESPN id.
- DraftKings props via ESPN's core API carry current and opening lines, no prices.
- `app/app.js` must stay pure ASCII. Write typographic characters as `\uXXXX` escapes and check with the audit.
