# GridIron

An NFL matchup board for betting and fantasy decisions: every game's conditions, GridIron's own
prediction beside the Vegas line, a live win probability and projected final while games are on,
injury fallout, weather-adjusted player projections, DraftKings prop lines, and a backtested track
record that says plainly what the model can and cannot do.

Live at https://mvrcotc.github.io/gridiron/

## Layout

```
app/                  page source: gridiron-v2.html, app.js (pure ASCII), context.js, heads.webp
data/                 inputs and the built dataset gi2.json
data/raw/             raw sources exactly as fetched (depth charts, coverage, ESPN summaries and box scores)
data/history/         history.sqlite, every game, team week, player week and play since 1999 (not in git)
pipeline/             stages, the models and their fitted constants (*.json)
tools/audit/          the independent audit: run.py plus one module per area
tools/build_site.py   writes site/ for GitHub Pages
tools/stress_espn.py  feeds corrupted ESPN payloads through the ESPN-reading stages
refresh.py            runs a lane of stages; stops before publishing on any failure
.github/workflows/    the cloud refresh and deploy
```

## Refresh

```bash
python3 refresh.py --lane live     # lines, injuries, weather, projections, props, site, audit
python3 refresh.py --lane daily    # also nflverse sources, stats and the backtest; full audit
python3 refresh.py --list
python3 refresh.py --stage props
```

| Stage | What it does |
|---|---|
| `sources` | nflverse releases, every CSV header checked |
| `espn` | scoreboard and per-game summaries into `data/raw/espn/`; fails if any summary is missing |
| `slate` | the week's games, venues, roofs, broadcasts |
| `roster` | players, depth charts, usage and coverage for the slate week |
| `weather` | **sustained** 10m wind per venue (Open-Meteo); recorded conditions for finished games |
| `games` | status, final scores, lines, forecast weather, ESPN win probability, attendance |
| `context` | pace, pass rate, new-QB flag, venue home edge, referee crew, two-source line badges |
| `stats` | season and last-3 production; target share = his targets / his team's targets |
| `results` | finished-game stat lines; points are nflverse's own `fantasy_points_ppr` |
| `injuries` | injury report matched by ESPN athlete ID, name+team only when no ID exists |
| `project` | player projections: model inputs -> weather -> injury fallout -> simulate |
| `backtest` | (daily) track record from the exact live model, plus held-out tests of excluded ingredients |
| `predict` | game predictions from that same model; carries the live model's constants into the data |
| `props` | DraftKings lines, de-duplicated, fetch time stamped |
| `ids` | ESPN athlete id -> gsis_id map the browser uses for live box scores |
| `site` | versioned site files |
| `audit` | independent audit; **any FAIL stops here** |

`project` changes the model's *inputs* (volume, efficiency) for weather and injuries and then simulates,
so count stats stay whole numbers and before/after figures share a per-player seed. Nothing rescales a
finished distribution.

`predict` uses only what `backtest` measured: team ratings, a flat home edge (zero at neutral sites), the
backup-QB term, and recalibrated win probability. Per-venue home edges and conditions adjustments to game
totals were tested on held-out seasons, did not help, and are not used.

## Hosting and how fresh it is

- **In the browser, every minute during game windows** (every 10 minutes otherwise): scores, clock, box
  scores and the live win probability come straight from ESPN, which allows cross-origin requests.
- **In the cloud:** `.github/workflows/refresh.yml` runs the live lane, audits, and deploys to GitHub Pages.
  GitHub starts scheduled runs late and skips many (about one every two hours in practice), so while a
  game is within 8 hours of kickoff, under way, or finished within 5 hours, each run queues the next one
  itself about 10 minutes after it started. Only one chain runs; cancelling a run ends it. The daily lane
  runs at 09:03 UTC and commits `data/gi2.json` and `pipeline/track.json`.
- **Cache-safe deploys:** the Pages CDN caches for up to 10 minutes and ignores query strings, so each build
  writes content-versioned files (`data.<v>.json`, `app.<code>.js`, `context.<code>.js`). `version.json` names
  the current ones and the page swaps in new data without reloading. Two previous builds stay served.

## History database

```bash
python3 pipeline/history.py              # incremental: reloads the current and previous season
python3 pipeline/history.py --rebuild    # everything since 1999 (about 600 MB)
```

SQLite at `data/history/history.sqlite`: `games` (7,548), `team_week` (14,535), `player_week` (476,294),
`plays` (1.28 million, about 90 play-by-play columns). It is local only; the fitted constants built from it
are committed.

## Live model

`pipeline/livewp.py` fits it from the history database and writes `pipeline/livefit.json`:

```
mean = D + a*EP_home + b*M0*frac + c*frac      D = home lead, M0 = GridIron's pregame margin,
sd   = sqrt(sigma^2*frac + eps^2)              frac = share of regulation left,
home win probability = Phi(mean / sd)          EP_home = expected points of the current possession
```

A Platt tail calibration is applied only because it improved both Brier score and log loss on a validation
season (fit 2019-21, checked on 2022) before the test seasons were looked at. The projected total uses
the same inputs. Fitted on 2019-22 plays, tested on 2023-25 (140,155 plays):

| | Brier | Log loss |
|---|---|---|
| GridIron live | 0.1518 | 0.4560 |
| nflfastR, no line | 0.1606 | 0.4758 |
| nflfastR, with the Vegas line | **0.1467** | **0.4431** |

It beats a model without the market and trails one that uses the line. Final margin error from mid-game
plays: 6.84 vs 6.78 for the market's line faded the same way.

## The audit -- run it before every publish

```bash
python3 tools/audit/run.py          # exit code 1 on any FAIL
python3 tools/stress_espn.py DIR    # ESPN schema drift: numbers sent as words, fields missing
```

Every check rebuilds a displayed number from raw sources with code written only for the audit, never by
calling the pipeline. It covers game facts against ESPN and nflverse, every player and stat, context
factors, projections, predictions, props, the track record, the rendered page itself (every number, label
and direction a reader sees), a game in progress rendered from real ESPN payloads (U8), the live win
probability recomputed from the fitted model for both field-position forms ESPN sends (U9), code
regressions, and live geodata and line drift.

**Rule: never publish with a FAIL.** WARNs are disclosed limits (e.g. prop prices are not published, the
under lean is unproven, ESPN sent a word where a number belongs) and do not block.

Bug classes it now guards against: ESPN/nflverse team codes (LAR/LA, WSH/WAS); gusts used as sustained
wind; receiving yards scaled by catch rate twice; averaged weekly target shares; lost fumbles missed in
PPR; name-based joins (accents, suffixes); rescaled count distributions; stale two-source badges; a live
model that differs from its backtest; breakdown rows that do not add up; non-ASCII scripts; duplicate
function definitions; hardcoded paths and stale track numbers; ESPN values that change type on game day;
field position read from the wrong goal line.

## Fitted constants

Fitted once and reused, so a refresh cannot tune the model to flatter the current slate.

| File | What it holds |
|---|---|
| `ptsfit.json` | points from a box score (2025, R² 0.81): TD 5.1, 100 yds 2.3, turnover −1.2 |
| `hp2.json` | rating shrinkage, decay, ensemble weights and the flat home edge, tuned on 2019–22 |
| `wpfit.json` | win-probability recalibration, fitted on 2019–22 |
| `qbfit.json` | a backup quarterback is worth 3.9 points of margin |
| `livefit.json` | the live model: expected-points table, margin and total coefficients, tail calibration, held-out report |
| `fit1.json`, `fit_k.json`, `fit_opp.json`, `fit_cal.json` | player model: game script, regression constants, pass-defence adjustments, simulator calibration |
| `wxfit.json`, `wxcentre.json` | weather coefficients (sustained wind) and the average conditions they are centred on |
| `absorb.json` | teammates recover 75% of a missing starter's targets and 54% of his carries |
| `hfafit.json`, `reffit.json` | venue edge and referee crew studies shown on the Model page |
| `track.json` | the backtest record, rebuilt by `backtest.py` |

## Track record

Held out, 2023–25, 816 games the model never trained on: margin error **10.16** vs the closing line's
**9.74**; **49.7%** against the spread. All seasons 2019–25: 10.15 vs 9.83, 51.1%. Break-even is 52.4%.
It does not beat the market. Its value is explaining why a line sits where it does, and player detail.

## Not yet done

- The player projection model is still fitted on 2025 alone; the history database is there to widen it.

## Data gotchas

- ESPN's weather field is **gusts** (~1.8× sustained). Weather coefficients are fitted on sustained wind.
- ESPN's `site.api` returns **403 to browser-style User-Agents**; send none.
- ESPN team codes `LAR`/`WSH` are nflverse's `LA`/`WAS` -- resolve before every join and lookup.
- On game day ESPN sent weather `conditionId` as words (`"Sunny"`) instead of a number. Parse every ESPN
  value defensively; `tools/stress_espn.py` feeds these cases through the stages.
- ESPN's `yardLine` is measured from the **home** goal line. Yards to the end zone are `100 - yardLine` when
  the home team has the ball and `yardLine` when the away team does; prefer `yardsToEndzone` or the
  `"KC 35"` possession text when present.
- Join players on `gsis_id`; ESPN athlete ids map through `espn_id`. Several players have no ESPN id.
- DraftKings props via ESPN's core API carry current and opening lines, no prices.
- GitHub Pages caches for up to 10 minutes and ignores query strings: version file names, never `?v=`.
- `app/app.js` must stay pure ASCII. Write typographic characters as `\uXXXX` escapes and check with the audit.
