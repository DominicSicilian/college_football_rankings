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
import argparse


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
    return parser.parse_args()


os.makedirs("data_exports", exist_ok=True)

configuration = cfbd.Configuration(
    host="https://api.collegefootballdata.com",
    access_token=os.getenv("CFBD_API_KEY"),
)

teams_api = cfbd.TeamsApi(cfbd.ApiClient(configuration))
games_api = cfbd.GamesApi(cfbd.ApiClient(configuration))
stats_api = cfbd.StatsApi(cfbd.ApiClient(configuration))
rankings_api = cfbd.RankingsApi(cfbd.ApiClient(configuration))
conferences_api = cfbd.ConferencesApi(cfbd.ApiClient(configuration))

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


def api_call_with_week_range(api_function, start_week=1, end_week=56, **kwargs):
    """Make API calls with week range support"""
    if start_week == 1 and end_week == 56:
        return api_function(**kwargs)

    all_results = []
    for week in range(start_week, end_week + 1):
        week_kwargs = kwargs.copy()
        week_kwargs["week"] = week
        try:
            results = api_function(**week_kwargs)
            all_results.extend(results)
        except:
            try:
                results = api_function(**kwargs)
            except ApiException as e:
                print(f"API Exception for week {week}: {e}")

    return all_results


def get_team_record(team_name, year, start_week=1, end_week=56):
    """Get a team's overall record for a given year and week range"""
    games = api_call_with_week_range(
        games_api.get_games, start_week, end_week, year=year, team=team_name
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


def get_team_conference_record(team_name, conference, year, start_week=1, end_week=56):
    """Get a team's conference record for a given year and week range"""
    games = api_call_with_week_range(
        games_api.get_games, start_week, end_week, year=year, team=team_name
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


def get_conference_champions(year, start_week=1, end_week=56):
    """Get conference champions for a given year and week range"""
    champions = {}
    conferences = [
        conf.name.lower()
        for conf in conferences_api.get_conferences()
        if hasattr(conf, "classification") and conf.classification == "fbs"
    ]

    # First try to get conference championship games
    print("Making API call...")
    postseason_games = games_api.get_games(year=year, classification="fbs")
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

    return champions


def conference_rankings(year, start_week=1, end_week=56):
    """Compute conference rankings for a given year and week range"""
    conf_objects = {}
    games_played = []

    teams = teams_api.get_fbs_teams(year=year)

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
            wins, losses = get_team_record(team.school, year, start_week, end_week)
            conf_wins, conf_losses = get_team_conference_record(
                team.school, conference, year, start_week, end_week
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


def total_conference_rankings(today_year, start_week=1, end_week=56):
    """Calculate total conference rankings combining previous and current year data"""
    combined_conf_objects = {}

    # First, establish conference stats for previous season
    last_year = conference_rankings(today_year - 1, start_week, end_week)
    LY_confs = last_year[0]

    this_year = conference_rankings(today_year, start_week, end_week)
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


def main():
    args = parse_arguments()

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

    start_week = args.start_week
    end_week = args.end_week

    week_suffix = (
        f"_w{start_week}-{end_week}" if start_week != 1 or end_week != 56 else ""
    )

    dashes()
    skips()
    spaced("Welcome to Dominic Sicilian's college football rankings!")
    if start_week != 1 or end_week != 56:
        spaced(
            f"Analyzing data from week {start_week} through week {end_week} of {today_year}"
        )
    else:
        spaced(f"Analyzing all available data for {today_year}")
    spaced("The code will first examine the nature (N) of a team's games.")
    spaced(
        "Then, it will establish rankings for conferences, then consider a team's standing within its conference."
    )
    spaced("This will allow us to estimate a team's strength of record (SOR).")
    spaced("Combining N with SOR yields SPI: The Sicilian Power Index!")
    spaced("AND THAT'S HOW WE RANK 'EM!")
    skips()

    os.makedirs("data_exports", exist_ok=True)

    print("Getting last year's conference champs...")
    conf_champions_file = os.path.join(
        "data_exports", f"conference_champions_{today_year-1}{week_suffix}.csv"
    )

    print("Grabbing from API")
    conf_champions = get_conference_champions(today_year - 1, start_week, end_week)
    print("Successful API pull.")

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

    N_raw_list = []
    team_objects = {}
    team_objects_by_name = {}
    team_object_list = []

    skips()
    dashes()
    spaced('COMPUTING "NATURE" STATISTIC...')

    teams = teams_api.get_fbs_teams(year=today_year)

    # Save teams data
    teams_file = os.path.join("data_exports", f"teams_{today_year}{week_suffix}.csv")
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
            team_stats = api_call_with_week_range(
                stats_api.get_team_stats,
                start_week,
                end_week,
                year=today_year,
                team=team.school,
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
            games = api_call_with_week_range(
                games_api.get_games,
                start_week,
                end_week,
                year=today_year,
                team=team.school,
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

    sorted_confs = total_conference_rankings(today_year, start_week, end_week)
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

    SOR_raw_list = []
    teams = teams_api.get_fbs_teams(year=today_year)

    for i_it, team in enumerate(teams):
        if hasattr(team, "school"):
            team_fullname = team.school

            if team_fullname in team_objects_by_name:
                team_object = team_objects_by_name[team_fullname]

                games = api_call_with_week_range(
                    games_api.get_games,
                    start_week,
                    end_week,
                    year=today_year,
                    team=team.school,
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

    SOR_adj_rankings = sorted(team_object_list, key=attrgetter("SOR_adj"), reverse=True)

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

    SPI_final_rankings = sorted(team_object_list, key=attrgetter("SPI"), reverse=True)

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
