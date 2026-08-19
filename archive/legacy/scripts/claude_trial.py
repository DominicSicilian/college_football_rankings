import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats as statz
from operator import itemgetter, attrgetter
from datetime import datetime
import cfbd
from cfbd.rest import ApiException
import pickle
import json
import hashlib
import argparse


# Parse command line arguments
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="College Football Rankings with week range support"
    )
    parser.add_argument(
        "--end_week",
        type=int,
        default=56,
        help="End week for data collection (default: all available)",
    )
    parser.add_argument(
        "--start_week",
        type=int,
        default=1,
        help="Start week for data collection (default: 1)",
    )
    parser.add_argument(
        "--year", type=int, help="Year to analyze (default: current year)"
    )
    parser.add_argument(
        "--date", type=str, help="Specific date to analyze (format: YYYY-MM-DD)"
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Ignore cache and fetch fresh data"
    )
    return parser.parse_args()


# Create data directories if they don't exist
os.makedirs("data_exports", exist_ok=True)
os.makedirs("cache", exist_ok=True)

# ------------------------------------------------------------------------------
#   CACHING SYSTEM
# ------------------------------------------------------------------------------


def get_cache_key(function_name, **kwargs):
    """Generate a unique cache key based on function name and parameters"""
    # Extract week range parameters if they exist
    start_week = kwargs.get("start_week", 1)
    end_week = kwargs.get("end_week", 56)

    # Add week range to key if specified and not default
    week_suffix = ""
    if start_week != 1 or end_week != 56:
        week_suffix = f"_w{start_week}-{end_week}"

    # Sort kwargs to ensure consistent key generation
    sorted_kwargs = sorted(kwargs.items())
    # Convert to string and hash
    kwargs_str = json.dumps(sorted_kwargs)
    key = f"{function_name}{week_suffix}_{kwargs_str}"
    return hashlib.md5(key.encode()).hexdigest()


def cache_api_call(function_name, api_function, use_cache=True, **kwargs):
    """Cache API results to avoid repeated calls"""
    # Special handling for get_games with week range
    if (
        function_name in ["get_games", "get_team_games"]
        and "start_week" in kwargs
        and "end_week" in kwargs
    ):
        start_week = kwargs.pop("start_week", 1)
        end_week = kwargs.pop("end_week", 56)

        # If using default values, don't specify week at all
        if start_week == 1 and end_week == 56:
            return cache_api_call_single(
                function_name, api_function, use_cache=use_cache, **kwargs
            )

        # Otherwise, fetch each week separately and combine results
        all_results = []
        for week in range(start_week, end_week + 1):
            week_kwargs = kwargs.copy()
            week_kwargs["week"] = week
            results = cache_api_call_single(
                f"{function_name}_week{week}",
                api_function,
                use_cache=use_cache,
                **week_kwargs,
            )
            all_results.extend(results)
        return all_results
    else:
        # For other functions, proceed normally
        return cache_api_call_single(
            function_name, api_function, use_cache=use_cache, **kwargs
        )


def cache_api_call_single(function_name, api_function, use_cache=True, **kwargs):
    """Cache a single API call"""
    # Generate a unique cache key
    cache_key = get_cache_key(function_name, **kwargs)
    year = kwargs.get("year", datetime.now().year)

    # Include week range in directory structure if specified
    start_week = kwargs.get("start_week", 1)
    end_week = kwargs.get("end_week", 56)
    week_dir = ""
    if start_week != 1 or end_week != 56:
        week_dir = f"w{start_week}-{end_week}_"

    # Create cache directory for the year if it doesn't exist
    year_cache_dir = os.path.join("cache", str(year), week_dir)
    os.makedirs(year_cache_dir, exist_ok=True)

    cache_file = os.path.join(year_cache_dir, f"{cache_key}.csv")

    # Check if cache exists and we're allowed to use it
    if os.path.exists(cache_file) and use_cache:
        try:
            # Different loading methods based on function name
            if "get_games" in function_name or "get_team_games" in function_name:
                # Load games data
                df = pd.read_csv(cache_file)
                # Convert back to CFBD game objects
                games = []
                for _, row in df.iterrows():
                    game = type("obj", (object,), {})
                    for col in df.columns:
                        setattr(game, col, row[col])
                    games.append(game)
                return games
            elif function_name in ["get_fbs_teams", "get_team_stats"]:
                # Load team data
                df = pd.read_csv(cache_file)
                # Convert back to objects
                items = []
                for _, row in df.iterrows():
                    item = type("obj", (object,), {})
                    for col in df.columns:
                        setattr(item, col, row[col])
                    items.append(item)
                return items
            elif function_name == "get_conferences":
                # Load conference data
                df = pd.read_csv(cache_file)
                conferences = []
                for _, row in df.iterrows():
                    conf = type("obj", (object,), {})
                    for col in df.columns:
                        setattr(conf, col, row[col])
                    conferences.append(conf)
                return conferences
            else:
                # Generic loading
                return pd.read_csv(cache_file)
        except Exception as e:
            print(f"Error loading from cache: {e}. Fetching fresh data.")

    # If no cache, error, or cache override, call the API
    try:
        result = api_function(**kwargs)

        # Save to cache based on data type
        if "get_games" in function_name or "get_team_games" in function_name:
            # Save games data
            games_data = []
            for game in result:
                game_dict = {}
                # Extract relevant attributes
                attrs = [
                    "id",
                    "season",
                    "week",
                    "season_type",
                    "start_date",
                    "neutral_site",
                    "conference_game",
                    "attendance",
                    "venue",
                    "home_team",
                    "home_conference",
                    "home_points",
                    "away_team",
                    "away_conference",
                    "away_points",
                    "notes",
                ]
                for attr in attrs:
                    if hasattr(game, attr):
                        game_dict[attr] = getattr(game, attr)
                    else:
                        game_dict[attr] = None
                games_data.append(game_dict)
            pd.DataFrame(games_data).to_csv(cache_file, index=False)
        elif function_name in ["get_fbs_teams"]:
            # Save team data
            teams_data = []
            for team in result:
                team_dict = {}
                attrs = [
                    "id",
                    "school",
                    "mascot",
                    "abbreviation",
                    "conference",
                    "division",
                    "color",
                    "alt_color",
                ]
                for attr in attrs:
                    if hasattr(team, attr):
                        team_dict[attr] = getattr(team, attr)
                    else:
                        team_dict[attr] = None
                teams_data.append(team_dict)
            pd.DataFrame(teams_data).to_csv(cache_file, index=False)
        elif function_name == "get_team_stats":
            # Save team stats
            stats_data = []
            for stat in result:
                stat_dict = {
                    "stat_name": stat.stat_name,
                    "stat_value": stat.stat_value.actual_instance
                    if hasattr(stat.stat_value, "actual_instance")
                    else stat.stat_value,
                }
                stats_data.append(stat_dict)
            pd.DataFrame(stats_data).to_csv(cache_file, index=False)
        elif function_name == "get_conferences":
            # Save conference data
            conf_data = []
            for conf in result:
                conf_dict = {}
                attrs = ["id", "name", "short_name", "abbreviation", "classification"]
                for attr in attrs:
                    if hasattr(conf, attr):
                        conf_dict[attr] = getattr(conf, attr)
                    else:
                        conf_dict[attr] = None
                conf_data.append(conf_dict)
            pd.DataFrame(conf_data).to_csv(cache_file, index=False)
        else:
            # Generic saving
            if hasattr(result, "__dict__"):
                pd.DataFrame([result.__dict__]).to_csv(cache_file, index=False)
            elif isinstance(result, list):
                if all(hasattr(item, "__dict__") for item in result):
                    pd.DataFrame([item.__dict__ for item in result]).to_csv(
                        cache_file, index=False
                    )
                else:
                    pd.DataFrame(result).to_csv(cache_file, index=False)
            else:
                pd.DataFrame([result]).to_csv(cache_file, index=False)

        return result
    except ApiException as e:
        print(f"API Exception: {e}")
        # If API fails, return empty result based on function
        if (
            "get_games" in function_name
            or "get_team_games" in function_name
            or function_name in ["get_fbs_teams", "get_conferences", "get_team_stats"]
        ):
            return []
        else:
            return None


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


def save_conference_champions(champions, year, week_suffix=""):
    """Save conference champions to CSV"""
    if champions:
        df = pd.DataFrame(list(champions.items()), columns=["Conference", "Champion"])
        filename = f"conference_champions_{year}{week_suffix}.csv"
        filepath = os.path.join("data_exports", filename)
        df.to_csv(filepath, index=False)
        print(f"Saved conference champions to {filepath}")


def load_conference_champions(year, week_suffix=""):
    """Load conference champions from CSV"""
    filename = f"conference_champions_{year}{week_suffix}.csv"
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


# ------------------------------------------------------------------------------
#   CORE FUNCTIONS
# ------------------------------------------------------------------------------


def get_team_record(team_name, year, start_week=1, end_week=56, use_cache=True):
    """Get a team's overall record for a given year and week range"""
    games = cache_api_call(
        "get_team_games",
        games_api.get_games,
        year=year,
        team=team_name,
        start_week=start_week,
        end_week=end_week,
        use_cache=use_cache,
    )
    wins = 0
    losses = 0

    for game in games:
        if (
            hasattr(game, "home_points")
            and hasattr(game, "away_points")
            and game.home_points is not None
            and game.away_points is not None
        ):
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


def get_team_conference_record(
    team_name, conference, year, start_week=1, end_week=56, use_cache=True
):
    """Get a team's conference record for a given year and week range"""
    games = cache_api_call(
        "get_team_games",
        games_api.get_games,
        year=year,
        team=team_name,
        start_week=start_week,
        end_week=end_week,
        use_cache=use_cache,
    )
    conf_wins = 0
    conf_losses = 0

    for game in games:
        if (
            hasattr(game, "home_points")
            and hasattr(game, "away_points")
            and game.home_points is not None
            and game.away_points is not None
        ):
            # Check if this is a conference game
            is_conf_game = False

            if game.home_team == team_name:
                if (
                    hasattr(game, "away_conference")
                    and game.away_conference
                    and game.away_conference.lower() == conference
                ):
                    is_conf_game = True
                    if game.home_points > game.away_points:
                        conf_wins += 1
                    else:
                        conf_losses += 1
            else:
                if (
                    hasattr(game, "home_conference")
                    and game.home_conference
                    and game.home_conference.lower() == conference
                ):
                    is_conf_game = True
                    if game.away_points > game.home_points:
                        conf_wins += 1
                    else:
                        conf_losses += 1

    return conf_wins, conf_losses


def get_conference_champions(year, start_week=1, end_week=56, use_cache=True):
    """Get conference champions for a given year and week range"""
    # Create a week suffix for cache files
    week_suffix = (
        f"_w{start_week}-{end_week}" if start_week != 1 or end_week != 56 else ""
    )

    # Check if we have cached conference champions
    cache_file = os.path.join(
        "cache", str(year), f"w{start_week}-{end_week}_", "conference_champions.json"
    )
    if os.path.exists(cache_file) and use_cache:
        with open(cache_file, "r") as f:
            return json.load(f)

    champions = {}
    conferences = [
        conf.name.lower()
        for conf in cache_api_call(
            "get_conferences", conferences_api.get_conferences, use_cache=use_cache
        )
        if hasattr(conf, "classification") and conf.classification == "fbs"
    ]

    # First try to get conference championship games
    print("Making API call...")
    postseason_games = cache_api_call(
        "get_games",
        games_api.get_games,
        year=year,
        classification="fbs",
        #  start_week=start_week, end_week=end_week,
        use_cache=use_cache,
    )
    print("Processing API response")
    # Filter for conference championship games
    for game in postseason_games:
        if (
            hasattr(game, "notes")
            and game.notes
            and "championship" in game.notes.lower()
        ):
            print(f"Found {game.notes}...")
            conf_name = None
            # Extract conference name from notes
            for conf in conferences:
                if conf.lower() in game.notes.lower():
                    conf_name = conf.lower()
                    break

            if (
                conf_name
                and hasattr(game, "home_points")
                and hasattr(game, "away_points")
                and game.home_points is not None
                and game.away_points is not None
            ):
                # Determine winner
                if game.home_points > game.away_points:
                    champions[conf_name] = game.home_team
                else:
                    champions[conf_name] = game.away_team
                print(f"Found {conf_name} champ {champions[conf_name]}")

    # If we couldn't get all champions from championship games, try standings
    # if len(champions) < len([c for c in conferences if c.lower() not in ['fbs independents', 'independent']]):
    #     print("Missing champs...")
    #     for conf in conferences:
    #         if conf.lower() in champions:
    #             continue

    #         if conf.lower() in ['fbs independents', 'independent']:
    #             continue

    #         # Get regular season conference games
    #         conf_games = cache_api_call('get_games', games_api.get_games,
    #                                    year=year, conference=conf,
    #                                    start_week=start_week, end_week=end_week,
    #                                    use_cache=use_cache)

    #         # Build standings from games
    #         teams = {}
    #         for game in conf_games:
    #             if hasattr(game, 'home_conference') and hasattr(game, 'away_conference') and game.home_conference == conf and game.away_conference == conf:
    #                 # This is a conference game
    #                 if hasattr(game, 'home_points') and hasattr(game, 'away_points') and game.home_points is not None and game.away_points is not None:
    #                     # Home team
    #                     if game.home_team not in teams:
    #                         teams[game.home_team] = {"wins": 0, "losses": 0}
    #                     # Away team
    #                     if game.away_team not in teams:
    #                         teams[game.away_team] = {"wins": 0, "losses": 0}

    #                     # Update records
    #                     if game.home_points > game.away_points:
    #                         teams[game.home_team]["wins"] += 1
    #                         teams[game.away_team]["losses"] += 1
    #                     else:
    #                         teams[game.away_team]["wins"] += 1
    #                         teams[game.home_team]["losses"] += 1

    #         # Find team with best conference record
    #         if teams:
    #             best_team = max(teams.items(),
    #                            key=lambda x: (x[1]["wins"]/(x[1]["wins"]+x[1]["losses"]) if (x[1]["wins"]+x[1]["losses"]) > 0 else 0,
    #                                          x[1]["wins"]))
    #             champions[conf.lower()] = best_team[0]

    # Cache the results
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(champions, f)

    return champions


def conference_rankings(year, start_week=1, end_week=56, use_cache=True):
    """Compute conference rankings for a given year and week range"""
    # Create a week suffix for cache files
    week_suffix = (
        f"_w{start_week}-{end_week}" if start_week != 1 or end_week != 56 else ""
    )

    # Check if we have cached conference rankings
    cache_file = os.path.join(
        "cache", str(year), f"w{start_week}-{end_week}_", "conference_rankings.pkl"
    )
    if os.path.exists(cache_file) and use_cache:
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    conf_objects = {}
    games_played = []

    teams = cache_api_call(
        "get_fbs_teams", teams_api.get_fbs_teams, year=year, use_cache=use_cache
    )

    power5 = ["acc", "big ten", "big 12", "pac 12", "sec"]
    if int(year) < 2005:
        power5 = ["acc", "big ten", "big 12", "pac 10", "sec", "big east"]

    print(f"\n-->considering conferences in {year} (weeks {start_week}-{end_week})")

    for i_it, team in enumerate(teams):
        if hasattr(team, "conference"):
            conference = team.conference.lower()
            if conference in power5:
                is_p5 = True
            else:
                is_p5 = False

            if conference not in conf_objects:
                this_conf = My_Conf(name=conference, p5=is_p5)
                conf_objects.update({conference: this_conf})

            # Get team records directly from games
            wins, losses = get_team_record(
                team.school, year, start_week, end_week, use_cache
            )
            conf_wins, conf_losses = get_team_conference_record(
                team.school, conference, year, start_week, end_week, use_cache
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

    result = [conf_objects, mean_games_played]

    # Cache the results
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "wb") as f:
        pickle.dump(result, f)

    return result


def total_conference_rankings(today_year, start_week=1, end_week=56, use_cache=True):
    """Calculate total conference rankings combining previous and current year data"""
    # Create a week suffix for cache files
    week_suffix = (
        f"_w{start_week}-{end_week}" if start_week != 1 or end_week != 56 else ""
    )

    # Check if we have cached total conference rankings
    cache_file = os.path.join(
        "cache",
        str(today_year),
        f"w{start_week}-{end_week}_",
        "total_conference_rankings.pkl",
    )
    if os.path.exists(cache_file) and use_cache:
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    combined_conf_objects = {}

    # First, establish conference stats for previous season
    last_year = conference_rankings(today_year - 1, start_week, end_week, use_cache)
    LY_confs = last_year[0]

    this_year = conference_rankings(today_year, start_week, end_week, use_cache)
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

    # Cache the results
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "wb") as f:
        pickle.dump(sorted_confs, f)

    return sorted_confs


def display_and_save(SPI_final_rankings, conf_rankings, week_suffix=""):
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

        # Printing basic results for top 25
        print(
            "%9s  %2i  %24s  %2i -%2i  %5.2f" % (" ", ranking, name, wins, losses, SPI)
        )
        if ranking == 4:
            break_rank()
        if ranking == 25:
            break_rank()
            break_rank()
            break

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
    df_database.to_csv(f"SPI_Rankings_{str(todays_datetime)}{week_suffix}.csv", sep=",")


# ------------------------------------------------------------------------------
#   MAIN EXECUTION
# ------------------------------------------------------------------------------
def main():
    # Parse command line arguments
    args = parse_arguments()

    # Set up date and year
    global todays_datetime, today_year

    if args.date:
        todays_datetime = datetime.fromisoformat(args.date)
    else:
        todays_datetime = os.environ.get("DATE_STRING", str(datetime.today()))
        todays_datetime = datetime.fromisoformat(todays_datetime)

    if args.year:
        today_year = args.year
    else:
        today_year = todays_datetime.year
        sept1 = datetime(today_year, 9, 1)
        if todays_datetime < sept1:
            today_year = today_year - 1

    # Set up week range
    start_week = args.start_week
    end_week = args.end_week

    # Set cache usage
    use_cache = not args.no_cache

    # Create a suffix for filenames based on week range
    week_suffix = (
        f"_w{start_week}-{end_week}" if start_week != 1 or end_week != 56 else ""
    )

    # Welcome message
    dashes()
    skips()
    spaced("Welcome to Dominic Sicilian's college football rankings!")
    if start_week != 1 or end_week != 56:
        spaced(
            f"Analyzing data from week {start_week} through week {end_week} of {today_year}"
        )
    else:
        spaced(f"Analyzing all available data for {today_year}")
    if not use_cache:
        spaced("Cache override enabled - fetching fresh data from API")
    spaced("The code will first examine the nature (N) of a team's games.")
    spaced(
        "Then, it will establish rankings for conferences, then consider a team's standing within its conference."
    )
    spaced("This will allow us to estimate a team's strength of record (SOR).")
    spaced("Combining N with SOR yields SPI: The Sicilian Power Index!")
    spaced("AND THAT'S HOW WE RANK 'EM!")
    skips()

    # Create data directory if it doesn't exist
    os.makedirs("data_exports", exist_ok=True)

    # Get conference champions from previous season directly from API or from saved file
    print("Getting last year's conference champs...")
    conf_champions_file = os.path.join(
        "data_exports", f"conference_champions_{today_year-1}{week_suffix}.csv"
    )

    if os.path.exists(conf_champions_file) and use_cache:
        # Load from file if available
        champs_df = pd.read_csv(conf_champions_file)
        conf_champions = dict(zip(champs_df["Conference"], champs_df["Champion"]))
        print("Loaded conference champions from file.")
    else:
        # Otherwise get from API
        print("Grabbing from API")
        conf_champions = get_conference_champions(
            today_year - 1, start_week, end_week, use_cache
        )
        print("Successful API pull.")
        # Save to file
        if conf_champions:
            print("Saving conference champions")
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

    # Check if we have cached Nature statistics
    nature_cache_file = os.path.join(
        "cache", str(today_year), f"w{start_week}-{end_week}_", "nature_stats.pkl"
    )
    if os.path.exists(nature_cache_file) and use_cache:
        with open(nature_cache_file, "rb") as f:
            cached_data = pickle.load(f)
            team_objects = cached_data["team_objects"]
            team_objects_by_name = cached_data["team_objects_by_name"]
            team_object_list = cached_data["team_object_list"]
            N_raw_list = cached_data["N_raw_list"]
            N_adj_rankings = cached_data["N_adj_rankings"]
            print("Loaded Nature statistics from cache.")
    else:
        teams = cache_api_call(
            "get_fbs_teams",
            teams_api.get_fbs_teams,
            year=today_year,
            use_cache=use_cache,
        )

        # Save teams data
        teams_file = os.path.join(
            "data_exports", f"teams_{today_year}{week_suffix}.csv"
        )
        teams_data = [
            {"id": t.id, "school": t.school, "conference": t.conference}
            for t in teams
            if hasattr(t, "id") and hasattr(t, "school") and hasattr(t, "conference")
        ]
        pd.DataFrame(teams_data).to_csv(teams_file, index=False)
        print(f"Saved {len(teams_data)} teams to {teams_file}")

        for i_it, team in enumerate(teams):
            if hasattr(team, "school") and hasattr(team, "conference"):
                # Set up name, abbreviation, conference
                team_fullname = team.school
                conference = team.conference.lower()

                if conference not in team_objects:
                    team_objects.update({conference: []})

                # Get team stats with week range
                team_stats = cache_api_call(
                    "get_team_stats",
                    stats_api.get_team_stats,
                    year=today_year,
                    team=team.school,
                    start_week=start_week,
                    end_week=end_week,
                    use_cache=use_cache,
                )
                stats = {}
                if team_stats:
                    for stat in team_stats:
                        if hasattr(stat, "stat_name") and hasattr(stat, "stat_value"):
                            if hasattr(stat.stat_value, "actual_instance"):
                                stats[stat.stat_name] = stat.stat_value.actual_instance
                            else:
                                stats[stat.stat_name] = stat.stat_value

                # Get games and calculate points and record with week range
                games = cache_api_call(
                    "get_team_games",
                    games_api.get_games,
                    year=today_year,
                    team=team.school,
                    start_week=start_week,
                    end_week=end_week,
                    use_cache=use_cache,
                )

                G = float(
                    len(
                        [
                            g
                            for g in games
                            if hasattr(g, "home_points")
                            and hasattr(g, "away_points")
                            and g.home_points is not None
                            and g.away_points is not None
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
                    if (
                        hasattr(game, "home_points")
                        and hasattr(game, "away_points")
                        and game.home_points is not None
                        and game.away_points is not None
                    ):
                        if game.home_team == team.school:
                            P += game.home_points
                            PA += game.away_points
                            if game.home_points > game.away_points:
                                wins += 1
                                if (
                                    hasattr(game, "away_conference")
                                    and game.away_conference
                                    and game.away_conference.lower() == conference
                                ):
                                    conf_wins += 1
                            else:
                                losses += 1
                                if (
                                    hasattr(game, "away_conference")
                                    and game.away_conference
                                    and game.away_conference.lower() == conference
                                ):
                                    conf_losses += 1
                        else:
                            P += game.away_points
                            PA += game.home_points
                            if game.away_points > game.home_points:
                                wins += 1
                                if (
                                    hasattr(game, "home_conference")
                                    and game.home_conference
                                    and game.home_conference.lower() == conference
                                ):
                                    conf_wins += 1
                            else:
                                losses += 1
                                if (
                                    hasattr(game, "home_conference")
                                    and game.home_conference
                                    and game.home_conference.lower() == conference
                                ):
                                    conf_losses += 1

                # Calculate average margin
                A = ave_margin(G, P, PA)

                # Offensive touchdowns
                passTD = team_stat(stats.get("passingTDs", 0))
                rushTD = team_stat(stats.get("rushingTDs", 0))
                TD = passTD + rushTD

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
                INTf = team_stat(
                    stats.get("interceptions", 0)
                )  # Interceptions by defense
                Ff = team_stat(stats.get("fumblesRecovered", 0))  # Fumbles recovered
                TO_forced = INTf + Ff

                INT = team_stat(
                    stats.get("passesIntercepted", 0)
                )  # Interceptions thrown
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
                    team_fullname in conf_champions.values()
                    if conf_champions
                    else False
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

        # Compute N_adj for all teams
        N_raw_max = np.amax(N_raw_list) if N_raw_list else 1.0

        for team_object in team_object_list:
            team_object.N_adj = team_object.N_raw / N_raw_max

        N_adj_rankings = sorted(team_object_list, key=attrgetter("N_adj"), reverse=True)

        # Cache the Nature statistics
        os.makedirs(os.path.dirname(nature_cache_file), exist_ok=True)
        with open(nature_cache_file, "wb") as f:
            pickle.dump(
                {
                    "team_objects": team_objects,
                    "team_objects_by_name": team_objects_by_name,
                    "team_object_list": team_object_list,
                    "N_raw_list": N_raw_list,
                    "N_adj_rankings": N_adj_rankings,
                },
                f,
            )

    # Save Nature statistics to CSV
    nature_file = os.path.join(
        "data_exports", f"nature_stats_{today_year}{week_suffix}.csv"
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

    N_adj_rankings = sorted(team_object_list, key=attrgetter("N_adj"), reverse=True)
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

    sorted_confs = total_conference_rankings(
        today_year, start_week, end_week, use_cache
    )
    conference_database = {conf_obj.name: conf_obj for conf_obj in sorted_confs}

    # Save conference rankings
    conf_file = os.path.join(
        "data_exports", f"conference_rankings_{today_year}{week_suffix}.csv"
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

    # Check if we have cached team standings
    standings_cache_file = os.path.join(
        "cache", str(today_year), f"w{start_week}-{end_week}_", "team_standings.pkl"
    )
    if os.path.exists(standings_cache_file) and use_cache:
        with open(standings_cache_file, "rb") as f:
            cached_data = pickle.load(f)
            team_objects = cached_data["team_objects"]
            team_objects_by_name = cached_data["team_objects_by_name"]
            team_object_list = cached_data["team_object_list"]
            print("Loaded team standings from cache.")
    else:
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

        # Cache the team standings
        os.makedirs(os.path.dirname(standings_cache_file), exist_ok=True)
        with open(standings_cache_file, "wb") as f:
            pickle.dump(
                {
                    "team_objects": team_objects,
                    "team_objects_by_name": team_objects_by_name,
                    "team_object_list": team_object_list,
                },
                f,
            )

    # Save team standings within conferences
    standings_file = os.path.join(
        "data_exports", f"team_standings_{today_year}{week_suffix}.csv"
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

    # Check if we have cached SOR data
    sor_cache_file = os.path.join(
        "cache", str(today_year), f"w{start_week}-{end_week}_", "sor_stats.pkl"
    )
    if os.path.exists(sor_cache_file) and use_cache:
        with open(sor_cache_file, "rb") as f:
            cached_data = pickle.load(f)
            team_object_list = cached_data["team_object_list"]
            SOR_adj_rankings = cached_data["SOR_adj_rankings"]
            print("Loaded Strength of Record data from cache.")
    else:
        SOR_raw_list = []
        teams = cache_api_call(
            "get_fbs_teams",
            teams_api.get_fbs_teams,
            year=today_year,
            use_cache=use_cache,
        )

        for i_it, team in enumerate(teams):
            if hasattr(team, "school"):
                team_fullname = team.school

                if team_fullname in team_objects_by_name:
                    team_object = team_objects_by_name[team_fullname]

                    games = cache_api_call(
                        "get_team_games",
                        games_api.get_games,
                        year=today_year,
                        team=team.school,
                        start_week=start_week,
                        end_week=end_week,
                        use_cache=use_cache,
                    )

                    WCC = []
                    LCC = []

                    for game in games:
                        if (
                            hasattr(game, "home_points")
                            and hasattr(game, "away_points")
                            and game.home_points is not None
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

                # Update progress bar
                progress = (i_it + 1) / len(teams)
                update_progress(progress)

        # Compute SOR_adj for all teams
        SOR_raw_max = np.amax(SOR_raw_list) if SOR_raw_list else 1.0

        for team_object in team_object_list:
            if hasattr(team_object, "SOR_raw"):
                team_object.SOR_adj = team_object.SOR_raw / SOR_raw_max
            else:
                team_object.SOR_raw = 0.0
                team_object.SOR_adj = 0.0

        SOR_adj_rankings = sorted(
            team_object_list, key=attrgetter("SOR_adj"), reverse=True
        )

        # Cache the SOR data
        os.makedirs(os.path.dirname(sor_cache_file), exist_ok=True)
        with open(sor_cache_file, "wb") as f:
            pickle.dump(
                {
                    "team_object_list": team_object_list,
                    "SOR_adj_rankings": SOR_adj_rankings,
                },
                f,
            )

    # Save SOR data
    sor_file = os.path.join("data_exports", f"sor_stats_{today_year}{week_suffix}.csv")
    sor_data = [
        {
            "team": obj.name,
            "conference": obj.conf_name,
            "SOR_raw": obj.SOR_raw if hasattr(obj, "SOR_raw") else 0.0,
            "SOR_adj": obj.SOR_adj if hasattr(obj, "SOR_adj") else 0.0,
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

    SOR_adj_rankings = sorted(team_object_list, key=attrgetter("SOR_adj"), reverse=True)
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

    # Check if we have cached SPI rankings
    spi_cache_file = os.path.join(
        "cache", str(today_year), f"w{start_week}-{end_week}_", "spi_rankings.pkl"
    )
    if os.path.exists(spi_cache_file) and use_cache:
        with open(spi_cache_file, "rb") as f:
            SPI_final_rankings = pickle.load(f)
            print("Loaded SPI rankings from cache.")
    else:
        for team_object in team_object_list:
            team_object.SPI = SPI_calc(team_object.SOR_adj, team_object.N_adj)

        SPI_final_rankings = sorted(
            team_object_list, key=attrgetter("SPI"), reverse=True
        )

        # Cache the SPI rankings
        os.makedirs(os.path.dirname(spi_cache_file), exist_ok=True)
        with open(spi_cache_file, "wb") as f:
            pickle.dump(SPI_final_rankings, f)

    # Save final SPI rankings
    spi_file = os.path.join(
        "data_exports", f"spi_rankings_{today_year}{week_suffix}.csv"
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
    pd.DataFrame(spi_data).to_csv(spi_file, index=False)
    print(f"Saved SPI rankings to {spi_file}")

    # Display and save results
    display_and_save(SPI_final_rankings, sorted_confs, week_suffix)

    # Create a comparison of different ranking methods
    comparison_file = os.path.join(
        "data_exports", f"rankings_comparison_{today_year}{week_suffix}.csv"
    )

    # Get top 25 teams from each ranking method
    nature_top25 = [team.name for team in N_adj_rankings[:25]]
    sor_top25 = [team.name for team in SOR_adj_rankings[:25]]
    spi_top25 = [team.name for team in SPI_final_rankings[:25]]

    # Create comparison dataframe
    comparison_data = []
    for i in range(25):
        row = {
            "Rank": i + 1,
            "Nature": nature_top25[i] if i < len(nature_top25) else None,
            "SOR": sor_top25[i] if i < len(sor_top25) else None,
            "SPI": spi_top25[i] if i < len(spi_top25) else None,
        }
        comparison_data.append(row)

    pd.DataFrame(comparison_data).to_csv(comparison_file, index=False)
    print(f"Saved rankings comparison to {comparison_file}")

    # Display comparison of top 10
    skips()
    dashes()
    spaced("COMPARISON OF RANKING METHODS (TOP 10):")
    print("%5s  %24s  %24s  %24s" % ("Rank", "Nature", "SOR", "SPI"))
    break_rank()

    for i in range(10):
        rank = i + 1
        nature = nature_top25[i] if i < len(nature_top25) else "-"
        sor = sor_top25[i] if i < len(sor_top25) else "-"
        spi = spi_top25[i] if i < len(spi_top25) else "-"

        print("%5i  %24s  %24s  %24s" % (rank, nature, sor, spi))

    break_rank()


if __name__ == "__main__":
    main()

"""

## Key Changes Made:

1. **Fixed Week Range Handling**:
   - Created a special case in `cache_api_call` to handle `get_games` with week ranges
   - For week ranges, it now makes separate API calls for each week and combines the results

2. **Added Cache Override Option**:
   - Added a `--no-cache` command line argument
   - Modified `cache_api_call` to accept a `use_cache` parameter
   - When `--no-cache` is specified, the code will always fetch fresh data from the API
   - Still saves results to cache for future use

3. **Improved Error Handling**:
   - Better handling of missing attributes in API responses
   - More robust checking for valid data before processing

4. **Enhanced Progress Reporting**:
   - Added message indicating when cache is being bypassed
   - Improved progress messages to include week range information

## Usage Examples:


# Analyze all available weeks (default)
python rankings.py

# Analyze weeks 1-8 only
python rankings.py --start_week 1 --end_week 8

# Analyze weeks 1-8 for 2022, ignoring cache
python rankings.py --start_week 1 --end_week 8 --year 2022 --no-cache

# Analyze up to a specific date, ignoring cache
python rankings.py --date 2023-10-15 --no-cache
"""
