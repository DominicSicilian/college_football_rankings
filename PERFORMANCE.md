# Model Performance

> Auto-generated 2026-09-08 22:10 UTC from `data_exports/predictions/spi_game_predictions_2021_2026.csv`.
> Do not edit by hand — run `python generate_performance_report.py` instead.

[Latest Rankings →](RANKINGS.md) &nbsp;•&nbsp; [Season Predictions →](PREDICTIONS.md) &nbsp;•&nbsp; [Back to README →](README.md)

Every prediction is made from the newest ranking that existed **before kickoff** — see
[the ledger design](README.md#prediction-ledger-point-in-time). Nothing here is fit in
hindsight.

## Headline Accuracy

| Scope | Games | Correct | Accuracy |
|:---|---:|---:|---:|
| **All logged games** | 4643 | 3363 | **72.43%** |
| FBS vs FBS _(competitive games)_ | 3995 | 2752 | **68.89%** |
| FBS vs FCS _(near-automatic wins)_ | 648 | 611 | 94.29% |
| _Baseline: home team always wins_ | 4643 | 2949 | 63.51% |
| _Baseline: home team always wins (FBS vs FBS)_ | 3995 | 2339 | 58.55% |

> [!NOTE]
> The headline number includes FBS-vs-FCS games, which are near-automatic wins and lift
> it by roughly three to four points. The FBS-vs-FBS row is the record against genuinely
> competitive opponents.

## Accuracy by Season

| Season | Games | Correct | Accuracy | FBS-vs-FBS Games | FBS-vs-FBS Accuracy |
|:---|---:|---:|---:|---:|---:|
| 2021 | 887 | 643 | 72.49% | 770 | **69.87%** |
| 2022 | 896 | 647 | 72.21% | 776 | **68.94%** |
| 2023 | 910 | 660 | 72.53% | 792 | **68.94%** |
| 2024 | 919 | 658 | 71.60% | 798 | **68.05%** |
| 2025 | 934 | 673 | 72.06% | 808 | **68.19%** |
| 2026 | 97 | 82 | 84.54% | 51 | **76.47%** |

## Accuracy by Segment

| Segment | Games | Correct | Accuracy |
|:---|---:|---:|---:|
| Regular season | 4429 | 3235 | 73.04% |
| Postseason (all bowls) | 214 | 128 | 59.81% |
| CFP playoff games | 31 | 20 | 64.52% |
| National championship | 5 | 3 | 60.00% |

## Calibration

Does an 80%-confidence pick actually win 80% of the time? `Gap` is the actual hit rate
minus the **mean predicted probability** in that band — positive means the model is
underconfident, negative means it overstates its edge.

| Stated Confidence | Games | Mean Predicted | Actual Hit Rate | Gap |
|:---|---:|---:|---:|---:|
| 50–60% | 1299 | 54.97% | 56.04% | +1.07 pts |
| 60–70% | 1039 | 64.81% | 66.51% | +1.70 pts |
| 70–80% | 878 | 74.91% | 75.17% | +0.26 pts |
| 80–90% | 624 | 84.72% | 85.10% | +0.37 pts |
| 90–100% | 803 | 98.54% | 93.77% | -4.77 pts |

| Metric | All Games | FBS vs FBS |
|:---|---:|---:|
| Games | 4643 | 3995 |
| Expected calibration error | 1.61 pts | 0.96 pts |
| Brier score _(lower is better)_ | 0.1815 | 0.2017 |
| Brier skill vs base rate | +0.0911 | +0.0590 |

Expected calibration error is the average gap, weighted by how many games fall in each
band. Brier skill compares the model's probabilities to always predicting the overall
base rate; positive means the probabilities carry real information.

The top band is worth reading carefully. Nearly all of it is FBS-vs-FCS games, which the
model calls at a clamped 99.9% but which actually go the favourite's way about 94% of the
time — the single place the model is meaningfully overconfident. Restricted to FBS-vs-FBS
games the same band lands within a point, which is why the two columns above differ.

## Accuracy by Week (regular season, all years)

| Week | Games | Correct | Accuracy |
|---:|---:|---:|---:|
| 1 | 570 | 472 | 82.81% |
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

## Full Prediction Log

Every logged prediction with the ranking snapshot it came from, one file per season,
collapsible by week. Split out because the combined log is ~400 KB, past the point
where GitHub renders a markdown file reliably.

| Season | Games | Correct | Accuracy | Log |
|:---|---:|---:|---:|:---|
| 2026 | 97 | 82 | 84.54% | [2026 log →](docs/game_log/2026.md) |
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
| Scored games | 4643 |
| FBS-vs-FBS accuracy | 68.89% |
| Generated | 2026-09-08 22:10 UTC |

```bash
python generate_performance_report.py
```
