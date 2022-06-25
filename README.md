# college_football_rankings

To generate current rankings, run 

```bash
cfb_full_rankings.py
```

To generate rankings at any point in the past, change the environment variable ```DATE_STRING``` to a ```datetime```-compatible string of your choice.

```python
# Pick any valid year, month, and day strings
os.environ["DATE_STRING"] = str(datetime(year, month, day, 0, 0, 0, 0))
```

Will only work from 2001-Present due to lack of data in the 1990s available on the ```SportsReference``` database.
