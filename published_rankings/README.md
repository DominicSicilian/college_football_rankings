# Published Rankings Archive

This folder stores immutable, timestamped ranking releases for git history.

Each publication run creates:

- A timestamped snapshot folder containing the selected live rankings files
- `manifest.csv` row with publication metadata

Use:

```bash
python publish_weekly_rankings.py --year 2026 --label week3_release
```

By default, the publisher archives the latest `spi_rankings_<year>*` live file and matching companion exports for the same snapshot label when present.
