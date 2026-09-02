# College Football Rankings

End-to-end college football rankings and prediction workflow using SPI, Nature, and SOR components, plus a Flask dashboard for projections and historical performance analysis.

## 📊 Live Reports

| Report | What's In It |
|:---|:---|
| **[📈 Latest Rankings →](RANKINGS.md)** | Current SPI Top 25, the full FBS board, and conference strength |
| **[🔮 Season Predictions →](PREDICTIONS.md)** | Every team's full-season schedule with win probabilities and projected records |

Both files are regenerated automatically every Monday and rendered right here in GitHub — no
download, no local setup needed.

<!-- BEGIN:TOP25 -->

**2026 SPI Top 25 — Preseason**  
_Updated 2026-09-02 02:52 UTC • [Full rankings](RANKINGS.md) • [Season predictions](PREDICTIONS.md)_

> Preseason board — only 12% of teams have played, below the 90% threshold for an in-season ranking.

| # | Team | Conf | Record | SPI | Nature | SOR |
|---:|:---|:---|:---:|---:|---:|---:|
| 1 | **Indiana** | Big Ten | 16-0 | 100.00 | 1.000 | 1.000 |
| 2 | **Oregon** | Big Ten | 13-2 | 85.99 | 0.812 | 0.886 |
| 3 | **Ohio State** | Big Ten | 12-2 | 85.82 | 0.926 | 0.822 |
| 4 | **Texas Tech** | Big 12 | 12-2 | 84.05 | 0.924 | 0.796 |
| 5 | **Miami** | ACC | 13-3 | 81.44 | 0.782 | 0.832 |
| 6 | **Georgia** | SEC | 12-2 | 80.61 | 0.769 | 0.826 |
| 7 | **Utah** | Big 12 | 11-2 | 79.91 | 0.892 | 0.749 |
| 8 | **Notre Dame** | FBS Independents | 10-2 | 79.41 | 0.910 | 0.731 |
| 9 | **Ole Miss** | SEC | 13-2 | 77.35 | 0.753 | 0.785 |
| 10 | **North Texas** | American | 12-2 | 74.47 | 0.882 | 0.671 |
| 11 | **BYU** | Big 12 | 12-2 | 74.20 | 0.637 | 0.798 |
| 12 | **Vanderbilt** | SEC | 10-3 | 72.65 | 0.824 | 0.674 |
| 13 | **Texas A&M** | SEC | 11-2 | 72.41 | 0.752 | 0.709 |
| 14 | **James Madison** | Sun Belt | 12-2 | 72.19 | 0.825 | 0.667 |
| 15 | **Alabama** | SEC | 11-4 | 72.09 | 0.673 | 0.746 |
| 16 | **USC** | Big Ten | 9-4 | 70.13 | 0.707 | 0.698 |
| 17 | **Texas** | SEC | 10-3 | 69.78 | 0.637 | 0.730 |
| 18 | **Oklahoma** | SEC | 10-3 | 69.44 | 0.592 | 0.750 |
| 19 | **Washington** | Big Ten | 9-4 | 69.28 | 0.788 | 0.641 |
| 20 | **Iowa** | Big Ten | 9-4 | 67.83 | 0.637 | 0.701 |
| 21 | **Navy** | American | 11-2 | 67.74 | 0.671 | 0.681 |
| 22 | **Michigan** | Big Ten | 9-4 | 66.03 | 0.640 | 0.671 |
| 23 | **Arizona** | Big 12 | 9-4 | 65.69 | 0.696 | 0.636 |
| 24 | **Tulane** | American | 11-3 | 65.61 | 0.535 | 0.721 |
| 25 | **TCU** | Big 12 | 9-4 | 65.57 | 0.635 | 0.667 |

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
- `generate_markdown_reports.py`: Builds `RANKINGS.md` / `PREDICTIONS.md` / README Top 25
- `scripts/weekly_update.sh`: One-shot weekly refresh + publish + push
- `scripts/completed_week.py`: Detects the latest fully completed week
- `scripts/fetch_season_games.py`: Exports the full season schedule (played + upcoming)
- `ranking_index.py` / `scripts/build_ranking_index.py`: Point-in-time ranking index
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
