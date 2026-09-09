"""Generate the git-visible markdown reports for the repo UI.

Writes three artifacts from the newest data in ``data_exports/``:

* ``RANKINGS.md``    - the latest SPI rankings release (top 25 + full FBS + conferences)
* ``PREDICTIONS.md`` - every team's full-season schedule outlook (actual + projected)
* ``README.md``      - refreshes the embedded Top 25 block between marker comments

Run it after ``rankings.py`` / ``predict_upcoming_matchups.py`` so the markdown
always matches the newest CSV exports.
"""

import argparse
import csv
import datetime as dt
import glob
import os
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from model_config import clamp_win_prob_pct

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_EXPORTS_DIR = os.path.join(BASE_DIR, "data_exports")
PREDICTIONS_DIR = os.path.join(DATA_EXPORTS_DIR, "predictions")

RANKINGS_MD = os.path.join(BASE_DIR, "RANKINGS.md")
PREDICTIONS_MD = os.path.join(BASE_DIR, "PREDICTIONS.md")
UPCOMING_MD = os.path.join(BASE_DIR, "UPCOMING.md")
README_MD = os.path.join(BASE_DIR, "README.md")

README_TOP25_START = "<!-- BEGIN:TOP25 -->"
README_TOP25_END = "<!-- END:TOP25 -->"

CONFERENCE_DISPLAY = {
    "acc": "ACC",
    "american": "American",
    "american athletic": "American",
    "big 12": "Big 12",
    "big ten": "Big Ten",
    "conference usa": "Conference USA",
    "fbs independents": "FBS Independents",
    "independent": "FBS Independents",
    "mid-american": "Mid-American",
    "mountain west": "Mountain West",
    "pac-12": "Pac-12",
    "sec": "SEC",
    "sun belt": "Sun Belt",
}

POWER_CONFERENCES = ["sec", "big ten", "big 12", "acc"]


# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------

def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    ascii_value = re.sub(r"[^A-Za-z0-9]+", "-", ascii_value).strip("-").lower()
    return ascii_value or "team"


def conference_label(raw: str) -> str:
    key = (raw or "").strip().lower()
    return CONFERENCE_DISPLAY.get(key, (raw or "Unknown").title())


def to_float(value, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value, default: Optional[int] = None) -> Optional[int]:
    result = to_float(value, None)
    return default if result is None else int(result)


def read_csv(path: str) -> List[Dict[str, str]]:
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


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


# ----------------------------------------------------------------------------
# locating the newest exports
# ----------------------------------------------------------------------------

def latest_rankings_file(year: int) -> Optional[str]:
    """Newest rankings release for ``year``: postseason > weekly > preseason > season."""
    candidates = []
    for path in glob.glob(os.path.join(DATA_EXPORTS_DIR, "spi_rankings_*.csv")):
        base = os.path.basename(path)
        if "detailed" in base.lower() or str(year) not in base:
            continue
        candidates.append(path)

    if not candidates:
        return None

    def rank_key(path: str) -> Tuple[int, int, float]:
        base = os.path.basename(path)
        tier, week = 0, 0
        if re.match(rf"spi_rankings_{year}_post_w(\d+)\.csv$", base):
            tier, week = 5, int(re.findall(r"post_w(\d+)", base)[0])
        elif re.match(rf"spi_rankings_{year}_w(\d+)\.csv$", base):
            tier, week = 4, int(re.findall(r"_w(\d+)", base)[0])
        elif base == f"spi_rankings_final_{year}.csv":
            tier = 3
        elif base == f"spi_rankings_{year}.csv":
            tier = 2
        elif base == f"spi_rankings_preseason_{year}.csv":
            tier = 1
        return (tier, week, os.path.getmtime(path))

    best = max(candidates, key=rank_key)
    return best if rank_key(best)[0] > 0 else None


DEFAULT_MIN_PLAYED_PCT = 90.0


def played_pct(rows: List[Dict]) -> float:
    """Share of ranked teams that have played at least one game."""
    if not rows:
        return 0.0
    played = sum(1 for r in rows if (r["wins"] or 0) + (r["losses"] or 0) >= 1)
    return 100.0 * played / len(rows)


def resolve_rankings_source(year: int, min_played_pct: float) -> Tuple[str, str, Dict]:
    """Pick which rankings release to publish.

    A one-week sample produces a mathematically correct but useless board, so an
    in-season release is only published once at least ``min_played_pct`` of teams
    have played a game. Below that we fall back to the preseason release, which
    already carries the prior season forward through the SOR component.
    """
    newest = latest_rankings_file(year)
    if not newest:
        raise SystemExit(f"No spi_rankings_*.csv found for {year} in {DATA_EXPORTS_DIR}")

    label = snapshot_label(newest)
    preseason_path = os.path.join(DATA_EXPORTS_DIR, f"spi_rankings_preseason_{year}.csv")

    if label == f"preseason_{year}":
        return newest, label, {"gated": False, "pct": None, "threshold": min_played_pct}

    pct = played_pct(rankings_rows(newest))
    if pct < min_played_pct and os.path.exists(preseason_path):
        return (
            preseason_path,
            f"preseason_{year}",
            {
                "gated": True,
                "pct": pct,
                "threshold": min_played_pct,
                "held_back": release_title(label, year),
                "held_back_file": os.path.basename(newest),
            },
        )

    return newest, label, {"gated": False, "pct": pct, "threshold": min_played_pct}


def gate_banner(gate: Dict, year: int) -> List[str]:
    if gate.get("gated"):
        return [
            "> [!NOTE]",
            f"> **Showing preseason rankings.** Only {gate['pct']:.0f}% of teams have played a",
            f"> game so far, below the {gate['threshold']:.0f}% threshold needed for a meaningful",
            f"> in-season board. The computed `{gate['held_back_file']}` release "
            f"({gate['held_back']}) is",
            "> held back until enough of the season is on the field. Preseason SPI already carries",
            "> last season forward through its Strength of Record component.",
            "",
        ]
    if gate.get("pct") is not None:
        return [
            f"> [!NOTE]",
            f"> Computed from games played this season — {gate['pct']:.0f}% of teams have played.",
            "",
        ]
    return []


def snapshot_label(rankings_path: str) -> str:
    base = os.path.basename(rankings_path)[: -len(".csv")]
    return base[len("spi_rankings_") :] if base.startswith("spi_rankings_") else base


def release_title(label: str, year: int) -> str:
    if label == f"preseason_{year}":
        return "Preseason"
    if label == f"final_{year}":
        return "Final"
    if label == str(year):
        return "Season To Date"
    post = re.match(rf"{year}_post_w(\d+)$", label)
    if post:
        return f"Postseason Week {post.group(1)}"
    week = re.match(rf"{year}_w(\d+)$", label)
    if week:
        return f"Week {week.group(1)}"
    return label.replace("_", " ").title()


def conference_rankings_file(label: str) -> Optional[str]:
    path = os.path.join(DATA_EXPORTS_DIR, f"conference_rankings_{label}.csv")
    return path if os.path.exists(path) else None


def historical_predictions_file(year: int) -> Optional[str]:
    """Newest spi_game_predictions_*.csv whose year range covers ``year``."""
    matches = []
    for path in glob.glob(os.path.join(PREDICTIONS_DIR, "spi_game_predictions_*.csv")):
        found = re.findall(r"spi_game_predictions_(\d{4})_(\d{4})\.csv$", os.path.basename(path))
        if not found:
            continue
        start, end = int(found[0][0]), int(found[0][1])
        if start <= year <= end:
            matches.append((end - start, os.path.getmtime(path), path))
    if not matches:
        return None
    # Prefer the tightest year range, then the freshest file.
    return min(matches, key=lambda item: (item[0], -item[1]))[2]


def upcoming_predictions_file(year: int) -> Optional[str]:
    for name in (
        f"upcoming_spi_predictions_{year}_all_pending.csv",
        f"upcoming_spi_predictions_{year}_next_week.csv",
    ):
        path = os.path.join(PREDICTIONS_DIR, name)
        if os.path.exists(path):
            return path
    return None


# ----------------------------------------------------------------------------
# schedule assembly
# ----------------------------------------------------------------------------

def game_key(week, home: str, away: str) -> Tuple:
    return (to_int(week, -1), (home or "").strip().lower(), (away or "").strip().lower())


def load_completed_games(year: int) -> Tuple[List[Dict], Optional[str]]:
    path = historical_predictions_file(year)
    games = []
    for row in read_csv(path):
        if to_int(row.get("year"), -1) != year:
            continue
        home_points = to_float(row.get("home_points"))
        away_points = to_float(row.get("away_points"))
        if home_points is None or away_points is None:
            continue
        games.append(
            {
                "status": "final",
                "week": to_int(row.get("week"), 0),
                "season_type": (row.get("season_type") or "regular").strip(),
                "start_date": row.get("start_date", ""),
                "home_team": (row.get("home_team") or "").strip(),
                "away_team": (row.get("away_team") or "").strip(),
                "home_points": home_points,
                "away_points": away_points,
                "actual_winner": (row.get("actual_winner") or "").strip(),
                "predicted_winner": (row.get("predicted_winner") or "").strip(),
                "home_win_prob": clamp_win_prob_pct(
                    to_float(
                        row.get("home_win_prob_home_adj_pct") or row.get("home_win_prob_pure_pct")
                    )
                ),
                "away_win_prob": clamp_win_prob_pct(
                    to_float(
                        row.get("away_win_prob_home_adj_pct") or row.get("away_win_prob_pure_pct")
                    )
                ),
                "neutral_site": False,
                "notes": (row.get("notes") or "").strip(),
            }
        )
    return games, path


def load_pending_games(year: int) -> Tuple[List[Dict], Optional[str]]:
    path = upcoming_predictions_file(year)
    games = []
    for row in read_csv(path):
        games.append(
            {
                "status": "projected",
                "week": to_int(row.get("week"), 0),
                "season_type": (row.get("season_type") or "regular").strip(),
                "start_date": row.get("start_date", ""),
                "home_team": (row.get("home_team") or "").strip(),
                "away_team": (row.get("away_team") or "").strip(),
                "home_points": None,
                "away_points": None,
                "actual_winner": "",
                "predicted_winner": (row.get("predicted_winner") or "").strip(),
                # Same precedence the dashboard uses in prepare_upcoming_frame().
                "home_win_prob": clamp_win_prob_pct(
                    to_float(row.get("home_win_prob_home_adj_pct"))
                    if to_float(row.get("home_win_prob_home_adj_pct")) is not None
                    else to_float(row.get("home_win_prob_pct"))
                ),
                "away_win_prob": clamp_win_prob_pct(
                    to_float(row.get("away_win_prob_home_adj_pct"))
                    if to_float(row.get("away_win_prob_home_adj_pct")) is not None
                    else to_float(row.get("away_win_prob_pct"))
                ),
                "neutral_site": str(row.get("neutral_site", "")).strip().lower() == "true",
                "notes": (row.get("notes") or "").strip(),
            }
        )
    return games, path


def season_games_file(year: int) -> Optional[str]:
    path = os.path.join(DATA_EXPORTS_DIR, f"season_games_{year}.csv")
    return path if os.path.exists(path) else None


def load_season_games(year: int) -> Tuple[List[Dict], Optional[str]]:
    """Every game on the season schedule, played or not.

    This is the authoritative game list. The prediction exports cannot serve
    that role: upcoming_spi_predictions drops games once they are played, and
    spi_game_predictions only contains games the backtest has scored (which
    needs a completed-week snapshot). A game that has been played while its
    week is still in progress is in neither file -- USC beating San Jose State
    in week 1 while the week 1 Fresno State game is still upcoming is exactly
    that case -- so building schedules from those two sources silently drops it.
    """
    path = season_games_file(year)
    games = []
    for row in read_csv(path):
        home_points = to_float(row.get("home_points"))
        away_points = to_float(row.get("away_points"))
        final = home_points is not None and away_points is not None
        games.append(
            {
                "status": "final" if final else "projected",
                "week": to_int(row.get("week"), 0),
                "season_type": (row.get("season_type") or "regular").strip(),
                "start_date": row.get("start_date", ""),
                "home_team": (row.get("home_team") or "").strip(),
                "away_team": (row.get("away_team") or "").strip(),
                "home_points": home_points,
                "away_points": away_points,
                "actual_winner": "",
                "predicted_winner": "",
                "home_win_prob": None,
                "away_win_prob": None,
                "neutral_site": str(row.get("neutral_site", "")).strip().lower() == "true",
                "notes": (row.get("notes") or "").strip(),
            }
        )
    return games, path


def build_team_schedules(year: int) -> Tuple[Dict[str, List[Dict]], Dict[str, Optional[str]]]:
    completed, completed_path = load_completed_games(year)
    pending, pending_path = load_pending_games(year)
    season, season_path = load_season_games(year)

    merged: Dict[Tuple, Dict] = {}

    if season:
        # Start from the full schedule, then layer prediction data onto it.
        for game in season:
            merged[game_key(game["week"], game["home_team"], game["away_team"])] = game

        for source in (pending, completed):
            for game in source:
                key = game_key(game["week"], game["home_team"], game["away_team"])
                target = merged.get(key)
                if target is None:
                    merged[key] = game
                    continue
                # Keep the schedule's own result; borrow the model's numbers.
                for field in ("home_win_prob", "away_win_prob", "predicted_winner"):
                    if target.get(field) in (None, "") and game.get(field) not in (None, ""):
                        target[field] = game[field]
    else:
        # No schedule export available -- fall back to the prediction artifacts.
        for game in pending:
            merged[game_key(game["week"], game["home_team"], game["away_team"])] = game
        for game in completed:
            merged[game_key(game["week"], game["home_team"], game["away_team"])] = game

    schedules: Dict[str, List[Dict]] = {}
    for game in merged.values():
        for team, opponent, is_home in (
            (game["home_team"], game["away_team"], True),
            (game["away_team"], game["home_team"], False),
        ):
            if not team:
                continue
            win_prob = game["home_win_prob"] if is_home else game["away_win_prob"]
            if game["status"] == "final":
                team_points = game["home_points"] if is_home else game["away_points"]
                opp_points = game["away_points"] if is_home else game["home_points"]
                if team_points > opp_points:
                    result = "W"
                elif team_points < opp_points:
                    result = "L"
                else:
                    result = "T"
                score = f"{team_points:.0f}-{opp_points:.0f}"
            elif (game["predicted_winner"] or "").strip():
                result = "W" if game["predicted_winner"].strip() == team else "L"
                score = ""
            elif win_prob is not None:
                result = "W" if win_prob >= 50.0 else "L"
                score = ""
            else:
                # Scheduled, but the model has no projection for it yet.
                result = ""
                score = ""

            schedules.setdefault(team, []).append(
                {
                    "week": game["week"],
                    "season_type": game["season_type"],
                    "start_date": game["start_date"],
                    "opponent": opponent,
                    "is_home": is_home,
                    "neutral_site": game["neutral_site"],
                    "status": game["status"],
                    "result": result,
                    "score": score,
                    "win_prob": win_prob,
                    "notes": game["notes"],
                }
            )

    for games in schedules.values():
        games.sort(key=lambda g: (0 if g["season_type"] == "regular" else 1, g["week"], g["start_date"]))

    sources = {"completed": completed_path, "pending": pending_path, "season": season_path}
    return schedules, sources


def summarize_record(games: List[Dict]) -> Dict[str, float]:
    actual_w = sum(1 for g in games if g["status"] == "final" and g["result"] == "W")
    actual_l = sum(1 for g in games if g["status"] == "final" and g["result"] == "L")
    proj_w = sum(1 for g in games if g["status"] == "projected" and g["result"] == "W")
    proj_l = sum(1 for g in games if g["status"] == "projected" and g["result"] == "L")
    unprojected = sum(1 for g in games if g["status"] == "projected" and not g["result"])
    expected_wins = float(actual_w)
    for g in games:
        if g["status"] == "projected" and g["win_prob"] is not None:
            expected_wins += g["win_prob"] / 100.0
    return {
        "actual_w": actual_w,
        "actual_l": actual_l,
        "played": actual_w + actual_l,
        "remaining": proj_w + proj_l + unprojected,
        "unprojected": unprojected,
        "proj_w": actual_w + proj_w,
        "proj_l": actual_l + proj_l,
        "expected_wins": expected_wins,
    }


# ----------------------------------------------------------------------------
# markdown rendering
# ----------------------------------------------------------------------------

def md_escape(value: str) -> str:
    return str(value).replace("|", "\\|")


def generated_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def rankings_rows(rankings_path: str) -> List[Dict]:
    rows = []
    for row in read_csv(rankings_path):
        rows.append(
            {
                "rank": to_int(row.get("rank"), 0),
                "team": (row.get("team") or "").strip(),
                "conference": (row.get("conference") or "").strip(),
                "wins": to_int(row.get("wins"), 0),
                "losses": to_int(row.get("losses"), 0),
                "spi": to_float(row.get("SPI"), 0.0),
                "n_adj": to_float(row.get("N_adj"), 0.0),
                "sor_adj": to_float(row.get("SOR_adj"), 0.0),
            }
        )
    rows.sort(key=lambda r: r["rank"])
    return rows


def render_top25_table(rows: List[Dict]) -> str:
    lines = [
        "| # | Team | Conf | Record | SPI | Nature | SOR |",
        "|---:|:---|:---|:---:|---:|---:|---:|",
    ]
    for row in rows[:25]:
        lines.append(
            "| {rank} | **{team}** | {conf} | {w}-{l} | {spi:.2f} | {n:.3f} | {sor:.3f} |".format(
                rank=row["rank"],
                team=md_escape(row["team"]),
                conf=md_escape(conference_label(row["conference"])),
                w=row["wins"],
                l=row["losses"],
                spi=row["spi"],
                n=row["n_adj"],
                sor=row["sor_adj"],
            )
        )
    return "\n".join(lines)


def render_full_rankings_table(rows: List[Dict]) -> str:
    lines = [
        "| # | Team | Conference | Record | SPI | Nature (N_adj) | SOR (SOR_adj) |",
        "|---:|:---|:---|:---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {rank} | {team} | {conf} | {w}-{l} | {spi:.2f} | {n:.3f} | {sor:.3f} |".format(
                rank=row["rank"],
                team=md_escape(row["team"]),
                conf=md_escape(conference_label(row["conference"])),
                w=row["wins"],
                l=row["losses"],
                spi=row["spi"],
                n=row["n_adj"],
                sor=row["sor_adj"],
            )
        )
    return "\n".join(lines)


def render_conference_table(rows: List[Dict], conf_path: Optional[str]) -> str:
    by_conf: Dict[str, List[Dict]] = {}
    for row in rows:
        by_conf.setdefault(row["conference"].strip().lower(), []).append(row)

    conf_meta = {}
    for row in read_csv(conf_path):
        conf_meta[(row.get("name") or "").strip().lower()] = row

    table = []
    for conf, teams in by_conf.items():
        ranks = [t["rank"] for t in teams if t["rank"]]
        spis = [t["spi"] for t in teams]
        meta = conf_meta.get(conf, {})
        table.append(
            {
                "conference": conference_label(conf),
                "teams": len(teams),
                "avg_spi": sum(spis) / len(spis) if spis else 0.0,
                "best_rank": min(ranks) if ranks else 0,
                "top25": sum(1 for r in ranks if r <= 25),
                "cvc": "{}-{}".format(
                    to_int(meta.get("cvc_wins"), 0) or 0, to_int(meta.get("cvc_losses"), 0) or 0
                )
                if meta
                else "-",
            }
        )
    table.sort(key=lambda c: -c["avg_spi"])

    lines = [
        "| # | Conference | Teams | Avg SPI | Top-25 Teams | Best Rank | Cross-Conf W-L |",
        "|---:|:---|---:|---:|---:|---:|:---:|",
    ]
    for idx, conf in enumerate(table, start=1):
        lines.append(
            "| {i} | {name} | {teams} | {avg:.2f} | {top} | {best} | {cvc} |".format(
                i=idx,
                name=md_escape(conf["conference"]),
                teams=conf["teams"],
                avg=conf["avg_spi"],
                top=conf["top25"],
                best=conf["best_rank"],
                cvc=conf["cvc"],
            )
        )
    return "\n".join(lines)


def write_rankings_md(year: int, rankings_path: str, rows: List[Dict], label: str, gate: Dict) -> str:
    title = release_title(label, year)
    conf_path = conference_rankings_file(label)

    parts = [
        f"# {year} SPI Rankings — {title}",
        "",
        f"> Auto-generated {generated_stamp()} from `{os.path.relpath(rankings_path, BASE_DIR)}`.",
        "> Do not edit by hand — run `python generate_markdown_reports.py` instead.",
        "",
        f"**Release:** {title} &nbsp;•&nbsp; **Teams ranked:** {len(rows)} &nbsp;•&nbsp; "
        f"[Season Predictions →](PREDICTIONS.md) &nbsp;•&nbsp; [Back to README →](README.md)",
        "",
    ] + gate_banner(gate, year) + [
        "SPI blends **Nature** (how good a team looks) and **Strength of Record** (what they have",
        "actually done) into a single 0–100 index. `N_adj` and `SOR_adj` are the normalized",
        "components behind each team's SPI.",
        "",
        "## Top 25",
        "",
        render_top25_table(rows),
        "",
        "## Full FBS Rankings",
        "",
        "<details open>",
        f"<summary><b>All {len(rows)} ranked teams</b></summary>",
        "",
        render_full_rankings_table(rows),
        "",
        "</details>",
        "",
        "## Conference Strength",
        "",
        render_conference_table(rows, conf_path),
        "",
        "---",
        "",
        "### Where This Comes From",
        "",
        f"| Field | Value |",
        f"|:---|:---|",
        f"| Season | {year} |",
        f"| Release | {title} |",
        f"| Teams that have played | {gate['pct']:.0f}% |" if gate.get("pct") is not None else "| Teams that have played | n/a (preseason) |",
        f"| In-season gate | held back below {gate['threshold']:.0f}% |" if gate.get("gated") else f"| In-season gate | passed ({gate['threshold']:.0f}% threshold) |",
        f"| Source file | `{os.path.relpath(rankings_path, BASE_DIR)}` |",
        f"| Conference file | `{os.path.relpath(conf_path, BASE_DIR) if conf_path else 'n/a'}` |",
        f"| Generated | {generated_stamp()} |",
        "",
        "Regenerate with:",
        "",
        "```bash",
        f"python rankings.py --year {year}",
        "python generate_markdown_reports.py",
        "```",
        "",
    ]
    body = "\n".join(parts)
    with open(RANKINGS_MD, "w", encoding="utf-8") as f:
        f.write(body)
    return body


def render_team_schedule_table(games: List[Dict], rank_lookup: Dict[str, int]) -> str:
    lines = [
        "| Wk | Date | Opponent | Site | Win Prob | Projection | Result |",
        "|---:|:---|:---|:---:|---:|:---:|:---|",
    ]
    for game in games:
        opponent = game["opponent"]
        opp_rank = rank_lookup.get(opponent)
        opp_label = f"#{opp_rank} {opponent}" if opp_rank else opponent
        if game["neutral_site"]:
            site = "N"
        else:
            site = "H" if game["is_home"] else "A"
        prob = f"{game['win_prob']:.1f}%" if game["win_prob"] is not None else "—"

        if game["status"] == "final":
            projection = "—"
            outcome = "✅ **W**" if game["result"] == "W" else ("❌ **L**" if game["result"] == "L" else "T")
            result = f"{outcome} {game['score']}".strip()
        elif game["result"] == "W":
            projection = "🟢 **W**"
            result = "_pending_"
        elif game["result"] == "L":
            projection = "🔴 **L**"
            result = "_pending_"
        else:
            projection = "—"
            result = "_pending_"

        lines.append(
            "| {wk} | {date} | {opp} | {site} | {prob} | {proj} | {res} |".format(
                wk=game["week"],
                date=format_date(game["start_date"]),
                opp=md_escape(opp_label),
                site=site,
                prob=prob,
                proj=projection,
                res=result,
            )
        )
    return "\n".join(lines)


def write_predictions_md(
    year: int,
    rows: List[Dict],
    schedules: Dict[str, List[Dict]],
    sources: Dict[str, Optional[str]],
    label: str,
) -> None:
    rank_lookup = {r["team"]: r["rank"] for r in rows}
    conf_lookup = {r["team"]: r["conference"] for r in rows}
    title = release_title(label, year)

    entries = []
    for row in rows:
        games = schedules.get(row["team"], [])
        if not games:
            continue
        summary = summarize_record(games)
        entries.append({"row": row, "games": games, "summary": summary})

    total_games = sum(len(e["games"]) for e in entries) // 2
    played = sum(e["summary"]["played"] for e in entries)
    remaining = sum(e["summary"]["remaining"] for e in entries)

    parts = [
        f"# {year} Season Predictions — Every Team's Projected Schedule",
        "",
        f"> Auto-generated {generated_stamp()} from the newest prediction exports.",
        "> Do not edit by hand — run `python generate_markdown_reports.py` instead.",
        "",
        f"**Ranking basis:** {title} &nbsp;•&nbsp; **Teams:** {len(entries)} &nbsp;•&nbsp; "
        f"[Latest Rankings →](RANKINGS.md) &nbsp;•&nbsp; [Back to README →](README.md)",
        "",
        "Each team below has its full season laid out game by game: completed games show the",
        "actual result, and every remaining game shows the model's win probability and projected",
        "outcome. **Proj. Record** is the straight favorite-picks record; **xWins** sums the win",
        "probabilities for a smoother expected-wins estimate.",
        "",
        "**Legend** — Site: `H` home, `A` away, `N` neutral &nbsp;•&nbsp; "
        "🟢 projected win &nbsp;•&nbsp; 🔴 projected loss &nbsp;•&nbsp; "
        "✅ actual win &nbsp;•&nbsp; ❌ actual loss",
        "",
        "## Projected Final Records",
        "",
        "| # | Team | Conference | Current | Proj. Record | xWins | Played | Remaining |",
        "|---:|:---|:---|:---:|:---:|---:|---:|---:|",
    ]

    for entry in entries:
        row, summary = entry["row"], entry["summary"]
        parts.append(
            "| {rank} | [{team}](#{anchor}) | {conf} | {aw}-{al} | **{pw}-{pl}** | {xw:.1f} | {played} | {rem} |".format(
                rank=row["rank"],
                team=md_escape(row["team"]),
                anchor=slugify(row["team"]) + "-schedule",
                conf=md_escape(conference_label(row["conference"])),
                aw=summary["actual_w"],
                al=summary["actual_l"],
                pw=summary["proj_w"],
                pl=summary["proj_l"],
                xw=summary["expected_wins"],
                played=summary["played"],
                rem=summary["remaining"],
            )
        )

    parts += [
        "",
        "## Team-by-Team Schedules",
        "",
        "Grouped by conference. Click a team to expand its full-season outlook.",
        "",
    ]

    by_conf: Dict[str, List[Dict]] = {}
    for entry in entries:
        by_conf.setdefault(conf_lookup.get(entry["row"]["team"], "").strip().lower(), []).append(entry)

    def conf_sort_key(item):
        conf = item[0]
        power_index = POWER_CONFERENCES.index(conf) if conf in POWER_CONFERENCES else len(POWER_CONFERENCES)
        return (power_index, conference_label(conf))

    for conf, conf_entries in sorted(by_conf.items(), key=conf_sort_key):
        conf_entries.sort(key=lambda e: e["row"]["rank"])
        parts += [
            f'<a id="{slugify(conference_label(conf))}"></a>',
            "",
            f"### {conference_label(conf)}",
            "",
        ]
        for entry in conf_entries:
            row, summary = entry["row"], entry["summary"]
            header = (
                f"#{row['rank']} {row['team']} — "
                f"proj. {summary['proj_w']}-{summary['proj_l']} "
                f"({summary['expected_wins']:.1f} xWins)"
            )
            parts += [
                f'<a id="{slugify(row["team"])}-schedule"></a>',
                "<details>",
                f"<summary><b>{header}</b></summary>",
                "",
                render_team_schedule_table(entry["games"], rank_lookup),
                "",
                "</details>",
                "",
            ]

    parts += [
        "---",
        "",
        "### Where This Comes From",
        "",
        "| Field | Value |",
        "|:---|:---|",
        f"| Season | {year} |",
        f"| Ranking basis | {title} |",
        f"| Games covered | {total_games} ({played // 2} played, {remaining // 2} remaining) |",
        "| Completed-game source | `{}` |".format(
            os.path.relpath(sources["completed"], BASE_DIR) if sources["completed"] else "n/a"
        ),
        "| Pending-game source | `{}` |".format(
            os.path.relpath(sources["pending"], BASE_DIR) if sources["pending"] else "n/a"
        ),
        "| Schedule source | `{}` |".format(
            os.path.relpath(sources["season"], BASE_DIR) if sources.get("season") else "n/a (derived from predictions)"
        ),
        f"| Generated | {generated_stamp()} |",
        "",
        "Regenerate with:",
        "",
        "```bash",
        f"python predict_upcoming_matchups.py --year {year} --all-pending",
        "python generate_markdown_reports.py",
        "```",
        "",
    ]

    with open(PREDICTIONS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def upcoming_week(pending: List[Dict]) -> Optional[int]:
    """The soonest week that still has unplayed games.

    The pending export is regenerated each run with only not-yet-played games,
    so the smallest week number in it is the next slate to preview. A game
    played late in its week keeps that week 'upcoming' until it actually kicks
    off, which is the behavior we want.
    """
    weeks = [g["week"] for g in pending if g.get("week")]
    return min(weeks) if weeks else None


def confidence_of(game: Dict) -> Optional[float]:
    """Win probability the model assigns to the side it picked (50-99.9)."""
    pick = (game.get("predicted_winner") or "").strip()
    if pick and pick == game.get("home_team"):
        return game.get("home_win_prob")
    if pick and pick == game.get("away_team"):
        return game.get("away_win_prob")
    hp, ap = game.get("home_win_prob"), game.get("away_win_prob")
    if hp is None or ap is None:
        return hp if ap is None else ap
    return max(hp, ap)


def write_upcoming_md(year: int, rows: List[Dict], pending: List[Dict], pending_path: Optional[str]) -> Optional[int]:
    rank_lookup = {r["team"]: r["rank"] for r in rows}
    target = upcoming_week(pending)
    week_games = [g for g in pending if g.get("week") == target] if target is not None else []
    week_games.sort(key=lambda g: (g.get("start_date") or "", -(confidence_of(g) or 0)))

    def team_cell(team: str) -> str:
        rk = rank_lookup.get(team)
        return f"#{rk} {md_escape(team)}" if rk else md_escape(team)

    parts = [
        f"# {year} Upcoming Game Predictions",
        "",
        f"> Auto-generated {generated_stamp()} from the newest prediction export.",
        "> Do not edit by hand — run `python generate_markdown_reports.py` instead.",
        "",
        f"**Week {target if target is not None else '?'}** &nbsp;•&nbsp; "
        f"{len(week_games)} games &nbsp;•&nbsp; "
        "[Latest Rankings →](RANKINGS.md) &nbsp;•&nbsp; [Full-Season Predictions →](PREDICTIONS.md)"
        " &nbsp;•&nbsp; [Model Performance →](PERFORMANCE.md) &nbsp;•&nbsp; [Back to README →](README.md)",
        "",
        "Every pending game for the upcoming week, with the model's pick and its win probability.",
        "Ranks are current SPI ranks. Win probabilities are capped at 0.1–99.9%.",
        "",
    ]

    if not week_games:
        pretty = os.path.relpath(pending_path, BASE_DIR) if pending_path else "n/a"
        parts += [
            "> [!NOTE]",
            "> No pending games found — either the season is between slates or the prediction",
            f"> export (`{pretty}`) has no remaining games. This page will fill in on the next run.",
            "",
        ]
    else:
        parts += [
            "| Date | Matchup | Site | Prediction | Win Prob |",
            "|:---|:---|:---:|:---|---:|",
        ]
        for g in week_games:
            home, away = g["home_team"], g["away_team"]
            if g["neutral_site"]:
                site, matchup = "N", f"{team_cell(away)} vs {team_cell(home)}"
            else:
                site, matchup = "@", f"{team_cell(away)} @ {team_cell(home)}"
            conf = confidence_of(g)
            pick = (g.get("predicted_winner") or "").strip() or "—"
            note = f" · _{md_escape(g['notes'])}_" if g.get("notes") else ""
            parts.append(
                "| {date} | {matchup}{note} | {site} | **{pick}** | {conf} |".format(
                    date=format_date(g["start_date"]),
                    matchup=matchup,
                    note=note,
                    site=site,
                    pick=md_escape(pick),
                    conf=f"{conf:.1f}%" if conf is not None else "—",
                )
            )
        parts.append("")
        upsets = [g for g in week_games
                  if (rank_lookup.get(g["predicted_winner"], 999) or 999)
                  > (rank_lookup.get(g["away_team"] if g["predicted_winner"] == g["home_team"] else g["home_team"], 999) or 999)]
        if upsets:
            parts += [
                f"**Model disagrees with the ranking in {len(upsets)} game(s)** "
                "(picks the lower-ranked team):",
                "",
            ]
            for g in sorted(upsets, key=lambda x: x.get("start_date") or ""):
                conf = confidence_of(g)
                parts.append(
                    f"- {format_date(g['start_date'])}: **{md_escape(g['predicted_winner'])}** over "
                    f"{team_cell(g['away_team'] if g['predicted_winner']==g['home_team'] else g['home_team'])}"
                    f" ({conf:.1f}%)" if conf is not None else ""
                )
            parts.append("")

    parts += [
        "---",
        "",
        "| Field | Value |",
        "|:---|:---|",
        f"| Season | {year} |",
        f"| Week previewed | {target if target is not None else 'n/a'} |",
        f"| Games | {len(week_games)} |",
        "| Source | `{}` |".format(os.path.relpath(pending_path, BASE_DIR) if pending_path else "n/a"),
        f"| Generated | {generated_stamp()} |",
        "",
        "Regenerate with:",
        "",
        "```bash",
        f"python predict_upcoming_matchups.py --year {year} --all-pending",
        "python generate_markdown_reports.py",
        "```",
        "",
    ]

    with open(UPCOMING_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return target


def update_readme(year: int, rows: List[Dict], label: str, gate: Dict) -> bool:
    if not os.path.exists(README_MD):
        return False
    with open(README_MD, encoding="utf-8") as f:
        readme = f.read()
    if README_TOP25_START not in readme or README_TOP25_END not in readme:
        return False

    block = "\n".join(
        [
            README_TOP25_START,
            "",
            f"**{year} SPI Top 25 — {release_title(label, year)}**  ",
            f"_Updated {generated_stamp()} • [Full rankings](RANKINGS.md) • "
            f"[Season predictions](PREDICTIONS.md)_",
            "",
            (f"> Preseason board — only {gate['pct']:.0f}% of teams have played, below the "
             f"{gate['threshold']:.0f}% threshold for an in-season ranking.\n"
             if gate.get("gated") else ""),
            render_top25_table(rows),
            "",
            README_TOP25_END,
        ]
    )
    start = readme.index(README_TOP25_START)
    end = readme.index(README_TOP25_END) + len(README_TOP25_END)
    with open(README_MD, "w", encoding="utf-8") as f:
        f.write(readme[:start] + block + readme[end:])
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=dt.date.today().year)
    parser.add_argument(
        "--rankings-file",
        type=str,
        default="",
        help="Explicit rankings CSV to publish (bypasses the in-season gate).",
    )
    parser.add_argument(
        "--min-played-pct",
        type=float,
        default=DEFAULT_MIN_PLAYED_PCT,
        help=(
            "Share of teams that must have played before an in-season board is published "
            f"instead of the preseason one (default: {DEFAULT_MIN_PLAYED_PCT:.0f})."
        ),
    )
    args = parser.parse_args()

    if args.rankings_file:
        rankings_path = args.rankings_file
        if not os.path.isabs(rankings_path):
            rankings_path = os.path.join(BASE_DIR, rankings_path)
        label = snapshot_label(rankings_path)
        gate = {"gated": False, "pct": None, "threshold": args.min_played_pct}
    else:
        rankings_path, label, gate = resolve_rankings_source(args.year, args.min_played_pct)

    rows = rankings_rows(rankings_path)
    if not rows:
        raise SystemExit(f"No ranking rows parsed from {rankings_path}")

    schedules, sources = build_team_schedules(args.year)

    write_rankings_md(args.year, rankings_path, rows, label, gate)
    write_predictions_md(args.year, rows, schedules, sources, label)
    pending, pending_path = load_pending_games(args.year)
    upcoming_target = write_upcoming_md(args.year, rows, pending, pending_path)
    readme_updated = update_readme(args.year, rows, label, gate)

    print(f"Season:           {args.year} ({release_title(label, args.year)})")
    print(f"Rankings source:  {os.path.relpath(rankings_path, BASE_DIR)}")
    if gate.get("gated"):
        print(
            f"In-season gate:   HELD BACK — {gate['pct']:.0f}% of teams played "
            f"(need {gate['threshold']:.0f}%); using preseason instead of {gate['held_back_file']}"
        )
    elif gate.get("pct") is not None:
        print(f"In-season gate:   passed — {gate['pct']:.0f}% of teams have played")
    print(f"Teams ranked:     {len(rows)}")
    print(f"Teams scheduled:  {sum(1 for r in rows if schedules.get(r['team']))}")
    print(f"Wrote:            {os.path.relpath(RANKINGS_MD, BASE_DIR)}")
    print(f"Wrote:            {os.path.relpath(PREDICTIONS_MD, BASE_DIR)}")
    print(f"Wrote:            {os.path.relpath(UPCOMING_MD, BASE_DIR)} "
          f"(week {upcoming_target if upcoming_target is not None else 'n/a'})")
    print(f"README Top 25:    {'updated' if readme_updated else 'markers not found — skipped'}")


if __name__ == "__main__":
    main()
