# Sicilian Power Rankings

Welcome to the Sicilian Power Rankings (**SPR**) code repository! Below is a brief introduction, motivation, and description of the algorithm.

## Background & Purpose

Division I-A (FBS) college football is perhaps the most difficult sport in which to rank teams, and as a result, unsurprisingly, every ranking system is met with controversy and frustration. Due to the large number of teams (~130) but small number of regular season games (~12), as well as the wide variance in programs' resources & player/coaching talent, it is nearly impossible to devise a fair system that doesn't involve wildly subjective metrics (like "the eye test"), particularly for the postseason.

Here, by formulating my own algorithm and data pulled from the [```SportsReference```](https://pypi.org/project/sportsreference/) Python API, I have given my best attempt at establishing a more objective ranking system for college football teams. The goal is not necessarily to predict the winner of a given game--a task optimized by the [ESPN Football Power Index (FPI)](https://www.espn.com/college-football/fpi)--but rather to assign a merit-based ranking to each team for establishing postseason worthiness. There should, of course, be a correlation between the relative ranking of two teams in a given game and the winner of that game, so my rankings do correctly predict the winner of a game >70% of the time (as discussed more thoroughly below), falling only a small margin short of FPI's predictive power (~75% accurate over the past 10 seasons). The inspiration I have drawn from ESPN FPI is evident in the metric computed to determine the rankings--a final number with a maximum value of 100 called the Sicilian Power Index (SPI), by which the teams are ranked in order from highest SPI to lowest SPI.

# The Algorithm

## Main Criteria and Description

There are two main criteria for **SPR**: **Strength of Record (SOR)** and **Nature of Gameplay**.

**SOR** is determined using my own methodology and considers the quality of a team's opponents in both its wins and losses, but otherwise does not look further than whether the team won or lost. With SOR, beating a top opponent is equivalent regardless of the final score.

**Nature of Gameplay**, on the other hand, looks at the *nature* of those wins and losses--so, it makes sure beating that top opponent by 35 is more valuable than winning on a last-second field goal.

Together, these two metrics account for both the quality of opponents you won (or lost) against **AND** the level of dominance you displayed in those wins (or level of ineptitude you displayed in those losses), which paints the most comprehensive picture of a team. This is not a new idea, as all rankings seek to do this, including the current CFP Committee-based rankings.

What is notable here, however, is using a mathematical algorithm for both aspects to aggressively minimize the level of subjectivity. For example, rankings such as CFP Committee are often criticized for giving teams high rankings for beating other highly-ranked teams (the same idea as **SOR**)--however, this is a self-perpetuating logical loop, as the other highly-ranked teams were granted that ranking by that same Committee in the first place.

Additionally, the infamous "eye test" is applied by the Committee, which is entirely subjective and causes constant rankings controversy. However, it is undoubtedly an important criteria, since almost any rational person would agree that, if there are two teams with nearly identical SORs, but one of them blows everyone out while the other barely wins most games, the more dominant team should clearly be ranked higher. That's why I use the formulaic **Nature of Gameplay** criteria to more objectively encapsulate this important aspect of rankings.

## SOR

### Defining a notion of "strength" independent of the rankings

The first step of SOR is to protect against the self-perpetuating nature of traditional SOR and SOR-like metrics. This is done by using conference standings and ranking each conference among the other conferences to give an estimated level of strength to each team. A conference's rank is determined based on the total **non-conference** wins and losses of all teams in that conference, which gives that conference's total record vs. other conferences.

One caveat that is somewhat subjective is all Power-5 (P5) conferences are ranked above all non-P5 conferences, regardless of W-L. So, effectively the top 5 is determined by the non-conference W-L of the P5 conferences, and the remaining rankings (6 and beyond) are determined by the non-conference W-L of the other conferences. FBS Independents are considered here as a single non-P5 conference. The strength of a conference is then described on a scale from 0-1 (with **1** being the **strongest**) with equal intervals between conferences.

Teams are then ranked within their own conferences by their in-conference wins and losses, just as in the traditional conference standings (except here, divisions within conferences are entirely ignored). One exception is, once a conference champion is determined, the conference champion is guaranteed the top ranking in its own conference, even if another team manages to have a better in-conference W-L. *Note: Currently this feature is only being implemented for the most recent season (2021), but soon it will be fully available for all past seasons.*

Then, each team's ***relative** strength within their own conference* is described on a scale from 0-1, mimicking the style of the conference strength scale. Finally, a team's ***overall** strength* (hereafter referred to as the **Strength Coefficient**) is found by multiplying the conference's strength by the team's in-conference strength to give a final value, also guaranteed to be between 0-1. Note that early in the season, when few games have been played, the previous season's conference play is considered. As the season progresses, the previous season carries less and less weight until eventually it is no longer needed. This is inspired by FPI's similar use of the previous season's data.

### Using strength of opponents to compute SOR

We can determine the strength of each team's record by considering the **Strength Coefficient** of each opponent that team has faced, as well as whether the team beat those opponents or not.

For a Win, the team will be credited an amount of points equal to the opponent's Strength Coefficient. Beating the best team in the best conference will give the maximum possible reward (1 point), while beating a bad team in a weak conference will give a minimal reward (~0 points).

For a Loss, the team will be punished according to the opponent's Strength Coefficient. In this case, the penalty will be the *complement* of the opponent's Strength Coefficient, i.e. ```1 - Opponent's Strength Coefficient``` will be *subtracted* from the team's SOR. Losing to a bad team in a weak conference will therefore give the maximum possible penalty (subtracting ~1 point), while losing to the best team in the best conference will give no penalty (and losing to a great team in a top conference will also give a near-zero penalty).

The SOR is found by adding up the rewards/penalties from all games played.

## Nature of Gameplay

*Section in progress*

## Putting it all together

*Section in progress*

## Evaluation

![SPI-based Prediction Accuracy](plots/Margin_vs_SPI.png)

## Running the code

After cloning the repository, to generate current rankings, run

```bash
$ python cfb_full_rankings.py
```

To generate rankings at any given date in the past, before running the code you can change the environment variable ```DATE_STRING``` to a ```datetime```-compatible string of your choice. For example, this can be done from ```python``` using

```python
# Pick any valid year, month, and day strings
os.environ["DATE_STRING"] = str(datetime(year, month, day, 0, 0, 0, 0))
```

or the ```bash``` command line using the following (with an arbitrary past date shown)

```bash
$ export DATETIME_STRING="2019-11-30"
```

*Note: this is only compatible with seasons 2001-Present due to lack of data in the 1990s and prior available on the ```SportsReference``` database.*
