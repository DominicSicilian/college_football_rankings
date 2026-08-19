# College Football Rankings

End-to-end college football rankings and prediction workflow using SPI, Nature, and SOR components, plus a Flask dashboard for projections and historical performance analysis.

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
5. Commit to git

Example commit sequence:

```bash
git add data_exports/ published_rankings/ README.md
git commit -m "Publish 2026 week 3 rankings + projections"
```

## Notes

- If CFBD API is unavailable, some scripts can still operate from existing cached/exported files.
- Dashboard historical views depend on files in `data_exports/predictions/`.
- This repo currently uses SPI-only prediction mode in the dashboard and historical views.
