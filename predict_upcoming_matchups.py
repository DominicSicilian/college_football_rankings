import argparse
import datetime as dt
import glob
import json
import math
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd

from model_config import HOME_FIELD_X_DEFAULT

try:
    import cfbd
except Exception:
    cfbd = None

BASE_DIR = os.path.dirname(__file__)
DATA_EXPORTS_DIR = os.path.join(BASE_DIR, "data_exports")
CACHE_DIR = os.path.join(DATA_EXPORTS_DIR, "dashboard_cache")
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

SPI_LOGIT_BETA = 0.0425
SPI_LOGIT_INTERCEPT = 0.0


def normalize_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _team_key(name: str) -> str:
    txt = normalize_text(name).lower()
    return "".join(ch for ch in txt if ch.isalnum())


def _cfbd_games_api():
    if cfbd is None:
        return None
    api_key = os.environ.get("CFBD_API_KEY")
    if not api_key:
        return None
    api_key = str(api_key).strip()
    if api_key.lower().startswith("bearer "):
        api_key = api_key[7:].strip()
    conf = cfbd.Configuration(
        host="https://api.collegefootballdata.com",
        access_token=api_key,
    )
    return cfbd.GamesApi(cfbd.ApiClient(conf))


def latest_spi_rankings_file(data_exports_dir: str, preferred_year: Optional[int] = None) -> Optional[str]:
    pattern = os.path.join(data_exports_dir, "spi_rankings_*.csv")
    files = glob.glob(pattern)
    filtered = []
    for f in files:
        base = os.path.basename(f)
        if "detailed" in base.lower():
            continue
        if base.startswith("spi_rankings_final"):
            continue
        filtered.append(f)
    if not filtered:
        return None

    def classify(path: str):
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

        preferred_match = 1 if (preferred_year is not None and year == preferred_year) else 0
        return (preferred_match, year, tier, week, os.path.getmtime(path))

    return max(filtered, key=classify)


def apply_conference_overrides(frame: pd.DataFrame, season_year: Optional[int]) -> pd.DataFrame:
    if frame.empty or season_year is None or "team" not in frame.columns or "conference" not in frame.columns:
        return frame

    out = frame.copy()
    team_keys = out["team"].map(_team_key)
    conf = out["conference"].map(normalize_text)
    for team_key, effective_year, target_conf in CONFERENCE_REALIGNMENT_OVERRIDES:
        if int(season_year) < int(effective_year):
            continue
        mask = team_keys == team_key
        if mask.any():
            conf.loc[mask] = target_conf
    out["conference"] = conf
    return out


def load_spi_table(file_path: str, season_year: Optional[int] = None) -> pd.DataFrame:
    df = pd.read_csv(file_path)
    if df.empty:
        return df

    cols = {c.lower(): c for c in df.columns}
    team_col = cols.get("team") or cols.get("team name") or list(df.columns)[0]
    conf_col = cols.get("conference") or cols.get("conf.")
    wins_col = cols.get("wins") or cols.get("w")
    loss_col = cols.get("losses") or cols.get("l")
    spi_col = cols.get("spi")

    out = pd.DataFrame()
    out["team"] = df[team_col].map(normalize_text)
    out["conference"] = df[conf_col].map(normalize_text) if conf_col else "Unknown"
    out["wins"] = pd.to_numeric(df[wins_col], errors="coerce").fillna(0).astype(int) if wins_col else 0
    out["losses"] = pd.to_numeric(df[loss_col], errors="coerce").fillna(0).astype(int) if loss_col else 0
    out["spi"] = pd.to_numeric(df[spi_col], errors="coerce") if spi_col else pd.NA
    out = apply_conference_overrides(out, season_year)

    out = out[out["team"] != ""].copy()
    out = out.sort_values("spi", ascending=False, na_position="last").reset_index(drop=True)
    out["rank"] = out.index + 1
    out["team_key"] = out["team"].map(_team_key)
    return out


def _cache_file(year: int) -> str:
    return os.path.join(CACHE_DIR, f"upcoming_games_{int(year)}.json")


def load_upcoming_cache(year: int, max_age_minutes: int) -> Optional[List[dict]]:
    path = _cache_file(year)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None

    cached_at_raw = payload.get("cached_at") if isinstance(payload, dict) else None
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None

    if not isinstance(cached_at_raw, str) or not cached_at_raw:
        return None

    try:
        cached_at = dt.datetime.fromisoformat(cached_at_raw.replace("Z", "+00:00"))
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None

    age = (dt.datetime.now(dt.timezone.utc) - cached_at).total_seconds() / 60.0
    if age > max_age_minutes:
        return None
    return rows


def load_upcoming_cache_any_age(year: int) -> Optional[List[dict]]:
    path = _cache_file(year)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None

    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    return rows


def save_upcoming_cache(year: int, rows: List[dict]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload = {
        "year": int(year),
        "cached_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "rows": rows,
    }
    def _json_default(value):
        if isinstance(value, (dt.datetime, dt.date)):
            return value.isoformat()
        raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")

    with open(_cache_file(year), "w", encoding="utf-8") as f:
        json.dump(payload, f, default=_json_default)


def fetch_upcoming_games(year: int, cache_minutes: int, cache_only: bool = False) -> List[dict]:
    cached = load_upcoming_cache(year, cache_minutes)
    if cached is not None:
        return cached

    stale_cached = load_upcoming_cache_any_age(year)

    if cache_only:
        if stale_cached is not None:
            return stale_cached
        raise RuntimeError(
            f"No cached upcoming games found for {year}. Expected cache file: {_cache_file(year)}"
        )

    api = _cfbd_games_api()
    if api is None:
        if stale_cached is not None:
            return stale_cached
        raise RuntimeError(
            "CFBD API unavailable. Set CFBD_API_KEY and ensure cfbd is installed, "
            "or run once with valid API access to warm the cache."
        )

    try:
        reg_games = api.get_games(year=year, season_type="regular")
        post_games = api.get_games(year=year, season_type="postseason")
    except Exception as exc:
        if stale_cached is not None:
            print("Warning: CFBD request failed; using stale cached upcoming games.")
            return stale_cached

        err_text = str(exc)
        if "401" in err_text or "Unauthorized" in err_text:
            raise RuntimeError(
                "CFBD returned 401 Unauthorized. Check CFBD_API_KEY and set it to the raw key value "
                "(do not include 'Bearer ')."
            ) from exc

        raise RuntimeError(f"Failed to fetch games from CFBD: {exc}") from exc

    rows: List[dict] = []

    for g in list(reg_games) + list(post_games):
        game_dict = g.to_dict() if hasattr(g, "to_dict") else {
            k: v for k, v in getattr(g, "__dict__", {}).items() if not str(k).startswith("_")
        }
        rows.append(game_dict)

    save_upcoming_cache(year, rows)
    return rows


def parse_start(game: dict) -> Optional[dt.datetime]:
    raw = game.get("start_date") or game.get("startDate")
    if raw is None:
        return None
    try:
        if isinstance(raw, dt.datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=dt.timezone.utc)
        txt = str(raw).replace(" ", "T")
        parsed = dt.datetime.fromisoformat(txt)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except Exception:
        return None


def clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def is_true_flag(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def logit(probability: float) -> float:
    p = clamp_probability(probability)
    p = max(1e-9, min(1.0 - 1e-9, p))
    return math.log(p / (1.0 - p))


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def home_field_logit_shift_from_x(home_field_x: float) -> float:
    # Convert an intuitive probability bump around a 50/50 game into a log-odds shift.
    baseline = 0.5
    bumped = clamp_probability(baseline + float(home_field_x))
    return logit(bumped) - logit(baseline)


def raw_home_probability_from_spi(home_spi: Optional[float], away_spi: Optional[float]) -> Optional[float]:
    if home_spi is None and away_spi is None:
        return None
    if home_spi is None:
        return 0.0
    if away_spi is None:
        return 1.0

    spi_delta = float(home_spi) - float(away_spi)
    z = SPI_LOGIT_INTERCEPT + SPI_LOGIT_BETA * spi_delta
    return sigmoid(z)


def apply_home_field_adjustment(
    home_prob_raw: Optional[float],
    is_neutral_site: bool,
    home_field_x: float,
) -> Optional[float]:
    if home_prob_raw is None:
        return None
    if bool(is_neutral_site):
        return clamp_probability(home_prob_raw)

    z = logit(float(home_prob_raw)) + home_field_logit_shift_from_x(home_field_x)
    return clamp_probability(sigmoid(z))


def predict_games(
    rank_df: pd.DataFrame,
    games: List[dict],
    next_week_only: bool = True,
    home_field_x: float = HOME_FIELD_X_DEFAULT,
) -> pd.DataFrame:
    now_utc = dt.datetime.now(dt.timezone.utc)

    spi_map: Dict[str, float] = {
        _team_key(r.team): float(r.spi)
        for r in rank_df.itertuples()
        if pd.notna(r.spi)
    }
    rank_map: Dict[str, int] = {_team_key(r.team): int(r.rank) for r in rank_df.itertuples()}

    pending = []
    for g in games:
        completed = g.get("completed") is True
        if completed:
            continue

        start = parse_start(g)
        if start is not None and start < now_utc:
            continue

        home_team = normalize_text(g.get("home_team") or g.get("homeTeam"))
        away_team = normalize_text(g.get("away_team") or g.get("awayTeam"))
        if not home_team or not away_team:
            continue

        week = g.get("week")
        try:
            week = int(week) if week is not None else None
        except Exception:
            week = None

        pending.append((g, start, week, home_team, away_team))

    if not pending:
        return pd.DataFrame()

    pending.sort(key=lambda x: x[1] or now_utc)

    if next_week_only:
        weeks = [w for _, _, w, _, _ in pending if w is not None]
        if weeks:
            target_week = min(weeks)
            pending = [row for row in pending if row[2] == target_week]

    rows = []
    for g, start, week, home_team, away_team in pending:
        home_key = _team_key(home_team)
        away_key = _team_key(away_team)

        home_spi = spi_map.get(home_key)
        away_spi = spi_map.get(away_key)

        home_class = normalize_text(g.get("home_classification") or g.get("homeClassification")).lower()
        away_class = normalize_text(g.get("away_classification") or g.get("awayClassification")).lower()
        neutral_raw = g.get("neutral_site") if "neutral_site" in g else g.get("neutralSite")
        is_neutral = is_true_flag(neutral_raw)

        if home_class == "fbs" and away_class != "fbs":
            pred_pure = home_team
            p_home_raw = 1.0
            reason_pure = "fbs_vs_fcs_override"
        elif away_class == "fbs" and home_class != "fbs":
            pred_pure = away_team
            p_home_raw = 0.0
            reason_pure = "fbs_vs_fcs_override"
        else:
            if home_spi is None and away_spi is None:
                continue
            if home_spi is None:
                pred_pure = away_team
                p_home_raw = 0.0
                reason_pure = "away_has_spi_only"
            elif away_spi is None:
                pred_pure = home_team
                p_home_raw = 1.0
                reason_pure = "home_has_spi_only"
            else:
                reason_pure = "higher_spi"
                p_home_raw = raw_home_probability_from_spi(home_spi, away_spi)
                if p_home_raw is None:
                    p_home_raw = 0.5
                pred_pure = home_team if home_spi >= away_spi else away_team

        p_home_raw = clamp_probability(p_home_raw)
        p_away_raw = clamp_probability(1.0 - p_home_raw)

        p_home_adj = apply_home_field_adjustment(
            p_home_raw,
            is_neutral_site=is_neutral,
            home_field_x=home_field_x,
        )
        if p_home_adj is None:
            continue
        p_away_adj = clamp_probability(1.0 - p_home_adj)
        pred_home_adj = home_team if p_home_adj >= 0.5 else away_team

        reason_home_adj = reason_pure
        if reason_pure == "higher_spi":
            reason_home_adj = "higher_spi_home_field_adjusted"

        rows.append(
            {
                "start_date": start.isoformat() if start else "",
                "season_type": normalize_text(g.get("season_type") or g.get("seasonType")),
                "week": week,
                "home_team": home_team,
                "away_team": away_team,
                "home_rank": rank_map.get(home_key),
                "away_rank": rank_map.get(away_key),
                "home_spi": home_spi,
                "away_spi": away_spi,
                "home_win_prob_pct": round(100.0 * p_home_adj, 1),
                "away_win_prob_pct": round(100.0 * p_away_adj, 1),
                "predicted_winner": pred_home_adj,
                "prediction_reason": reason_home_adj,
                "predicted_winner_pure": pred_pure,
                "predicted_winner_home_adj": pred_home_adj,
                "prediction_reason_pure": reason_pure,
                "prediction_reason_home_adj": reason_home_adj,
                "home_win_prob_pure_pct": round(100.0 * p_home_raw, 1),
                "away_win_prob_pure_pct": round(100.0 * p_away_raw, 1),
                "home_win_prob_home_adj_pct": round(100.0 * p_home_adj, 1),
                "away_win_prob_home_adj_pct": round(100.0 * p_away_adj, 1),
                "home_field_x": float(home_field_x),
                "neutral_site": bool(is_neutral),
                "notes": normalize_text(g.get("notes")),
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(["start_date", "week", "home_team"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Predict upcoming CFB matchups from latest SPI rankings."
    )
    parser.add_argument("--year", type=int, default=dt.date.today().year)
    parser.add_argument("--data-exports-dir", type=str, default=DATA_EXPORTS_DIR)
    parser.add_argument(
        "--output-file",
        type=str,
        default="",
        help="Optional explicit output path. Defaults to data_exports/predictions/upcoming_spi_predictions_<year>_next_week.csv",
    )
    parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Predict all pending games instead of only the next available week.",
    )
    parser.add_argument(
        "--home-field-x",
        type=float,
        default=HOME_FIELD_X_DEFAULT,
        help="Home-field strength X around a 50/50 game; converted to a log-odds shift.",
    )
    parser.add_argument(
        "--cache-minutes",
        type=int,
        default=20,
        help="Minutes to reuse cached upcoming games before refreshing from API.",
    )
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Use cached upcoming games only and never call CFBD API.",
    )
    args = parser.parse_args()

    rankings_file = latest_spi_rankings_file(args.data_exports_dir, preferred_year=args.year)
    if rankings_file is None:
        raise SystemExit("No SPI rankings file found in data_exports.")

    rank_df = load_spi_table(rankings_file, season_year=args.year)
    if rank_df.empty:
        raise SystemExit(f"Rankings file is empty: {rankings_file}")

    games = fetch_upcoming_games(args.year, args.cache_minutes, cache_only=args.cache_only)
    pred_df = predict_games(
        rank_df,
        games,
        next_week_only=not args.all_pending,
        home_field_x=args.home_field_x,
    )

    if pred_df.empty:
        raise SystemExit("No upcoming games to predict from current data.")

    default_name = (
        f"upcoming_spi_predictions_{args.year}_all_pending.csv"
        if args.all_pending
        else f"upcoming_spi_predictions_{args.year}_next_week.csv"
    )

    output_path = args.output_file or os.path.join(args.data_exports_dir, "predictions", default_name)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pred_df.to_csv(output_path, index=False)

    print(f"Using rankings: {os.path.basename(rankings_file)}")
    print(f"Predicted games: {len(pred_df)}")
    print(f"Saved: {output_path}")
    print(f"Home-field additive X: {args.home_field_x:.6f}")


if __name__ == "__main__":
    main()
