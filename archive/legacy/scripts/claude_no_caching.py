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

# Date handling
todays_datetime = os.environ.get("DATE_STRING", str(datetime.today()))
todays_datetime = datetime.fromisoformat(todays_datetime)

today_year = todays_datetime.year
sept1 = datetime(today_year, 9, 1)

if todays_datetime < sept1:
    today_year = today_year - 1

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


def get_team_record(team_name, year):
    """Get a team's overall record for a given year"""
    try:
        games = games_api.get_games(year=year, team=team_name)
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
        games = games_api.get_games(year=year, team=team_name)
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
            postseason_games = games_api.get_games(year=year, season_type="postseason")

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
                    conf_games = games_api.get_games(year=year, conference=conf)

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
    df_database.to_csv(f"SPI_Rankings_{str(todays_datetime)}.csv", sep=",")


# ------------------------------------------------------------------------------
#   MAIN EXECUTION
# ------------------------------------------------------------------------------
def main():
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
        teams_file = os.path.join("data_exports", f"teams_{today_year}.csv")
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
                team_stats = stats_api.get_team_stats(year=today_year, team=team.school)
                if team_stats and len(team_stats) > 0:
                    stats = {
                        tm_st.stat_name: tm_st.stat_value.actual_instance
                        for tm_st in team_stats
                    }
                else:
                    stats = {}
            except ApiException:
                stats = {}

            # Get games and calculate points and record
            try:
                games = games_api.get_games(year=today_year, team=team.school)
                G = float(
                    len(
                        [
                            g
                            for g in games
                            if g.home_points is not None or g.away_points is not None
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

        # Compute N_adj for all teams
        N_raw_max = np.amax(N_raw_list) if N_raw_list else 1.0

        for team_object in team_object_list:
            team_object.N_adj = team_object.N_raw / N_raw_max

        N_adj_rankings = sorted(team_object_list, key=attrgetter("N_adj"), reverse=True)

        # Save Nature statistics
        nature_file = os.path.join("data_exports", f"nature_stats_{today_year}.csv")
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
            "data_exports", f"conference_rankings_{today_year}.csv"
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
            "data_exports", f"team_standings_{today_year}.csv"
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
                    games = games_api.get_games(year=today_year, team=team.school)

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

        # Compute SOR_adj for all teams
        SOR_raw_max = np.amax(SOR_raw_list) if SOR_raw_list else 1.0

        for team_object in team_object_list:
            team_object.SOR_adj = team_object.SOR_raw / SOR_raw_max

        SOR_adj_rankings = sorted(
            team_object_list, key=attrgetter("SOR_adj"), reverse=True
        )

        # Save SOR data
        sor_file = os.path.join("data_exports", f"sor_stats_{today_year}.csv")
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
        spi_file = os.path.join("data_exports", f"spi_rankings_{today_year}.csv")
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
        display_and_save(SPI_final_rankings, sorted_confs)

        # Create a comparison of different ranking methods
        comparison_file = os.path.join(
            "data_exports", f"rankings_comparison_{today_year}.csv"
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

    except ApiException as e:
        print(f"Exception when calling API: {e}")
        # Save the error to a log file
        with open(os.path.join("data_exports", "error_log.txt"), "a") as f:
            f.write(f"{datetime.now()}: {str(e)}\n")


if __name__ == "__main__":
    main()
