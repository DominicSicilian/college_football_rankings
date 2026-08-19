import datetime as dt
import glob
import json
import math
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd
from flask import Flask, jsonify, render_template, request

from model_config import HOME_FIELD_X_DEFAULT

try:
    import cfbd
except Exception:
    cfbd = None

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)
DATA_EXPORTS_DIR = os.path.join(BASE_DIR, "data_exports")
PREDICTIONS_DIR = os.path.join(DATA_EXPORTS_DIR, "predictions")
DASHBOARD_CACHE_DIR = os.path.join(DATA_EXPORTS_DIR, "dashboard_cache")

DEFAULT_PAGE_SIZE = 250
MAX_PAGE_SIZE = 2000

_PLAYOFF_RESULTS_CACHE_MEM: Dict[int, Tuple[dt.datetime, List[Dict]]] = {}

# Team conference overrides by first effective season.
CONFERENCE_REALIGNMENT_OVERRIDES = [
    ("oklahoma", 2024, "SEC"),
    ("texas", 2024, "SEC"),
    ("usc", 2024, "Big Ten"),
    ("ucla", 2024, "Big Ten"),
    ("oregon", 2024, "Big Ten"),
    ("washington", 2024, "Big Ten"),
    ("arizona", 2024, "Big 12"),
    ("arizonastate", 2024, "Big 12"),
    ("utah", 2024, "Big 12"),
    ("colorado", 2024, "Big 12"),
    ("cal", 2024, "ACC"),
    ("stanford", 2024, "ACC"),
    ("smu", 2024, "ACC"),
]

HOME_FIELD_X_OFFICIAL = HOME_FIELD_X_DEFAULT

CONFERENCE_DISPLAY_MAP = {
    "acc": "ACC",
    "sec": "SEC",
    "big ten": "Big Ten",
    "big 12": "Big 12",
    "pac 12": "Pac-12",
    "pac-12": "Pac-12",
    "american": "American",
    "american athletic": "American",
    "conference usa": "Conference USA",
    "cusa": "Conference USA",
    "mid american": "MAC",
    "mid-american": "MAC",
    "mac": "MAC",
    "mountain west": "Mountain West",
    "sun belt": "Sun Belt",
    "independent": "Independent",
    "fbs independent": "FBS Independent",
    "fbs independents": "FBS Independent",
    "fcs independent": "FCS Independent",
    "fcs independents": "FCS Independent",
}


def normalize_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize_team_key(name: str) -> str:
    txt = normalize_text(name).lower()
    chars = []
    for ch in txt:
        if ch.isalnum():
            chars.append(ch)
    return "".join(chars)


def format_conference_name(value) -> str:
    txt = normalize_text(value)
    if not txt:
        return ""

    norm = " ".join(txt.lower().replace("_", " ").split())
    mapped = CONFERENCE_DISPLAY_MAP.get(norm)
    if mapped:
        return mapped

    words = norm.split(" ")
    out = []
    for word in words:
        if not word:
            continue
        if word.isalpha() and len(word) <= 3:
            out.append(word.upper())
        else:
            out.append(word.capitalize())
    return " ".join(out)


def clamp_probability(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return max(0.0, min(1.0, float(value)))


def apply_home_field_adjustment(
    home_prob_raw: Optional[float],
    is_neutral_site: bool,
    home_field_x: float = HOME_FIELD_X_OFFICIAL,
) -> Optional[float]:
    if home_prob_raw is None:
        return None
    if is_neutral_site:
        return clamp_probability(home_prob_raw)
    return clamp_probability(float(home_prob_raw) + float(home_field_x))


def apply_conference_overrides(
    frame: pd.DataFrame,
    season_year: Optional[int],
    team_col: str = "team",
    conference_col: str = "conference",
) -> pd.DataFrame:
    if frame.empty or season_year is None:
        return frame
    if team_col not in frame.columns or conference_col not in frame.columns:
        return frame

    out = frame.copy()
    team_keys = out[team_col].map(normalize_team_key)
    conf = out[conference_col].map(normalize_text)

    for team_key, effective_year, target_conf in CONFERENCE_REALIGNMENT_OVERRIDES:
        if int(season_year) < int(effective_year):
            continue
        mask = team_keys == team_key
        if mask.any():
            conf.loc[mask] = target_conf

    out[conference_col] = conf.map(format_conference_name)
    return out


def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, float) and math.isnan(value):
        return None

    return value


def apply_current_ranking_method(
    rank_df: pd.DataFrame,
    season_year: int,
    ranking_file: str,
    requested_method: str,
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    if rank_df.empty:
        return rank_df, {
            "requested": "spi",
            "used": "spi",
            "toggle_active": "no",
            "reason": "no_rankings",
            "talent_file": "",
        }

    out = rank_df.copy()
    out = out.sort_values("spi", ascending=False, na_position="last").reset_index(drop=True)
    out["rank"] = out.index + 1
    out["is_top_25"] = out["rank"] <= 25
    return out, {
        "requested": "spi",
        "used": "spi",
        "toggle_active": "no",
        "reason": "official_spi_only",
        "talent_file": "",
    }


def _sorted_unique_text(values: pd.Series) -> List[str]:
    out = [normalize_text(v) for v in values.tolist()]
    out = [v for v in out if v]
    return sorted(set(out), key=lambda x: x.lower())


def _resolve_prediction_file(method: str = "current") -> Tuple[Optional[str], str]:
    def sort_key(path: str) -> Tuple[int, float, int, int]:
        # Prefer latest modeled season and latest run time; use span as a tie-breaker.
        base = os.path.basename(path)
        match = __import__("re").search(
            r"spi_game_predictions_(\d{4})_(\d{4})\.csv$",
            base,
        )
        if match:
            start_year = int(match.group(1))
            end_year = int(match.group(2))
            span = max(0, end_year - start_year)
            return (end_year, os.path.getmtime(path), span, start_year)
        return (-1, os.path.getmtime(path), -1, -1)

    pattern = os.path.join(PREDICTIONS_DIR, "spi_game_predictions_*.csv")
    method_used = "current"

    files = sorted(glob.glob(pattern), key=sort_key, reverse=True)
    if not files:
        return None, method_used
    return files[0], method_used


def load_predictions_df(method: str = "current") -> Tuple[pd.DataFrame, Dict[str, str]]:
    selected_file, method_used = _resolve_prediction_file(method)
    if selected_file is None:
        return pd.DataFrame(), {
            "requested_method": normalize_text(method).lower() or "current",
            "method_used": method_used,
            "source_file": "",
        }

    df = pd.read_csv(selected_file)
    if df.empty:
        return df, {
            "requested_method": normalize_text(method).lower() or "current",
            "method_used": method_used,
            "source_file": os.path.basename(selected_file),
        }

    defaults = {
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
        "neutral_site": False,
    }
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val

    df["year"] = pd.to_numeric(df["year"], errors="coerce").fillna(0).astype(int)
    df["week"] = pd.to_numeric(df["week"], errors="coerce").fillna(0).astype(int)
    df["correct"] = pd.to_numeric(df["correct"], errors="coerce")
    df["ranking_source_team_count"] = pd.to_numeric(df["ranking_source_team_count"], errors="coerce")

    # Canonical dashboard metrics should use home-field-adjusted outputs when available.
    if "correct_home_adj" in df.columns:
        correct_home_adj = pd.to_numeric(df["correct_home_adj"], errors="coerce")
        if correct_home_adj.notna().any():
            df["correct"] = correct_home_adj.where(correct_home_adj.notna(), df["correct"])

    if "predicted_winner_home_adj" in df.columns:
        pred_home_adj = df["predicted_winner_home_adj"].map(normalize_text)
        mask = pred_home_adj != ""
        if mask.any():
            df.loc[mask, "predicted_winner"] = pred_home_adj[mask]

    if "home_win_prob_home_adj_pct" in df.columns:
        home_pct = pd.to_numeric(df["home_win_prob_home_adj_pct"], errors="coerce")
        if home_pct.notna().any():
            df["home_win_prob_pct"] = home_pct.where(home_pct.notna(), df.get("home_win_prob_pct"))

    if "away_win_prob_home_adj_pct" in df.columns:
        away_pct = pd.to_numeric(df["away_win_prob_home_adj_pct"], errors="coerce")
        if away_pct.notna().any():
            df["away_win_prob_pct"] = away_pct.where(away_pct.notna(), df.get("away_win_prob_pct"))

    bool_cols = [
        "conference_game",
        "is_playoff",
        "is_national_championship",
        "neutral_site",
    ]
    for col in bool_cols:
        df[col] = df[col].map(lambda v: str(v).strip().lower() in {"1", "true", "yes"})

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

    if "home_conference" in df.columns:
        df["home_conference"] = df["home_conference"].map(format_conference_name)
    if "away_conference" in df.columns:
        df["away_conference"] = df["away_conference"].map(format_conference_name)

    # Build/refresh conference matchup.
    df["conference_matchup"] = df.apply(
        lambda r: " vs ".join(
            sorted(
                [
                    format_conference_name(r.get("home_conference")) or "Unknown",
                    format_conference_name(r.get("away_conference")) or "Unknown",
                ]
            )
        ),
        axis=1,
    )

    # Home/away analysis helper columns.
    def predicted_side(row) -> str:
        p = normalize_text(row.get("predicted_winner"))
        h = normalize_text(row.get("home_team"))
        a = normalize_text(row.get("away_team"))
        if p and p == h:
            return "home_pick"
        if p and p == a:
            return "away_pick"
        return "unknown"

    df["predicted_side"] = df.apply(predicted_side, axis=1)
    df["game_site"] = df["neutral_site"].map(lambda n: "neutral" if bool(n) else "non_neutral")

    return df, {
        "requested_method": normalize_text(method).lower() or "current",
        "method_used": method_used,
        "source_file": os.path.basename(selected_file),
    }


def accuracy_tuple(frame: pd.DataFrame) -> Dict[str, Optional[float]]:
    scored = frame[frame["correct"].notna()]
    games = int(len(scored))
    correct = int(scored["correct"].sum()) if games else 0
    acc = (correct / games) if games else None
    return {"games": games, "correct": correct, "accuracy": acc}


def metrics_bundle(frame: pd.DataFrame) -> Dict[str, Dict[str, Optional[float]]]:
    return {
        "overall": accuracy_tuple(frame),
        "regular": accuracy_tuple(frame[frame["season_type"] == "regular"]),
        "postseason": accuracy_tuple(frame[frame["season_type"] == "postseason"]),
        "playoff": accuracy_tuple(frame[frame["is_playoff"]]),
        "national_championship": accuracy_tuple(frame[frame["is_national_championship"]]),
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


def slice_pack(frame: pd.DataFrame) -> Dict[str, List[Dict]]:
    return {
        "by_year": grouped_accuracy(frame, ["year"]),
        "by_year_regular": grouped_accuracy(frame[frame["season_type"] == "regular"], ["year"]),
        "by_year_postseason": grouped_accuracy(frame[frame["season_type"] == "postseason"], ["year"]),
        "by_year_playoff": grouped_accuracy(frame[frame["is_playoff"]], ["year"]),
        "by_year_week": grouped_accuracy(frame, ["year", "season_type", "week"]),
        "by_week_all_years": grouped_accuracy(frame, ["season_type", "week"]),
    }


def home_away_slice_pack(frame: pd.DataFrame) -> Dict[str, List[Dict]]:
    # Home/away analysis layered onto all prior slices.
    return {
        "by_year": grouped_accuracy(frame, ["year", "predicted_side"]),
        "by_year_regular": grouped_accuracy(
            frame[frame["season_type"] == "regular"], ["year", "predicted_side"]
        ),
        "by_year_postseason": grouped_accuracy(
            frame[frame["season_type"] == "postseason"], ["year", "predicted_side"]
        ),
        "by_year_playoff": grouped_accuracy(
            frame[frame["is_playoff"]], ["year", "predicted_side"]
        ),
        "by_year_week": grouped_accuracy(
            frame, ["year", "season_type", "week", "predicted_side"]
        ),
        "by_week_all_years": grouped_accuracy(
            frame, ["season_type", "week", "predicted_side"]
        ),
        "headline": grouped_accuracy(frame, ["season_type", "predicted_side"]),
    }


def apply_filters(df: pd.DataFrame, payload: Dict) -> pd.DataFrame:
    out = df.copy()

    years = payload.get("years") or []
    if years:
        out = out[out["year"].isin([int(v) for v in years])]

    season_types = payload.get("season_types") or []
    if season_types:
        season_set = {str(v).strip().lower() for v in season_types}
        out = out[out["season_type"].str.lower().isin(season_set)]

    weeks = payload.get("weeks") or []
    if weeks:
        out = out[out["week"].isin([int(v) for v in weeks])]

    teams = payload.get("teams") or []
    if teams:
        team_set = {str(v).strip().lower() for v in teams}
        out = out[
            out["home_team"].str.lower().isin(team_set)
            | out["away_team"].str.lower().isin(team_set)
        ]

    conference_involved = payload.get("conference_involved") or []
    if conference_involved:
        conf_set = {str(v).strip().lower() for v in conference_involved}
        out = out[
            out["home_conference"].str.lower().isin(conf_set)
            | out["away_conference"].str.lower().isin(conf_set)
        ]

    if bool(payload.get("conference_play_only", False)):
        out = out[out["conference_game"]]

    conference_play_conferences = payload.get("conference_play_conferences") or []
    if conference_play_conferences:
        conf_set = {str(v).strip().lower() for v in conference_play_conferences}
        out = out[
            out["conference_game"]
            & (out["home_conference"].str.lower() == out["away_conference"].str.lower())
            & (out["home_conference"].str.lower().isin(conf_set))
        ]

    specific_matchups = payload.get("specific_matchups") or []
    if specific_matchups:
        mm = {str(v).strip().lower() for v in specific_matchups}
        out = out[out["conference_matchup"].str.lower().isin(mm)]

    pair = payload.get("conference_pair_any") or []
    if len(pair) == 2:
        a = str(pair[0]).strip().lower()
        b = str(pair[1]).strip().lower()
        out = out[
            (
                (out["home_conference"].str.lower() == a)
                & (out["away_conference"].str.lower() == b)
            )
            | (
                (out["home_conference"].str.lower() == b)
                & (out["away_conference"].str.lower() == a)
            )
        ]

    if bool(payload.get("playoff_only", False)):
        out = out[out["is_playoff"]]

    if bool(payload.get("title_only", False)):
        out = out[out["is_national_championship"]]

    pred_reasons = payload.get("prediction_reasons") or []
    if pred_reasons:
        rr = {str(v).strip().lower() for v in pred_reasons}
        out = out[out["prediction_reason"].str.lower().isin(rr)]

    pred_sides = payload.get("predicted_sides") or []
    if pred_sides:
        ss = {str(v).strip().lower() for v in pred_sides}
        out = out[out["predicted_side"].str.lower().isin(ss)]

    min_source_teams = payload.get("min_source_teams")
    if min_source_teams not in (None, ""):
        try:
            threshold = float(min_source_teams)
            out = out[out["ranking_source_team_count"].fillna(0.0) >= threshold]
        except ValueError:
            pass

    return out


def predictions_metadata(df: pd.DataFrame) -> Dict:
    matchup_values = _sorted_unique_text(df["conference_matchup"])
    matchup_values = [
        m
        for m in matchup_values
        if " vs " in m and m.split(" vs ")[0].strip().lower() != m.split(" vs ")[1].strip().lower()
    ]

    return {
        "years": sorted(df["year"].dropna().astype(int).unique().tolist()),
        "season_types": _sorted_unique_text(df["season_type"]),
        "weeks": sorted(df["week"].dropna().astype(int).unique().tolist()),
        "teams": _sorted_unique_text(pd.concat([df["home_team"], df["away_team"]], ignore_index=True)),
        "conferences": _sorted_unique_text(pd.concat([df["home_conference"], df["away_conference"]], ignore_index=True)),
        "conference_matchups": matchup_values,
        "prediction_reasons": _sorted_unique_text(df["prediction_reason"]),
        "predicted_sides": _sorted_unique_text(df["predicted_side"]),
        "row_count": int(len(df)),
    }


def latest_spi_rankings_file(preferred_year: Optional[int] = None) -> Optional[str]:
    pattern = os.path.join(DATA_EXPORTS_DIR, "spi_rankings_*.csv")
    files = glob.glob(pattern)
    filtered = []
    for f in files:
        base = os.path.basename(f)
        if "detailed" in base.lower():
            continue
        if base.startswith("spi_rankings_final_"):
            continue
        if base.startswith("spi_rankings_final"):
            continue
        filtered.append(f)
    if not filtered:
        return None

    def classify(path: str) -> Tuple[int, int, int, float]:
        # Sort key fields:
        # 1) same-year preference (if provided)
        # 2) season year
        # 3) snapshot tier (post_w > reg_w > preseason > season_summary)
        # 4) week (for post/reg)
        # 5) mtime tie-breaker
        base = os.path.basename(path)
        re_mod = __import__("re")

        year = -1
        tier = 0
        week = -1

        m = re_mod.match(r"spi_rankings_(\d+)_post_w(\d+)\.csv$", base)
        if m:
            year = int(m.group(1))
            tier = 4
            week = int(m.group(2))
        else:
            m = re_mod.match(r"spi_rankings_(\d+)_w(\d+)\.csv$", base)
            if m:
                year = int(m.group(1))
                tier = 3
                week = int(m.group(2))
            else:
                m = re_mod.match(r"spi_rankings_preseason_(\d+)\.csv$", base)
                if m:
                    year = int(m.group(1))
                    tier = 2
                    week = 0
                else:
                    m = re_mod.match(r"spi_rankings_(\d+)\.csv$", base)
                    if m:
                        year = int(m.group(1))
                        tier = 1
                        week = 0

        same_year = 1 if (preferred_year is not None and year == preferred_year) else 0
        return (same_year, year, tier, week, os.path.getmtime(path))

    return max(filtered, key=classify)


def load_spi_table(file_path: str, season_year: Optional[int] = None) -> pd.DataFrame:
    df = pd.read_csv(file_path)
    if df.empty:
        return df

    cols = {c.lower(): c for c in df.columns}

    # Normalize to a shared schema.
    if "team" in cols:
        team_col = cols["team"]
    elif "team name" in cols:
        team_col = cols["team name"]
    else:
        team_col = list(df.columns)[0]

    if "conference" in cols:
        conf_col = cols["conference"]
    elif "conf." in cols:
        conf_col = cols["conf."]
    else:
        conf_col = None

    if "wins" in cols:
        wins_col = cols["wins"]
    elif "w" in cols:
        wins_col = cols["w"]
    else:
        wins_col = None

    if "losses" in cols:
        loss_col = cols["losses"]
    elif "l" in cols:
        loss_col = cols["l"]
    else:
        loss_col = None

    spi_col = cols.get("spi")
    n_col = cols.get("n_adj")
    sor_col = cols.get("sor_adj")

    out = pd.DataFrame()
    out["team"] = df[team_col].map(normalize_text)
    out["conference"] = df[conf_col].map(format_conference_name) if conf_col else "Unknown"
    out["wins"] = pd.to_numeric(df[wins_col], errors="coerce").fillna(0).astype(int) if wins_col else 0
    out["losses"] = pd.to_numeric(df[loss_col], errors="coerce").fillna(0).astype(int) if loss_col else 0
    out["spi"] = pd.to_numeric(df[spi_col], errors="coerce") if spi_col else pd.NA
    out["n_adj"] = pd.to_numeric(df[n_col], errors="coerce") if n_col else pd.NA
    out["sor_adj"] = pd.to_numeric(df[sor_col], errors="coerce") if sor_col else pd.NA

    out = apply_conference_overrides(out, season_year, team_col="team", conference_col="conference")

    out = out[out["team"] != ""].copy()
    out = out.sort_values("spi", ascending=False, na_position="last").reset_index(drop=True)
    out["rank"] = out.index + 1
    out["is_top_25"] = out["rank"] <= 25
    return out


def projected_twelve_team_field(rank_df: pd.DataFrame) -> pd.DataFrame:
    if rank_df.empty:
        return rank_df

    # 2026 criteria projection using SPI ranking as a committee ranking proxy.
    # Auto bids:
    # - ACC, Big 12, Big Ten, SEC champions
    # - Highest-ranked Group of 6 champion
    # - Notre Dame auto if ranked in top 12
    # Remaining field spots are at-large up to 12 teams total.
    ranking = rank_df.sort_values("rank", ascending=True).copy()

    def conf_norm(conf: str) -> str:
        value = normalize_text(conf).lower()
        value = value.replace("-", " ")
        value = value.replace("  ", " ")
        return value

    p4_conf_aliases = {
        "acc": {"acc"},
        "big 12": {"big 12"},
        "big ten": {"big ten"},
        "sec": {"sec"},
    }
    g6_aliases = {
        "american",
        "american athletic",
        "conference usa",
        "cusa",
        "mid american",
        "mid-american",
        "mac",
        "mountain west",
        "pac 12",
        "pac-12",
        "sun belt",
    }

    ranking["conference_norm"] = ranking["conference"].map(conf_norm)
    ranking["team_norm"] = ranking["team"].map(lambda t: normalize_text(t).lower())

    auto_rows = []
    selected_team_norms = set()

    # P4 champions: best-ranked team in each required conference.
    for conf_label, aliases in p4_conf_aliases.items():
        conf_rows = ranking[ranking["conference_norm"].isin(aliases)]
        if conf_rows.empty:
            continue
        champ = conf_rows.sort_values("rank", ascending=True).iloc[0].copy()
        champ["bid_type"] = "auto_p4_champion"
        champ["auto_source"] = conf_label
        auto_rows.append(champ)
        selected_team_norms.add(champ["team_norm"])

    # Highest-ranked Group of 6 champion.
    g6_rows = ranking[
        ranking["conference_norm"].isin(g6_aliases)
        & (~ranking["team_norm"].isin(selected_team_norms))
    ]
    if not g6_rows.empty:
        g6_champ = g6_rows.sort_values("rank", ascending=True).iloc[0].copy()
        g6_champ["bid_type"] = "auto_g6_champion"
        g6_champ["auto_source"] = "g6"
        auto_rows.append(g6_champ)
        selected_team_norms.add(g6_champ["team_norm"])

    # Notre Dame rule: auto if top-12.
    nd_rows = ranking[
        ranking["team_norm"].isin({"notredame", "notredamefightingirish"})
        & (ranking["rank"] <= 12)
        & (~ranking["team_norm"].isin(selected_team_norms))
    ]
    if not nd_rows.empty:
        nd_team = nd_rows.sort_values("rank", ascending=True).iloc[0].copy()
        nd_team["bid_type"] = "auto_notre_dame"
        nd_team["auto_source"] = "notre_dame_top12"
        auto_rows.append(nd_team)
        selected_team_norms.add(nd_team["team_norm"])

    auto_df = pd.DataFrame(auto_rows)

    # Fill remaining spots with at-large bids to 12 total.
    remaining = ranking[~ranking["team_norm"].isin(selected_team_norms)].copy()
    at_large_slots = max(0, 12 - len(auto_df))
    at_large_df = remaining.sort_values("rank", ascending=True).head(at_large_slots).copy()
    if not at_large_df.empty:
        at_large_df["bid_type"] = "at_large"
        at_large_df["auto_source"] = ""

    field = pd.concat([auto_df, at_large_df], ignore_index=True)
    if field.empty:
        return field

    field = field.sort_values("rank", ascending=True).reset_index(drop=True)

    # Top 4 seeds/byes: highest-ranked conference champions only.
    conference_champ_mask = field["bid_type"].isin({"auto_p4_champion", "auto_g6_champion"})
    champs_only = field[conference_champ_mask].sort_values("rank", ascending=True)
    top_bye_team_norms = set(champs_only.head(4)["team_norm"].tolist())

    seed_records = []
    used_team_norms = set()

    # Seeds 1-4 for bye champions by ranking order.
    bye_order = champs_only[champs_only["team_norm"].isin(top_bye_team_norms)].sort_values(
        "rank", ascending=True
    )
    for seed, (_, row) in enumerate(bye_order.iterrows(), start=1):
        out = row.copy()
        out["seed"] = seed
        out["has_bye"] = True
        seed_records.append(out)
        used_team_norms.add(out["team_norm"])

    # Seeds 5-12 by ranking among remaining qualifiers.
    remaining_field = field[~field["team_norm"].isin(used_team_norms)].sort_values(
        "rank", ascending=True
    )
    next_seed = 5
    for _, row in remaining_field.iterrows():
        if next_seed > 12:
            break
        out = row.copy()
        out["seed"] = next_seed
        out["has_bye"] = False
        seed_records.append(out)
        next_seed += 1

    seeded = pd.DataFrame(seed_records).sort_values("seed", ascending=True).reset_index(
        drop=True
    )

    return seeded[
        [
            "seed",
            "team",
            "conference",
            "wins",
            "losses",
            "rank",
            "spi",
            "bid_type",
            "auto_source",
            "has_bye",
        ]
    ]


def _snapshot_label_from_rankings_file(file_path: str) -> str:
    base = os.path.basename(file_path)
    if base.startswith("spi_rankings_") and base.endswith(".csv"):
        return base[len("spi_rankings_") : -len(".csv")]
    return ""


def load_team_standings_for_snapshot(rankings_file: str) -> pd.DataFrame:
    label = _snapshot_label_from_rankings_file(rankings_file)
    if not label:
        return pd.DataFrame()

    path = os.path.join(DATA_EXPORTS_DIR, f"team_standings_{label}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()

    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame()

    required = ["team", "conference", "conf_wins", "conf_losses"]
    for col in required:
        if col not in df.columns:
            return pd.DataFrame()

    df = df.copy()
    df["team"] = df["team"].map(normalize_text)
    df["conference"] = df["conference"].map(format_conference_name)
    df["conf_wins"] = pd.to_numeric(df["conf_wins"], errors="coerce").fillna(0.0)
    df["conf_losses"] = pd.to_numeric(df["conf_losses"], errors="coerce").fillna(0.0)
    if "overall_index" in df.columns:
        df["overall_index"] = pd.to_numeric(df["overall_index"], errors="coerce").fillna(0.0)
    else:
        df["overall_index"] = 0.0

    denom = df["conf_wins"] + df["conf_losses"]
    df["conf_win_pct"] = denom.where(denom > 0, 0.0)
    df.loc[denom > 0, "conf_win_pct"] = df.loc[denom > 0, "conf_wins"] / denom[denom > 0]
    return df


def projected_twelve_team_field_with_mode(
    rank_df: pd.DataFrame,
    standings_df: pd.DataFrame,
    champ_mode: str = "spi",
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    if rank_df.empty:
        return rank_df, {"champ_mode_requested": champ_mode, "champ_mode_used": champ_mode}

    ranking = rank_df.sort_values("rank", ascending=True).copy()

    def conf_norm(conf: str) -> str:
        value = normalize_text(conf).lower()
        value = value.replace("-", " ")
        value = value.replace("  ", " ")
        return value

    p4_conf_aliases = {
        "acc": {"acc"},
        "big 12": {"big 12"},
        "big ten": {"big ten"},
        "sec": {"sec"},
    }
    g6_aliases = {
        "american",
        "american athletic",
        "conference usa",
        "cusa",
        "mid american",
        "mid-american",
        "mac",
        "mountain west",
        "pac 12",
        "pac-12",
        "sun belt",
    }

    ranking["conference_norm"] = ranking["conference"].map(conf_norm)
    ranking["team_norm"] = ranking["team"].map(lambda t: normalize_text(t).lower())

    standings_ready = not standings_df.empty
    mode_used = champ_mode
    if champ_mode == "standings" and not standings_ready:
        mode_used = "spi"

    standings_lookup = standings_df.copy() if standings_ready else pd.DataFrame()
    if standings_ready:
        standings_lookup["conference_norm"] = standings_lookup["conference"].map(conf_norm)
        standings_lookup["team_norm"] = standings_lookup["team"].map(
            lambda t: normalize_text(t).lower()
        )

    def champion_for_aliases(aliases: set) -> Optional[pd.Series]:
        conf_rows = ranking[ranking["conference_norm"].isin(aliases)]
        if conf_rows.empty:
            return None

        if mode_used == "standings":
            s_rows = standings_lookup[standings_lookup["conference_norm"].isin(aliases)]
            if not s_rows.empty:
                s_best = s_rows.sort_values(
                    ["conf_win_pct", "conf_wins", "overall_index"],
                    ascending=[False, False, False],
                ).iloc[0]
                matching = conf_rows[conf_rows["team_norm"] == s_best["team_norm"]]
                if not matching.empty:
                    return matching.sort_values("rank", ascending=True).iloc[0].copy()

        return conf_rows.sort_values("rank", ascending=True).iloc[0].copy()

    auto_rows = []
    selected_team_norms = set()

    for conf_label, aliases in p4_conf_aliases.items():
        champ = champion_for_aliases(aliases)
        if champ is None:
            continue
        champ["bid_type"] = "auto_p4_champion"
        champ["auto_source"] = conf_label
        auto_rows.append(champ)
        selected_team_norms.add(champ["team_norm"])

    # Highest-ranked G6 champion from champion set.
    g6_champion_candidates = []
    for conf_name in sorted(ranking[ranking["conference_norm"].isin(g6_aliases)]["conference_norm"].unique()):
        champ = champion_for_aliases({conf_name})
        if champ is None:
            continue
        if champ["team_norm"] in selected_team_norms:
            continue
        g6_champion_candidates.append(champ)

    if g6_champion_candidates:
        g6_df = pd.DataFrame(g6_champion_candidates).sort_values("rank", ascending=True)
        g6_champ = g6_df.iloc[0].copy()
        g6_champ["bid_type"] = "auto_g6_champion"
        g6_champ["auto_source"] = "g6"
        auto_rows.append(g6_champ)
        selected_team_norms.add(g6_champ["team_norm"])

    nd_rows = ranking[
        ranking["team_norm"].isin({"notredame", "notredamefightingirish"})
        & (ranking["rank"] <= 12)
        & (~ranking["team_norm"].isin(selected_team_norms))
    ]
    if not nd_rows.empty:
        nd_team = nd_rows.sort_values("rank", ascending=True).iloc[0].copy()
        nd_team["bid_type"] = "auto_notre_dame"
        nd_team["auto_source"] = "notre_dame_top12"
        auto_rows.append(nd_team)
        selected_team_norms.add(nd_team["team_norm"])

    auto_df = pd.DataFrame(auto_rows)

    remaining = ranking[~ranking["team_norm"].isin(selected_team_norms)].copy()
    at_large_slots = max(0, 12 - len(auto_df))
    at_large_df = remaining.sort_values("rank", ascending=True).head(at_large_slots).copy()
    if not at_large_df.empty:
        at_large_df["bid_type"] = "at_large"
        at_large_df["auto_source"] = ""

    field = pd.concat([auto_df, at_large_df], ignore_index=True)
    if field.empty:
        return field, {
            "champ_mode_requested": champ_mode,
            "champ_mode_used": mode_used,
        }

    field = field.sort_values("rank", ascending=True).reset_index(drop=True)

    conference_champ_mask = field["bid_type"].isin({"auto_p4_champion", "auto_g6_champion"})
    champs_only = field[conference_champ_mask].sort_values("rank", ascending=True)
    top_bye_team_norms = set(champs_only.head(4)["team_norm"].tolist())

    seed_records = []
    used_team_norms = set()

    bye_order = champs_only[champs_only["team_norm"].isin(top_bye_team_norms)].sort_values(
        "rank", ascending=True
    )
    for seed, (_, row) in enumerate(bye_order.iterrows(), start=1):
        out = row.copy()
        out["seed"] = seed
        out["has_bye"] = True
        seed_records.append(out)
        used_team_norms.add(out["team_norm"])

    remaining_field = field[~field["team_norm"].isin(used_team_norms)].sort_values(
        "rank", ascending=True
    )
    next_seed = 5
    for _, row in remaining_field.iterrows():
        if next_seed > 12:
            break
        out = row.copy()
        out["seed"] = next_seed
        out["has_bye"] = False
        seed_records.append(out)
        next_seed += 1

    seeded = pd.DataFrame(seed_records).sort_values("seed", ascending=True).reset_index(
        drop=True
    )

    info = {
        "champ_mode_requested": champ_mode,
        "champ_mode_used": mode_used,
        "standings_available": "yes" if standings_ready else "no",
    }

    return seeded[
        [
            "seed",
            "team",
            "conference",
            "wins",
            "losses",
            "rank",
            "spi",
            "bid_type",
            "auto_source",
            "has_bye",
        ]
    ], info


def _cfbd_games_api():
    if cfbd is None:
        return None
    api_key = os.environ.get("CFBD_API_KEY")
    if not api_key:
        return None
    conf = cfbd.Configuration()
    conf.api_key["Authorization"] = api_key
    conf.api_key_prefix["Authorization"] = "Bearer"
    return cfbd.GamesApi(cfbd.ApiClient(conf))


def _ensure_dashboard_cache_dir() -> None:
    os.makedirs(DASHBOARD_CACHE_DIR, exist_ok=True)


def _playoff_cache_file(year: int) -> str:
    return os.path.join(DASHBOARD_CACHE_DIR, f"postseason_games_{int(year)}.json")


def _cache_is_fresh(cached_at: Optional[dt.datetime], max_age_seconds: int) -> bool:
    if cached_at is None:
        return False
    if max_age_seconds <= 0:
        return True
    now = dt.datetime.now(dt.timezone.utc)
    return (now - cached_at).total_seconds() <= max_age_seconds


def _playoff_cache_max_age_seconds(year: int) -> int:
    # Current season: refresh more often in case games are in progress.
    # Past seasons: keep API calls very low.
    current_year = dt.date.today().year
    if year >= current_year:
        return 20 * 60
    return 7 * 24 * 60 * 60


def _read_playoff_cache_file(year: int) -> Tuple[List[Dict], Optional[dt.datetime]]:
    path = _playoff_cache_file(year)
    if not os.path.exists(path):
        return [], None

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return [], None

    rows = payload.get("rows") if isinstance(payload, dict) else None
    cached_at_raw = payload.get("cached_at") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return [], None

    cached_at = None
    if isinstance(cached_at_raw, str) and cached_at_raw:
        try:
            txt = cached_at_raw.replace("Z", "+00:00")
            cached_at = dt.datetime.fromisoformat(txt)
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=dt.timezone.utc)
        except Exception:
            cached_at = None

    normalized_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        pair_raw = row.get("pair_key")
        if isinstance(pair_raw, (list, tuple)) and len(pair_raw) == 2:
            pair_key = (normalize_text(pair_raw[0]), normalize_text(pair_raw[1]))
        else:
            home_key = normalize_text(row.get("home_key"))
            away_key = normalize_text(row.get("away_key"))
            pair_key = tuple(sorted([home_key, away_key]))

        normalized = dict(row)
        normalized["home_team"] = normalize_text(row.get("home_team"))
        normalized["away_team"] = normalize_text(row.get("away_team"))
        normalized["home_key"] = normalize_text(row.get("home_key"))
        normalized["away_key"] = normalize_text(row.get("away_key"))
        normalized["pair_key"] = pair_key
        normalized["winner"] = normalize_text(row.get("winner"))
        normalized["notes"] = normalize_text(row.get("notes"))
        normalized["completed"] = bool(row.get("completed", False))
        normalized_rows.append(normalized)

    return normalized_rows, cached_at


def _write_playoff_cache_file(year: int, rows: List[Dict]) -> None:
    _ensure_dashboard_cache_dir()
    path = _playoff_cache_file(year)
    payload = {
        "year": int(year),
        "cached_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "rows": rows,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _load_postseason_games_from_api(year: int) -> List[Dict]:
    api = _cfbd_games_api()
    if api is None:
        return []

    try:
        games = api.get_games(year=year, season_type="postseason")
    except Exception:
        return []

    rows = []
    for g in games:
        home_team = normalize_text(getattr(g, "home_team", None))
        away_team = normalize_text(getattr(g, "away_team", None))
        if not home_team or not away_team:
            continue

        home_points = getattr(g, "home_points", None)
        if home_points is None:
            home_points = getattr(g, "homePoints", None)
        away_points = getattr(g, "away_points", None)
        if away_points is None:
            away_points = getattr(g, "awayPoints", None)

        try:
            home_points = int(home_points) if home_points is not None else None
        except Exception:
            home_points = None
        try:
            away_points = int(away_points) if away_points is not None else None
        except Exception:
            away_points = None

        completed = getattr(g, "completed", None) is True
        winner = ""
        if completed and home_points is not None and away_points is not None:
            if home_points > away_points:
                winner = home_team
            elif away_points > home_points:
                winner = away_team

        rows.append(
            {
                "home_team": home_team,
                "away_team": away_team,
                "home_key": _team_key(home_team),
                "away_key": _team_key(away_team),
                "pair_key": tuple(sorted([_team_key(home_team), _team_key(away_team)])),
                "week": getattr(g, "week", None),
                "notes": normalize_text(getattr(g, "notes", "")),
                "completed": completed,
                "home_points": home_points,
                "away_points": away_points,
                "winner": winner,
            }
        )

    return rows


def cached_postseason_games(year: int) -> List[Dict]:
    year = int(year)
    max_age_seconds = _playoff_cache_max_age_seconds(year)
    now = dt.datetime.now(dt.timezone.utc)

    mem = _PLAYOFF_RESULTS_CACHE_MEM.get(year)
    if mem:
        cached_at, rows = mem
        if _cache_is_fresh(cached_at, max_age_seconds):
            return rows

    file_rows, file_cached_at = _read_playoff_cache_file(year)
    if file_rows and _cache_is_fresh(file_cached_at, max_age_seconds):
        _PLAYOFF_RESULTS_CACHE_MEM[year] = (file_cached_at or now, file_rows)
        return file_rows

    fresh_rows = _load_postseason_games_from_api(year)
    if fresh_rows:
        _PLAYOFF_RESULTS_CACHE_MEM[year] = (now, fresh_rows)
        try:
            _write_playoff_cache_file(year, fresh_rows)
        except Exception:
            pass
        return fresh_rows

    # API unavailable or failed: return stale cache if we have it.
    if file_rows:
        _PLAYOFF_RESULTS_CACHE_MEM[year] = (file_cached_at or now, file_rows)
        return file_rows
    if mem:
        return mem[1]
    return []


def _infer_snapshot_context(file_path: str) -> Tuple[int, str, Optional[int]]:
    base = os.path.basename(file_path)

    m = None
    for pattern in [
        r"spi_rankings_(\d+)_post_w(\d+)\.csv$",
        r"spi_rankings_(\d+)_w(\d+)\.csv$",
        r"spi_rankings_preseason_(\d+)\.csv$",
        r"spi_rankings_(\d+)\.csv$",
    ]:
        m = __import__("re").match(pattern, base)
        if m:
            if "post" in pattern:
                return int(m.group(1)), "postseason", int(m.group(2))
            if "_w" in pattern:
                return int(m.group(1)), "regular", int(m.group(2))
            if "preseason" in pattern:
                return int(m.group(1)), "preseason", 0
            return int(m.group(1)), "regular", None

    today = dt.date.today()
    return today.year, "regular", None


def _load_saved_upcoming_predictions(
    preferred_year: Optional[int],
    mode: str = "next_week",
) -> Tuple[List[Dict], str]:
    mode_name = "all_pending" if mode == "all_pending" else "next_week"
    predictions_dir = os.path.join(DATA_EXPORTS_DIR, "predictions")
    patterns = []
    if preferred_year is not None:
        patterns.append(
            os.path.join(
                predictions_dir,
                f"upcoming_spi_predictions_{preferred_year}_{mode_name}.csv",
            )
        )

    patterns.append(
        os.path.join(predictions_dir, f"upcoming_spi_predictions_*_{mode_name}.csv")
    )

    candidates: List[str] = []
    for pat in patterns:
        if "*" in pat:
            candidates.extend(glob.glob(pat))
        elif os.path.exists(pat):
            candidates.append(pat)

    # De-duplicate while preserving order.
    deduped = []
    seen = set()
    for c in candidates:
        if c not in seen:
            deduped.append(c)
            seen.add(c)

    if not deduped:
        return [], "none"

    # Prefer exact-year files first, then recency.
    def candidate_score(path: str) -> Tuple[int, float]:
        base = os.path.basename(path)
        exact = 1 if (preferred_year is not None and f"_{preferred_year}_" in base) else 0
        return (exact, os.path.getmtime(path))

    chosen = max(deduped, key=candidate_score)
    try:
        df = pd.read_csv(chosen)
    except Exception:
        return [], "none"

    if df.empty:
        return [], "none"

    # Ensure canonical dashboard columns reflect home-field-adjusted outputs when present.
    if "predicted_winner_home_adj" in df.columns:
        pred_home_adj = df["predicted_winner_home_adj"].map(normalize_text)
        if "predicted_winner" not in df.columns:
            df["predicted_winner"] = pred_home_adj
        else:
            mask = pred_home_adj != ""
            if mask.any():
                df.loc[mask, "predicted_winner"] = pred_home_adj[mask]

    if "home_win_prob_home_adj_pct" in df.columns:
        home_pct = pd.to_numeric(df["home_win_prob_home_adj_pct"], errors="coerce")
        if "home_win_prob_pct" not in df.columns:
            df["home_win_prob_pct"] = home_pct
        else:
            df["home_win_prob_pct"] = home_pct.where(home_pct.notna(), pd.to_numeric(df["home_win_prob_pct"], errors="coerce"))

    if "away_win_prob_home_adj_pct" in df.columns:
        away_pct = pd.to_numeric(df["away_win_prob_home_adj_pct"], errors="coerce")
        if "away_win_prob_pct" not in df.columns:
            df["away_win_prob_pct"] = away_pct
        else:
            df["away_win_prob_pct"] = away_pct.where(away_pct.notna(), pd.to_numeric(df["away_win_prob_pct"], errors="coerce"))

    required = [
        "start_date",
        "season_type",
        "week",
        "home_team",
        "away_team",
        "home_rank",
        "away_rank",
        "home_spi",
        "away_spi",
        "home_win_prob_pct",
        "away_win_prob_pct",
        "predicted_winner",
        "neutral_site",
        "home_field_x",
        "notes",
    ]
    for col in required:
        if col not in df.columns:
            df[col] = pd.NA

    subset = df[required].copy()
    subset = subset.where(pd.notna(subset), None)
    if "notes" in subset.columns:
        subset["notes"] = subset["notes"].map(normalize_text)
    rows = subset.to_dict(orient="records")
    return rows, f"file:{os.path.basename(chosen)}"


def upcoming_matchups_next_week(rank_df: pd.DataFrame, rankings_file: str) -> Tuple[List[Dict], str]:
    if rank_df.empty:
        return [], "none"

    inferred_year, _, _ = _infer_snapshot_context(rankings_file)
    saved_rows, saved_source = _load_saved_upcoming_predictions(
        inferred_year,
        mode="next_week",
    )
    if saved_rows:
        return saved_rows, saved_source

    api = _cfbd_games_api()
    if api is None:
        return [], "none"

    year, season_type, week = _infer_snapshot_context(rankings_file)

    try:
        reg_games = api.get_games(year=year, season_type="regular")
        post_games = api.get_games(year=year, season_type="postseason")
        all_games = list(reg_games) + list(post_games)
    except Exception:
        return [], "none"

    now_utc = dt.datetime.now(dt.timezone.utc)

    def parse_start(g) -> Optional[dt.datetime]:
        raw = getattr(g, "start_date", None) or getattr(g, "startDate", None)
        if raw is None:
            return None
        try:
            if isinstance(raw, dt.datetime):
                return raw
            txt = str(raw).replace(" ", "T")
            return dt.datetime.fromisoformat(txt)
        except Exception:
            return None

    pending = []
    for g in all_games:
        completed = getattr(g, "completed", None)
        start = parse_start(g)
        if completed is True:
            continue
        if start is not None and start < now_utc:
            continue
        pending.append((g, start))

    pending.sort(key=lambda x: x[1] or now_utc)

    pending_weeks = [
        int(getattr(g, "week", 0))
        for g, _ in pending
        if getattr(g, "week", None) is not None
    ]
    if pending_weeks:
        target_week = min(pending_weeks)
        pending = [
            (g, start)
            for g, start in pending
            if getattr(g, "week", None) is not None and int(getattr(g, "week")) == target_week
        ]

    spi_map = {normalize_text(r.team): float(r.spi) for r in rank_df.itertuples() if pd.notna(r.spi)}
    rank_map = {normalize_text(r.team): int(r.rank) for r in rank_df.itertuples()}

    rows = []
    for g, start in pending:
        home = normalize_text(getattr(g, "home_team", None))
        away = normalize_text(getattr(g, "away_team", None))
        home_name = normalize_text(getattr(g, "home_team", None))
        away_name = normalize_text(getattr(g, "away_team", None))

        if not home_name or not away_name:
            continue

        home_spi = spi_map.get(home)
        away_spi = spi_map.get(away)

        home_class = normalize_text(getattr(g, "home_classification", None)).lower()
        away_class = normalize_text(getattr(g, "away_classification", None)).lower()
        neutral_site_raw = getattr(g, "neutral_site", None)
        if neutral_site_raw is None:
            neutral_site_raw = getattr(g, "neutralSite", None)
        is_neutral_site = str(neutral_site_raw).strip().lower() in {"1", "true", "yes"}

        # FBS vs FCS override.
        if home_class == "fbs" and away_class != "fbs":
            pred = home_name
            p_home = 1.0
            p_away = 0.0
        elif away_class == "fbs" and home_class != "fbs":
            pred = away_name
            p_home = 0.0
            p_away = 1.0
        else:
            if home_spi is None and away_spi is None:
                continue
            if home_spi is None:
                pred = away_name
                p_home = 0.0
                p_away = 1.0
            elif away_spi is None:
                pred = home_name
                p_home = 1.0
                p_away = 0.0
            else:
                denom = home_spi + away_spi
                if denom <= 0:
                    p_home_raw = 0.5
                else:
                    p_home_raw = home_spi / denom
                p_home = apply_home_field_adjustment(p_home_raw, is_neutral_site, HOME_FIELD_X_OFFICIAL)
                if p_home is None:
                    p_home = p_home_raw
                p_away = 1.0 - p_home
                pred = home_name if p_home >= 0.5 else away_name

        rows.append(
            {
                "start_date": start.isoformat() if start else "",
                "season_type": normalize_text(getattr(g, "season_type", "")),
                "week": getattr(g, "week", None),
                "home_team": home_name,
                "away_team": away_name,
                "home_rank": rank_map.get(home),
                "away_rank": rank_map.get(away),
                "home_spi": home_spi,
                "away_spi": away_spi,
                "home_win_prob_pct": round(100.0 * p_home, 1),
                "away_win_prob_pct": round(100.0 * p_away, 1),
                "predicted_winner": pred,
                "neutral_site": bool(is_neutral_site),
                "home_field_x": HOME_FIELD_X_OFFICIAL,
                "notes": normalize_text(getattr(g, "notes", "")),
            }
        )

    return rows, "api"


def future_matchups_all_pending(rankings_file: str) -> Tuple[List[Dict], str]:
    inferred_year, _, _ = _infer_snapshot_context(rankings_file)
    rows, source = _load_saved_upcoming_predictions(inferred_year, mode="all_pending")
    if not rows:
        return [], "none"

    def sort_key(row: Dict):
        week = row.get("week")
        try:
            week_val = int(week)
        except Exception:
            week_val = 999
        start = normalize_text(row.get("start_date"))
        home = normalize_text(row.get("home_team"))
        return (week_val, start, home)

    rows = sorted(rows, key=sort_key)
    return rows, source


def _team_key(name: str) -> str:
    txt = normalize_text(name).lower()
    chars = []
    for ch in txt:
        if ch.isalnum():
            chars.append(ch)
    return "".join(chars)


def load_postseason_game_results(year: int) -> List[Dict]:
    return cached_postseason_games(year)


def build_playoff_bracket_payload(
    rank_df: pd.DataFrame,
    field_df: pd.DataFrame,
    rankings_file: str,
    playoff_mode: str = "live",
    simulate_remaining: bool = False,
) -> Dict:
    mode = playoff_mode if playoff_mode in {"live", "projection"} else "live"
    if field_df.empty:
        return {
            "mode_requested": playoff_mode,
            "mode_used": mode,
            "rounds": {
                "first_round": [],
                "quarterfinals": [],
                "semifinals": [],
                "championship": [],
            },
            "champion": "",
            "actual_results_available": "no",
        }

    year, _, _ = _infer_snapshot_context(rankings_file)
    postseason_results = load_postseason_game_results(year) if mode == "live" else []
    actual_available = len(postseason_results) > 0

    completed_by_pair = {}
    for row in postseason_results:
        if not row.get("completed"):
            continue
        pair_key = row["pair_key"]
        existing = completed_by_pair.get(pair_key)
        current_week = row.get("week") if row.get("week") is not None else -1
        existing_week = existing.get("week") if existing and existing.get("week") is not None else -1
        if existing is None or current_week >= existing_week:
            completed_by_pair[pair_key] = row

    by_seed = {}
    for r in field_df.to_dict(orient="records"):
        try:
            seed = int(r.get("seed"))
        except Exception:
            continue
        by_seed[seed] = r

    spi_map = {
        _team_key(r.team): float(r.spi)
        for r in rank_df.itertuples()
        if pd.notna(r.spi)
    }

    def predict_winner(team_a: str, team_b: str) -> str:
        a_key = _team_key(team_a)
        b_key = _team_key(team_b)
        a_spi = spi_map.get(a_key)
        b_spi = spi_map.get(b_key)
        if a_spi is None and b_spi is None:
            return team_a
        if a_spi is None:
            return team_b
        if b_spi is None:
            return team_a
        return team_a if a_spi >= b_spi else team_b

    def team_from_seed(seed: int) -> str:
        row = by_seed.get(seed)
        if not row:
            return ""
        return normalize_text(row.get("team"))

    def resolve_game(
        game_id: str,
        team1: str,
        team2: str,
        team1_seed: Optional[int],
        team2_seed: Optional[int],
        round_name: str,
    ) -> Dict:
        t1 = normalize_text(team1)
        t2 = normalize_text(team2)
        if not t1 or not t2:
            return {
                "id": game_id,
                "round": round_name,
                "team1": t1,
                "team2": t2,
                "team1_seed": team1_seed,
                "team2_seed": team2_seed,
                "predicted_winner": "",
                "actual_winner": "",
                "winner": "",
                "winner_source": "tbd",
                "status": "tbd",
                "score": "",
                "notes": "",
            }

        pair_key = tuple(sorted([_team_key(t1), _team_key(t2)]))
        actual_row = completed_by_pair.get(pair_key)
        predicted = predict_winner(t1, t2)

        if mode == "projection":
            return {
                "id": game_id,
                "round": round_name,
                "team1": t1,
                "team2": t2,
                "team1_seed": team1_seed,
                "team2_seed": team2_seed,
                "predicted_winner": predicted,
                "actual_winner": "",
                "winner": predicted,
                "winner_source": "projected",
                "status": "projected",
                "score": "",
                "notes": "",
            }

        if actual_row is None:
            if not simulate_remaining:
                return {
                    "id": game_id,
                    "round": round_name,
                    "team1": t1,
                    "team2": t2,
                    "team1_seed": team1_seed,
                    "team2_seed": team2_seed,
                    "predicted_winner": predicted,
                    "actual_winner": "",
                    "winner": "",
                    "winner_source": "pending",
                    "status": "pending",
                    "score": "",
                    "notes": "",
                }
            return {
                "id": game_id,
                "round": round_name,
                "team1": t1,
                "team2": t2,
                "team1_seed": team1_seed,
                "team2_seed": team2_seed,
                "predicted_winner": predicted,
                "actual_winner": "",
                "winner": predicted,
                "winner_source": "projected",
                "status": "projected",
                "score": "",
                "notes": "",
            }

        score = ""
        hp = actual_row.get("home_points")
        ap = actual_row.get("away_points")
        if hp is not None and ap is not None:
            score = f"{actual_row.get('home_team')} {hp}, {actual_row.get('away_team')} {ap}"

        actual_winner = normalize_text(actual_row.get("winner"))
        resolved_winner = actual_winner or predicted

        return {
            "id": game_id,
            "round": round_name,
            "team1": t1,
            "team2": t2,
            "team1_seed": team1_seed,
            "team2_seed": team2_seed,
            "predicted_winner": predicted,
            "actual_winner": actual_winner,
            "winner": resolved_winner,
            "winner_source": "actual" if actual_winner else "projected",
            "status": "completed" if actual_winner else "projected",
            "score": score,
            "notes": normalize_text(actual_row.get("notes", "")),
        }

    # Bracket structure: 5v12, 6v11, 7v10, 8v9 then bye seeds 1..4.
    r1 = [
        resolve_game("R1-1", team_from_seed(5), team_from_seed(12), 5, 12, "first_round"),
        resolve_game("R1-2", team_from_seed(6), team_from_seed(11), 6, 11, "first_round"),
        resolve_game("R1-3", team_from_seed(7), team_from_seed(10), 7, 10, "first_round"),
        resolve_game("R1-4", team_from_seed(8), team_from_seed(9), 8, 9, "first_round"),
    ]

    qf = [
        resolve_game("QF-1", team_from_seed(1), r1[3].get("winner", ""), 1, None, "quarterfinal"),
        resolve_game("QF-2", team_from_seed(2), r1[2].get("winner", ""), 2, None, "quarterfinal"),
        resolve_game("QF-3", team_from_seed(3), r1[1].get("winner", ""), 3, None, "quarterfinal"),
        resolve_game("QF-4", team_from_seed(4), r1[0].get("winner", ""), 4, None, "quarterfinal"),
    ]

    sf = [
        resolve_game("SF-1", qf[0].get("winner", ""), qf[3].get("winner", ""), None, None, "semifinal"),
        resolve_game("SF-2", qf[1].get("winner", ""), qf[2].get("winner", ""), None, None, "semifinal"),
    ]

    title = [
        resolve_game(
            "NCG-1",
            sf[0].get("winner", ""),
            sf[1].get("winner", ""),
            None,
            None,
            "championship",
        )
    ]

    champion = normalize_text(title[0].get("winner", "")) if title else ""
    return {
        "mode_requested": playoff_mode,
        "mode_used": mode,
        "simulate_remaining": "yes" if simulate_remaining else "no",
        "season_year": year,
        "actual_results_available": "yes" if actual_available else "no",
        "champion": champion,
        "rounds": {
            "first_round": r1,
            "quarterfinals": qf,
            "semifinals": sf,
            "championship": title,
        },
    }


def current_snapshot_payload() -> Dict:
    ranking_file = latest_spi_rankings_file(preferred_year=dt.date.today().year)
    if ranking_file is None:
        return {
            "has_rankings": False,
            "message": "No SPI ranking files found under data_exports.",
        }

    season_year, snapshot_stage, _ = _infer_snapshot_context(ranking_file)
    rank_df = load_spi_table(ranking_file, season_year=season_year)
    if rank_df.empty:
        return {
            "has_rankings": False,
            "message": f"Ranking file {ranking_file} exists but has no rows.",
        }

    ranking_method = "spi"
    rank_df, ranking_method_info = apply_current_ranking_method(
        rank_df,
        season_year=season_year,
        ranking_file=ranking_file,
        requested_method=ranking_method,
    )

    preseason_override = snapshot_stage == "preseason"
    if preseason_override:
        rank_df = rank_df.copy()
        rank_df["wins"] = 0
        rank_df["losses"] = 0

    champ_mode = normalize_text(request.args.get("champ_mode", "spi")).lower()
    if champ_mode not in {"spi", "standings"}:
        champ_mode = "spi"
    playoff_mode = normalize_text(request.args.get("playoff_mode", "live")).lower()
    if playoff_mode not in {"live", "projection"}:
        playoff_mode = "live"
    simulate_remaining = normalize_text(request.args.get("simulate_remaining", "")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    standings_df = load_team_standings_for_snapshot(ranking_file)
    field_df, champ_info = projected_twelve_team_field_with_mode(
        rank_df,
        standings_df,
        champ_mode=champ_mode,
    )
    if preseason_override and not field_df.empty:
        field_df = field_df.copy()
        field_df["wins"] = 0
        field_df["losses"] = 0
    playoff_bracket = build_playoff_bracket_payload(
        rank_df,
        field_df,
        ranking_file,
        playoff_mode=playoff_mode,
        simulate_remaining=simulate_remaining,
    )
    upcoming, upcoming_source = upcoming_matchups_next_week(rank_df, ranking_file)
    future, future_source = future_matchups_all_pending(ranking_file)

    return {
        "has_rankings": True,
        "ranking_file": os.path.basename(ranking_file),
        "ranking_method": ranking_method_info,
        "rankings": rank_df.to_dict(orient="records"),
        "projected_field": field_df.to_dict(orient="records"),
        "champ_projection": champ_info,
        "playoff_bracket": playoff_bracket,
        "components": {
            "n_rankings": rank_df.sort_values("n_adj", ascending=False).head(50).to_dict(orient="records"),
            "sor_rankings": rank_df.sort_values("sor_adj", ascending=False).head(50).to_dict(orient="records"),
        },
        "upcoming_matchups_source": upcoming_source,
        "upcoming_matchups": upcoming,
        "future_matchups_source": future_source,
        "future_matchups": future,
    }


@app.route("/")
def home():
    return render_template("spi_dashboard.html")


@app.route("/api/current")
def api_current():
    payload = {"ok": True, "current": current_snapshot_payload()}
    return jsonify(json_safe(payload))


@app.route("/api/historical/metadata")
def api_historical_metadata():
    method = "current"
    df, dataset_info = load_predictions_df(method)
    if df.empty:
        return jsonify({"ok": False, "error": "No prediction files found in data_exports/predictions."}), 404
    return jsonify(
        {
            "ok": True,
            "metadata": predictions_metadata(df),
            "dataset": dataset_info,
        }
    )


@app.route("/api/historical/query", methods=["POST"])
def api_historical_query():
    payload = request.get_json(silent=True) or {}
    method = "current"
    df, dataset_info = load_predictions_df(method)
    if df.empty:
        return jsonify({"ok": False, "error": "No prediction files found in data_exports/predictions."}), 404

    page = max(1, int(payload.get("page", 1) or 1))
    page_size = max(1, min(MAX_PAGE_SIZE, int(payload.get("page_size", DEFAULT_PAGE_SIZE) or DEFAULT_PAGE_SIZE)))

    baseline = df.copy()
    filtered = apply_filters(df, payload)

    base_metrics = metrics_bundle(baseline)
    filt_metrics = metrics_bundle(filtered)

    slices = slice_pack(filtered)
    home_away_slices = home_away_slice_pack(filtered)


    sort_cols = [c for c in ["year", "season_type", "week", "start_date", "home_team"] if c in filtered.columns]
    display = filtered.sort_values(sort_cols)

    total_rows = int(len(display))
    start = (page - 1) * page_size
    end = start + page_size
    page_df = display.iloc[start:end].copy()

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
        "predicted_side",
        "is_playoff",
        "is_national_championship",
        "ranking_source",
        "ranking_source_file",
        "ranking_source_team_count",
    ]
    table_columns = [c for c in table_columns if c in page_df.columns]

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
            "dataset": dataset_info,
            "metrics": {"baseline": base_metrics, "filtered": filt_metrics},
            "slices": slices,
            "home_away_slices": home_away_slices,
            "table": {
                "columns": table_columns,
                "rows": page_df[table_columns].to_dict(orient="records"),
            },
        }
    )


if __name__ == "__main__":
    host = os.environ.get("SPI_DASHBOARD_HOST", "127.0.0.1")
    port_raw = os.environ.get("SPI_DASHBOARD_PORT", "5055")
    try:
        port = int(port_raw)
    except ValueError:
        port = 5055

    debug = os.environ.get("SPI_DASHBOARD_DEBUG", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    print(f"Starting SPI Dashboard on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
