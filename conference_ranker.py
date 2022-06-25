import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats as statz

import rankings_functions as rfx # The file containing all necessary functions

from operator import itemgetter, attrgetter
from datetime import datetime

from sportsreference.ncaaf.schedule import Schedule 
from sportsreference.ncaaf.boxscore import Boxscore
from sportsreference.ncaaf.teams import Teams
from sportsreference.ncaaf.conferences import Conferences

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
         
# For creating objects for each conference

class My_Conf:
    def __init__(self, name, p5=None, cvc_wins=0.0, cvc_losses=0.0, conf_index=None, cvc_perc=None):
        self.name = name
        self.p5 = p5
        self.cvc_wins = cvc_wins
        self.cvc_losses = cvc_losses
        self.cvc_perc = cvc_perc
        self.conf_index = conf_index
         
#------------------------------------------------------------------------------
#   
#    END CLASS DEFINITION
#
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#   
#   BEGIN CONFERENCE RANKINGS FUNCTION
#
#------------------------------------------------------------------------------

# Defines a function for computing conference rankings for a given season

def conference_rankings(year):
    
    conf_objects = {} # Dictionary to store conference objects & associate with the conference name
    games_played = []
        
    teams = Teams( year )
    
    '''
    Below I define the Power-5. Note that I punish the Independents (*cough cough* NOTRE DAME *cough cough*) for not playing 
    in a conference by NOT giving them the "Power-5" designation and therefore not allowing the
    Independents "Conference" ranking to ever break the top 5. This is fair considering Notre Dame
    is the only Independent that is truly competitive.
    
    Also, in case of rankings from long-ago seasons, I consider the main 6 conferences pre-2005 to get the top designation
    in those years.
    '''
    power5 = ['acc','big-ten','big-12','pac-12','sec']
    if int(year) < 2005:
        power5 = ['acc','big-ten','big-12','pac-10','sec','big-east']
    
    print("\n-->considering conferences in",year)
    
    for i_it,team in enumerate(teams):
        
        conference = team.conference.lower()
        if conference in power5:
            is_p5 = True
        else:
            is_p5 = False

        if conference not in conf_objects:
             this_conf = My_Conf(name=conference, p5=is_p5) # Create the conference object if not already made
             conf_objects.update({conference:this_conf}) # Associate it with the correct name in the dictionary
        
        # Total W/L
        wins = rfx.team_total_WL(team)[0]
        losses = rfx.team_total_WL(team)[1]
        
        games_played.append(float(wins+losses))
        
        conf_wins = rfx.team_conf_WL(team)[0]
        conf_losses = rfx.team_conf_WL(team)[1]
                           
        OOC_W = wins-conf_wins # The main goal here is to find out of conference wins and losses
        OOC_L = losses-conf_losses
        
        conf_objects[conference].cvc_wins += OOC_W # Update the conference object with its conference-vs-conference wins/losses
        conf_objects[conference].cvc_losses += OOC_L
        
        if (OOC_W + OOC_L) > 0:
            OOC_perc = float(OOC_W) / float(OOC_W + OOC_L)
        else:
            OOC_perc = 0.0
        
        conf_objects[conference].cvc_perc = OOC_perc
        
        # Update progress bar
        progress = (i_it+1)/ len(teams)
        rfx.update_progress(progress)
    
    mean_games_played = np.mean(games_played)
    
    return [conf_objects, mean_games_played ]# return the ranked list of conference objects and length of season

#------------------------------------------------------------------------------
#   
#   END CONFERENCE RANKINGS FUNCTION
#
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#   
#   BEGIN ASSIGN CONFERENCE RANKINGS FUNCTION
#
#------------------------------------------------------------------------------        

def total_conference_rankings():
    
    combined_conf_objects = {}
    
    # First, establish conference stats for previous season
    
    last_year = conference_rankings(today_year-1)
    LY_confs = last_year[0]
    
    this_year = conference_rankings(today_year)
    TY_confs = this_year[0]
    TY_games = this_year[1]
    
    LYW = (8.0 - TY_games) / 8.0 # Establishing Last Year's Weight (LYW); After 8 games, Last Year no longer has an impact
    if LYW < 0:
        LYW = 0.0
    TYW = 1.0 - LYW # This Year's Weight (TYW) is the same
    
    # Account for last year's wins and losses with proper Last Year weights
    
    for conference in LY_confs:
        
        that_conf = LY_confs[conference]
        
        this_conf = My_Conf(name=conference, p5=that_conf.p5, cvc_wins=LYW*that_conf.cvc_wins, cvc_losses=LYW*that_conf.cvc_losses)
        combined_conf_objects.update({conference:this_conf})
    
    # Add data for this year's wins and losses with proper This Year weights
    
    
    print("\nTeams have played an average of", round(TY_games,2), "this year, so last year is weighted by", round(LYW,2))
    print("\n-->computing W/L stats between conferences...")
    for i_it,conference in enumerate(TY_confs):
        
        that_conf = TY_confs[conference]
        
        if conference not in combined_conf_objects:
            
            #If the conference is not already listed, its weight should be 1.0, so we do not multiply by any weights
        
            this_conf = My_Conf(name=conference, p5=that_conf.p5, cvc_wins=that_conf.cvc_wins, cvc_losses=that_conf.cvc_losses)
            combined_conf_objects.update({conference:this_conf})
        
        else:
            
            this_conf = combined_conf_objects[conference]
            
            this_conf.cvc_wins += TYW*that_conf.cvc_wins
            this_conf.cvc_losses += TYW*that_conf.cvc_losses
            
        
        this_conf.cvc_perc = this_conf.cvc_wins / (this_conf.cvc_wins + this_conf.cvc_losses)
            
        this_conf.p5 = that_conf.p5 # Making sure that only current Power-5 teams have the Power-5 distinction
        if this_conf.p5 == None:
            this_conf.p5 = False
        
        # Update progress bar
        progress = (i_it+1) / len(TY_confs)
        rfx.update_progress(progress)
    
    # Now, rank them
        
    myconfs = []
    [myconfs.append(combined_conf_objects[conference]) for conference in TY_confs] # Include only conferences that exist now
    
    sorted_confs = rfx.multisort(myconfs, (('p5',True), ('cvc_perc',True),('cvc_wins',True),('cvc_losses',False) ))
    
    return sorted_confs

#------------------------------------------------------------------------------
#   
#   END ASSIGN CONFERENCE RANKINGS FUNCTION
#
#------------------------------------------------------------------------------