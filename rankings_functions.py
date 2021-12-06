import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats as statz

from operator import itemgetter, attrgetter

from datetime import datetime

from sportsreference.ncaaf.schedule import Schedule 
from sportsreference.ncaaf.boxscore import Boxscore
from sportsreference.ncaaf.teams import Teams
from sportsreference.ncaaf.conferences import Conferences

#------------------------------------------------------------------------------
#   
#    BEGIN FUNCTION DEFINITIONS
#
#------------------------------------------------------------------------------

'''
Basic print formatting functions
'''

def dashes():
    print('-'*120)
    
def skips():
    print('\n'*5)

def spaced(mystring):
    print(' '*10, mystring, '\n')

def break_rank():
    print(' '*10, '-'*60)

def miami():
    print(' '*10, '*'*60)

#------------------------------------------------------------------------------

'''
Controlled reading of any team stat from the SportsReference database
'''

def team_stat(sports_ref_stat):
    
    if sports_ref_stat == None:
        mystat = 0.0
    elif np.isnan(sports_ref_stat):
        mystat = 0.0
    else:
        mystat = float(sports_ref_stat)

        
    return mystat
    
#------------------------------------------------------------------------------

'''
Compute Average Margin of victory based on games played, points, and points allowed
'''

def ave_margin(G,P,PA):
    
    if G == 0.0:
        A = 0.0
    else:
        A = (P - PA) / G
    
    return A
    
#------------------------------------------------------------------------------

'''
Compute the conference record for an FBS-Independent team,
treating the Independents as a conference.
'''
    
def indy_conf(sched, date_time_object):
    
    conf_wins = 0.0
    conf_losses = 0.0
        
    for game in sched:
        
        if game.opponent_conference == 'independent':
        
            gametime = game.datetime 
            
            if gametime < date_time_object:
                outcome = game.result
                if outcome == 'Win':
                    conf_wins = conf_wins + 1.0
                elif outcome == 'Loss':
                    conf_losses = conf_losses + 1.0
                    
    return [conf_wins, conf_losses]
    
#------------------------------------------------------------------------------

'''
Compute the conference record for a team
'''

def team_conf_WL(team):
    
    if team.conference == 'independent': # If team is Independent, treat that as a conference and manually compute "conference" record

        conf_WL = indy_conf(team.schedule, datetime.today())            
        conf_wins = conf_WL[0]
        conf_losses = conf_WL[1]
        
    else: # Otherwise, grab the values from the SportsReference team object
        
        conf_wins = team_stat(team.conference_wins)
        conf_losses = team_stat(team.conference_losses)
    
    return [conf_wins, conf_losses]

#------------------------------------------------------------------------------

'''
For seasons that are finished, check if a team won its conference title.
Only seasons with known conference champs will have existing data, so all
teams will get a conf_champs=False for a season in progress.
'''

def check_for_conf_champ(team_fullname, year):
    
    conf_champs_file = 'conf_champs/conf_champs_'+str(year)+'.csv'
    if os.path.exists(conf_champs_file):
        df = pd.read_csv(conf_champs_file)

        champs = df.champion.tolist()
        
        if team_fullname in champs:
            conf_champ = True
        else:
            conf_champ = False
    
    else:
        conf_champ = False
    
    return conf_champ

#------------------------------------------------------------------------------
    
'''
Defining a function to print a progress bar.
See https://www.programcreek.com/python/?CodeExample=progress+update 
'''
 
def update_progress(progress):
    barLength = 50 # Modify this to change the length of the progress bar
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
    block = int(round(barLength*progress))
    text = "\rPercent: [{0}] {1}% {2}".format( "#"*block + "-"*(barLength-block), round(progress*100,1), status)
    sys.stdout.write(text)
    sys.stdout.flush()
    
#------------------------------------------------------------------------------

'''
Order a list of team objects (xs) according to the specifications given 
'''

def multisort(xs, specs):
    for key, reverse in reversed(specs):
        xs.sort(key=attrgetter(key), reverse=reverse)
    return xs

#------------------------------------------------------------------------------
    
''' 
This calculates the strength of record, given a list of opponents and W/L results.

Instructions:
Input alist of Cc values for wins and a list of Cc values for losses, where
Cc is the opponent's in-Conference ranking value (i.e., conference standings index times overall Conference index)
'''
 
def SOR_calc(wins,losses):
    
    v_sum = 0.0
    d_sum = 0.0
    
    for Cc in wins:
        v_sum = v_sum + Cc
    
    for Cc in losses:
        d_sum = d_sum + (Cc - 1.0)
    
    S_raw = v_sum + d_sum
    
    return S_raw

#------------------------------------------------------------------------------

'''
This calculates the "Nature" metric of a team's success given the following stats:
    
    A = average points margin: (points scored - points allowed) / (total games played)
    TD = # of TDs scored
    P = total points scored
    
    TD = # of TDs allowed
    PA = total points allowed
    
    TM = turnover margin
    G = total games played
    
    FIRST_DOWNS = # of first downs gained
    OPP_FIRST_DOWNS = # of first downs allowed

Here, we return the raw Nature value (N_raw) to be rescaled in the main file.
'''

def Nature(A, TD,P, TDA,PA, TM,G, FIRST_DOWNS, OPP_FIRST_DOWNS):
    
    if G == 0.0:
        N_raw = A
    elif P == 0.0:
        if PA != 0.0:
            N_raw = A + ( 50.0*( 0.0  - ((TDA * 7.0)/PA) )  + TM/G  )
        elif PA == 0.0:
            N_raw = A + TM/G
    elif PA == 0.0:
        if P != 0:
            N_raw = A + ( 50.0*( ((TD * 7.0)/P)  )  + TM/G  )
    else:
        N_raw = A + ( 50.0*( ((TD * 7.0)/P)  - ((TDA * 7.0)/PA) )  + TM/G  )
   
    return N_raw

#------------------------------------------------------------------------------

'''
Now, use the adjusted Nature (N_adj) to compute the final SPI for the team
Here we use 65% weighting on the SOR and 35% weighting on the Nature of victories
This is a simple estimated choice that will be optimized for future releases
'''

def SPI_calc(SOR,N_adj):
    
    Psi = 100.0 * ( 0.65*SOR + 0.35*N_adj )
    
    return Psi

#------------------------------------------------------------------------------

'''
Display rankings and make a pandas DataFrame to save results
'''

def display_and_save(SPI_final_rankings, conf_rankings):
    
    rankings_database = {}
    
    # Printing results for top 25

    print("%9s  %2s  %24s  %6s  %5s" % (" ", "Rk", "Team", "Record", "SPI" ) )
    break_rank()
    for i_it,tm_obj in enumerate(SPI_final_rankings):
        
        #Collecting data needed for basic rundown
        
        ranking = i_it + 1
        name = tm_obj.name
        SPI = tm_obj.SPI
        
        wins = int(tm_obj.wins)
        losses = int(tm_obj.losses)
        
        if name == 'Miami (FL)':
            miami()
        
        #Printing basic results for top 25
        
        print("%9s  %2i  %24s  %2i -%2i  %5.2f" % (" ", ranking, name, wins, losses, SPI) )
        if ranking == 4:
            break_rank()
        if ranking == 25:
            break_rank()
            break_rank()
            
        if name == 'Miami (FL)':
            miami()        
        
        #Collecting the rest of the data
        
        conf_name = tm_obj.conf_name
        conf_wins = tm_obj.conf_wins
        conf_losses = tm_obj.conf_losses
        
        for j_it,conf_obj in enumerate(conf_rankings):
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
        
        all_team_data = [ name,
                         wins, losses, conf_name, conf_ranking, conf_wins, conf_losses,
                         C_index, c_index, Cc,
                         N_raw, N_adj,
                         SOR_raw, SOR_adj,
                         SPI
                         ]
        
        rankings_database.update({ranking:all_team_data})
         
    skips()
    dashes()
    
    df_index = [ 'Team Name','W', 'L',
                'Conf.', 'Conf. Rank', 'Conf. W', 'Conf. L',
                'C', 'c', 'Cc',
                'N_raw', 'N_adj',
                'SOR_raw', 'SOR_adj',
                'SPI'
                ]
    
    df_database = pd.DataFrame(rankings_database, index=df_index)
    df_database = df_database.transpose()
    df_database.to_csv('SPI_Rankings.csv',sep=',')
    

#------------------------------------------------------------------------------
#   
#    END FUNCTION DEFINITIONS
#
#------------------------------------------------------------------------------
