import os
import sys
import argparse
import json
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats as statz
from operator import itemgetter, attrgetter
from datetime import datetime
from types import SimpleNamespace
import cfbd
from cfbd.rest import ApiException
import pickle

# Runtime context (set in __main__)
todays_datetime = datetime.today()
today_year = todays_datetime.year
RUN_WEEK = None
RUN_MODE = "regular"
RUN_SEASON_TYPE = "regular"
TEAM_STATS_CACHE = {}
REGULAR_WEEK_MAX = 16


def default_rankings_year(date_ref: datetime) -> int:
    this_year = date_ref.year
    sept1 = datetime(this_year, 9, 1)
    return this_year - 1 if date_ref < sept1 else this_year


def week_for_year(year: int):
    if RUN_WEEK is not None and int(year) == int(today_year):
        return RUN_WEEK
    return None


def cache_dir() -> str:
    path = os.path.join("data_exports", "cache")
    os.makedirs(path, exist_ok=True)
    return path


def weekly_games_cache_file(year: int, week: int, season_type: str = "regular") -> str:
    season_type = (season_type or "regular").lower()
    if season_type == "regular":
        return os.path.join(cache_dir(), f"games_{year}_w{week}.json")
    return os.path.join(cache_dir(), f"games_{year}_{season_type}_w{week}.json")


def team_stats_cache_file(year: int) -> str:
    return os.path.join(cache_dir(), f"team_stats_{year}.csv")


def _to_plain_data(obj):
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, list):
        return [_to_plain_data(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_plain_data(v) for k, v in obj.items()}
    if hasattr(obj, "to_dict"):
        return _to_plain_data(obj.to_dict())
    if hasattr(obj, "__dict__"):
        return {
            k: _to_plain_data(v)
            for k, v in obj.__dict__.items()
            if not str(k).startswith("_")
        }
    return str(obj)


def _game_from_plain_record(record: dict):
    # Cached API payloads are camelCase; ranking logic expects snake_case attrs.
    normalized = {}
    for key, value in record.items():
        normalized[key] = value
        snake_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key)).lower()
        normalized[snake_key] = value

    return SimpleNamespace(**normalized)


def save_weekly_games_cache(year: int, week: int, games, season_type: str = "regular"):
    records = [_to_plain_data(g) for g in games]
    file_path = weekly_games_cache_file(year, week, season_type=season_type)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(records, f)
    print(f"Saved weekly games cache: {file_path} ({len(records)} games)")


def load_weekly_games_cache(year: int, week: int, season_type: str = "regular"):
    candidate_files = [weekly_games_cache_file(year, week, season_type=season_type)]

    # Backward compatibility for older regular-season cache naming.
    if (season_type or "regular").lower() == "regular":
        legacy_file = os.path.join(cache_dir(), f"games_{year}_regular_w{week}.json")
        candidate_files.append(legacy_file)

    for file_path in candidate_files:
        if not os.path.exists(file_path):
            continue
        with open(file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        print(f"Loaded weekly games cache: {file_path} ({len(records)} games)")
        return [_game_from_plain_record(rec) for rec in records]

    return None


def fetch_weekly_games(year: int, week: int, season_type: str = "regular"):
    cached = load_weekly_games_cache(year, week, season_type=season_type)
    if cached is not None:
        return cached

    games = games_api.get_games(year=year, season_type=season_type, week=week)
    save_weekly_games_cache(year, week, games, season_type=season_type)
    return games


def _filter_games_by_params(games, params: dict):
    team = params.get("team")
    conference = params.get("conference")

    team_norm = str(team).strip().lower() if team else None
    conf_norm = str(conference).strip().lower() if conference else None

    filtered = []
    for game in games:
        if team_norm:
            home_team = str(getattr(game, "home_team", "")).strip().lower()
            away_team = str(getattr(game, "away_team", "")).strip().lower()
            if team_norm not in (home_team, away_team):
                continue

        if conf_norm:
            home_conf = str(getattr(game, "home_conference", "")).strip().lower()
            away_conf = str(getattr(game, "away_conference", "")).strip().lower()
            if conf_norm not in (home_conf, away_conf):
                continue

        filtered.append(game)

    return filtered


def get_cumulative_games_with_cache(
    year: int, through_week: int, params: dict, season_type: str = "regular"
):
    all_games = []
    for week in range(1, through_week + 1):
        weekly_games = fetch_weekly_games(
            year=year,
            week=week,
            season_type=season_type,
        )
        all_games.extend(weekly_games)

    return _filter_games_by_params(all_games, params)


def load_team_stats_year_cache(year: int):
    if year in TEAM_STATS_CACHE:
        return TEAM_STATS_CACHE[year]

    file_path = team_stats_cache_file(year)
    year_cache = {}
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path)
        except pd.errors.EmptyDataError:
            df = pd.DataFrame(columns=["team", "stat_name", "stat_value"])
        for _, row in df.iterrows():
            team = str(row.get("team", "")).strip()
            if not team:
                continue
            stat_name = str(row.get("stat_name", "")).strip()
            stat_value = row.get("stat_value", 0.0)
            if team not in year_cache:
                year_cache[team] = {}
            year_cache[team][stat_name] = float(stat_value)
        print(f"Loaded team stats cache: {file_path}")

    TEAM_STATS_CACHE[year] = year_cache
    return year_cache


def save_team_stats_year_cache(year: int):
    year_cache = TEAM_STATS_CACHE.get(year, {})
    rows = []
    for team, stats in year_cache.items():
        for stat_name, stat_value in stats.items():
            rows.append(
                {
                    "team": team,
                    "stat_name": stat_name,
                    "stat_value": stat_value,
                }
            )

    file_path = team_stats_cache_file(year)
    if rows:
        pd.DataFrame(rows).to_csv(file_path, index=False)
    else:
        pd.DataFrame(columns=["team", "stat_name", "stat_value"]).to_csv(
            file_path, index=False
        )
    print(f"Saved team stats cache: {file_path}")


def get_team_stats_with_cache(year: int, team: str):
    year_cache = load_team_stats_year_cache(year)
    if team in year_cache:
        return year_cache[team]

    team_stats = stats_api.get_team_stats(year=year, team=team)
    stats = {}
    if team_stats and len(team_stats) > 0:
        stats = {
            tm_st.stat_name: tm_st.stat_value.actual_instance
            for tm_st in team_stats
        }

    year_cache[team] = stats
    TEAM_STATS_CACHE[year] = year_cache
    save_team_stats_year_cache(year)
    return stats


def get_games_with_context(year: int, **kwargs):
    params = {"year": year, **kwargs}
    asof_week = week_for_year(year)
    requested_season_type = params.get("season_type")

    if asof_week is not None:
        if requested_season_type is None:
            params["season_type"] = RUN_SEASON_TYPE
        params.pop("week", None)

    if asof_week is not None:
        # As-of regular mode: cumulative regular-season weeks only.
        if RUN_SEASON_TYPE == "regular":
            if requested_season_type in (None, "regular"):
                return get_cumulative_games_with_cache(
                    year=year,
                    through_week=int(asof_week),
                    params=params,
                    season_type="regular",
                )
            if requested_season_type == "postseason":
                return []

        # As-of postseason mode: full regular season + cumulative postseason week N.
        if RUN_SEASON_TYPE == "postseason":
            if requested_season_type in (None, "postseason"):
                post_games = get_cumulative_games_with_cache(
                    year=year,
                    through_week=int(asof_week),
                    params=params,
                    season_type="postseason",
                )

                if requested_season_type == "postseason":
                    return post_games

                regular_games = get_cumulative_games_with_cache(
                    year=year,
                    through_week=REGULAR_WEEK_MAX,
                    params=params,
                    season_type="regular",
                )
                return regular_games + post_games

            if requested_season_type == "regular":
                return get_cumulative_games_with_cache(
                    year=year,
                    through_week=REGULAR_WEEK_MAX,
                    params=params,
                    season_type="regular",
                )

    games = games_api.get_games(**params)

    if asof_week is None:
        return games

    effective_season_type = params.get("season_type")
    if effective_season_type == "postseason":
        return []

    filtered_games = []
    for game in games:
        game_week = getattr(game, "week", None)
        if game_week is not None and int(game_week) <= int(asof_week):
            filtered_games.append(game)
    return filtered_games


def output_label(year: int) -> str:
    if RUN_WEEK is not None and int(year) == int(today_year):
        if RUN_SEASON_TYPE == "postseason":
            return f"{year}_post_w{RUN_WEEK}"
        return f"{year}_w{RUN_WEEK}"
    return str(year)


def conference_cache_file(year: int) -> str:
    return os.path.join(
        "data_exports", f"conference_rankings_cache_{output_label(year)}.csv"
    )


def save_conference_rankings_cache(year: int, conf_objects: dict, mean_games_played: float):
    rows = []
    for conf_name, conf_obj in conf_objects.items():
        rows.append(
            {
                "name": conf_name,
                "p5": bool(conf_obj.p5) if conf_obj.p5 is not None else False,
                "cvc_wins": float(conf_obj.cvc_wins),
                "cvc_losses": float(conf_obj.cvc_losses),
                "cvc_perc": float(conf_obj.cvc_perc) if conf_obj.cvc_perc is not None else 0.0,
                "mean_games_played": float(mean_games_played),
            }
        )

    if not rows:
        return

    cache_file = conference_cache_file(year)
    pd.DataFrame(rows).to_csv(cache_file, index=False)
    print(f"Loaded/saved cache support: wrote conference cache to {cache_file}")


def load_conference_rankings_cache(year: int):
    cache_file = conference_cache_file(year)
    if not os.path.exists(cache_file):
        return None

    df = pd.read_csv(cache_file)
    if df.empty:
        return None

    conf_objects = {}
    for _, row in df.iterrows():
        conf_name = str(row.get("name", "")).strip()
        if not conf_name:
            continue

        conf_obj = My_Conf(
            name=conf_name,
            p5=bool(row.get("p5", False)),
            cvc_wins=float(row.get("cvc_wins", 0.0)),
            cvc_losses=float(row.get("cvc_losses", 0.0)),
            cvc_perc=float(row.get("cvc_perc", 0.0)),
        )
        conf_objects[conf_name] = conf_obj

    if not conf_objects:
        return None

    mean_games_played = float(df["mean_games_played"].iloc[0]) if "mean_games_played" in df.columns else 0.0
    print(f"Loaded conference cache from {cache_file}")
    return [conf_objects, mean_games_played]


def save_dual_spi_exports(spi_df: pd.DataFrame, base_year: int):
    """Save interchangeable final/preseason SPI files for adjacent seasons."""
    final_file = os.path.join("data_exports", f"spi_rankings_final_{base_year}.csv")
    preseason_file = os.path.join(
        "data_exports", f"spi_rankings_preseason_{base_year + 1}.csv"
    )
    spi_df.to_csv(final_file, index=False)
    spi_df.to_csv(preseason_file, index=False)
    print(f"Saved final SPI alias to {final_file}")
    print(f"Saved preseason SPI alias to {preseason_file}")


def save_dual_spi_detailed_exports(detailed_df: pd.DataFrame, base_year: int):
    """Save interchangeable detailed SPI files for adjacent seasons."""
    final_file = os.path.join(
        "data_exports", f"spi_rankings_detailed_final_{base_year}.csv"
    )
    preseason_file = os.path.join(
        "data_exports", f"spi_rankings_detailed_preseason_{base_year + 1}.csv"
    )
    detailed_df.to_csv(final_file, sep=",")
    detailed_df.to_csv(preseason_file, sep=",")
    print(f"Saved detailed final SPI alias to {final_file}")
    print(f"Saved detailed preseason SPI alias to {preseason_file}")


def run_preseason_mode(preseason_year: int):
    """Create preseason rankings from the previous year's final rankings."""
    prior_year = preseason_year - 1
    source_candidates = [
        os.path.join("data_exports", f"spi_rankings_final_{prior_year}.csv"),
        os.path.join("data_exports", f"spi_rankings_{prior_year}.csv"),
    ]

    source_file = next((p for p in source_candidates if os.path.exists(p)), None)
    if source_file is None:
        raise SystemExit(
            f"Could not find prior-year SPI file for {prior_year}. "
            f"Expected one of: {source_candidates}"
        )

    spi_df = pd.read_csv(source_file)

    final_file = os.path.join("data_exports", f"spi_rankings_final_{prior_year}.csv")
    preseason_file = os.path.join(
        "data_exports", f"spi_rankings_preseason_{preseason_year}.csv"
    )
    spi_df.to_csv(final_file, index=False)
    spi_df.to_csv(preseason_file, index=False)

    print(f"Loaded prior final rankings from {source_file}")
    print(f"Saved final SPI file to {final_file}")
    print(f"Saved preseason SPI file to {preseason_file}")

# Create a data directory if it doesn't exist
os.makedirs("data_exports", exist_ok=True)


# Add these functions to save/load data at key points
def save_to_csv(data, filename, index=True):
    """Save data to CSV file in the data_exports directory"""
    filepath = os.path.join("data_exports", filename)
    if isinstance(data, list) and all(hasattr(item, "__dict__") for item in data):
        # Convert list of objects to DataFrame
        df = pd.DataFrame([item.__dict__ for item in data])
        df.to_csv(filepath, index=index)
        print(f"Saved {len(data)} records to {filepath}")
    elif isinstance(data, dict):
        # Convert dictionary to DataFrame
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=index)
        print(f"Saved dictionary with {len(data)} keys to {filepath}")
    else:
        print(f"Could not save {filename} - unsupported data type")


def load_from_csv(filename, class_type=None):
    """Load data from CSV file in the data_exports directory"""
    filepath = os.path.join("data_exports", filename)
    if os.path.exists(filepath):
        df = pd.read_csv(filepath)
        if class_type:
            # Convert DataFrame back to list of objects
            objects = []
            for _, row in df.iterrows():
                obj = class_type(**{k: v for k, v in row.items() if k != "Unnamed: 0"})
                objects.append(obj)
            return objects
        return df
    return None


def save_conference_champions(champions, year):
    """Save conference champions to CSV"""
    if champions:
        df = pd.DataFrame(list(champions.items()), columns=["Conference", "Champion"])
        filename = f"conference_champions_{year}.csv"
        filepath = os.path.join("data_exports", filename)
        df.to_csv(filepath, index=False)
        print(f"Saved conference champions to {filepath}")


def load_conference_champions(year):
    """Load conference champions from CSV"""
    filename = f"conference_champions_{year}.csv"
    filepath = os.path.join("data_exports", filename)
    if os.path.exists(filepath):
        df = pd.read_csv(filepath)
        return dict(zip(df["Conference"], df["Champion"]))
    return None


# ------------------------------------------------------------------------------
#   CONFIGURATION
# ------------------------------------------------------------------------------

# API setup
# Configure API key
configuration = cfbd.Configuration(
    host="https://api.collegefootballdata.com",
    access_token=os.getenv("CFBD_API_KEY"),
)

# Initialize API clients
teams_api = cfbd.TeamsApi(cfbd.ApiClient(configuration))
games_api = cfbd.GamesApi(cfbd.ApiClient(configuration))
stats_api = cfbd.StatsApi(cfbd.ApiClient(configuration))
rankings_api = cfbd.RankingsApi(cfbd.ApiClient(configuration))
conferences_api = cfbd.ConferencesApi(cfbd.ApiClient(configuration))

# Conference conversion dictionary
conf_conversion = {
    "american": ["american"],
    "acc": ["acc"],
    "big 12": ["big 12", "big-12"],
    "big east": ["big east", "big-east"],
    "big west": ["big west", "big-west"],
    "big ten": ["big ten", "big-ten"],
    "conference usa": ["conference usa", "cusa"],
    "independent": ["independent", "ind"],
    "mac": ["mac"],
    "mountain west": ["mountain west", "mwc"],
    "pac 10": ["pac 10", "pac-10"],
    "pac 12": ["pac 12", "pac-12"],
    "sec": ["sec"],
    "sun belt": ["sun belt", "sun-belt"],
    "wac": ["wac"],
}

# ------------------------------------------------------------------------------
#   UTILITY FUNCTIONS
# ------------------------------------------------------------------------------


def dashes():
    print("-" * 120)


def skips():
    print("\n" * 5)


def spaced(mystring):
    print(" " * 10, mystring, "\n")


def break_rank():
    print(" " * 10, "-" * 60)


def miami():
    print(" " * 10, "*" * 60)


def update_progress(progress):
    barLength = 50
    status = ""
    if isinstance(progress, int):
        progress = float(progress)
    if not isinstance(progress, float):
        progress = 0
        status = "error: progress var must be float\r\n"
    if progress < 0:
        progress = 0
        status = "Halt...\r\n"
    if progress >= 1:
        progress = 1
        status = "Done...\r\n"
    block = int(round(barLength * progress))
    text = "\rPercent: [{0}] {1}% {2}".format(
        "#" * block + "-" * (barLength - block), round(progress * 100, 1), status
    )
    sys.stdout.write(text)
    sys.stdout.flush()


def team_stat(stat):
    if stat is None or np.isnan(stat):
        return 0.0
    return float(stat)


def ave_margin(G, P, PA):
    return (P - PA) / G if G > 0 else 0.0


def multisort(xs, specs):
    for key, reverse in reversed(specs):
        xs.sort(key=attrgetter(key), reverse=reverse)
    return xs


def SOR_calc(wins, losses):
    v_sum = sum(wins)
    d_sum = sum([(Cc - 1.0) for Cc in losses])
    return v_sum + d_sum


def Nature(A, TD, P, TDA, PA, TM, G, FIRST_DOWNS, OPP_FIRST_DOWNS):
    if G == 0.0:
        return A
    elif P == 0.0:
        if PA != 0.0:
            return A + (50.0 * (0.0 - ((TDA * 7.0) / PA)) + TM / G)
        else:
            return A + TM / G
    elif PA == 0.0:
        if P != 0:
            return A + (50.0 * ((TD * 7.0) / P) + TM / G)
    else:
        return A + (50.0 * (((TD * 7.0) / P) - ((TDA * 7.0) / PA)) + TM / G)


def SPI_calc(SOR, N_adj):
    return 100.0 * (0.65 * SOR + 0.35 * N_adj)


def safe_minmax_scale(values, default_value=0.0):
    """Scale numeric values to [0, 1] robustly even when all values are equal."""
    arr = np.asarray(values, dtype=float)
    finite_mask = np.isfinite(arr)
    if not finite_mask.any():
        return np.full_like(arr, float(default_value), dtype=float)

    finite_vals = arr[finite_mask]
    vmin = float(np.min(finite_vals))
    vmax = float(np.max(finite_vals))

    scaled = np.full_like(arr, float(default_value), dtype=float)
    if np.isclose(vmax, vmin):
        return scaled

    scaled[finite_mask] = (arr[finite_mask] - vmin) / (vmax - vmin)
    return scaled


# ------------------------------------------------------------------------------
#   CLASSES
# ------------------------------------------------------------------------------


class My_Conf:
    def __init__(
        self,
        name,
        p5=None,
        cvc_wins=0.0,
        cvc_losses=0.0,
        conf_index=None,
        cvc_perc=None,
    ):
        self.name = name
        self.p5 = p5
        self.cvc_wins = cvc_wins
        self.cvc_losses = cvc_losses
        self.cvc_perc = cvc_perc
        self.conf_index = conf_index


class My_Team:
    def __init__(
        self,
        name,
        wins=None,
        losses=None,
        conf_wins=None,
        conf_losses=None,
        conf_name=None,
        conf_champ=None,
        ave_margin=None,
        points=None,
        standing_index=None,
        conf_index=None,
        overall_index=None,
        N_adj=None,
        SOR_adj=None,
        N_raw=None,
        SOR_raw=None,
        SPI=None,
        cross_conf_value=None,
    ):
        self.name = name
        self.conf_name = conf_name
        self.wins = wins
        self.losses = losses
        self.conf_wins = conf_wins
        self.conf_losses = conf_losses
        self.conf_champ = conf_champ
        self.ave_margin = ave_margin
        self.points = points
        self.standing_index = standing_index
        self.conf_index = conf_index
        self.overall_index = overall_index
        self.N_adj = N_adj
        self.N_raw = N_raw
        self.SOR_adj = SOR_adj
        self.SOR_raw = SOR_raw
        self.SPI = SPI
        self.cross_conf_value = cross_conf_value  # Added for cross-conference standings


# ------------------------------------------------------------------------------
#   CORE FUNCTIONS
# ------------------------------------------------------------------------------


def get_team_record(team_name, year):
    """Get a team's overall record for a given year"""
    try:
        games = get_games_with_context(year=year, team=team_name)
        wins = 0
        losses = 0

        for game in games:
            if game.home_points is not None and game.away_points is not None:
                if game.home_team == team_name:
                    if game.home_points > game.away_points:
                        wins += 1
                    else:
                        losses += 1
                else:
                    if game.away_points > game.home_points:
                        wins += 1
                    else:
                        losses += 1

        return wins, losses
    except ApiException:
        return 0, 0


def get_team_conference_record(team_name, conference, year):
    """Get a team's conference record for a given year"""
    try:
        games = get_games_with_context(year=year, team=team_name)
        conf_wins = 0
        conf_losses = 0

        for game in games:
            if game.home_points is not None and game.away_points is not None:
                # Check if this is a conference game
                is_conf_game = False

                if game.home_team == team_name:
                    if (
                        game.away_conference
                        and game.away_conference.lower() == conference
                    ):
                        is_conf_game = True
                        if game.home_points > game.away_points:
                            conf_wins += 1
                        else:
                            conf_losses += 1
                else:
                    if (
                        game.home_conference
                        and game.home_conference.lower() == conference
                    ):
                        is_conf_game = True
                        if game.away_points > game.home_points:
                            conf_wins += 1
                        else:
                            conf_losses += 1

        return conf_wins, conf_losses
    except ApiException:
        return 0, 0


def get_conference_champions(year):
    """Get conference champions for a given year"""
    try:
        champions = {}
        conferences = [
            conf.name.lower()
            for conf in conferences_api.get_conferences()
            if conf.classification == "fbs"
        ]

        # First try to get conference champions from the games API
        try:
            # Get postseason games (conference championships)
            postseason_games = get_games_with_context(
                year=year, season_type="postseason"
            )

            # Filter for conference championship games
            for game in postseason_games:
                if game.notes and "championship" in game.notes.lower():
                    conf_name = None
                    # Extract conference name from notes
                    for conf in conferences:
                        if conf.lower() in game.notes.lower():
                            conf_name = conf.lower()
                            break

                    if conf_name:
                        # Determine winner
                        if game.home_points > game.away_points:
                            champions[conf_name] = game.home_team
                        else:
                            champions[conf_name] = game.away_team
        except ApiException:
            pass

        # If we couldn't get all champions from championship games, try standings
        if len(champions) < len(
            [
                c
                for c in conferences
                if c.lower() not in ["fbs independents", "independent"]
            ]
        ):
            for conf in conferences:
                if conf.lower() in champions:
                    continue

                if conf.lower() in ["fbs independents", "independent"]:
                    continue

                try:
                    # Get regular season conference games
                    conf_games = get_games_with_context(year=year, conference=conf)

                    # Build standings from games
                    teams = {}
                    for game in conf_games:
                        if (
                            game.home_conference == conf
                            and game.away_conference == conf
                        ):
                            # This is a conference game
                            if (
                                game.home_points is not None
                                and game.away_points is not None
                            ):
                                # Home team
                                if game.home_team not in teams:
                                    teams[game.home_team] = {"wins": 0, "losses": 0}
                                # Away team
                                if game.away_team not in teams:
                                    teams[game.away_team] = {"wins": 0, "losses": 0}

                                # Update records
                                if game.home_points > game.away_points:
                                    teams[game.home_team]["wins"] += 1
                                    teams[game.away_team]["losses"] += 1
                                else:
                                    teams[game.away_team]["wins"] += 1
                                    teams[game.home_team]["losses"] += 1

                    # Find team with best conference record
                    if teams:
                        best_team = max(
                            teams.items(),
                            key=lambda x: (
                                x[1]["wins"] / (x[1]["wins"] + x[1]["losses"])
                                if (x[1]["wins"] + x[1]["losses"]) > 0
                                else 0,
                                x[1]["wins"],
                            ),
                        )
                        champions[conf.lower()] = best_team[0]
                except ApiException:
                    continue

        return champions
    except ApiException:
        return {}


def conference_rankings(year):
    """Compute conference rankings for a given year"""
    cached = load_conference_rankings_cache(year)
    if cached is not None:
        return cached

    conf_objects = {}
    games_played = []

    try:
        teams = teams_api.get_fbs_teams(year)

        power5 = ["acc", "big ten", "big 12", "pac 12", "sec"]
        if int(year) < 2005:
            power5 = ["acc", "big ten", "big 12", "pac 10", "sec", "big east"]

        print(f"\n-->considering conferences in {year}")

        for i_it, team in enumerate(teams):
            conference = team.conference.lower()
            if conference in power5:
                is_p5 = True
            else:
                is_p5 = False

            if conference not in conf_objects:
                this_conf = My_Conf(name=conference, p5=is_p5)
                conf_objects.update({conference: this_conf})

            # Get team records directly from games
            wins, losses = get_team_record(team.school, year)
            conf_wins, conf_losses = get_team_conference_record(
                team.school, conference, year
            )

            games_played.append(float(wins + losses))

            OOC_W = wins - conf_wins
            OOC_L = losses - conf_losses

            conf_objects[conference].cvc_wins += OOC_W
            conf_objects[conference].cvc_losses += OOC_L

            if (OOC_W + OOC_L) > 0:
                OOC_perc = float(OOC_W) / float(OOC_W + OOC_L)
            else:
                OOC_perc = 0.0

            conf_objects[conference].cvc_perc = OOC_perc

            # Update progress bar
            progress = (i_it + 1) / len(teams)
            update_progress(progress)

        mean_games_played = np.mean(games_played) if games_played else 0
        save_conference_rankings_cache(
            year=year,
            conf_objects=conf_objects,
            mean_games_played=mean_games_played,
        )

        return [conf_objects, mean_games_played]

    except ApiException:
        return [{}, 0]


def total_conference_rankings():
    """Calculate total conference rankings combining previous and current year data"""
    combined_conf_objects = {}

    # First, establish conference stats for previous season
    last_year = conference_rankings(today_year - 1)
    LY_confs = last_year[0]

    this_year = conference_rankings(today_year)
    TY_confs = this_year[0]
    TY_games = this_year[1]

    LYW = (8.0 - TY_games) / 8.0  # Last Year's Weight
    if LYW < 0:
        LYW = 0.0
    TYW = 1.0 - LYW  # This Year's Weight

    # Account for last year's wins and losses with proper Last Year weights
    for conference in LY_confs:
        that_conf = LY_confs[conference]
        this_conf = My_Conf(
            name=conference,
            p5=that_conf.p5,
            cvc_wins=LYW * that_conf.cvc_wins,
            cvc_losses=LYW * that_conf.cvc_losses,
        )
        combined_conf_objects.update({conference: this_conf})

    # Add data for this year's wins and losses with proper This Year weights
    print(
        f"\nTeams have played an average of {round(TY_games,2)} this year, so last year is weighted by {round(LYW,2)}"
    )
    print("\n-->computing W/L stats between conferences...")

    for i_it, conference in enumerate(TY_confs):
        that_conf = TY_confs[conference]

        if conference not in combined_conf_objects:
            this_conf = My_Conf(
                name=conference,
                p5=that_conf.p5,
                cvc_wins=that_conf.cvc_wins,
                cvc_losses=that_conf.cvc_losses,
            )
            combined_conf_objects.update({conference: this_conf})
        else:
            this_conf = combined_conf_objects[conference]
            this_conf.cvc_wins += TYW * that_conf.cvc_wins
            this_conf.cvc_losses += TYW * that_conf.cvc_losses

        this_conf.cvc_perc = (
            this_conf.cvc_wins / (this_conf.cvc_wins + this_conf.cvc_losses)
            if (this_conf.cvc_wins + this_conf.cvc_losses) > 0
            else 0
        )
        this_conf.p5 = that_conf.p5
        if this_conf.p5 is None:
            this_conf.p5 = False

        # Update progress bar
        progress = (i_it + 1) / len(TY_confs)
        update_progress(progress)

    # Now, rank them
    myconfs = []
    [myconfs.append(combined_conf_objects[conference]) for conference in TY_confs]

    sorted_confs = multisort(
        myconfs,
        (("p5", True), ("cvc_perc", True), ("cvc_wins", True), ("cvc_losses", False)),
    )

    return sorted_confs


def calculate_cross_conference_standings(team_object_list, sorted_confs):
    """Calculate cross-conference standings based on conference strength and team standing"""

    # Create a dictionary to map conference names to their rankings
    conf_rankings = {}
    for i, conf in enumerate(sorted_confs):
        conf_rankings[conf.name] = i + 1

    # Calculate cross-conference value for each team
    for team in team_object_list:
        # Cross-conference value is a combination of:
        # 1. Conference strength (conf_index)
        # 2. Team standing within conference (standing_index)
        # 3. Overall record (win percentage)

        # Get win percentage
        total_games = team.wins + team.losses
        win_pct = team.wins / total_games if total_games > 0 else 0

        # Calculate cross-conference value
        # This uses the same formula as overall_index but adds win percentage as a factor
        if hasattr(team, "conf_index") and hasattr(team, "standing_index"):
            team.cross_conf_value = (
                (0.5 * team.conf_index) + (0.3 * team.standing_index) + (0.2 * win_pct)
            )
        else:
            team.cross_conf_value = 0.0

    # Sort teams by cross-conference value
    sorted_teams = sorted(
        team_object_list, key=attrgetter("cross_conf_value"), reverse=True
    )

    return sorted_teams


def display_and_save(SPI_final_rankings, conf_rankings):
    """Display rankings and save to CSV"""
    rankings_database = {}

    # Printing results for top 25
    print("%9s  %2s  %24s  %6s  %5s" % (" ", "Rk", "Team", "Record", "SPI"))
    break_rank()

    for i_it, tm_obj in enumerate(SPI_final_rankings):
        # Collecting data needed for basic rundown
        ranking = i_it + 1
        name = tm_obj.name
        SPI = tm_obj.SPI

        wins = int(tm_obj.wins)
        losses = int(tm_obj.losses)

        if name == "Miami (FL)":
            miami()

        # Print only top 25 to console, but keep collecting all teams for CSV.
        if ranking <= 25:
            print(
                "%9s  %2i  %24s  %2i -%2i  %5.2f"
                % (" ", ranking, name, wins, losses, SPI)
            )
            if ranking == 4:
                break_rank()
            if ranking == 25:
                break_rank()
                break_rank()

        if name == "Miami (FL)":
            miami()

        # Collecting the rest of the data
        conf_name = tm_obj.conf_name
        conf_wins = tm_obj.conf_wins
        conf_losses = tm_obj.conf_losses

        conf_ranking = 0
        for j_it, conf_obj in enumerate(conf_rankings):
            c_rk = j_it + 1
            if conf_obj.name == conf_name:
                conf_ranking = c_rk

        C_index = tm_obj.conf_index
        c_index = tm_obj.standing_index
        Cc = tm_obj.overall_index

        N_raw = tm_obj.N_raw
        N_adj = tm_obj.N_adj * 35.0

        SOR_raw = tm_obj.SOR_raw
        SOR_adj = tm_obj.SOR_adj * 65.0

        all_team_data = [
            name,
            wins,
            losses,
            conf_name,
            conf_ranking,
            conf_wins,
            conf_losses,
            C_index,
            c_index,
            Cc,
            N_raw,
            N_adj,
            SOR_raw,
            SOR_adj,
            SPI,
        ]

        rankings_database.update({ranking: all_team_data})

    skips()
    dashes()

    df_index = [
        "Team Name",
        "W",
        "L",
        "Conf.",
        "Conf. Rank",
        "Conf. W",
        "Conf. L",
        "C",
        "c",
        "Cc",
        "N_raw",
        "N_adj",
        "SOR_raw",
        "SOR_adj",
        "SPI",
    ]

    df_database = pd.DataFrame(rankings_database, index=df_index)
    df_database = df_database.transpose()
    spi_full_file = os.path.join(
        "data_exports", f"spi_rankings_detailed_{output_label(today_year)}.csv"
    )
    df_database.to_csv(spi_full_file, sep=",")
    print(f"Saved detailed SPI rankings to {spi_full_file}")
    return df_database


def display_cross_conference_standings(cross_conf_rankings):
    """Display cross-conference standings"""
    skips()
    dashes()
    spaced("CROSS-CONFERENCE STANDINGS:")
    print(
        "%9s  %2s  %24s  %15s  %6s  %10s"
        % (" ", "Rk", "Team", "Conference", "Record", "Value")
    )
    break_rank()

    # Save data for CSV export
    cross_conf_data = []

    for i, team in enumerate(cross_conf_rankings[:50]):  # Show top 50 teams
        ranking = i + 1
        name = team.name
        conf = team.conf_name
        wins = int(team.wins)
        losses = int(team.losses)
        value = team.cross_conf_value

        print(
            "%9s  %2i  %24s  %15s  %2i -%2i  %10.4f"
            % (" ", ranking, name, conf, wins, losses, value)
        )

        # Add to data for CSV
        cross_conf_data.append(
            {
                "Rank": ranking,
                "Team": name,
                "Conference": conf,
                "Wins": wins,
                "Losses": losses,
                "Cross_Conf_Value": value,
            }
        )

        if ranking == 25:
            break_rank()

    break_rank()

    # Save to CSV
    cross_conf_file = os.path.join(
        "data_exports", f"cross_conference_standings_{output_label(today_year)}.csv"
    )
    pd.DataFrame(cross_conf_data).to_csv(cross_conf_file, index=False)
    print(f"Saved cross-conference standings to {cross_conf_file}")


# ------------------------------------------------------------------------------
#   MAIN EXECUTION
# ------------------------------------------------------------------------------
def main():
    if RUN_MODE == "preseason":
        run_preseason_mode(preseason_year=today_year)
        return

    # Welcome message
    dashes()
    skips()
    spaced("Welcome to Dominic Sicilian's college football rankings!")
    spaced("The code will first examine the nature (N) of a team's games.")
    spaced(
        "Then, it will establish rankings for conferences, then consider a team's standing within its conference."
    )
    spaced("This will allow us to estimate a team's strength of record (SOR).")
    spaced("Combining N with SOR yields SPI: The Sicilian Power Index!")
    spaced("AND THAT'S HOW WE RANK 'EM!")
    spaced(f"Running for year={today_year} as-of week={RUN_WEEK if RUN_WEEK is not None else 'full season'}")
    skips()

    # Create data directory if it doesn't exist
    os.makedirs("data_exports", exist_ok=True)

    # Get conference champions from previous season directly from API or from saved file
    print("Getting last year's conference champs...")
    conf_champions_file = os.path.join(
        "data_exports", f"conference_champions_{today_year-1}.csv"
    )

    if os.path.exists(conf_champions_file):
        # Load from file if available
        champs_df = pd.read_csv(conf_champions_file)
        conf_champions = dict(zip(champs_df["Conference"], champs_df["Champion"]))
        print("Loaded conference champions from file.")
    else:
        # Otherwise get from API
        conf_champions = get_conference_champions(today_year - 1)
        # Save to file
        if conf_champions:
            champs_df = pd.DataFrame(
                list(conf_champions.items()), columns=["Conference", "Champion"]
            )
            champs_df.to_csv(conf_champions_file, index=False)
            print(f"Saved conference champions to {conf_champions_file}")

    print("Conference Champions:")
    for conf, champ in conf_champions.items():
        print(f"  {conf}: {champ}")

    # Step 1: Calculate Nature statistic
    N_raw_list = []
    team_objects = {}
    team_objects_by_name = {}
    team_object_list = []

    skips()
    dashes()
    spaced('COMPUTING "NATURE" STATISTIC...')

    try:
        teams = teams_api.get_fbs_teams(year=today_year)

        # Save teams data
        teams_file = os.path.join("data_exports", f"teams_{output_label(today_year)}.csv")
        teams_data = [
            {"id": t.id, "school": t.school, "conference": t.conference} for t in teams
        ]
        pd.DataFrame(teams_data).to_csv(teams_file, index=False)
        print(f"Saved {len(teams_data)} teams to {teams_file}")

        for i_it, team in enumerate(teams):
            # Set up name, abbreviation, conference
            team_fullname = team.school
            conference = team.conference.lower()

            if conference not in team_objects:
                team_objects.update({conference: []})

            # Get team stats
            try:
                if RUN_WEEK is None:
                    stats = get_team_stats_with_cache(year=today_year, team=team.school)
                else:
                    # Team stats endpoint is season-level in this script usage; avoid leakage past as-of week.
                    stats = {}
            except ApiException:
                stats = {}

            # Get games and calculate points and record
            try:
                games = get_games_with_context(year=today_year, team=team.school)
                # Count only completed games with both scores present.
                G = float(
                    len(
                        [
                            g
                            for g in games
                            if g.home_points is not None and g.away_points is not None
                        ]
                    )
                )

                # Calculate points scored and allowed directly from games
                P = 0.0
                PA = 0.0
                wins = 0
                losses = 0
                conf_wins = 0
                conf_losses = 0

                for game in games:
                    if game.home_points is not None and game.away_points is not None:
                        if game.home_team == team.school:
                            P += game.home_points
                            PA += game.away_points
                            if game.home_points > game.away_points:
                                wins += 1
                                if (
                                    game.away_conference
                                    and game.away_conference.lower() == conference
                                ):
                                    conf_wins += 1
                            else:
                                losses += 1
                                if (
                                    game.away_conference
                                    and game.away_conference.lower() == conference
                                ):
                                    conf_losses += 1
                        else:
                            P += game.away_points
                            PA += game.home_points
                            if game.away_points > game.home_points:
                                wins += 1
                                if (
                                    game.home_conference
                                    and game.home_conference.lower() == conference
                                ):
                                    conf_wins += 1
                            else:
                                losses += 1
                                if (
                                    game.home_conference
                                    and game.home_conference.lower() == conference
                                ):
                                    conf_losses += 1

            except ApiException:
                G = 0.0
                P = 0.0
                PA = 0.0
                wins = 0
                losses = 0
                conf_wins = 0
                conf_losses = 0

            # Calculate average margin
            A = ave_margin(G, P, PA)

            # Offensive touchdowns
            passTD = team_stat(stats.get("passingTDs", 0))
            rushTD = team_stat(stats.get("rushingTDs", 0))
            TD = passTD + rushTD

            # In as-of week mode we intentionally skip season-level team stats
            # to avoid leakage, so derive a points-based TD proxy.
            if RUN_WEEK is not None and TD == 0.0 and P > 0.0:
                TD = P / 7.0

            # Defensive touchdowns - use only what's available
            interceptionTDs = team_stat(stats.get("interceptionTDs", 0))
            puntReturnTDs = team_stat(stats.get("puntReturnTDs", 0))
            kickReturnTDs = team_stat(stats.get("kickReturnTDs", 0))

            # Calculate defensive TDs as sum of INT TDs and return TDs
            defensiveTDs = interceptionTDs + puntReturnTDs + kickReturnTDs
            defensivePoints = defensiveTDs * 6  # 6 points per TD

            # For TDs allowed, we'll use what we know: points allowed
            # Each TD is worth 6 points (plus potential PAT)
            # We'll use this as a proxy for TDs allowed
            TDA = (
                PA / 7.0
            )  # Rough approximation of total TDs allowed (7 points per TD with PAT)

            # Turnovers
            INTf = team_stat(stats.get("interceptions", 0))  # Interceptions by defense
            Ff = team_stat(stats.get("fumblesRecovered", 0))  # Fumbles recovered
            TO_forced = INTf + Ff

            INT = team_stat(stats.get("passesIntercepted", 0))  # Interceptions thrown
            Fumbles = team_stat(stats.get("fumblesLost", 0))  # Fumbles lost
            TO_allowed = INT + Fumbles

            TM = TO_forced - TO_allowed  # Turnover margin

            # First downs
            FIRST_DOWNS = team_stat(stats.get("firstDowns", 0))

            # We don't have opponent first downs directly, so we'll use 0
            OPP_FIRST_DOWNS = 0.0

            # Compute Nature statistic
            N_raw = Nature(A, TD, P, TDA, PA, TM, G, FIRST_DOWNS, OPP_FIRST_DOWNS)

            # Check if team was conference champion last year
            conf_champ = (
                team_fullname in conf_champions.values() if conf_champions else False
            )

            # Create team object
            team_obj = My_Team(
                name=team_fullname,
                wins=wins,
                losses=losses,
                conf_wins=conf_wins,
                conf_losses=conf_losses,
                conf_name=conference,
                conf_champ=conf_champ,
                N_raw=N_raw,
                ave_margin=A,
                points=P,
            )

            # Store team object
            team_objects[conference].append(team_obj)
            team_object_list.append(team_obj)
            team_objects_by_name.update({team_fullname: team_obj})

            # Add raw Nature stat for rescaling
            N_raw_list.append(team_obj.N_raw)

            # Update progress bar
            progress = (i_it + 1) / len(teams)
            update_progress(progress)

        # Compute N_adj robustly to avoid divide-by-zero in as-of snapshots.
        n_scaled = safe_minmax_scale(N_raw_list, default_value=0.0)
        for team_object, n_adj in zip(team_object_list, n_scaled):
            team_object.N_adj = float(n_adj)

        N_adj_rankings = sorted(team_object_list, key=attrgetter("N_adj"), reverse=True)

        # Save Nature statistics
        nature_file = os.path.join(
            "data_exports", f"nature_stats_{output_label(today_year)}.csv"
        )
        nature_data = [
            {
                "team": obj.name,
                "conference": obj.conf_name,
                "N_raw": obj.N_raw,
                "N_adj": obj.N_adj,
                "ave_margin": obj.ave_margin,
                "points": obj.points,
                "wins": obj.wins,
                "losses": obj.losses,
            }
            for obj in team_object_list
        ]
        pd.DataFrame(nature_data).to_csv(nature_file, index=False)
        print(f"Saved Nature statistics to {nature_file}")

        # Display Nature rankings
        skips()
        dashes()
        spaced("NATURE (N) RANKINGS - TOP 25:")
        print("%9s  %2s  %24s  %6s  %5s" % (" ", "Rk", "Team", "Record", "N_adj"))
        break_rank()

        for i, tm_obj in enumerate(N_adj_rankings[:25]):
            ranking = i + 1
            name = tm_obj.name
            n_adj = tm_obj.N_adj
            wins = int(tm_obj.wins)
            losses = int(tm_obj.losses)

            print(
                "%9s  %2i  %24s  %2i -%2i  %5.3f"
                % (" ", ranking, name, wins, losses, n_adj)
            )
            if ranking == 4:
                break_rank()

        break_rank()

        # Step 2: Rank conferences
        skips()
        dashes()
        spaced("RANKING CONFERENCES...")

        sorted_confs = total_conference_rankings()
        conference_database = {conf_obj.name: conf_obj for conf_obj in sorted_confs}

        # Save conference rankings
        conf_file = os.path.join(
            "data_exports", f"conference_rankings_{output_label(today_year)}.csv"
        )
        conf_data = [
            {
                "name": conf.name,
                "p5": conf.p5,
                "cvc_wins": conf.cvc_wins,
                "cvc_losses": conf.cvc_losses,
                "cvc_perc": conf.cvc_perc,
                "conf_index": conf.conf_index if hasattr(conf, "conf_index") else None,
            }
            for conf in sorted_confs
        ]
        pd.DataFrame(conf_data).to_csv(conf_file, index=False)
        print(f"Saved conference rankings to {conf_file}")

        # Display conference rankings
        skips()
        dashes()
        spaced("CONFERENCE RANKINGS:")
        print(
            "%9s  %2s  %24s  %6s  %6s  %6s"
            % (" ", "Rk", "Conference", "OOC W", "OOC L", "Win %")
        )
        break_rank()

        for i, conf in enumerate(sorted_confs):
            ranking = i + 1
            name = conf.name
            wins = conf.cvc_wins
            losses = conf.cvc_losses
            win_pct = conf.cvc_perc

            print(
                "%9s  %2i  %24s  %6.1f  %6.1f  %6.3f"
                % (" ", ranking, name, wins, losses, win_pct)
            )

        break_rank()

        # Compute Conference Index for each conference
        num_conferences = float(len(sorted_confs))

        for index, conf_obj in enumerate(sorted_confs):
            ranking_index = 1.0 - (float(index) / num_conferences)
            conf_obj.conf_index = ranking_index

        # Compute Team in-Conference Index for each team
        for conference in team_objects:
            conf_team_list = team_objects[conference]
            conf_sorted_teams = multisort(
                conf_team_list,
                (
                    ("conf_champ", True),
                    ("conf_wins", True),
                    ("conf_losses", False),
                    ("ave_margin", True),
                    ("points", True),
                ),
            )

            for index, tm_obj in enumerate(conf_sorted_teams):
                ranking_index = 1.0 - (float(index) / float(len(conf_sorted_teams)))
                tm_obj.standing_index = ranking_index

            for tm_obj in conf_sorted_teams:
                if conference in conference_database:
                    tm_obj.conf_index = conference_database[conference].conf_index
                    tm_obj.overall_index = tm_obj.conf_index * tm_obj.standing_index
                else:
                    tm_obj.conf_index = 0.0
                    tm_obj.overall_index = 0.0

        # Save team standings within conferences
        standings_file = os.path.join(
            "data_exports", f"team_standings_{output_label(today_year)}.csv"
        )
        standings_data = []
        for conference in team_objects:
            for tm_obj in team_objects[conference]:
                standings_data.append(
                    {
                        "team": tm_obj.name,
                        "conference": tm_obj.conf_name,
                        "conf_wins": tm_obj.conf_wins,
                        "conf_losses": tm_obj.conf_losses,
                        "standing_index": tm_obj.standing_index,
                        "conf_index": tm_obj.conf_index,
                        "overall_index": tm_obj.overall_index,
                    }
                )
        pd.DataFrame(standings_data).to_csv(standings_file, index=False)
        print(f"Saved team standings to {standings_file}")

        # Display conference standings
        for i, conf in enumerate(sorted_confs):
            conf_name = conf.name
            if conf_name in team_objects:
                conf_teams = sorted(
                    team_objects[conf_name],
                    key=lambda x: (-x.conf_wins, x.conf_losses, -x.ave_margin),
                )

                skips()
                print(f"{i+1}. {conf_name.upper()} STANDINGS:")
                print("%9s  %24s  %6s  %6s" % (" ", "Team", "Conf W", "Conf L"))
                print("%9s  %s" % (" ", "-" * 40))

                for j, team in enumerate(conf_teams):
                    print(
                        "%9s  %24s  %6.1f  %6.1f"
                        % (" ", team.name, team.conf_wins, team.conf_losses)
                    )
                    if j == 4:  # Show only top 5 teams per conference
                        break

        # Step 3: Compute Strength of Record
        skips()
        dashes()
        skips()
        spaced("COMPUTING STRENGTH OF RECORD...")

        SOR_raw_list = []

        for i_it, team in enumerate(teams):
            team_fullname = team.school

            if team_fullname in team_objects_by_name:
                team_object = team_objects_by_name[team_fullname]

                try:
                    games = get_games_with_context(year=today_year, team=team.school)

                    WCC = []
                    LCC = []

                    for game in games:
                        if (
                            game.home_points is not None
                            and game.away_points is not None
                        ):
                            if game.home_team == team.school:
                                opp_id = game.away_team
                                win = game.home_points > game.away_points
                            else:
                                opp_id = game.home_team
                                win = game.away_points > game.home_points

                            # Find opponent team
                            if opp_id in team_objects_by_name:
                                opp_object = team_objects_by_name[opp_id]
                                oppCc = opp_object.overall_index
                            else:
                                oppCc = 0.0

                            if win:
                                WCC.append(oppCc)
                            else:
                                LCC.append(oppCc)

                    team_object.winsCC = WCC
                    team_object.lossesCC = LCC
                    SOR_raw = SOR_calc(WCC, LCC)

                    team_object.SOR_raw = SOR_raw
                    SOR_raw_list.append(team_object.SOR_raw)

                except ApiException:
                    team_object.winsCC = []
                    team_object.lossesCC = []
                    team_object.SOR_raw = 0.0

            # Update progress bar
            progress = (i_it + 1) / len(teams)
            update_progress(progress)

        # Compute SOR_adj robustly to avoid divide-by-zero edge cases.
        sor_raw_values = [tm.SOR_raw for tm in team_object_list]
        sor_scaled = safe_minmax_scale(sor_raw_values, default_value=0.0)
        for team_object, sor_adj in zip(team_object_list, sor_scaled):
            team_object.SOR_adj = float(sor_adj)

        SOR_adj_rankings = sorted(
            team_object_list, key=attrgetter("SOR_adj"), reverse=True
        )

        # Save SOR data
        sor_file = os.path.join(
            "data_exports", f"sor_stats_{output_label(today_year)}.csv"
        )
        sor_data = [
            {
                "team": obj.name,
                "conference": obj.conf_name,
                "SOR_raw": obj.SOR_raw,
                "SOR_adj": obj.SOR_adj,
                "wins": obj.wins,
                "losses": obj.losses,
            }
            for obj in team_object_list
        ]
        pd.DataFrame(sor_data).to_csv(sor_file, index=False)
        print(f"Saved Strength of Record statistics to {sor_file}")

        # Display SOR rankings
        skips()
        dashes()
        spaced("STRENGTH OF RECORD (SOR) RANKINGS - TOP 25:")
        print("%9s  %2s  %24s  %6s  %5s" % (" ", "Rk", "Team", "Record", "SOR"))
        break_rank()

        for i, tm_obj in enumerate(SOR_adj_rankings[:25]):
            ranking = i + 1
            name = tm_obj.name
            sor_adj = tm_obj.SOR_adj
            wins = int(tm_obj.wins)
            losses = int(tm_obj.losses)

            print(
                "%9s  %2i  %24s  %2i -%2i  %5.3f"
                % (" ", ranking, name, wins, losses, sor_adj)
            )
            if ranking == 4:
                break_rank()

        break_rank()

        # Step 4: Calculate final SPI rankings
        skips()
        dashes()
        spaced("SICILIAN POWER INDEX RANKINGS:")

        for team_object in team_object_list:
            team_object.SPI = SPI_calc(team_object.SOR_adj, team_object.N_adj)

        SPI_final_rankings = sorted(
            team_object_list, key=attrgetter("SPI"), reverse=True
        )

        # Save final SPI rankings
        spi_file = os.path.join(
            "data_exports", f"spi_rankings_{output_label(today_year)}.csv"
        )
        spi_data = [
            {
                "rank": i + 1,
                "team": obj.name,
                "conference": obj.conf_name,
                "wins": obj.wins,
                "losses": obj.losses,
                "SPI": obj.SPI,
                "N_adj": obj.N_adj,
                "SOR_adj": obj.SOR_adj,
            }
            for i, obj in enumerate(SPI_final_rankings)
        ]
        spi_df = pd.DataFrame(spi_data)
        spi_df.to_csv(spi_file, index=False)
        print(f"Saved SPI rankings to {spi_file}")

        # Display and save results
        detailed_spi_df = display_and_save(SPI_final_rankings, sorted_confs)

        # Full-season run: also save interchangeable final(Y) + preseason(Y+1) aliases.
        if RUN_WEEK is None:
            save_dual_spi_exports(spi_df=spi_df, base_year=today_year)
            save_dual_spi_detailed_exports(
                detailed_df=detailed_spi_df,
                base_year=today_year,
            )

        # Step 5: Calculate Cross-Conference Standings
        skips()
        dashes()
        spaced("CALCULATING CROSS-CONFERENCE STANDINGS...")

        # Calculate cross-conference standings
        cross_conf_rankings = calculate_cross_conference_standings(
            team_object_list, sorted_confs
        )

        # Display and save cross-conference standings
        display_cross_conference_standings(cross_conf_rankings)

        # Create a comparison of different ranking methods
        comparison_file = os.path.join(
            "data_exports", f"rankings_comparison_{output_label(today_year)}.csv"
        )

        # Get top 25 teams from each ranking method
        nature_top25 = [team.name for team in N_adj_rankings[:25]]
        sor_top25 = [team.name for team in SOR_adj_rankings[:25]]
        spi_top25 = [team.name for team in SPI_final_rankings[:25]]
        cross_conf_top25 = [team.name for team in cross_conf_rankings[:25]]

        # Create comparison dataframe
        comparison_data = []
        for i in range(25):
            row = {
                "Rank": i + 1,
                "Nature": nature_top25[i] if i < len(nature_top25) else None,
                "SOR": sor_top25[i] if i < len(sor_top25) else None,
                "SPI": spi_top25[i] if i < len(spi_top25) else None,
                "Cross-Conf": cross_conf_top25[i]
                if i < len(cross_conf_top25)
                else None,
            }
            comparison_data.append(row)

        pd.DataFrame(comparison_data).to_csv(comparison_file, index=False)
        print(f"Saved rankings comparison to {comparison_file}")

        # Display comparison of top 10
        skips()
        dashes()
        spaced("COMPARISON OF RANKING METHODS (TOP 10):")
        print(
            "%5s  %24s  %24s  %24s  %24s"
            % ("Rank", "Nature", "SOR", "SPI", "Cross-Conf")
        )
        break_rank()

        for i in range(10):
            rank = i + 1
            nature = nature_top25[i] if i < len(nature_top25) else "-"
            sor = sor_top25[i] if i < len(sor_top25) else "-"
            spi = spi_top25[i] if i < len(spi_top25) else "-"
            cross_conf = cross_conf_top25[i] if i < len(cross_conf_top25) else "-"

            print("%5i  %24s  %24s  %24s  %24s" % (rank, nature, sor, spi, cross_conf))

        break_rank()

    except ApiException as e:
        print(f"Exception when calling API: {e}")
        # Save the error to a log file
        with open(os.path.join("data_exports", "error_log.txt"), "a") as f:
            f.write(f"{datetime.now()}: {str(e)}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sicilian Power Index rankings with explicit year/week as-of support."
    )
    parser.add_argument(
        "--mode",
        choices=["regular", "preseason"],
        default="regular",
        help="regular: run ranking algorithm; preseason: reuse prior-year final rankings.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Season year to run. Defaults to current season inferred by date.",
    )
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="As-of regular season week cutoff for the selected year.",
    )
    parser.add_argument(
        "--season-type",
        choices=["regular", "postseason"],
        default="regular",
        help="With --week in regular mode: choose regular or postseason week timeline.",
    )
    parser.add_argument(
        "--date-string",
        type=str,
        default=os.environ.get("DATE_STRING"),
        help="Optional ISO timestamp used only for default year inference.",
    )
    args = parser.parse_args()

    if args.date_string:
        todays_datetime = datetime.fromisoformat(args.date_string)
    else:
        todays_datetime = datetime.today()

    inferred_year = default_rankings_year(todays_datetime)
    today_year = args.year if args.year is not None else inferred_year

    if args.week is not None and args.week < 1:
        raise SystemExit("--week must be >= 1")

    if args.mode == "preseason" and args.week is not None:
        raise SystemExit("--week is not used in preseason mode")

    if args.mode == "preseason" and args.season_type != "regular":
        raise SystemExit("--season-type is only used in regular mode")

    RUN_MODE = args.mode
    RUN_WEEK = args.week
    RUN_SEASON_TYPE = args.season_type

    main()
