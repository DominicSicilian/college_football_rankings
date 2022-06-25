# Sicilian Power Rankings

Welcome to the Sicilian Power Rankings code repository! Below is a brief introduction, motivation, and description of the algorithm.

## Background & Purpose

Division I-A (FBS) college football is perhaps the most difficult sport in which to rank teams, and as a result, unsurprisingly, every ranking system is met with controversy and frustration. Due to the large number of teams (~130) but small number of regular season games (~12), as well as the wide variance in programs' resources & player/coaching talent, it is nearly impossible to devise a fair system that doesn't involve wildly subjective metrics (like "the eye test"), particularly for the postseason.

Here, by formulating my own algorithm and data pulled from the [```SportsReference```](https://pypi.org/project/sportsreference/) Python API, I have given my best attempt at establishing a more objective ranking system for college football teams. The goal is not necessarily to predict the winner of a given game--a task optimized by ESPN's Football Power Index (FPI)--but rather to assign a merit-based ranking to each team for establishing postseason worthiness. There should, of course, be a correlation between the relative ranking of two teams in a given game and the winner of that game, so my rankings do correctly predict the winner of a game >70% of the time, falling only a small margin short of FPI's predictive power.

## The Algorithm



## Running the code

To generate current rankings, run 

```bash
cfb_full_rankings.py
```

To generate rankings at any point in the past, change the environment variable ```DATE_STRING``` to a ```datetime```-compatible string of your choice.

```python
# Pick any valid year, month, and day strings
os.environ["DATE_STRING"] = str(datetime(year, month, day, 0, 0, 0, 0))
```

*Note: this is only compatible with seasons 2001-Present due to lack of data in the 1990s and prior available on the ```SportsReference``` database.*
