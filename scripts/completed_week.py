"""Print the latest regular-season week of <year> that is fully in the books.

Used by scripts/weekly_update.sh to stamp the weekly rankings snapshot with the
right week number. A week counts as complete when every FBS game scheduled in it
has a final score. Prints 0 when no week has finished yet.
"""

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cfbd  # noqa: E402

from api_cache import cached_call  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=dt.date.today().year)
    args = parser.parse_args()

    api_key = (os.environ.get("CFBD_API_KEY") or "").strip()
    if not api_key:
        print(0)
        return

    config = cfbd.Configuration(
        host="https://api.collegefootballdata.com", access_token=api_key
    )
    games_api = cfbd.GamesApi(cfbd.ApiClient(config))

    try:
        games = cached_call(
            games_api.get_games, year=args.year, season_type="regular", classification="fbs"
        )
    except Exception as exc:  # network/API trouble should not break the pipeline
        print(f"completed_week: could not reach CFBD ({exc})", file=sys.stderr)
        print(0)
        return

    by_week = {}
    for game in games:
        week = getattr(game, "week", None)
        if week is None:
            continue
        done = (
            getattr(game, "home_points", None) is not None
            and getattr(game, "away_points", None) is not None
        )
        total, finished = by_week.get(week, (0, 0))
        by_week[week] = (total + 1, finished + (1 if done else 0))

    complete = [w for w, (total, finished) in by_week.items() if total > 0 and total == finished]
    print(max(complete) if complete else 0)


if __name__ == "__main__":
    main()
