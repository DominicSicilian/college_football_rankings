import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats as statz

import rankings_functions as rfx # The file containing all necessary functions
import conference_ranker as CR # The file for ranking conferences

from operator import itemgetter, attrgetter
from datetime import datetime

from sportsreference.ncaaf.schedule import Schedule 
from sportsreference.ncaaf.boxscore import Boxscore
from sportsreference.ncaaf.teams import Teams
from sportsreference.ncaaf.conferences import Conferences

#------------------------------------------------------------------------------
#   
#    BEGIN PRINT FORMATTING FUNCTIONS
#
#------------------------------------------------------------------------------

def dashes():
    print('-'*120)
    
def skips():
    print('\n'*5)

def spaced(mystring):
    print(' '*10, mystring, '\n')

#------------------------------------------------------------------------------
#   
#    END PRINT FORMATTING FUNCTIONS
#
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#   
#    BEGIN WELCOME MESSAGE
#
#------------------------------------------------------------------------------

dashes()
skips()

spaced("Welcome to Dominic Sicilian's college football rankings!")
spaced("The code will first examine the nature (N) of a team's games.")
spaced("Then, it will establish rankings for conferences, then consider a team's standing within its conference.")
spaced("This will allow us to estimate a team's strength of record (SOR).")
spaced("Combining N with SOR yields SPI: The Sicilian Power Index!")
spaced("AND THAT'S HOW WE RANK 'EM!")
skips()
spaced("The method and its motivation are detailed in the READ_ME.txt file!")
spaced("Please send any questions or suggestions to: d.sicilian@miami.edu")
spaced("Or contact me on Twitter @DominicSicilian or Instagram @domsicilian")
spaced("ENJOY! AND GO CANES! #TheU")

skips()
dashes()

#------------------------------------------------------------------------------
#   
#    END WELCOME MESSAGE
#
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#   
#    BEGIN GLOBAL VARIABLES
#
#------------------------------------------------------------------------------

# Establishing current day, month, and year for rankings. Adjust to rank for a previous week or year

todays_datetime = os.environ.get('DATE_STRING', str(datetime.today()))
todayy = datetime.fromisoformat(todays_datetime)

today_month = todayy.month
today_day = todayy.day
today_year = todayy.year

sept1 = datetime(today_year, 9, 1)

if todayy < sept1:
    today_year = today_year - 1

#------------------------------------------------------------------------------
#   
#    END GLOBAL VARIABLES
#
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#   
#    BEGIN CLASS DEFINITION
#
#------------------------------------------------------------------------------

# For creating objects for each team. Teams come pre-packaged with objects, but this object is tailored to our needs

class My_Team:
    def __init__(self, name, wins=None, losses=None, conf_wins=None, conf_losses=None, conf_name=None, conf_champ=None, ave_margin=None, points=None, standing_index=None, conf_index=None, overall_index=None, N_adj=None, SOR_adj=None, N_raw=None, SOR_raw=None, SPI=None):

        #From initialization
        self.name = name
        self.conf_name = conf_name
        
        self.wins = wins
        self.losses = losses
        self.conf_wins = conf_wins
        self.conf_losses = conf_losses
        self.conf_champ = conf_champ
        
        self.ave_margin = ave_margin
        self.points = points
        
        self.standing_index = standing_index # This corresponds to the little c in conference ranking index calculation
        self.conf_index = conf_index # This corresponds to the big C in conference ranking index
        
        self.overall_index = overall_index # This is C*c
        
        self.N_adj = N_adj
        self.N_raw = N_raw
        
        self.SOR_adj = SOR_adj
        self.SOR_raw = SOR_raw

        self.SPI = SPI
        
#------------------------------------------------------------------------------
#   
#    END CLASS DEFINITION
#
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#   
#   BEGIN FINDING "NATURE" STATISTIC
#
#------------------------------------------------------------------------------

N_raw_list = []

name_abbrev_converter = {}
team_objects = {} 
team_objects_by_name = {} 
team_object_list = []
    
teams = Teams( today_year )

skips()
spaced('COMPUTING "NATURE" STATISTIC')

for i_it,team in enumerate(teams):
    
    #------------------------------------------------------------------------------
    #  Set up name, abbreviation, conference
    #------------------------------------------------------------------------------
    
    team_abb = team.abbreviation.lower()
    team_fullname = team.name   
    name_abbrev_converter.update({ team_abb: team_fullname})
    
    conference = team.conference.lower()
    
    if conference not in team_objects:
        team_objects.update({conference:[]}) # Note that the team objects will be sorted into their respective conferences

    #------------------------------------------------------------------------------
    #  Compute relevant team stats
    #------------------------------------------------------------------------------

    G = rfx.team_stat(team.games) # total games played
    
    ppg = rfx.team_stat(team.points_per_game) # points scored per game
    P = G*ppg # total points scored    
    papg = rfx.team_stat(team.points_against_per_game) # points allowed per game
    PA = G*papg # total points allowed
    
    A = rfx.ave_margin(G,P,PA) # Average points margin (could be + or -)
    
    passTDpg = rfx.team_stat(team.pass_touchdowns) # Passing TDs scored per game
    passTD = G*passTDpg # Total passing TDs    
    rushTDpg = rfx.team_stat(team.rush_touchdowns) # Rushing TDs scored per game
    rushTD = G*rushTDpg # Total rushing TDs scored
    
    TD = passTD + rushTD # Total offensive TDs scored

    passTDApg = rfx.team_stat(team.opponents_pass_touchdowns) # Pass TDs allowed per game
    passTDA = G*passTDApg # Total pass TDs allowed    
    rushTDApg = rfx.team_stat(team.opponents_rush_touchdowns) # Rush TDs allowed per game
    rushTDA = G*rushTDApg # Total rush TDs allowed
    
    TDA = passTDA + rushTDA # Total TDs allowed on defense
    
    INTfpg = rfx.team_stat(team.opponents_interceptions) # INTs achieved per game on defense
    INTf = G*INTfpg # Total INTs achieved by the defense   
    Ffpg = rfx.team_stat(team.opponents_fumbles_lost) # Fumbles recovered by defense per game 
    Ff = G*Ffpg # Total fumbles recovered by defense
    
    TO_forced = INTf + Ff # Total takeaways    
    
    INTpg = rfx.team_stat(team.interceptions) # INTs thrown by offense per game
    INT = G*INTpg # Total INTs thrown by offense
    Fpg = rfx.team_stat(team.fumbles_lost) # Fumbles lost by offense per game
    Fumbles = G*Fpg # Total fumbles lost by offense
    
    TO_allowed = INT + Fumbles # Total giveaways    
    TM = TO_forced - TO_allowed # Total turnover margin
    
    FIRST_DOWNS_RAW = rfx.team_stat(team.first_downs) # Total first downs achieved
    FD_penalties = rfx.team_stat(team.first_downs_from_penalties) # First downs achieved through opponent penalties

    FIRST_DOWNS = FIRST_DOWNS_RAW - FD_penalties # First downs achieved by offensive plays only    
    OPP_FIRST_DOWNS = rfx.team_stat(team.opponents_first_downs) # Total first downs allowed to opponent on defense, including by penalties
    
    #------------------------------------------------------------------------------
    #  Compute raw NATURE statistic
    #  
    #  NATURE includes Average points margin, TDs, Points scored, TDs allowed, points allowed,
    #  turnover margin, games played, first downs gained, and first downs allowed
    #
    #------------------------------------------------------------------------------
    
    N_raw = rfx.Nature(A, TD,P, TDA,PA, TM,G, FIRST_DOWNS, OPP_FIRST_DOWNS)
    
    wins = rfx.team_total_WL(team)[0]
    losses = rfx.team_total_WL(team)[1]

    conf_wins = rfx.team_conf_WL(team)[0]
    conf_losses = rfx.team_conf_WL(team)[1]
        
    OOC_W = wins-conf_wins
    OOC_L = losses-conf_losses 
    
    conf_champ = rfx.check_for_conf_champ(team_fullname,today_year)
    
    # Create the team object    
    team_obj = My_Team(name=team_fullname, wins=wins, losses=losses, conf_wins=conf_wins, conf_losses=conf_losses, conf_name=conference, conf_champ=conf_champ, N_raw=N_raw, ave_margin=A, points=P)

    # Place it in the correct conference
    team_objects[conference].append(team_obj)
    
    # Put in a large array for easy iteration
    team_object_list.append(team_obj)
    
    # Put in a dictionary to be searched by name
    team_objects_by_name.update({ team_fullname : team_obj })
    
    # Add its raw Nature stat to the total set for rescaling
    N_raw_list.append(team_obj.N_raw)
    
    # Update progress bar
    progress = (i_it+1) / len(teams)
    rfx.update_progress(progress)

    
    

# Now, computing N_adj for all teams, then ranking them
N_raw_max = np.amax(N_raw_list)

for team_object in team_object_list:
    team_object.N_adj = team_object.N_raw / N_raw_max

N_adj_rankings = sorted(team_object_list, key=attrgetter('N_adj'), reverse=True)
 
#------------------------------------------------------------------------------
#   
#   END FINDING "NATURE" STATISTIC
#
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#   
#   BEGIN ASSIGN CONFERENCE RANKINGS
#
#------------------------------------------------------------------------------
skips()
dashes()
skips()
spaced('RANKING CONFERENCES...')


sorted_confs = CR.total_conference_rankings()

conference_database = {}
[conference_database.update({ ConfObj.name : ConfObj }) for ConfObj in sorted_confs]

#------------------------------------------------------------------------------
#   
#   END ASSIGN CONFERENCE RANKINGS
#
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#   
#   BEGIN FINDING "STRENGTH OF RECORD" STATISTIC
#
#------------------------------------------------------------------------------

'''
Compute and update the "Conference Index" (big C) for each conference
This value is based completely on its ranking
'''

conf_rank_value_dict = {}
num_conferences = float(len(sorted_confs))

# Assign C based on conference ranking among other conferences
for index,conf_obj in enumerate(sorted_confs):
    ranking_index = 1.0 - (float(index)/num_conferences)
    conf_obj.conf_index = ranking_index

#------------------------------------------------------------------------------
    
'''
Now, compute the "Team in-Conference Index" (little c) for each team
This value is based on the team's standing within its conference
'''

for conference in team_objects:
    
    #Load the teams in the conference
    conf_team_list = team_objects[conference]
    
    #Rank them to yield the conference standings
    conf_sorted_teams = rfx.multisort(conf_team_list, (('conf_champ',True), ('conf_wins',True),('conf_losses',False),('ave_margin',True), ('points',True)))
    
    #Assign the big C value based on value from conference
    for index,tm_obj in enumerate(conf_sorted_teams):
        ranking_index = 1.0 - (float(index)/ float(len(conf_sorted_teams) ) )
        tm_obj.standing_index = ranking_index
    
    #Assign the little c value based on team standing in conference
    for tm_obj in conf_sorted_teams:
        tm_obj.conf_index = conference_database[conference].conf_index
        tm_obj.overall_index = tm_obj.conf_index * tm_obj.standing_index
        
#------------------------------------------------------------------------------

'''
Compute the "winsCC" list (i.e., the value associated with each win)
and the "lossesCC" list (value associated with each loss)
'''  

skips()
dashes()
skips()
spaced('COMPUTING STRENGTH OF RECORD...')

SOR_raw_list = []

teams = Teams( today_year )

for i_it,team in enumerate(teams):
    
    team_abb = team.abbreviation.lower()
    team_fullname = team.name
    
    team_object = team_objects_by_name[team_fullname] # Load the team object from dictionary
    
    sched = team.schedule # Load the team's schedule from SportsReference
    
    WCC = []
    LCC = []
    
    for game in sched:
        
        gametime = game.datetime 
        
        if gametime < todayy:
            
            against_abb = game.opponent_abbr.lower()
            if against_abb in name_abbrev_converter: # Checking if the team is in FBS or not
                against = name_abbrev_converter[against_abb]
                opp_object = team_objects_by_name[against]
                oppCc = opp_object.overall_index # Obtain opponent's Cc index for outcome's SOR contribution
            
            else:
                oppCc = 0.0 # If not in the dictionary, team is FCS and gets 0 credit towards Cc. No bonus for beating them, heaviest possible punishment for losing
                
            outcome = game.result
    
            if outcome == 'Win':
                WCC.append(oppCc) # SOR contribution from wins
            elif outcome == 'Loss':
                LCC.append(oppCc) # SOR contribution from losses
    
    team_object.winsCC = WCC # Update the team object so we can now compute the SOR_raw
    team_object.lossesCC = LCC
    SOR_raw = rfx.SOR_calc(WCC,LCC) # Compute raw SOR
    
    team_object.SOR_raw = SOR_raw
    
    SOR_raw_list.append(team_object.SOR_raw)
    
    # Update progress bar
    progress = (i_it+1) / len(teams)
    rfx.update_progress(progress)
    
    

# Now, computing SOR_adj for all teams, then ranking them
SOR_raw_max = np.amax(SOR_raw_list)
for team_object in team_object_list:
    team_object.SOR_adj = team_object.SOR_raw / SOR_raw_max

SOR_adj_rankings = sorted(team_object_list, key=attrgetter('SOR_adj'), reverse=True)

#------------------------------------------------------------------------------
#   
#   END FINDING "STRENGTH OF RECORD" STATISTIC
#
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#   
#   BEGIN FINAL RANKINGS
#
#------------------------------------------------------------------------------ 

skips()
dashes()
spaced("SICILIAN POWER INDEX RANKINGS:")
for team_object in team_object_list:
    team_object.SPI = rfx.SPI_calc(team_object.SOR_adj, team_object.N_adj)

SPI_final_rankings = sorted(team_object_list, key=attrgetter('SPI'), reverse=True)

rfx.display_and_save(SPI_final_rankings, sorted_confs)



  


