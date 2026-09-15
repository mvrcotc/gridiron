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
| `teams` | standings and season statistics for all 32 teams, this season and last (records, division/conference/home/away splits, points, ATS, O/U, streaks, yards, turnover margin); ESPN finals count before nflverse catches up |
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

## The page

- **Teams** (home): standings by division or as one sortable league table, for this season or last, with leader
  tiles and each team's game this week. Ordering is win percentage, then division record, then point differential
  -- simpler than the NFL's full tiebreakers, and the page says so.
- **A game** (pick it in the sidebar): one page with everything about it, in the order the questions come up --
  line, total and implied points; GridIron's own call and injury fallout; both teams' seasons side by side;
  conditions; charts; every matchup with projections or results; and the field (formation or depth chart).
  Section links stay at the top as you scroll.
- **Model**: the track record and how GridIron learns.

Search filters the games in the sidebar (by team or player) and the teams on the Teams page.

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

## Learning loop

The weights of all three models live in versioned registries -- `pipeline/champion.json` (pregame odds),
`pipeline/champion_live.json` (live in-game) and `pipeline/champion_players.json` (player projections) -- and
nothing else sets them. Predictions, projections, the track record and the page all read the version in force
through `pipeline/gamemodel.py`, `pipeline/livemodel.py` and `pipeline/playermodel.py`.

```bash
python3 pipeline/learn.py review [--force] [--update-history]   # weekly, in the daily lane once a week is final
python3 pipeline/learn.py approve <proposal-id>                  # or: Actions -> GridIron refresh -> Run workflow
python3 pipeline/learn.py reject <proposal-id>
```

Each week, for every weight group in `pipeline/learning/spec.json` and `spec_live.json`:

1. **Re-tune** walk-forward: for every week of the last seasons, the value that fits best using only earlier games.
2. **Compare** game by game (play by play for the live model) against the weights actually in force, on games
   neither side saw. Confidence comes from resampling whole weeks, Holm-corrected for every idea tested that review.
3. **Check**: at least 500 games, genuinely better, 95% confidence after correction, better in at least 3 seasons
   with at most 1 worse, and no other measure worse beyond tolerance.
4. **Weigh** pros and cons with an explicit score (size and consistency of the gain vs how far the weight moves,
   added complexity, distance from the closing line, one-season flukes, instability). Cons must not win.
5. **Confirm** in a later review with at least 12 new games.
6. **Act**: a small move (one step, not switching a factor on or off, at most one step per category per season and
   two from launch) applies automatically -- one per model per review, 4-week cooldown -- and is rolled back if it
   then does worse on new games. Anything bigger becomes a proposal: a GitHub issue with the pros and cons, applied
   only when the owner approves and its evidence still holds on the latest games.

`pipeline/learning/` holds the rules, the review log, open proposals, the page summary and the per-game evidence
behind every pending, applied or proposed change. The audit (LG1-LG5) checks the registries, that every change
followed the rules, the review's arithmetic, and recomputes that evidence from raw final scores.

First reviews (games through 2025): nothing met the bar. Closest: backup-QB weight 3.9 -> 2.9 (58% confidence
after correcting for 14 ideas), win-probability calibration (79%). Expect few changes: NFL results are noisy, and
the loop is built to ignore noise.

## Player projections

`pipeline/playermodel.py` holds the panel, the projection formula (vectorised), expected PPR points and the
simulator; `project.py` runs it for the slate and `learn_players.py` reviews its weights. Each player's history is
this season's games before the week at full weight plus last season's at `prev_weight` (launched at ×0.1, the best
of 0–1 on 2021–22). Walk-forward, on player-weeks with a target or carry:

| History used | 2021–22 error (pts) | 2023–25 error (pts) | Players projectable |
|---|---|---|---|
| Last season only (the model before this change) | 5.10 | 5.00 | 81–84% |
| This season only | 4.85 | 4.60 | 90–91% |
| This season + last season ×0.1 / ×0.25 | **4.81** / 4.81 | — / 4.61 | **98%** |

The loop re-tests `prev_weight`, three sample-trust groups (volume, efficiency, passing), the opponent pass-defence
strength and the game-script strength every week (`pipeline/learning/spec_players.json`, registry
`pipeline/champion_players.json`), on expected PPR points per player-week.

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
the same inputs. Launch weights fitted on 2019-22 plays; tested on 2023-25 (140,155 plays), every play predicted
by the live weights in force from the pregame numbers GridIron actually showed (`pipeline/livewp.py`):

| | Brier | Log loss |
|---|---|---|
| GridIron live | 0.1530 | 0.4590 |
| nflfastR, no line | 0.1606 | 0.4758 |
| nflfastR, with the Vegas line | **0.1467** | **0.4431** |

It beats a model without the market and trails one that uses the line. Final margin error from mid-game
plays: 6.88 vs 6.78 for the market's line faded the same way. (An earlier 0.1518 used pregame numbers built
with a season-hindsight backup-QB flag.)

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
| `champion.json` | every pregame weight, versioned: ratings, home edge, backup QB, win-probability calibration, blend, and the zero-weight venue, rest, weather and referee factors. Launched from `hp2.json`, `qbfit.json`, `wpfit.json` (2019–22); changed only by the learning loop |
| `champion_live.json` | the live model's weights, versioned: possession-value table, margin and total coefficients, uncertainty, tail calibration |
| `ptsfit.json` | points from a box score (2025, R² 0.81): TD 5.1, 100 yds 2.3, turnover −1.2 |
| `livefit.json` | the live model's held-out report, written by `livewp.py` |
| `fit1.json`, `fit_k.json`, `fit_opp.json`, `fit_cal.json` | player model: game script, regression constants, pass-defence adjustments, simulator calibration |
| `wxfit.json`, `wxcentre.json` | weather coefficients (sustained wind) and the average conditions they are centred on |
| `absorb.json` | teammates recover 75% of a missing starter's targets and 54% of his carries |
| `hfafit.json`, `reffit.json` | venue edge and referee crew studies shown on the Model page |
| `track.json` | the backtest record, rebuilt by `backtest.py` |

## Track record

Held out, 2023–25, 816 games the model never trained on: margin error **10.27** vs the closing line's
**9.74**; **49.1%** against the spread. All seasons 2019–25: 10.27 vs 9.83, 49.8%. Break-even is 52.4%.
Every game is predicted by the weights in force before its week, and a backup quarterback is flagged only from
starts so far that season -- what the live site can know at kickoff. (The first published record, 10.16 and
49.7%, flagged backups with season hindsight.) It does not beat the market. Its value is explaining why a line
sits where it does, and player detail.

## Not yet done

- The player model's simulator spread (`vol`, `yshape`) and injury absorption rates are in its registry but not
  yet re-tested by the loop; positional baselines, the touchdown curve, game-script line and defence adjustments
  (`fit1.json`, `fit_opp.json`) are still 2025 fits.

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
