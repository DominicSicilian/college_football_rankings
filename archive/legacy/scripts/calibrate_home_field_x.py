import argparse
import glob
import math
import os
from typing import Dict, Optional

import pandas as pd


def find_latest_predictions_file(predictions_dir: str) -> Optional[str]:
    pattern = os.path.join(predictions_dir, "spi_game_predictions_*.csv")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def normalize_bool(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def logit(p: float) -> float:
    eps = 1e-9
    p = min(1.0 - eps, max(eps, p))
    return math.log(p / (1.0 - p))


def summarize_subset(name: str, frame: pd.DataFrame) -> Dict:
    games = int(len(frame))
    if games == 0:
        return {
            "subset": name,
            "games": 0,
            "home_win_rate": None,
            "x_additive": None,
            "x_logit": None,
        }

    home_wins = int((frame["actual_winner"] == frame["home_team"]).sum())
    home_rate = home_wins / games

    # Additive shift on probability scale around a 50/50 baseline.
    x_add = home_rate - 0.5

    # Logit shift where p' = sigmoid(logit(p) + h), anchored at p=0.5.
    # At p=0.5, this implies h = logit(home_rate).
    x_logit = logit(home_rate)

    return {
        "subset": name,
        "games": games,
        "home_win_rate": home_rate,
        "x_additive": x_add,
        "x_logit": x_logit,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate home-field probability adjustment X from historical outcomes."
    )
    parser.add_argument(
        "--predictions-file",
        type=str,
        default="",
        help="Optional explicit spi_game_predictions CSV path. Defaults to latest in data_exports/predictions.",
    )
    parser.add_argument(
        "--predictions-dir",
        type=str,
        default=os.path.join("data_exports", "predictions"),
        help="Directory for prediction files when --predictions-file is not provided.",
    )
    parser.add_argument("--start-year", type=int, default=None)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument(
        "--even-spi-diff-max",
        type=float,
        default=3.0,
        help="Max absolute SPI difference for the near-even subset.",
    )
    parser.add_argument(
        "--include-postseason",
        action="store_true",
        help="Include postseason in calibration. Default is regular season only.",
    )
    args = parser.parse_args()

    source_file = args.predictions_file or find_latest_predictions_file(args.predictions_dir)
    if not source_file:
        raise SystemExit("No prediction file found. Generate historical predictions first.")

    df = pd.read_csv(source_file)
    if df.empty:
        raise SystemExit(f"Prediction file has no rows: {source_file}")

    required = [
        "year",
        "season_type",
        "home_team",
        "away_team",
        "actual_winner",
        "conference_game",
        "home_spi_used",
        "away_spi_used",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Prediction file is missing required columns: {missing}")

    df = df.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["home_spi_used"] = pd.to_numeric(df["home_spi_used"], errors="coerce")
    df["away_spi_used"] = pd.to_numeric(df["away_spi_used"], errors="coerce")
    df["season_type"] = df["season_type"].astype(str).str.lower().str.strip()
    df["conference_game"] = df["conference_game"].map(normalize_bool)

    # Only scored outcomes.
    df = df[df["actual_winner"].notna()].copy()
    df = df[df["actual_winner"].astype(str).str.strip() != ""].copy()

    if args.start_year is not None:
        df = df[df["year"] >= int(args.start_year)]
    if args.end_year is not None:
        df = df[df["year"] <= int(args.end_year)]

    if not args.include_postseason:
        df = df[df["season_type"] == "regular"]

    if df.empty:
        raise SystemExit("No rows left after filtering.")

    all_games = df
    conference_only = df[df["conference_game"]].copy()

    spi_valid = df[df["home_spi_used"].notna() & df["away_spi_used"].notna()].copy()
    spi_valid["abs_spi_diff"] = (spi_valid["home_spi_used"] - spi_valid["away_spi_used"]).abs()
    near_even = spi_valid[spi_valid["abs_spi_diff"] <= float(args.even_spi_diff_max)].copy()

    summaries = [
        summarize_subset("all_games", all_games),
        summarize_subset("conference_only", conference_only),
        summarize_subset(f"near_even_abs_spi_diff_le_{args.even_spi_diff_max}", near_even),
    ]

    print(f"Source file: {source_file}")
    print(f"Rows used after filters: {len(df)}")
    print("\nCalibration summaries")
    print("subset,games,home_win_rate,x_additive,x_logit")

    def fmt(value) -> str:
        if value is None:
            return ""
        return f"{value:.6f}"

    for s in summaries:
        print(
            f"{s['subset']},{s['games']},"
            f"{fmt(s['home_win_rate'])},"
            f"{fmt(s['x_additive'])},"
            f"{fmt(s['x_logit'])}"
        )


if __name__ == "__main__":
    main()
