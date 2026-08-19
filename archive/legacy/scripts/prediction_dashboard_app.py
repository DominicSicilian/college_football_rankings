import glob
import os
from typing import Dict, List

import pandas as pd
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

PREDICTIONS_DIR = os.path.join(os.path.dirname(__file__), "data_exports", "predictions")
DEFAULT_PAGE_SIZE = 250
MAX_PAGE_SIZE = 2000


def normalize_text(value) -> str:
    if pd.isna(value) or value is None:
        return ""
    return str(value).strip()


def prediction_file_candidates() -> List[str]:
    pattern = os.path.join(PREDICTIONS_DIR, "spi_game_predictions_*.csv")
    return sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)


def load_predictions_df() -> pd.DataFrame:
    files = prediction_file_candidates()
    if not files:
        return pd.DataFrame()

    df = pd.read_csv(files[0])
    if df.empty:
        return df

    # Normalize expected columns and dtypes.
    required_defaults = {
        "year": 0,
        "season_type": "",
        "week": 0,
        "home_team": "",
        "away_team": "",
        "home_conference": "Unknown",
        "away_conference": "Unknown",
        "conference_game": False,
        "predicted_winner": "",
        "actual_winner": "",
        "correct": pd.NA,
        "prediction_reason": "",
        "is_playoff": False,
        "is_national_championship": False,
        "conference_matchup": "Unknown vs Unknown",
        "ranking_source": "",
        "ranking_source_file": "",
        "ranking_source_team_count": pd.NA,
    }

    for col, default in required_defaults.items():
        if col not in df.columns:
            df[col] = default

    df["year"] = pd.to_numeric(df["year"], errors="coerce").fillna(0).astype(int)
    df["week"] = pd.to_numeric(df["week"], errors="coerce").fillna(0).astype(int)
    df["correct"] = pd.to_numeric(df["correct"], errors="coerce")
    df["ranking_source_team_count"] = pd.to_numeric(
        df["ranking_source_team_count"], errors="coerce"
    )

    for bool_col in [
        "conference_game",
        "is_playoff",
        "is_national_championship",
    ]:
        df[bool_col] = (
            df[bool_col]
            .map(lambda v: str(v).strip().lower() in {"1", "true", "yes"})
            .fillna(False)
        )

    text_cols = [
        "season_type",
        "home_team",
        "away_team",
        "home_conference",
        "away_conference",
        "predicted_winner",
        "actual_winner",
        "prediction_reason",
        "conference_matchup",
        "ranking_source",
        "ranking_source_file",
        "notes",
    ]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].map(normalize_text)

    # Build conference matchup if missing/empty.
    missing_matchup = df["conference_matchup"].eq("")
    if missing_matchup.any():
        df.loc[missing_matchup, "conference_matchup"] = df.loc[missing_matchup].apply(
            lambda row: " vs ".join(
                sorted(
                    [
                        row.get("home_conference") or "Unknown",
                        row.get("away_conference") or "Unknown",
                    ]
                )
            ),
            axis=1,
        )

    return df


def accuracy_tuple(frame: pd.DataFrame) -> Dict[str, float]:
    scored = frame[frame["correct"].notna()]
    games = int(len(scored))
    correct = int(scored["correct"].sum()) if games > 0 else 0
    accuracy = (correct / games) if games > 0 else None
    return {"games": games, "correct": correct, "accuracy": accuracy}


def metric_bundle(frame: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    return {
        "overall": accuracy_tuple(frame),
        "regular": accuracy_tuple(frame[frame["season_type"] == "regular"]),
        "postseason": accuracy_tuple(frame[frame["season_type"] == "postseason"]),
        "playoff": accuracy_tuple(frame[frame["is_playoff"]]),
        "national_championship": accuracy_tuple(
            frame[frame["is_national_championship"]]
        ),
    }


def grouped_accuracy(frame: pd.DataFrame, group_cols: List[str]) -> List[Dict]:
    scored = frame[frame["correct"].notna()]
    if scored.empty:
        return []

    grouped = (
        scored.groupby(group_cols, as_index=False)
        .agg(games=("correct", "count"), correct=("correct", "sum"))
        .sort_values(group_cols)
    )
    grouped["accuracy"] = grouped["correct"] / grouped["games"]
    return grouped.to_dict(orient="records")


def apply_filters(df: pd.DataFrame, payload: Dict) -> pd.DataFrame:
    filtered = df.copy()

    years = payload.get("years") or []
    if years:
        year_set = {int(y) for y in years}
        filtered = filtered[filtered["year"].isin(year_set)]

    season_types = payload.get("season_types") or []
    if season_types:
        season_set = {str(s).strip().lower() for s in season_types}
        filtered = filtered[filtered["season_type"].str.lower().isin(season_set)]

    weeks = payload.get("weeks") or []
    if weeks:
        week_set = {int(w) for w in weeks}
        filtered = filtered[filtered["week"].isin(week_set)]

    teams = payload.get("teams") or []
    if teams:
        team_set = {str(t).strip().lower() for t in teams}
        filtered = filtered[
            filtered["home_team"].str.lower().isin(team_set)
            | filtered["away_team"].str.lower().isin(team_set)
        ]

    conference_involved = payload.get("conference_involved") or []
    if conference_involved:
        conf_set = {str(c).strip().lower() for c in conference_involved}
        filtered = filtered[
            filtered["home_conference"].str.lower().isin(conf_set)
            | filtered["away_conference"].str.lower().isin(conf_set)
        ]

    conference_play_only = bool(payload.get("conference_play_only", False))
    if conference_play_only:
        filtered = filtered[filtered["conference_game"]]

    conference_play_conferences = payload.get("conference_play_conferences") or []
    if conference_play_conferences:
        conf_set = {str(c).strip().lower() for c in conference_play_conferences}
        filtered = filtered[
            (filtered["conference_game"])
            & (filtered["home_conference"].str.lower() == filtered["away_conference"].str.lower())
            & (filtered["home_conference"].str.lower().isin(conf_set))
        ]

    specific_matchups = payload.get("specific_matchups") or []
    if specific_matchups:
        match_set = {str(m).strip().lower() for m in specific_matchups}
        filtered = filtered[filtered["conference_matchup"].str.lower().isin(match_set)]

    conference_pair_any = payload.get("conference_pair_any") or []
    if len(conference_pair_any) == 2:
        a, b = [str(x).strip().lower() for x in conference_pair_any]
        filtered = filtered[
            (
                (filtered["home_conference"].str.lower() == a)
                & (filtered["away_conference"].str.lower() == b)
            )
            | (
                (filtered["home_conference"].str.lower() == b)
                & (filtered["away_conference"].str.lower() == a)
            )
        ]

    include_playoff_only = bool(payload.get("playoff_only", False))
    if include_playoff_only:
        filtered = filtered[filtered["is_playoff"]]

    include_title_only = bool(payload.get("title_only", False))
    if include_title_only:
        filtered = filtered[filtered["is_national_championship"]]

    prediction_reasons = payload.get("prediction_reasons") or []
    if prediction_reasons:
        reason_set = {str(r).strip().lower() for r in prediction_reasons}
        filtered = filtered[filtered["prediction_reason"].str.lower().isin(reason_set)]

    min_source_teams = payload.get("min_source_teams")
    if min_source_teams not in (None, ""):
        try:
            threshold = float(min_source_teams)
            filtered = filtered[
                filtered["ranking_source_team_count"].fillna(0.0) >= threshold
            ]
        except ValueError:
            pass

    return filtered


def metadata(df: pd.DataFrame) -> Dict:
    def sorted_values(series: pd.Series) -> List[str]:
        vals = [v for v in series.dropna().astype(str).map(str.strip).tolist() if v]
        return sorted(set(vals), key=lambda x: x.lower())

    conf_matchups = sorted_values(df["conference_matchup"])
    # Keep only cross-conference pairs for this selector.
    conf_matchups = [
        m
        for m in conf_matchups
        if " vs " in m and m.split(" vs ")[0].strip().lower() != m.split(" vs ")[1].strip().lower()
    ]

    return {
        "years": sorted(df["year"].dropna().astype(int).unique().tolist()),
        "season_types": sorted_values(df["season_type"]),
        "weeks": sorted(df["week"].dropna().astype(int).unique().tolist()),
        "teams": sorted_values(pd.concat([df["home_team"], df["away_team"]], ignore_index=True)),
        "conferences": sorted_values(
            pd.concat([df["home_conference"], df["away_conference"]], ignore_index=True)
        ),
        "conference_matchups": conf_matchups,
        "prediction_reasons": sorted_values(df["prediction_reason"]),
        "row_count": int(len(df)),
    }


@app.route("/")
def home():
    df = load_predictions_df()
    if df.empty:
        return render_template(
            "prediction_dashboard.html",
            has_data=False,
            message=(
                "No prediction files found. Run predict_winners_from_spi_history.py first "
                "to create data_exports/predictions/spi_game_predictions_*.csv"
            ),
        )

    return render_template("prediction_dashboard.html", has_data=True, message="")


@app.route("/api/metadata")
def api_metadata():
    df = load_predictions_df()
    if df.empty:
        return jsonify({"ok": False, "error": "No prediction data available."}), 404
    return jsonify({"ok": True, "metadata": metadata(df)})


@app.route("/api/query", methods=["POST"])
def api_query():
    df = load_predictions_df()
    if df.empty:
        return jsonify({"ok": False, "error": "No prediction data available."}), 404

    payload = request.get_json(silent=True) or {}
    page = int(payload.get("page", 1) or 1)
    page_size = int(payload.get("page_size", DEFAULT_PAGE_SIZE) or DEFAULT_PAGE_SIZE)
    page = max(1, page)
    page_size = max(1, min(MAX_PAGE_SIZE, page_size))

    baseline = df.copy()
    filtered = apply_filters(df, payload)

    baseline_metrics = metric_bundle(baseline)
    filtered_metrics = metric_bundle(filtered)

    by_year = grouped_accuracy(filtered, ["year"])
    by_year_regular = grouped_accuracy(filtered[filtered["season_type"] == "regular"], ["year"])
    by_year_post = grouped_accuracy(filtered[filtered["season_type"] == "postseason"], ["year"])
    by_year_playoff = grouped_accuracy(filtered[filtered["is_playoff"]], ["year"])
    by_year_week = grouped_accuracy(filtered, ["year", "season_type", "week"])
    by_week_all_years = grouped_accuracy(filtered, ["season_type", "week"])

    total_rows = int(len(filtered))
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    sort_cols = ["year", "season_type", "week", "start_date", "home_team"]
    sort_cols = [c for c in sort_cols if c in filtered.columns]
    display_df = filtered.sort_values(sort_cols).iloc[start_idx:end_idx].copy()

    table_columns = [
        "year",
        "season_type",
        "week",
        "home_team",
        "away_team",
        "home_conference",
        "away_conference",
        "conference_game",
        "predicted_winner",
        "actual_winner",
        "correct",
        "prediction_reason",
        "is_playoff",
        "is_national_championship",
        "ranking_source",
        "ranking_source_file",
        "ranking_source_team_count",
    ]
    table_columns = [c for c in table_columns if c in display_df.columns]
    table_rows = display_df[table_columns].to_dict(orient="records")

    return jsonify(
        {
            "ok": True,
            "summary": {
                "total_rows_filtered": total_rows,
                "total_rows_baseline": int(len(baseline)),
                "page": page,
                "page_size": page_size,
                "total_pages": (total_rows + page_size - 1) // page_size,
            },
            "metrics": {
                "baseline": baseline_metrics,
                "filtered": filtered_metrics,
            },
            "slices": {
                "by_year": by_year,
                "by_year_regular": by_year_regular,
                "by_year_postseason": by_year_post,
                "by_year_playoff": by_year_playoff,
                "by_year_week": by_year_week,
                "by_week_all_years": by_week_all_years,
            },
            "table": {
                "columns": table_columns,
                "rows": table_rows,
            },
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
