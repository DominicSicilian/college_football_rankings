import argparse
import glob
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

from model_config import HOME_FIELD_X_DEFAULT

HOME_FIELD_X_ALL_GAMES = HOME_FIELD_X_DEFAULT
SPI_LOGIT_BETA = 0.0425
SPI_LOGIT_INTERCEPT = 0.0

try:
    import cfbd
    from cfbd.rest import ApiException
except Exception:
    cfbd = None
    ApiException = Exception


def normalize_team_name(name: Optional[str]) -> str:
    if not name:
        return ""
    text = str(name).strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_first_column(columns: List[str], candidates: List[str]) -> Optional[str]:
    lower_map = {str(c).strip().lower(): c for c in columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lower_map:
            return lower_map[key]
    return None


def clamp_probability(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return max(0.0, min(1.0, float(value)))


def is_true_flag(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def logit(probability: float) -> float:
    p = clamp_probability(probability)
    p = max(1e-9, min(1.0 - 1e-9, float(p)))
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
    return logit(float(bumped)) - logit(baseline)


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
    if is_neutral_site:
        return clamp_probability(home_prob_raw)

    z = logit(float(home_prob_raw)) + home_field_logit_shift_from_x(home_field_x)
    return clamp_probability(sigmoid(z))


def get_game_field(game: dict, snake_key: str, camel_key: str):
    if snake_key in game:
        return game.get(snake_key)
    return game.get(camel_key)


def load_games_from_cache(cache_dir: str, year: int, week: int, season_type: str) -> Optional[List[dict]]:
    season = "postseason" if season_type == "postseason" else "regular"
    candidates = [
        os.path.join(cache_dir, f"games_{year}_{season}_w{week}.json"),
        os.path.join(cache_dir, f"games_{year}_{season_type}_w{week}.json"),
        os.path.join(cache_dir, f"games_{year}_w{week}.json"),
    ]

    # Compatibility scan for alternate naming conventions.
    pattern = os.path.join(cache_dir, f"*{year}*{week}*.json")
    for path in sorted(glob.glob(pattern)):
        base = os.path.basename(path).lower()
        if "game" not in base:
            continue

        # Accept common cache names:
        # - games_<year>_w<week>.json (regular)
        # - games_<year>_regular_w<week>.json
        # - games_<year>_postseason_w<week>.json
        if re.search(rf"\b{year}\b", base) and re.search(rf"w{week}\b", base):
            candidates.append(path)

    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, list):
                return payload
        except Exception:
            continue
    return None


def save_games_to_cache(cache_dir: str, year: int, week: int, season_type: str, games: List[dict]) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    out_path = os.path.join(cache_dir, f"games_{year}_{season_type}_w{week}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(games, f)


def init_games_api():
    if cfbd is None:
        return None

    api_key = os.environ.get("CFBD_API_KEY")
    if not api_key:
        return None

    api_key = str(api_key).strip().strip('"').strip("'")
    if api_key.lower().startswith("bearer "):
        # Keep only the token; client will add the Bearer prefix.
        api_key = api_key.split(" ", 1)[1].strip()
    if not api_key:
        return None

    configuration = cfbd.Configuration()
    configuration.api_key["Authorization"] = api_key
    configuration.api_key_prefix["Authorization"] = "Bearer"
    client = cfbd.ApiClient(configuration)
    return cfbd.GamesApi(client)


def should_disable_api_after_error(exc: Exception) -> bool:
    text = str(exc).lower()
    if "401" in text or "unauthorized" in text:
        return True
    if "429" in text or "too many requests" in text or "rate limit" in text:
        return True
    return False


def fetch_games_from_api(games_api, year: int, week: int, season_type: str) -> List[dict]:
    games = games_api.get_games(year=year, week=week, season_type=season_type)
    result: List[dict] = []
    for game in games:
        if hasattr(game, "to_dict"):
            result.append(game.to_dict())
        elif hasattr(game, "__dict__"):
            result.append({k: v for k, v in game.__dict__.items() if not str(k).startswith("_")})
    return result


def is_fbs_game_side(game: dict, side: str, ranking_map: Dict[str, float]) -> bool:
    cls = get_game_field(game, f"{side}_classification", f"{side}Classification")
    if cls and str(cls).strip().lower() == "fbs":
        return True

    team_name = get_game_field(game, f"{side}_team", f"{side}Team")
    return normalize_team_name(team_name) in ranking_map


def classify_postseason_game(notes: Optional[str]) -> Tuple[bool, bool]:
    text = (notes or "").lower()
    is_playoff = "college football playoff" in text or "cfp" in text
    is_nat_champ = "national championship" in text
    return is_playoff, is_nat_champ


@dataclass
class RankingSource:
    file_path: str
    descriptor: str


def count_ranked_teams(file_path: str) -> int:
    if not os.path.exists(file_path):
        return 0

    df = pd.read_csv(file_path)
    if df.empty:
        return 0

    team_col = find_first_column(list(df.columns), ["Team Name", "team"])
    if team_col is None:
        return 0

    teams = {normalize_team_name(t) for t in df[team_col].tolist()}
    teams.discard("")
    return len(teams)


def ranking_file_candidates(file_path: str) -> List[str]:
    candidates = [file_path]
    base = os.path.basename(file_path)
    parent = os.path.dirname(file_path)

    transforms = [
        (r"^spi_rankings_(\d+)_w(\d+)\.csv$", r"spi_rankings_detailed_\1_w\2.csv"),
        (r"^spi_rankings_(\d+)_post_w(\d+)\.csv$", r"spi_rankings_detailed_\1_post_w\2.csv"),
        (r"^spi_rankings_preseason_(\d+)\.csv$", r"spi_rankings_detailed_preseason_\1.csv"),
        (r"^spi_rankings_final_(\d+)\.csv$", r"spi_rankings_detailed_final_\1.csv"),
        (r"^spi_rankings_(\d+)\.csv$", r"spi_rankings_detailed_\1.csv"),
    ]

    for pattern, replacement in transforms:
        alt_base = re.sub(pattern, replacement, base)
        if alt_base != base:
            candidates.append(os.path.join(parent, alt_base))

    deduped: List[str] = []
    seen = set()
    for path in candidates:
        if path not in seen:
            deduped.append(path)
            seen.add(path)
    return deduped


def choose_full_rankings_file(file_path: str, min_ranking_teams: int) -> Tuple[str, int]:
    best_path = ""
    best_count = -1

    for candidate in ranking_file_candidates(file_path):
        if not os.path.exists(candidate):
            continue
        team_count = count_ranked_teams(candidate)
        if team_count >= min_ranking_teams:
            return candidate, team_count
        if team_count > best_count:
            best_path = candidate
            best_count = team_count

    if best_count >= 0:
        raise ValueError(
            f"Ranking file coverage too small for {file_path}: best candidate "
            f"{best_path} has {best_count} teams, expected at least {min_ranking_teams}."
        )

    raise FileNotFoundError(
        f"No ranking file found for {file_path}. Checked: {ranking_file_candidates(file_path)}"
    )


def list_available_weeks(data_exports_dir: str, year: int, season_type: str) -> List[int]:
    if season_type == "regular":
        pattern = os.path.join(data_exports_dir, f"spi_rankings_{year}_w*.csv")
        regex = re.compile(rf"spi_rankings_{year}_w(\d+)\.csv$")
    else:
        pattern = os.path.join(data_exports_dir, f"spi_rankings_{year}_post_w*.csv")
        regex = re.compile(rf"spi_rankings_{year}_post_w(\d+)\.csv$")

    weeks: List[int] = []
    for path in glob.glob(pattern):
        m = regex.search(os.path.basename(path))
        if not m:
            continue
        weeks.append(int(m.group(1)))
    return sorted(set(weeks))


def previous_week_ranking_source(data_exports_dir: str, year: int, season_type: str, week: int) -> RankingSource:
    if season_type == "regular":
        if week == 1:
            file_path = os.path.join(data_exports_dir, f"spi_rankings_preseason_{year}.csv")
            return RankingSource(file_path=file_path, descriptor=f"preseason_{year}")

        file_path = os.path.join(data_exports_dir, f"spi_rankings_{year}_w{week - 1}.csv")
        return RankingSource(file_path=file_path, descriptor=f"regular_w{week - 1}")

    if week == 1:
        regular_weeks = list_available_weeks(data_exports_dir, year, "regular")
        if not regular_weeks:
            file_path = os.path.join(data_exports_dir, f"spi_rankings_{year}.csv")
            return RankingSource(file_path=file_path, descriptor=f"final_{year}")
        file_path = os.path.join(data_exports_dir, f"spi_rankings_{year}_w{max(regular_weeks)}.csv")
        return RankingSource(file_path=file_path, descriptor=f"regular_w{max(regular_weeks)}")

    file_path = os.path.join(data_exports_dir, f"spi_rankings_{year}_post_w{week - 1}.csv")
    return RankingSource(file_path=file_path, descriptor=f"post_w{week - 1}")


def load_rankings_map(file_path: str) -> Dict[str, float]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Ranking file not found: {file_path}")

    df = pd.read_csv(file_path)
    if df.empty:
        return {}

    team_col = find_first_column(list(df.columns), ["Team Name", "team", "school"])
    spi_col = find_first_column(list(df.columns), ["SPI", "spi", "rating", "score"])

    if team_col is None or spi_col is None:
        raise ValueError(f"Missing required columns in {file_path}. Need team and SPI columns.")

    work = df[[team_col, spi_col]].copy()
    work[spi_col] = pd.to_numeric(work[spi_col], errors="coerce")
    work = work.dropna(subset=[spi_col])

    ranking_map: Dict[str, float] = {}
    for row in work.itertuples(index=False):
        team = normalize_team_name(getattr(row, team_col))
        if not team:
            continue
        ranking_map[team] = float(getattr(row, spi_col))
    return ranking_map


def predict_winner(
    game: dict,
    ranking_map: Dict[str, float],
) -> Tuple[Optional[str], Optional[float], Optional[float], str]:
    home_team = get_game_field(game, "home_team", "homeTeam")
    away_team = get_game_field(game, "away_team", "awayTeam")
    home_norm = normalize_team_name(home_team)
    away_norm = normalize_team_name(away_team)

    home_spi = ranking_map.get(home_norm)
    away_spi = ranking_map.get(away_norm)

    home_fbs = is_fbs_game_side(game, "home", ranking_map)
    away_fbs = is_fbs_game_side(game, "away", ranking_map)

    if home_fbs and not away_fbs:
        return home_team, home_spi, away_spi, "fbs_vs_fcs_rule"
    if away_fbs and not home_fbs:
        return away_team, home_spi, away_spi, "fbs_vs_fcs_rule"

    if home_spi is not None and away_spi is not None:
        if home_spi >= away_spi:
            return home_team, home_spi, away_spi, "higher_spi"
        return away_team, home_spi, away_spi, "higher_spi"

    if home_spi is not None and away_spi is None:
        return home_team, home_spi, away_spi, "only_home_spi"
    if away_spi is not None and home_spi is None:
        return away_team, home_spi, away_spi, "only_away_spi"

    return None, home_spi, away_spi, "no_spi_available"


def predict_winner_variants(
    game: dict,
    ranking_map: Dict[str, float],
    home_field_x: float = HOME_FIELD_X_ALL_GAMES,
) -> Dict[str, Optional[object]]:
    predicted_pure, home_spi, away_spi, reason_pure = predict_winner(
        game,
        ranking_map,
    )

    home_team = get_game_field(game, "home_team", "homeTeam")
    away_team = get_game_field(game, "away_team", "awayTeam")
    home_norm = normalize_team_name(home_team)
    away_norm = normalize_team_name(away_team)
    neutral_site = get_game_field(game, "neutral_site", "neutralSite")
    is_neutral_site = is_true_flag(neutral_site)

    home_fbs = is_fbs_game_side(game, "home", ranking_map)
    away_fbs = is_fbs_game_side(game, "away", ranking_map)

    p_home_raw = raw_home_probability_from_spi(home_spi, away_spi)
    p_home_adj = apply_home_field_adjustment(p_home_raw, is_neutral_site, home_field_x)

    predicted_hfa = predicted_pure
    reason_hfa = reason_pure

    if home_fbs and not away_fbs:
        predicted_hfa = home_team
        reason_hfa = "fbs_vs_fcs_rule"
        p_home_raw = 1.0
        p_home_adj = 1.0
    elif away_fbs and not home_fbs:
        predicted_hfa = away_team
        reason_hfa = "fbs_vs_fcs_rule"
        p_home_raw = 0.0
        p_home_adj = 0.0
    elif p_home_adj is not None and home_team and away_team:
        predicted_hfa = home_team if p_home_adj >= 0.5 else away_team
        if reason_pure == "higher_spi":
            reason_hfa = "higher_spi_home_field_adjusted"

    away_raw = None if p_home_raw is None else clamp_probability(1.0 - p_home_raw)
    away_adj = None if p_home_adj is None else clamp_probability(1.0 - p_home_adj)

    return {
        "predicted_winner_pure": predicted_pure,
        "predicted_winner_home_adj": predicted_hfa,
        "home_spi": home_spi,
        "away_spi": away_spi,
        "prediction_reason_pure": reason_pure,
        "prediction_reason_home_adj": reason_hfa,
        "home_win_prob_pure": p_home_raw,
        "away_win_prob_pure": away_raw,
        "home_win_prob_home_adj": p_home_adj,
        "away_win_prob_home_adj": away_adj,
        "home_field_x": float(home_field_x),
        "neutral_site": bool(is_neutral_site),
    }


def actual_winner(game: dict) -> Optional[str]:
    home_points = get_game_field(game, "home_points", "homePoints")
    away_points = get_game_field(game, "away_points", "awayPoints")
    home_team = get_game_field(game, "home_team", "homeTeam")
    away_team = get_game_field(game, "away_team", "awayTeam")

    if home_points is None or away_points is None:
        return None

    if float(home_points) > float(away_points):
        return home_team
    if float(away_points) > float(home_points):
        return away_team
    return None


def evaluate_years(
    start_year: int,
    end_year: int,
    data_exports_dir: str,
    min_ranking_teams: int,
    home_field_x: float,
    cache_only: bool,
) -> pd.DataFrame:
    cache_dir = os.path.join(data_exports_dir, "cache")
    games_api = None if cache_only else init_games_api()
    api_disabled = cache_only
    records: List[dict] = []

    for year in range(start_year, end_year + 1):
        for season_type in ("regular", "postseason"):
            weeks = list_available_weeks(data_exports_dir, year, season_type)
            if not weeks:
                continue

            for week in weeks:
                ranking_source = previous_week_ranking_source(
                    data_exports_dir=data_exports_dir,
                    year=year,
                    season_type=season_type,
                    week=week,
                )

                try:
                    selected_ranking_file, ranked_team_count = choose_full_rankings_file(
                        ranking_source.file_path,
                        min_ranking_teams=min_ranking_teams,
                    )
                except (FileNotFoundError, ValueError) as exc:
                    print(f"Skipping {year} {season_type} week {week}: {exc}")
                    continue

                if selected_ranking_file != ranking_source.file_path:
                    print(
                        f"Using fallback ranking file for {year} {season_type} week {week}: "
                        f"{selected_ranking_file} ({ranked_team_count} teams)"
                    )

                ranking_map = load_rankings_map(selected_ranking_file)

                games = load_games_from_cache(cache_dir, year, week, season_type)
                if games is None and games_api is not None and not api_disabled:
                    try:
                        games = fetch_games_from_api(games_api, year, week, season_type)
                        save_games_to_cache(cache_dir, year, week, season_type, games)
                    except ApiException as exc:
                        print(f"Failed to fetch games for {year} {season_type} week {week}: {exc}")
                        if should_disable_api_after_error(exc):
                            api_disabled = True
                            print(
                                "Disabling further API requests for this run due to auth/rate-limit error. "
                                "Use --cache-only to force local cache mode."
                            )
                        games = None

                if games is None:
                    print(f"Skipping {year} {season_type} week {week}: no cache and no API access")
                    continue

                for game in games:
                    home_team = get_game_field(game, "home_team", "homeTeam")
                    away_team = get_game_field(game, "away_team", "awayTeam")
                    if not home_team or not away_team:
                        continue

                    home_conf = get_game_field(game, "home_conference", "homeConference")
                    away_conf = get_game_field(game, "away_conference", "awayConference")
                    conference_game = get_game_field(game, "conference_game", "conferenceGame")

                    home_fbs = is_fbs_game_side(game, "home", ranking_map)
                    away_fbs = is_fbs_game_side(game, "away", ranking_map)
                    if not (home_fbs or away_fbs):
                        continue

                    notes = get_game_field(game, "notes", "notes")
                    is_playoff, is_nat_champ = classify_postseason_game(notes)
                    variant = predict_winner_variants(
                        game,
                        ranking_map,
                        home_field_x=home_field_x,
                    )

                    actual = actual_winner(game)

                    predicted_pure = variant["predicted_winner_pure"]
                    predicted_hfa = variant["predicted_winner_home_adj"]
                    correct_pure = None
                    if predicted_pure is not None and actual is not None:
                        correct_pure = int(predicted_pure == actual)

                    correct_home_adj = None
                    if predicted_hfa is not None and actual is not None:
                        correct_home_adj = int(predicted_hfa == actual)

                    records.append(
                        {
                            "year": year,
                            "season_type": season_type,
                            "week": int(week),
                            "game_id": get_game_field(game, "id", "id"),
                            "start_date": get_game_field(game, "start_date", "startDate"),
                            "home_team": home_team,
                            "away_team": away_team,
                            "home_conference": home_conf,
                            "away_conference": away_conf,
                            "conference_game": bool(conference_game)
                            if conference_game is not None
                            else False,
                            "home_points": get_game_field(game, "home_points", "homePoints"),
                            "away_points": get_game_field(game, "away_points", "awayPoints"),
                            "home_classification": get_game_field(
                                game, "home_classification", "homeClassification"
                            ),
                            "away_classification": get_game_field(
                                game, "away_classification", "awayClassification"
                            ),
                            "predicted_winner": predicted_hfa,
                            "predicted_winner_pure": predicted_pure,
                            "predicted_winner_home_adj": predicted_hfa,
                            "actual_winner": actual,
                            "correct": correct_home_adj,
                            "correct_pure": correct_pure,
                            "correct_home_adj": correct_home_adj,
                            "prediction_reason": variant["prediction_reason_home_adj"],
                            "prediction_reason_pure": variant["prediction_reason_pure"],
                            "prediction_reason_home_adj": variant["prediction_reason_home_adj"],
                            "home_spi_used": variant["home_spi"],
                            "away_spi_used": variant["away_spi"],
                            "home_win_prob_pure_pct": None
                            if variant["home_win_prob_pure"] is None
                            else round(100.0 * float(variant["home_win_prob_pure"]), 3),
                            "away_win_prob_pure_pct": None
                            if variant["away_win_prob_pure"] is None
                            else round(100.0 * float(variant["away_win_prob_pure"]), 3),
                            "home_win_prob_home_adj_pct": None
                            if variant["home_win_prob_home_adj"] is None
                            else round(100.0 * float(variant["home_win_prob_home_adj"]), 3),
                            "away_win_prob_home_adj_pct": None
                            if variant["away_win_prob_home_adj"] is None
                            else round(100.0 * float(variant["away_win_prob_home_adj"]), 3),
                            "home_field_x": variant["home_field_x"],
                            "ranking_source": ranking_source.descriptor,
                            "ranking_source_file": os.path.basename(selected_ranking_file),
                            "ranking_source_team_count": ranked_team_count,
                            "notes": notes,
                            "is_playoff": bool(is_playoff),
                            "is_national_championship": bool(is_nat_champ),
                            "conference_matchup": " vs ".join(
                                sorted(
                                    [
                                        str(home_conf or "Unknown"),
                                        str(away_conf or "Unknown"),
                                    ]
                                )
                            ),
                        }
                    )

    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records)


def summarize_accuracy(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    scored = df[df["correct"].notna()].copy()

    def agg_accuracy(frame: pd.DataFrame, name: str) -> dict:
        games = len(frame)
        correct = int(frame["correct"].sum()) if games > 0 else 0
        acc = float(correct / games) if games > 0 else float("nan")
        return {"metric": name, "games": games, "correct": correct, "accuracy": acc}

    overall_rows = [agg_accuracy(scored, "overall")]
    overall_rows.append(agg_accuracy(scored[scored["season_type"] == "regular"], "regular"))
    overall_rows.append(agg_accuracy(scored[scored["season_type"] == "postseason"], "postseason"))
    overall_rows.append(agg_accuracy(scored[scored["is_playoff"]], "playoff"))
    overall_rows.append(
        agg_accuracy(scored[scored["is_national_championship"]], "national_championship")
    )
    overall_summary = pd.DataFrame(overall_rows)

    by_year = (
        scored.groupby("year", as_index=False)
        .agg(games=("correct", "count"), correct=("correct", "sum"))
        .sort_values("year")
    )
    by_year["accuracy"] = by_year["correct"] / by_year["games"]

    by_year_regular = (
        scored[scored["season_type"] == "regular"]
        .groupby("year", as_index=False)
        .agg(games=("correct", "count"), correct=("correct", "sum"))
        .sort_values("year")
    )
    by_year_regular["accuracy"] = by_year_regular["correct"] / by_year_regular["games"]

    by_year_post = (
        scored[scored["season_type"] == "postseason"]
        .groupby("year", as_index=False)
        .agg(games=("correct", "count"), correct=("correct", "sum"))
        .sort_values("year")
    )
    by_year_post["accuracy"] = by_year_post["correct"] / by_year_post["games"]

    by_year_playoff = (
        scored[scored["is_playoff"]]
        .groupby("year", as_index=False)
        .agg(games=("correct", "count"), correct=("correct", "sum"))
        .sort_values("year")
    )
    if not by_year_playoff.empty:
        by_year_playoff["accuracy"] = by_year_playoff["correct"] / by_year_playoff["games"]

    by_year_week = (
        scored.groupby(["year", "season_type", "week"], as_index=False)
        .agg(games=("correct", "count"), correct=("correct", "sum"))
        .sort_values(["year", "season_type", "week"])
    )
    by_year_week["accuracy"] = by_year_week["correct"] / by_year_week["games"]

    by_week_all_years = (
        scored.groupby(["season_type", "week"], as_index=False)
        .agg(games=("correct", "count"), correct=("correct", "sum"))
        .sort_values(["season_type", "week"])
    )
    by_week_all_years["accuracy"] = by_week_all_years["correct"] / by_week_all_years["games"]

    return {
        "overall_summary": overall_summary,
        "accuracy_by_year": by_year,
        "accuracy_by_year_regular": by_year_regular,
        "accuracy_by_year_postseason": by_year_post,
        "accuracy_by_year_playoff": by_year_playoff,
        "accuracy_by_year_week": by_year_week,
        "accuracy_by_week_all_years": by_week_all_years,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Predict historical game winners from prior-week SPI rankings and summarize accuracy."
    )
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--data-exports-dir", type=str, default="data_exports")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join("data_exports", "predictions"),
    )
    parser.add_argument(
        "--min-ranking-teams",
        type=int,
        default=80,
        help="Minimum number of ranked teams required in source SPI file.",
    )
    parser.add_argument(
        "--home-field-x",
        type=float,
        default=HOME_FIELD_X_ALL_GAMES,
        help="Home-field strength X around a 50/50 game; converted to a log-odds shift.",
    )
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Use cached games only; do not call CFBD API.",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    df = evaluate_years(
        start_year=args.start_year,
        end_year=args.end_year,
        data_exports_dir=args.data_exports_dir,
        min_ranking_teams=args.min_ranking_teams,
        home_field_x=args.home_field_x,
        cache_only=args.cache_only,
    )

    if df.empty:
        print("No prediction rows were produced. Check ranking files and game caches.")
        return

    raw_file = os.path.join(
        args.output_dir,
        f"spi_game_predictions_{args.start_year}_{args.end_year}.csv",
    )
    df.to_csv(raw_file, index=False)
    print(f"Saved raw per-game predictions: {raw_file}")

    summaries = summarize_accuracy(df)
    for name, summary_df in summaries.items():
        out_path = os.path.join(
            args.output_dir,
            f"{name}_{args.start_year}_{args.end_year}.csv",
        )
        summary_df.to_csv(out_path, index=False)
        print(f"Saved {name}: {out_path}")

    print("\nTop-level accuracy summary:")
    print(summaries["overall_summary"].to_string(index=False))


if __name__ == "__main__":
    main()
