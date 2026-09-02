# Model Performance

> Auto-generated 2026-09-02 04:05 UTC from `data_exports/predictions/spi_game_predictions_2021_2026.csv`.
> Do not edit by hand — run `python generate_performance_report.py` instead.

[Latest Rankings →](RANKINGS.md) &nbsp;•&nbsp; [Season Predictions →](PREDICTIONS.md) &nbsp;•&nbsp; [Back to README →](README.md)

Every prediction is made from the newest ranking that existed **before kickoff** — see
[the ledger design](README.md#prediction-ledger-point-in-time). Nothing here is fit in
hindsight.

## Headline Accuracy

| Scope | Games | Correct | Accuracy |
|:---|---:|---:|---:|
| **All logged games** | 4554 | 3285 | **72.13%** |
| FBS vs FBS _(competitive games)_ | 3952 | 2717 | **68.75%** |
| FBS vs FCS _(near-automatic wins)_ | 602 | 568 | 94.35% |

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
| Generated | 2026-09-02 04:05 UTC |

```bash
python generate_performance_report.py
```
