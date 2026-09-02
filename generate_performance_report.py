"""Build PERFORMANCE.md: model accuracy and the full prediction log.

Two sections:

* Accuracy, sliced by season, season type, week, and confidence band.
* The full prediction ledger, collapsible by season and week.

FBS-vs-FBS accuracy is reported alongside the headline number because
FBS-vs-FCS games are near-automatic wins that lift the overall figure by
roughly three to four points; the split shows how much of the record comes
from genuinely competitive games.
"""

import argparse
import csv
import datetime as dt
import glob
import os
import re
from typing import Dict, List, Optional, Tuple

from model_config import clamp_win_prob_pct

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_EXPORTS_DIR = os.path.join(BASE_DIR, "data_exports")
PREDICTIONS_DIR = os.path.join(DATA_EXPORTS_DIR, "predictions")
PERFORMANCE_MD = os.path.join(BASE_DIR, "PERFORMANCE.md")
GAME_LOG_DIR = os.path.join(BASE_DIR, "docs", "game_log")




def read_csv(path: str) -> List[Dict[str, str]]:
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def to_float(value, default=None):
    try:
        if value is None or str(value).strip() in ("", "nan", "None"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value, default=None):
    result = to_float(value, None)
    return default if result is None else int(result)


def generated_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def md_escape(value) -> str:
    return str(value).replace("|", "\\|")


def pct(value: Optional[float], digits: int = 1) -> str:
    return "—" if value is None else f"{100.0 * value:.{digits}f}%"


# ---------------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------------

def widest_ledger() -> Optional[str]:
    """The most recently written prediction ledger, preferring wider coverage.

    Sorting by span alone picks up stale files: a months-old 2020-2026 export
    outranks a freshly rebuilt 2021-2026 one and silently reports pre-fix
    numbers. Freshness is ranked first, using a one-day bucket so that files
    written by the same run are then separated by how many seasons they cover.
    """
    candidates = []
    for path in glob.glob(os.path.join(PREDICTIONS_DIR, "spi_game_predictions_*.csv")):
        m = re.search(r"spi_game_predictions_(\d{4})_(\d{4})\.csv$", os.path.basename(path))
        if not m:
            continue
        span = int(m.group(2)) - int(m.group(1))
        day_bucket = int(os.path.getmtime(path) // 86400)
        candidates.append((day_bucket, span, os.path.getmtime(path), path))
    if not candidates:
        return None
    return max(candidates)[3]


def load_ledger(path: str) -> List[Dict]:
    rows = []
    for row in read_csv(path):
        correct = to_float(row.get("correct"))
        home_class = (row.get("home_classification") or "").strip().lower()
        away_class = (row.get("away_classification") or "").strip().lower()
        rows.append(
            {
                "year": to_int(row.get("year"), 0),
                "week": to_int(row.get("week"), 0),
                "season_type": (row.get("season_type") or "regular").strip(),
                "start_date": (row.get("start_date") or "").strip(),
                "home_team": (row.get("home_team") or "").strip(),
                "away_team": (row.get("away_team") or "").strip(),
                "home_points": to_float(row.get("home_points")),
                "away_points": to_float(row.get("away_points")),
                "predicted_winner": (row.get("predicted_winner") or "").strip(),
                "actual_winner": (row.get("actual_winner") or "").strip(),
                "correct": correct,
                "scored": correct is not None,
                "fbs_vs_fbs": home_class == "fbs" and away_class == "fbs",
                "home_win_prob": to_float(row.get("home_win_prob_home_adj_pct")),
                "ranking_source": (row.get("ranking_source") or "").strip(),
                "is_playoff": str(row.get("is_playoff", "")).strip().lower() == "true",
                "is_title": str(row.get("is_national_championship", "")).strip().lower() == "true",
            }
        )
    return rows


def accuracy(rows: List[Dict]) -> Tuple[int, int, Optional[float]]:
    scored = [r for r in rows if r["scored"]]
    if not scored:
        return 0, 0, None
    hits = int(sum(r["correct"] for r in scored))
    return len(scored), hits, hits / len(scored)


def confidence_for(row: Dict) -> Optional[float]:
    """Model confidence in its own pick, as a 50-100% number.

    Clamped the same way the dashboard and the schedule reports clamp, so a
    lopsided FBS-vs-FCS matchup reads 99.9% rather than a flat 100%.
    """
    prob = row["home_win_prob"]
    if prob is None:
        return None
    picked_home = row["predicted_winner"] == row["home_team"]
    return clamp_win_prob_pct(prob if picked_home else 100.0 - prob)


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------

def summary_table(rows: List[Dict]) -> str:
    lines = [
        "| Scope | Games | Correct | Accuracy |",
        "|:---|---:|---:|---:|",
    ]
    all_n, all_c, all_a = accuracy(rows)
    fbs = [r for r in rows if r["fbs_vs_fbs"]]
    f_n, f_c, f_a = accuracy(fbs)
    non = [r for r in rows if not r["fbs_vs_fbs"]]
    n_n, n_c, n_a = accuracy(non)

    lines.append(f"| **All logged games** | {all_n} | {all_c} | **{pct(all_a, 2)}** |")
    lines.append(f"| FBS vs FBS _(competitive games)_ | {f_n} | {f_c} | **{pct(f_a, 2)}** |")
    lines.append(f"| FBS vs FCS _(near-automatic wins)_ | {n_n} | {n_c} | {pct(n_a, 2)} |")
    return "\n".join(lines)


def by_year_table(rows: List[Dict]) -> str:
    years = sorted({r["year"] for r in rows if r["year"]})
    lines = [
        "| Season | Games | Correct | Accuracy | FBS-vs-FBS Games | FBS-vs-FBS Accuracy |",
        "|:---|---:|---:|---:|---:|---:|",
    ]
    for year in years:
        yr = [r for r in rows if r["year"] == year]
        n, c, a = accuracy(yr)
        fn, fc, fa = accuracy([r for r in yr if r["fbs_vs_fbs"]])
        lines.append(f"| {year} | {n} | {c} | {pct(a, 2)} | {fn} | **{pct(fa, 2)}** |")
    return "\n".join(lines)


def by_season_type_table(rows: List[Dict]) -> str:
    buckets = [
        ("Regular season", [r for r in rows if r["season_type"] == "regular"]),
        ("Postseason (all bowls)", [r for r in rows if r["season_type"] == "postseason"]),
        ("CFP playoff games", [r for r in rows if r["is_playoff"]]),
        ("National championship", [r for r in rows if r["is_title"]]),
    ]
    lines = ["| Segment | Games | Correct | Accuracy |", "|:---|---:|---:|---:|"]
    for label, bucket in buckets:
        n, c, a = accuracy(bucket)
        if n == 0:
            continue
        lines.append(f"| {label} | {n} | {c} | {pct(a, 2)} |")
    return "\n".join(lines)


def by_week_table(rows: List[Dict]) -> str:
    regular = [r for r in rows if r["season_type"] == "regular" and r["scored"]]
    weeks = sorted({r["week"] for r in regular if r["week"]})
    lines = ["| Week | Games | Correct | Accuracy |", "|---:|---:|---:|---:|"]
    for week in weeks:
        n, c, a = accuracy([r for r in regular if r["week"] == week])
        lines.append(f"| {week} | {n} | {c} | {pct(a, 2)} |")
    return "\n".join(lines)


def calibration_table(rows: List[Dict]) -> str:
    """Does a stated confidence actually deliver that hit rate?"""
    bands = [(50, 60), (60, 70), (70, 80), (80, 90), (90, 100.01)]
    lines = [
        "| Model Confidence | Games | Correct | Actual Hit Rate | Gap |",
        "|:---|---:|---:|---:|---:|",
    ]
    for low, high in bands:
        bucket = []
        for row in rows:
            if not row["scored"]:
                continue
            conf = confidence_for(row)
            if conf is not None and low <= conf < high:
                bucket.append(row)
        n, c, a = accuracy(bucket)
        if n == 0:
            continue
        midpoint = (low + min(high, 100.0)) / 2.0 / 100.0
        gap = None if a is None else a - midpoint
        gap_text = "—" if gap is None else f"{gap * 100:+.1f} pts"
        upper = min(high, 100.0)
        lines.append(f"| {low:.0f}–{upper:.0f}% | {n} | {c} | {pct(a, 1)} | {gap_text} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# game log
# ---------------------------------------------------------------------------

def format_date(raw: str) -> str:
    if not raw:
        return "TBD"
    text = str(raw).strip().replace("Z", "+00:00")
    for candidate in (text, text.split("T")[0], text.split(" ")[0]):
        try:
            return dt.datetime.fromisoformat(candidate).strftime("%b %d")
        except ValueError:
            continue
    return str(raw)[:10]


def season_log_body(year: int, year_rows: List[Dict]) -> str:
    n, c, a = accuracy(year_rows)
    out = [
        f"# {year} Prediction Log",
        "",
        f"> Auto-generated {generated_stamp()}. "
        "Run `python generate_performance_report.py` to refresh.",
        "",
        f"**{n} scored games, {c} correct ({pct(a, 2)})** &nbsp;•&nbsp; "
        "[← Performance summary](../../PERFORMANCE.md) &nbsp;•&nbsp; "
        "[README](../../README.md)",
        "",
        "`Conf.` is the model's probability for the side it picked. `Ranking Used` is the",
        "snapshot that was newest before kickoff — the prediction could not have seen the result.",
        "",
    ]
    out.append(week_blocks(year_rows))
    return "\n".join(out)


def week_blocks(year_rows: List[Dict]) -> str:
    out = []
    if True:
        for season_type in ("regular", "postseason"):
            block = [r for r in year_rows if r["season_type"] == season_type]
            if not block:
                continue
            weeks = sorted({r["week"] for r in block})
            for week in weeks:
                wk = [r for r in block if r["week"] == week]
                wn, wc, wa = accuracy(wk)
                label = f"Week {week}" if season_type == "regular" else f"Postseason week {week}"
                header = (
                    f"{label} — {wn} scored, {wc} correct ({pct(wa, 1)})"
                    if wn
                    else f"{label} — {len(wk)} games, none scored yet"
                )
                out += [
                    "<details>",
                    f"<summary>{header}</summary>",
                    "",
                    "| Date | Matchup | Pick | Conf. | Final | Result | Ranking Used |",
                    "|:---|:---|:---|---:|:---|:---:|:---|",
                ]
                wk.sort(key=lambda r: (r["start_date"], r["home_team"]))
                for row in wk:
                    conf = confidence_for(row)
                    if row["home_points"] is not None and row["away_points"] is not None:
                        final = f"{row['home_points']:.0f}-{row['away_points']:.0f}"
                    else:
                        final = "—"
                    if not row["scored"]:
                        mark = "_pending_"
                    elif row["correct"] >= 1.0:
                        mark = "✅"
                    else:
                        mark = "❌"
                    out.append(
                        "| {d} | {m} | {p} | {c} | {f} | {r} | `{s}` |".format(
                            d=format_date(row["start_date"]),
                            m=md_escape(f"{row['home_team']} vs {row['away_team']}"),
                            p=md_escape(row["predicted_winner"] or "—"),
                            c="—" if conf is None else f"{conf:.1f}%",
                            f=final,
                            r=mark,
                            s=md_escape(row["ranking_source"] or "n/a"),
                        )
                    )
                out += ["", "</details>", ""]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def write_season_logs(rows: List[Dict]) -> Dict[int, str]:
    """One log file per season under docs/game_log/. Returns {year: rel_path}."""
    os.makedirs(GAME_LOG_DIR, exist_ok=True)
    written = {}
    for year in sorted({r["year"] for r in rows if r["year"]}):
        year_rows = [r for r in rows if r["year"] == year]
        path = os.path.join(GAME_LOG_DIR, f"{year}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(season_log_body(year, year_rows))
        written[year] = os.path.relpath(path, BASE_DIR)
    return written


def build(rows: List[Dict], ledger_path: str, include_log: bool) -> str:
    years = sorted({r["year"] for r in rows if r["year"]})
    fbs_rows = [r for r in rows if r["fbs_vs_fbs"]]
    _, _, overall_fbs = accuracy(fbs_rows)

    parts = [
        "# Model Performance",
        "",
        f"> Auto-generated {generated_stamp()} from `{os.path.relpath(ledger_path, BASE_DIR)}`.",
        "> Do not edit by hand — run `python generate_performance_report.py` instead.",
        "",
        "[Latest Rankings →](RANKINGS.md) &nbsp;•&nbsp; [Season Predictions →](PREDICTIONS.md)"
        " &nbsp;•&nbsp; [Back to README →](README.md)",
        "",
        "Every prediction is made from the newest ranking that existed **before kickoff** — see",
        "[the ledger design](README.md#prediction-ledger-point-in-time). Nothing here is fit in",
        "hindsight.",
        "",
        "## Headline Accuracy",
        "",
        summary_table(rows),
        "",
        "> [!NOTE]",
        "> The headline number includes FBS-vs-FCS games, which are near-automatic wins and lift",
        "> it by roughly three to four points. The FBS-vs-FBS row is the record against genuinely",
        "> competitive opponents.",
        "",
        "## Accuracy by Season",
        "",
        by_year_table(rows),
        "",
        "## Accuracy by Segment",
        "",
        by_season_type_table(rows),
        "",
        "## Calibration",
        "",
        "Does an 80%-confidence pick actually win 80% of the time? `Gap` is the hit rate minus the",
        "midpoint of the band — positive means the model is underconfident, negative means it",
        "overstates its edge.",
        "",
        calibration_table(rows),
        "",
        "## Accuracy by Week (regular season, all years)",
        "",
        by_week_table(rows),
        "",
    ]

    if include_log:
        written = write_season_logs(rows)
        parts += [
            "## Full Prediction Log",
            "",
            "Every logged prediction with the ranking snapshot it came from, one file per season,",
            "collapsible by week. Split out because the combined log is ~400 KB, past the point",
            "where GitHub renders a markdown file reliably.",
            "",
            "| Season | Games | Correct | Accuracy | Log |",
            "|:---|---:|---:|---:|:---|",
        ]
        for year in sorted(written, reverse=True):
            yr = [r for r in rows if r["year"] == year]
            n, c, a = accuracy(yr)
            parts.append(
                f"| {year} | {n} | {c} | {pct(a, 2)} | "
                f"[{year} log →]({written[year]}) |"
            )
        parts.append("")

    parts += [
        "---",
        "",
        "### Where This Comes From",
        "",
        "| Field | Value |",
        "|:---|:---|",
        f"| Ledger | `{os.path.relpath(ledger_path, BASE_DIR)}` |",
        f"| Seasons | {years[0]}–{years[-1]} |" if years else "| Seasons | n/a |",
        f"| Scored games | {accuracy(rows)[0]} |",
        f"| FBS-vs-FBS accuracy | {pct(overall_fbs, 2)} |",
        f"| Generated | {generated_stamp()} |",
        "",
        "```bash",
        "python generate_performance_report.py",
        "```",
        "",
    ]
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=str, default="")
    parser.add_argument("--no-log", action="store_true", help="Skip the per-game log section.")
    args = parser.parse_args()

    ledger_path = args.ledger or widest_ledger()
    if not ledger_path:
        raise SystemExit(f"No spi_game_predictions_*.csv found in {PREDICTIONS_DIR}")

    rows = load_ledger(ledger_path)
    if not rows:
        raise SystemExit(f"No rows parsed from {ledger_path}")

    body = build(rows, ledger_path, include_log=not args.no_log)
    with open(PERFORMANCE_MD, "w", encoding="utf-8") as f:
        f.write(body)

    n, c, a = accuracy(rows)
    fn, fc, fa = accuracy([r for r in rows if r["fbs_vs_fbs"]])
    print(f"Ledger:            {os.path.relpath(ledger_path, BASE_DIR)}")
    print(f"Scored games:      {n} ({c} correct, {pct(a, 2)})")
    print(f"FBS vs FBS:        {fn} ({fc} correct, {pct(fa, 2)})")
    print(f"Wrote:             {os.path.relpath(PERFORMANCE_MD, BASE_DIR)} "
          f"({os.path.getsize(PERFORMANCE_MD) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
