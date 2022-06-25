# college_football_rankings

To generate current rankings, run ```bash
cfb_full_rankings.py```

To generate rankings at any point in the past, change the environment variable 'DATE_STRING' to a datetime-compatible string of your choice.
Accomplish this straight from Python via a line like this, where you pick any valid year, month, and day integers:
os.environ["DATE_STRING"] = str(datetime(year, month, day, 0, 0, 0, 0))

Will only work from 2001-Present due to lack of data in the 1990s available on the SportsReference database

Full text detailing the algorithm coming soon!
