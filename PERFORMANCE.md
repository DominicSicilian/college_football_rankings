# Model Performance

> Auto-generated 2026-09-07 19:51 UTC from `data_exports/predictions/spi_game_predictions_2020_2026.csv`.
> Do not edit by hand — run `python generate_performance_report.py` instead.

[Latest Rankings →](RANKINGS.md) &nbsp;•&nbsp; [Season Predictions →](PREDICTIONS.md) &nbsp;•&nbsp; [Back to README →](README.md)

Every prediction is made from the newest ranking that existed **before kickoff** — see
[the ledger design](README.md#prediction-ledger-point-in-time). Nothing here is fit in
hindsight.

## Headline Accuracy

| Scope | Games | Correct | Accuracy |
|:---|---:|---:|---:|
| **All logged games** | 4546 | 3215 | **70.72%** |
| FBS vs FBS _(competitive games)_ | 3944 | 2647 | **67.11%** |
| FBS vs FCS _(near-automatic wins)_ | 602 | 568 | 94.35% |

> [!NOTE]
> The headline number includes FBS-vs-FCS games, which are near-automatic wins and lift
> it by roughly three to four points. The FBS-vs-FBS row is the record against genuinely
> competitive opponents.

## Accuracy by Season

| Season | Games | Correct | Accuracy | FBS-vs-FBS Games | FBS-vs-FBS Accuracy |
|:---|---:|---:|---:|---:|---:|
| 2021 | 887 | 628 | 70.80% | 770 | **67.92%** |
| 2022 | 896 | 613 | 68.42% | 776 | **64.56%** |
| 2023 | 910 | 662 | 72.75% | 792 | **69.19%** |
| 2024 | 919 | 652 | 70.95% | 798 | **67.29%** |
| 2025 | 934 | 660 | 70.66% | 808 | **66.58%** |

## Accuracy by Segment

| Segment | Games | Correct | Accuracy |
|:---|---:|---:|---:|
| Regular season | 4332 | 3087 | 71.26% |
| Postseason (all bowls) | 214 | 128 | 59.81% |
| CFP playoff games | 31 | 19 | 61.29% |
| National championship | 5 | 3 | 60.00% |

## Calibration

Does an 80%-confidence pick actually win 80% of the time? `Gap` is the actual hit rate
minus the **mean predicted probability** in that band — positive means the model is
underconfident, negative means it overstates its edge.

| Stated Confidence | Games | Mean Predicted | Actual Hit Rate | Gap |
|:---|---:|---:|---:|---:|



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
| 1 | 473 | 384 | 81.18% |
| 2 | 410 | 311 | 75.85% |
| 3 | 353 | 269 | 76.20% |
| 4 | 326 | 230 | 70.55% |
| 5 | 291 | 197 | 67.70% |
| 6 | 259 | 165 | 63.71% |
| 7 | 268 | 175 | 65.30% |
| 8 | 280 | 186 | 66.43% |
| 9 | 265 | 182 | 68.68% |
| 10 | 287 | 190 | 66.20% |
| 11 | 295 | 204 | 69.15% |
| 12 | 313 | 226 | 72.20% |
| 13 | 322 | 233 | 72.36% |
| 14 | 167 | 122 | 73.05% |
| 15 | 21 | 12 | 57.14% |
| 16 | 2 | 1 | 50.00% |

## Full Prediction Log

Every logged prediction with the ranking snapshot it came from, one file per season,
collapsible by week. Split out because the combined log is ~400 KB, past the point
where GitHub renders a markdown file reliably.

| Season | Games | Correct | Accuracy | Log |
|:---|---:|---:|---:|:---|
| 2025 | 934 | 660 | 70.66% | [2025 log →](docs/game_log/2025.md) |
| 2024 | 919 | 652 | 70.95% | [2024 log →](docs/game_log/2024.md) |
| 2023 | 910 | 662 | 72.75% | [2023 log →](docs/game_log/2023.md) |
| 2022 | 896 | 613 | 68.42% | [2022 log →](docs/game_log/2022.md) |
| 2021 | 887 | 628 | 70.80% | [2021 log →](docs/game_log/2021.md) |

---

### Where This Comes From

| Field | Value |
|:---|:---|
| Ledger | `data_exports/predictions/spi_game_predictions_2020_2026.csv` |
| Seasons | 2021–2025 |
| Scored games | 4546 |
| FBS-vs-FBS accuracy | 67.11% |
| Generated | 2026-09-07 19:51 UTC |

```bash
python generate_performance_report.py
```
