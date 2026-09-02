# Model Performance

> Auto-generated 2026-09-02 03:18 UTC from `data_exports/predictions/spi_game_predictions_2021_2026.csv`.
> Do not edit by hand — run `python generate_performance_report.py` instead.

[Latest Rankings →](RANKINGS.md) &nbsp;•&nbsp; [Season Predictions →](PREDICTIONS.md) &nbsp;•&nbsp; [Back to README →](README.md)

Every prediction is made from the newest ranking that existed **before kickoff** — see
[the ledger design](README.md#prediction-ledger-point-in-time). Nothing here is fit in
hindsight.

## Headline Accuracy

| Scope | Games | Correct | Accuracy |
|:---|---:|---:|---:|
| **All logged games** | 4554 | 3285 | **72.13%** |
| FBS vs FBS _(benchmark-comparable)_ | 3952 | 2717 | **68.75%** |
| FBS vs FCS _(near-automatic wins)_ | 602 | 568 | 94.35% |

> [!IMPORTANT]
> **Read the second row, not the first, when comparing to other systems.**
> The headline number counts FBS-vs-FCS games, which are near-automatic wins and lift it
> by roughly four points. ThePredictionTracker scores FBS-vs-FBS games only, so every
> benchmark below uses that subset. The game counts match theirs season by season, which
> is what makes the comparison fair.

## Accuracy by Season

| Season | Games | Correct | Accuracy | FBS-vs-FBS Games | FBS-vs-FBS Accuracy |
|:---|---:|---:|---:|---:|---:|
| 2021 | 887 | 643 | 72.49% | 770 | **69.87%** |
| 2022 | 896 | 647 | 72.21% | 776 | **68.94%** |
| 2023 | 910 | 660 | 72.53% | 792 | **68.94%** |
| 2024 | 919 | 658 | 71.60% | 798 | **68.05%** |
| 2025 | 934 | 673 | 72.06% | 808 | **68.19%** |
| 2026 | 8 | 4 | 50.00% | 8 | **50.00%** |

## Accuracy by Segment

| Segment | Games | Correct | Accuracy |
|:---|---:|---:|---:|
| Regular season | 4340 | 3157 | 72.74% |
| Postseason (all bowls) | 214 | 128 | 59.81% |
| CFP playoff games | 31 | 20 | 64.52% |
| National championship | 5 | 3 | 60.00% |

## Calibration

Does an 80%-confidence pick actually win 80% of the time? `Gap` is the hit rate minus the
midpoint of the band — positive means the model is underconfident, negative means it
overstates its edge.

| Model Confidence | Games | Correct | Actual Hit Rate | Gap |
|:---|---:|---:|---:|---:|
| 50–60% | 1289 | 722 | 56.0% | +1.0 pts |
| 60–70% | 1035 | 688 | 66.5% | +1.5 pts |
| 70–80% | 861 | 645 | 74.9% | -0.1 pts |
| 80–90% | 615 | 522 | 84.9% | -0.1 pts |
| 90–100% | 754 | 708 | 93.9% | -1.1 pts |

## Accuracy by Week (regular season, all years)

| Week | Games | Correct | Accuracy |
|---:|---:|---:|---:|
| 1 | 481 | 394 | 81.91% |
| 2 | 410 | 308 | 75.12% |
| 3 | 353 | 279 | 79.04% |
| 4 | 326 | 235 | 72.09% |
| 5 | 291 | 205 | 70.45% |
| 6 | 259 | 163 | 62.93% |
| 7 | 268 | 179 | 66.79% |
| 8 | 280 | 190 | 67.86% |
| 9 | 265 | 186 | 70.19% |
| 10 | 287 | 192 | 66.90% |
| 11 | 295 | 212 | 71.86% |
| 12 | 313 | 241 | 77.00% |
| 13 | 322 | 244 | 75.78% |
| 14 | 167 | 114 | 68.26% |
| 15 | 21 | 14 | 66.67% |
| 16 | 2 | 1 | 50.00% |

## Benchmark: ESPN FPI and the Field

Source: [ThePredictionTracker.com](https://www.thepredictiontracker.com/ncaaresults.php) — scraped by `scripts/fetch_prediction_tracker.py`, ~50 public rating systems per season.
`Implied Rank` is where this model's FBS-vs-FBS accuracy would place in that season's field.

| Season | Games | This Model | ESPN FPI | Δ vs FPI | Vegas Line | Field Best | Field Median | Implied Rank |
|:---|---:|---:|---:|---:|---:|---:|---:|:---|
| 2021 | 770 | **69.87%** | 69.87% | +0.00 | 71.82% | 77.03% | 69.87% | 28 of 55 |
| 2022 | 776 | **68.94%** | 70.35% | -1.41 | 72.04% | 72.04% | 68.86% | 27 of 55 |
| 2023 | 792 | **68.94%** | 72.60% | -3.66 | 73.74% | 74.30% | 72.54% | 50 of 53 |
| 2024 | 798 | **68.05%** | 70.96% | -2.92 | 71.71% | 71.71% | 69.84% | 46 of 56 |
| 2025 | 808 | **68.19%** | 74.02% | -5.82 | 73.89% | 76.11% | 71.78% | 51 of 51 |
| 2026 | 8 | **50.00%** | — | — | 75.00% | 87.50% | 75.00% | 40 of 44 |

### How To Read That

Across 5 seasons with FPI data, this model beat FPI in **0**, tied in **1**, and trailed in **4**. Across the 5 completed seasons it finished above the field median in **1**.

### 2025 Field Detail

Where this model would have placed among every system tracked in 2025, its last full season. 2026 is excluded here — only 8 games have been played, so every system's number is still noise.

| # | System | Pct. Correct | Games |
|---:|:---|---:|---:|
| 1 | Pigskin Index | 76.106% | 339 |
| 2 | ESPN FPI | 74.016% | 762 |
| 3 | Line (Midweek) | 73.886% | 808 |
| 4 | Computer Adjusted Line | 73.886% | 808 |
| 5 | Line (updated) | 73.515% | 808 |
| 6 | Line (opening) | 73.391% | 808 |
| 7 | Slate Fluker | 73.288% | 730 |
| 8 | Sagarin Ratings | 72.896% | 808 |
| 9 | Stephen Kerns | 72.896% | 808 |
| 10 | Talisman Red | 72.671% | 805 |
| 11 | Sagarin Points | 72.649% | 808 |
| 12 | TeamRankings.com | 72.525% | 808 |
| 13 | Sagarin Recent | 72.525% | 808 |
| 14 | Keeper | 72.525% | 808 |
| 15 | Big 200 | 72.525% | 808 |
| 16 | Pi-Ratings Mean | 72.491% | 807 |
| 17 | Dokter Entropy | 72.277% | 808 |
| 18 | Donchess Inference | 72.277% | 808 |
| 19 | Beck Elo | 72.153% | 808 |
| 20 | Sagarin Golden Mean | 72.153% | 808 |
| 21 | David Harville | 72.153% | 808 |
| 22 | FEI Projections | 72.050% | 805 |
| 23 | System Average | 72.030% | 808 |
| 24 | PI-Rate Bias | 71.995% | 807 |
| 25 | Linear Regression | 71.788% | 397 |
| … | … | | |
| 50 | Cleanup Hitter | 68.278% | 807 |
| 51 | **SPI (this repo)** ⬅ | 68.193% | — |

## Full Prediction Log

Every logged prediction with the ranking snapshot it came from, one file per season,
collapsible by week. Split out because the combined log is ~400 KB, past the point
where GitHub renders a markdown file reliably.

| Season | Games | Correct | Accuracy | Log |
|:---|---:|---:|---:|:---|
| 2026 | 8 | 4 | 50.00% | [2026 log →](docs/game_log/2026.md) |
| 2025 | 934 | 673 | 72.06% | [2025 log →](docs/game_log/2025.md) |
| 2024 | 919 | 658 | 71.60% | [2024 log →](docs/game_log/2024.md) |
| 2023 | 910 | 660 | 72.53% | [2023 log →](docs/game_log/2023.md) |
| 2022 | 896 | 647 | 72.21% | [2022 log →](docs/game_log/2022.md) |
| 2021 | 887 | 643 | 72.49% | [2021 log →](docs/game_log/2021.md) |

---

### Where This Comes From

| Field | Value |
|:---|:---|
| Ledger | `data_exports/predictions/spi_game_predictions_2021_2026.csv` |
| Seasons | 2021–2026 |
| Scored games | 4554 |
| FBS-vs-FBS accuracy | 68.75% |
| Benchmark source | `data_exports/benchmarks/prediction_tracker_*.csv` |
| Generated | 2026-09-02 03:18 UTC |

```bash
python scripts/fetch_prediction_tracker.py --year 2026 --refresh
python generate_performance_report.py
```
