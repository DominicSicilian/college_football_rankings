#!/usr/bin/env bash
# Weekly autonomous refresh: rankings -> predictions -> markdown reports -> git push.
#
# Usage:
#   ./scripts/weekly_update.sh [--year 2026] [--no-push] [--no-commit]
#
# Requires CFBD_API_KEY in the environment or in .env at the repo root.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Season year matches rankings.py: anything before Sep 1 belongs to the prior season.
YEAR="$(date -u +%Y)"
if [[ "$(date -u +%m%d)" < "0901" ]]; then
  YEAR=$((YEAR - 1))
fi
DO_PUSH=1
DO_COMMIT=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --year) YEAR="$2"; shift 2 ;;
    --no-push) DO_PUSH=0; shift ;;
    --no-commit) DO_COMMIT=0; DO_PUSH=0; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

log() { printf '\n=== %s ===\n' "$1"; }

# The CFBD API sits behind Cloudflare and intermittently returns retryable 5xx
# on the heavy full-season calls. Unattended runs retry with backoff.
RETRY_ATTEMPTS="${RETRY_ATTEMPTS:-4}"
RETRY_DELAY="${RETRY_DELAY:-90}"

retry() {
  local attempt=1
  until "$@"; do
    if [[ "$attempt" -ge "$RETRY_ATTEMPTS" ]]; then
      echo "Command failed after ${attempt} attempts: $*" >&2
      return 1
    fi
    echo "Attempt ${attempt}/${RETRY_ATTEMPTS} failed; retrying in ${RETRY_DELAY}s: $*" >&2
    sleep "$RETRY_DELAY"
    attempt=$((attempt + 1))
  done
}

# --- Environment -------------------------------------------------------------

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${CFBD_API_KEY:-}" ]]; then
  echo "CFBD_API_KEY is not set. Add it to .env or export it before running." >&2
  exit 1
fi
export CFBD_API_KEY

if [[ -x .venv/bin/python ]]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="$(command -v python3)"
fi
echo "Repo:   $REPO_DIR"
echo "Python: $PYTHON"
echo "Season: $YEAR"

# --- Refresh data ------------------------------------------------------------

log "Detecting latest completed week"
COMPLETED_WEEK="$("$PYTHON" scripts/completed_week.py --year "$YEAR" 2>/dev/null | tail -1)"
if ! [[ "$COMPLETED_WEEK" =~ ^[0-9]+$ ]]; then
  COMPLETED_WEEK=0
fi
echo "Latest fully completed regular-season week: $COMPLETED_WEEK"

log "Refreshing rankings ($YEAR)"
if [[ "$COMPLETED_WEEK" -gt 0 ]]; then
  # Stamp the snapshot as spi_rankings_<year>_w<N>.csv so the backtest in
  # predict_winners_from_spi_history.py can find and score it.
  retry "$PYTHON" rankings.py --year "$YEAR" --as-of-week "$COMPLETED_WEEK"
else
  echo "No week fully complete yet — writing the unstamped season-to-date file."
  retry "$PYTHON" rankings.py --year "$YEAR"
fi

log "Exporting full season schedule ($YEAR)"
retry "$PYTHON" scripts/fetch_season_games.py --year "$YEAR"

log "Refreshing upcoming predictions ($YEAR, all pending)"
retry "$PYTHON" predict_upcoming_matchups.py --year "$YEAR" --all-pending

log "Rebuilding point-in-time ranking index"
retry "$PYTHON" scripts/build_ranking_index.py

log "Verifying no indexed snapshot changed underneath us"
"$PYTHON" scripts/build_ranking_index.py --verify || \
  echo "WARNING: ranking snapshots drifted from the index; past predictions may have shifted."

log "Refreshing historical backtest through $YEAR"
retry "$PYTHON" predict_winners_from_spi_history.py --start-year 2021 --end-year "$YEAR" || \
  echo "Backtest refresh failed; continuing with existing history files."

# --- Publish -----------------------------------------------------------------

log "Archiving published snapshot"
"$PYTHON" publish_weekly_rankings.py --year "$YEAR" --label "weekly_auto_$(date -u +%Y%m%d)" || \
  echo "Snapshot publish skipped."

log "Refreshing benchmark comparison data"
"$PYTHON" scripts/fetch_prediction_tracker.py --year "$YEAR" --refresh || \
  echo "Benchmark refresh failed; PERFORMANCE.md will use the cached copy."

log "Regenerating markdown reports"
"$PYTHON" generate_markdown_reports.py --year "$YEAR"

log "Regenerating performance report"
"$PYTHON" generate_performance_report.py

# --- Commit and push ---------------------------------------------------------

if [[ "$DO_COMMIT" -eq 0 ]]; then
  log "Done (commit skipped)"
  exit 0
fi

log "Committing"
# Commit the reports plus the data the pipeline actually needs on a fresh CI
# checkout: ranking releases (the backtest scans these for available weeks),
# their conference companions, and prediction outputs. Intermediates
# (nature_stats_*, sor_stats_*, teams_*, team_standings_*) are regenerated on
# every run, so they stay out of git.
git add -A RANKINGS.md PREDICTIONS.md PERFORMANCE.md README.md docs published_rankings
shopt -s nullglob
git add -A data_exports/spi_rankings_*.csv \
           data_exports/conference_rankings_*.csv \
           data_exports/season_games_*.csv \
           published_rankings/ranking_index.csv \
           data_exports/benchmarks/*.csv \
           data_exports/predictions/*.csv
shopt -u nullglob

if git diff --cached --quiet; then
  echo "No changes to commit."
  exit 0
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git commit -m "Weekly update: $YEAR rankings and predictions ($(date -u +%Y-%m-%d))

Refreshed SPI rankings, full-season projections, and the generated
RANKINGS.md / PREDICTIONS.md reports.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"

if [[ "$DO_PUSH" -eq 1 ]]; then
  log "Pushing to origin/$BRANCH"
  git push origin "$BRANCH"
fi

log "Done"
