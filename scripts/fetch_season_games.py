"""Export a season's full game schedule, played and upcoming, to CSV.

The schedule reports need an authoritative list of every game a team plays.
Deriving it from the prediction artifacts does not work: upcoming_spi_predictions
only holds games that have NOT been played, and spi_game_predictions only holds
games the backtest has scored (which requires a completed-week ranking snapshot).
A game that has been played but whose week is not finished yet falls between the
two and disappears from the schedule entirely.

This pulls the schedule straight from CFBD, so it is complete by construction.
"""

import argparse
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cfbd  # noqa: E402

from api_cache import cached_call  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_EXPORTS_DIR = os.path.join(BASE_DIR, "data_exports")

FIELDS = [
    "week",
    "season_type",
    "start_date",
    "home_team",
    "away_team",
    "home_points",
    "away_points",
    "completed",
    "neutral_site",
    "conference_game",
    "home_conference",
    "away_conference",
    "home_classification",
    "away_classification",
    "notes",
]


def attr(game, *names):
    for name in names:
        if hasattr(game, name):
            value = getattr(game, name)
            if value is not None:
                return value
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=dt.date.today().year)
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args()

    api_key = (os.environ.get("CFBD_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("CFBD_API_KEY is not set.")

    config = cfbd.Configuration(
        host="https://api.collegefootballdata.com", access_token=api_key
    )
    games_api = cfbd.GamesApi(cfbd.ApiClient(config))

    rows = []
    seen = set()
    for season_type in ("regular", "postseason"):
        try:
            games = cached_call(games_api.get_games, year=args.year, season_type=season_type)
        except Exception as exc:
            print(f"Could not fetch {season_type} games: {exc}", file=sys.stderr)
            continue

        for game in games:
            home = attr(game, "home_team", "homeTeam")
            away = attr(game, "away_team", "awayTeam")
            week = attr(game, "week")
            if not home or not away:
                continue

            key = (season_type, week, home, away)
            if key in seen:
                continue
            seen.add(key)

            rows.append(
                {
                    "week": week,
                    "season_type": season_type,
                    "start_date": attr(game, "start_date", "startDate") or "",
                    "home_team": home,
                    "away_team": away,
                    "home_points": attr(game, "home_points", "homePoints"),
                    "away_points": attr(game, "away_points", "awayPoints"),
                    "completed": bool(attr(game, "completed") or False),
                    "neutral_site": bool(attr(game, "neutral_site", "neutralSite") or False),
                    "conference_game": bool(attr(game, "conference_game", "conferenceGame") or False),
                    "home_conference": attr(game, "home_conference", "homeConference") or "",
                    "away_conference": attr(game, "away_conference", "awayConference") or "",
                    "home_classification": attr(game, "home_classification", "homeClassification") or "",
                    "away_classification": attr(game, "away_classification", "awayClassification") or "",
                    "notes": attr(game, "notes") or "",
                }
            )

    rows.sort(key=lambda r: (0 if r["season_type"] == "regular" else 1, r["week"] or 0, str(r["start_date"])))

    out_path = args.out or os.path.join(DATA_EXPORTS_DIR, f"season_games_{args.year}.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    played = sum(1 for r in rows if r["home_points"] is not None and r["away_points"] is not None)
    print(f"Wrote {len(rows)} games ({played} played, {len(rows) - played} upcoming) to {out_path}")


if __name__ == "__main__":
    main()
