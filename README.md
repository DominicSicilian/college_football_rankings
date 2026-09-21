# College Football Rankings

End-to-end college football rankings and prediction workflow using SPI, Nature, and SOR components, plus a Flask dashboard for projections and historical performance analysis.

## 📊 Live Reports

| Report | What's In It |
|:---|:---|
| **[🗓️ This Week's Picks →](UPCOMING.md)** | Every game on the upcoming week's slate with the model's pick and win probability |
| **[📈 Latest Rankings →](RANKINGS.md)** | Current SPI Top 25, the full FBS board, and conference strength |
| **[🔮 Season Predictions →](PREDICTIONS.md)** | Every team's full-season schedule with win probabilities and projected records |
| **[🎯 Model Performance →](PERFORMANCE.md)** | Accuracy by season, segment, week and confidence band, plus the full prediction log |

Both files are regenerated automatically every Monday and rendered right here in GitHub — no
download, no local setup needed.

<!-- BEGIN:TOP25 -->

**2026 SPI Top 25 — Week 3**  
_Updated 2026-09-21 20:24 UTC • [Full rankings](RANKINGS.md) • [Season predictions](PREDICTIONS.md)_


| # | Team | Conf | Record | SPI | Nature | SOR |
|---:|:---|:---|:---:|---:|---:|---:|
| 1 | **Texas** | SEC | 3-0 | 78.64 | 0.390 | 1.000 |
| 2 | **Alabama** | SEC | 3-0 | 63.55 | 0.303 | 0.815 |
| 3 | **West Virginia** | Big 12 | 3-0 | 62.51 | 0.423 | 0.734 |
| 4 | **Mississippi State** | SEC | 3-0 | 58.45 | 0.514 | 0.623 |
| 5 | **Tennessee** | SEC | 3-0 | 56.10 | 0.645 | 0.516 |
| 6 | **Florida** | SEC | 3-0 | 55.57 | 0.604 | 0.529 |
| 7 | **Virginia Tech** | ACC | 3-0 | 54.40 | 0.606 | 0.511 |
| 8 | **Ole Miss** | SEC | 3-0 | 53.16 | 0.179 | 0.722 |
| 9 | **UCLA** | Big Ten | 3-0 | 51.79 | 0.381 | 0.591 |
| 10 | **Indiana** | Big Ten | 3-0 | 50.60 | 0.918 | 0.284 |
| 11 | **Notre Dame** | FBS Independents | 3-0 | 50.54 | 0.512 | 0.502 |
| 12 | **Pittsburgh** | ACC | 3-0 | 50.33 | 0.331 | 0.596 |
| 13 | **Iowa** | Big Ten | 3-0 | 49.69 | 0.570 | 0.457 |
| 14 | **Penn State** | Big Ten | 3-0 | 49.04 | 0.720 | 0.367 |
| 15 | **USC** | Big Ten | 4-0 | 47.06 | 0.305 | 0.560 |
| 16 | **Duke** | ACC | 3-0 | 44.66 | 0.295 | 0.528 |
| 17 | **Miami** | ACC | 3-0 | 43.69 | 0.915 | 0.179 |
| 18 | **Michigan** | Big Ten | 3-0 | 42.43 | 0.139 | 0.578 |
| 19 | **Kansas State** | Big 12 | 3-0 | 42.21 | 0.736 | 0.253 |
| 20 | **Georgia** | SEC | 3-0 | 39.89 | 1.000 | 0.075 |
| 21 | **Tulsa** | American | 3-0 | 39.23 | 0.341 | 0.420 |
| 22 | **Cincinnati** | Big 12 | 3-0 | 38.95 | 0.548 | 0.304 |
| 23 | **LSU** | SEC | 2-1 | 38.86 | 0.322 | 0.425 |
| 24 | **Texas A&M** | SEC | 2-1 | 35.72 | 0.307 | 0.384 |
| 25 | **Utah** | Big 12 | 3-0 | 35.31 | 0.876 | 0.071 |

<!-- END:TOP25 -->

## What This Repo Includes

- Weekly and postseason ranking generation
- Historical winner prediction backtests
- Upcoming matchup win-probability projections
- A dashboard with:
  - Current rankings and CFP field projection
  - Future matchup board
  - Team-level projected records
  - Historical performance by year/week with filters
- Weekly publication snapshots so each live rankings release is archived in git

## Repository Layout

- `rankings.py`: Core ranking generation pipeline
- `api_cache.py`: On-disk cache for CFBD API responses
- `generate_markdown_reports.py`: Builds `UPCOMING.md` / `RANKINGS.md` / `PREDICTIONS.md` / README Top 25
- `scripts/weekly_update.sh`: One-shot weekly refresh + publish + push
- `scripts/completed_week.py`: Detects the latest fully completed week
- `scripts/reconcile_cache.py`: Purges active-season game caches stale vs live results
- `scripts/fetch_season_games.py`: Exports the full season schedule (played + upcoming)
- `ranking_index.py` / `scripts/build_ranking_index.py`: Point-in-time ranking index
- `generate_performance_report.py`: Builds `PERFORMANCE.md` and `docs/game_log/`
- `predict_winners_from_spi_history.py`: Historical prediction backtest + accuracy slices
- `predict_upcoming_matchups.py`: Upcoming games predictions (next week or all pending)
- `spi_dashboard_app.py`: Main dashboard backend
- `templates/`, `static/`: Dashboard UI
- `data_exports/`: Generated ranking and stats artifacts
- `data_exports/predictions/`: Historical and upcoming prediction outputs
- `published_rankings/`: Git-friendly weekly publication snapshots (created by script)
- `publish_weekly_rankings.py`: Snapshot publisher for live weekly rankings

## Prerequisites

- Python 3.10+
- CFBD API key (for live pulls): https://collegefootballdata.com

## Setup

```bash
cd college_football_rankings
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Set your API key in your shell (or `.env` loader of choice):

```bash
export CFBD_API_KEY="your_key_here"
```

## Generate / Refresh Rankings

Example: refresh rankings for a specific year and week range.

```bash
python rankings.py --year 2026 --start_week 1 --end_week 3
```

This writes refreshed files under `data_exports/`, including `spi_rankings_*.csv` and related stats.

### API Response Caching

`rankings.py` makes several hundred sequential CFBD calls per run (one pair per team for the
Nature pass, one more per team for SOR). `api_cache.py` memoizes those responses to
`data_exports/api_cache/` so runs are fast and survive CFBD's intermittent Cloudflare 502s:

- **Closed seasons** (anything before the season in progress) are cached permanently — their
  results never change.
- **The active season** honors `CFB_CACHE_TTL_HOURS` (default `6`), so a weekly refresh always
  re-pulls live results while a single run reuses its own calls.
- The SOR pass reuses the Nature pass's per-team game queries, so roughly half the calls are
  cache hits even on a cold run.
- A retry after an API error replays from disk instead of starting over.
- **Staleness guard:** before each weekly run, `scripts/reconcile_cache.py` makes one
  cheap pass over the live slate and deletes any active-season game-cache entry that holds
  a now-final game as unfinished. This is what keeps a game that goes final *after* the
  cache was built (e.g. a Sunday-night result) from being missed on the next run — a
  failure mtime-based freshness alone can miss across a CI cache restore.

Responses are pickled, so cfbd's model objects round-trip exactly. Each run prints a hit/miss
summary on exit. To bypass the cache:

```bash
python rankings.py --year 2026 --no-cache     # or: CFB_NO_CACHE=1
```

The cache directory is gitignored and safe to delete at any time.

## Run Prediction Pipelines

Historical backtest + performance files:

```bash
python predict_winners_from_spi_history.py --start-year 2021 --end-year 2026
```

Upcoming predictions:

```bash
# Next week only
python predict_upcoming_matchups.py --year 2026

# All remaining games
python predict_upcoming_matchups.py --year 2026 --all-pending
```

## Run Dashboard

```bash
python spi_dashboard_app.py
```

Open: `http://127.0.0.1:5055`

Optional runtime overrides:

- `SPI_DASHBOARD_HOST`
- `SPI_DASHBOARD_PORT`
- `SPI_DASHBOARD_DEBUG`

## How To View Projections And Performance

### Current Landscape

- Current SPI rankings
- CFP projected 12-team field
- Playoff bracket view
- Component tables (Nature and SOR)
- Next-week matchups with win probabilities

### Future Matchups

- All upcoming games by week
- Team filter
- Team-oriented matchup rows and projected winner context

### Projected W-L

- Team-level projected records for remaining schedule
- Probabilistic record and binary pick-based record
- Includes current record and preseason override behavior (0-0)

### Historical Performance

- Yearly performance bars
- Baseline overall dotted reference line
- Filter controls for year/week/team/conference/etc.
- Raw predicted vs actual game table

## Publishing Live Weekly Rankings (Git Record)

Use the publisher to archive each live rankings release in `published_rankings/`.

```bash
python publish_weekly_rankings.py --year 2026 --label week3_release
```

What it does:

- Detects latest `spi_rankings_<year>*.csv` (unless `--source-file` is provided)
- Collects matching companion files for that same snapshot label when present:
  - `conference_rankings_*`
  - `nature_stats_*`
  - `sor_stats_*`
  - `team_standings_*`
  - `cross_conference_standings_*`
- Writes a timestamped folder in `published_rankings/`
- Updates `published_rankings/manifest.csv`

This gives you a clear audit trail of each weekly published ranking state in git.

## Suggested Weekly Workflow

1. Refresh rankings (`rankings.py`)
2. Generate upcoming projections (`predict_upcoming_matchups.py`)
3. (Optional) refresh backtest summary (`predict_winners_from_spi_history.py`)
4. Publish snapshot (`publish_weekly_rankings.py`)
5. Regenerate the markdown reports (`generate_markdown_reports.py`)
6. Commit to git

All of the above is wrapped up in one script:

```bash
./scripts/weekly_update.sh --year 2026
```

That refreshes rankings and predictions, rewrites `RANKINGS.md` / `PREDICTIONS.md` / the README
Top 25 block, archives a snapshot, then commits and pushes. It runs unattended every Monday.

Markdown-only refresh (no API calls, uses whatever CSVs are already on disk):

```bash
python generate_markdown_reports.py --year 2026
```

### Early-Season Gate

A ranking built from one week of games is mathematically correct and practically useless — a
single upset can put a two-win team in the top 10. So `generate_markdown_reports.py` will not
publish an in-season board until **at least 90% of teams have played a game**. Below that
threshold it publishes the preseason release instead and says so in a banner on both
`RANKINGS.md` and the README block.

This costs nothing in accuracy: preseason SPI already carries the previous season forward
through its Strength of Record component. Adjust or disable the threshold with:

```bash
python generate_markdown_reports.py --year 2026 --min-played-pct 50
```

The weekly snapshot is stamped with the latest *fully completed* week
(`scripts/completed_week.py` detects it) so `predict_winners_from_spi_history.py` can find and
score it:

```bash
python rankings.py --year 2026 --as-of-week 4    # writes spi_rankings_2026_w4.csv
```

## Prediction Ledger (Point-In-Time)

Every prediction is logged against the ranking snapshot that actually existed before kickoff, so
past accuracy can be audited rather than taken on faith.

`published_rankings/ranking_index.csv` holds one row per ranking snapshot: the instant it became
the newest available ranking (`effective_through_utc`), where it lives, and a SHA-256 of its
contents. Resolving a prediction means "the snapshot with the greatest `effective_through_utc`
strictly before this game's kickoff."

```bash
python scripts/build_ranking_index.py            # (re)build the index
python scripts/build_ranking_index.py --year 2026
python scripts/build_ranking_index.py --verify   # detect drift; exits 1 if any
```

Why by kickoff rather than by week number:

- A week can straddle two weekends. In 2026 USC plays San José State on Aug 29 and Fresno State
  on Sep 5, both filed as week 1. A week number cannot say which rankings existed at each
  kickoff; a timestamp can.
- `rankings.py` writes weekly snapshots to fixed paths, so re-running it overwrites them. The
  stored hash turns that from a silent rewrite of history into a reported drift.

The ledger itself is `data_exports/predictions/spi_game_predictions_<start>_<end>.csv`. Each row
records `ranking_source`, `ranking_source_file`, and `ranking_source_team_count` alongside the
prediction and the eventual result, so any row can be traced back to the exact board it came from.

Because the schedule drives the evaluation loop, predictions for games that have not happened yet
are logged with empty result fields and filled in once played. Re-running before kickoff refreshes
a pending prediction to the newest pre-game board; once a game is played its resolution is frozen,
since no later snapshot can precede its kickoff.

## Automated Weekly Updates

Everything on this page refreshes itself. Two pieces work together:

**1. GitHub Actions — does the work.** `.github/workflows/weekly-update.yml` runs every Monday at
16:00 UTC (noon ET during EDT, 11am ET once EST starts). It refreshes rankings and projections
from the CFBD API, regenerates `RANKINGS.md`, `PREDICTIONS.md`, and the README Top 25 block, then
commits and pushes to `main`.

One-time setup — add your CFBD key as a repository secret:

```bash
gh secret set CFBD_API_KEY --repo DominicSicilian/college_football_rankings
```

Trigger a run by hand any time:

```bash
gh workflow run weekly-update.yml --repo DominicSicilian/college_football_rankings
```

**2. A scheduled Claude agent — watches the work.** A cloud routine runs each Monday at 17:00 UTC,
one hour after the workflow. It verifies the report timestamps are fresh, checks the workflow run
status, sanity-checks the table contents, and opens a PR if the failure was a bug in this repo's
code. Manage it at <https://claude.ai/code/routines>.

## Notes

- If CFBD API is unavailable, some scripts can still operate from existing cached/exported files.
- Dashboard historical views depend on files in `data_exports/predictions/`.
- This repo currently uses SPI-only prediction mode in the dashboard and historical views.
