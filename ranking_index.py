"""Point-in-time index of every SPI ranking snapshot.

The prediction ledger's whole claim is that a game was predicted using the
newest ranking available *before kickoff*. That was previously enforced by week
arithmetic -- week N uses the week N-1 file -- which has two weaknesses:

1. It resolves by week number, not by clock. A week's games can span two
   weekends (in 2026, USC plays San Jose State on Aug 29 and Fresno State on
   Sep 5, both "week 1"), so a week number does not pin down what had actually
   been computed when a given game kicked off.
2. It reads mutable paths. ``rankings.py`` writes
   ``spi_rankings_<year>_w<N>.csv`` to a fixed location, so re-running it
   silently rewrites what "the prediction before that game" was.

This module builds ``published_rankings/ranking_index.csv``: one row per
snapshot, recording the instant it became the best available ranking
(``effective_through_utc``) and a SHA-256 of its contents. Resolution then means
"the snapshot with the greatest effective_through_utc strictly before kickoff",
and the hash makes silent drift detectable instead of invisible.
"""

import csv
import datetime as dt
import glob
import hashlib
import json
import os
import re
from typing import Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_EXPORTS_DIR = os.path.join(BASE_DIR, "data_exports")
GAME_CACHE_DIR = os.path.join(DATA_EXPORTS_DIR, "cache")
PUBLISHED_DIR = os.path.join(BASE_DIR, "published_rankings")
INDEX_PATH = os.path.join(PUBLISHED_DIR, "ranking_index.csv")

INDEX_FIELDS = [
    "snapshot_label",
    "season_year",
    "kind",
    "week",
    "effective_through_utc",
    "source_path",
    "sha256",
    "team_count",
    "provenance",
    "indexed_at_utc",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def parse_dt(value) -> Optional[dt.datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T")):
        try:
            parsed = dt.datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc)
        except ValueError:
            continue
    return None


def iso(value: Optional[dt.datetime]) -> str:
    return "" if value is None else value.astimezone(dt.timezone.utc).isoformat()


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def row_count(path: str) -> int:
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return max(0, sum(1 for _ in f) - 1)
    except OSError:
        return 0


def classify_snapshot(path: str) -> Optional[Dict]:
    """Pull (year, kind, week) out of a spi_rankings_* filename."""
    base = os.path.basename(path)
    if not base.startswith("spi_rankings_") or not base.endswith(".csv"):
        return None
    if "detailed" in base:
        return None

    label = base[len("spi_rankings_") : -len(".csv")]

    m = re.fullmatch(r"preseason_(\d{4})", label)
    if m:
        return {"label": label, "year": int(m.group(1)), "kind": "preseason", "week": 0}

    m = re.fullmatch(r"final_(\d{4})", label)
    if m:
        return {"label": label, "year": int(m.group(1)), "kind": "final", "week": 0}

    m = re.fullmatch(r"(\d{4})_post_w(\d+)", label)
    if m:
        return {"label": label, "year": int(m.group(1)), "kind": "postseason", "week": int(m.group(2))}

    m = re.fullmatch(r"(\d{4})_w(\d+)", label)
    if m:
        return {"label": label, "year": int(m.group(1)), "kind": "regular", "week": int(m.group(2))}

    m = re.fullmatch(r"(\d{4})", label)
    if m:
        return {"label": label, "year": int(m.group(1)), "kind": "season_to_date", "week": 0}

    # e.g. spi_rankings_2023_w1-12.csv -- an ad hoc range, not a weekly release.
    return None


# ---------------------------------------------------------------------------
# game timing
# ---------------------------------------------------------------------------

def load_week_kickoffs(year: int) -> Dict[str, Dict[int, dt.datetime]]:
    """Latest kickoff per (season_type, week), from the local game caches.

    Falls back to data_exports/season_games_<year>.csv when the JSON caches are
    absent (which is the case for a season still in progress).
    """
    latest: Dict[str, Dict[int, dt.datetime]] = {"regular": {}, "postseason": {}}
    # Week 0 of the "first" bucket holds the season's earliest kickoff. Taking a
    # min over the per-week maxima instead would land after the opening
    # weekend's games, leaving them with no snapshot to resolve to.
    latest["first"] = {}

    def record(season_type: str, week: Optional[int], when: Optional[dt.datetime]) -> None:
        if week is None or when is None:
            return
        bucket = latest.setdefault(season_type, {})
        if week not in bucket or when > bucket[week]:
            bucket[week] = when
        first = latest["first"]
        if 0 not in first or when < first[0]:
            first[0] = when

    def is_fbs(home_class, away_class) -> bool:
        """Only FBS games move the rankings.

        CFBD files lower-division playoff games under regular-season week 1 --
        2025 has D-II/D-III games dated Dec 13 sitting in week 1 -- which would
        drag every week boundary to the end of the season if counted.
        """
        return "fbs" in (
            str(home_class or "").strip().lower(),
            str(away_class or "").strip().lower(),
        )

    patterns = [
        (os.path.join(GAME_CACHE_DIR, f"games_{year}_w*.json"), "regular"),
        (os.path.join(GAME_CACHE_DIR, f"games_{year}_regular_w*.json"), "regular"),
        (os.path.join(GAME_CACHE_DIR, f"games_{year}_postseason_w*.json"), "postseason"),
    ]
    for pattern, season_type in patterns:
        for path in glob.glob(pattern):
            try:
                with open(path, encoding="utf-8") as f:
                    games = json.load(f)
            except (OSError, ValueError):
                continue
            for game in games or []:
                if not is_fbs(
                    game.get("homeClassification") or game.get("home_classification"),
                    game.get("awayClassification") or game.get("away_classification"),
                ):
                    continue
                week = game.get("week")
                when = parse_dt(game.get("startDate") or game.get("start_date"))
                record(season_type, week, when)

    season_csv = os.path.join(DATA_EXPORTS_DIR, f"season_games_{year}.csv")
    if os.path.exists(season_csv):
        with open(season_csv, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if not is_fbs(row.get("home_classification"), row.get("away_classification")):
                    continue
                season_type = (row.get("season_type") or "regular").strip()
                try:
                    week = int(float(row.get("week") or 0))
                except (TypeError, ValueError):
                    continue
                record(season_type, week, parse_dt(row.get("start_date")))

    return latest


def effective_through(snapshot: Dict, kickoffs: Dict[str, Dict[int, dt.datetime]]) -> Optional[dt.datetime]:
    """When this snapshot became the newest ranking available.

    A weekly snapshot incorporates every game through its week, so it cannot
    predate that week's final kickoff. Using the last kickoff (rather than a
    guessed publish time) keeps the boundary defensible: any game starting after
    it could legitimately have used this snapshot.
    """
    kind, week, year = snapshot["kind"], snapshot["week"], snapshot["year"]
    regular, post = kickoffs.get("regular", {}), kickoffs.get("postseason", {})

    if kind == "preseason":
        first = kickoffs.get("first", {}).get(0)
        if first is None:
            return dt.datetime(year, 8, 1, tzinfo=dt.timezone.utc)
        return first - dt.timedelta(days=1)

    # A week-N snapshot incorporates every game through week N, so its boundary
    # is the last kickoff among all games up to and including that week -- not
    # just that week's own games. Using the cumulative max keeps the boundaries
    # monotonic and gives weeks with no games (CFBD files every bowl under
    # postseason week 1, leaving weeks 2-5 empty) a sensible boundary instead of
    # dropping them from the index.
    if kind == "regular":
        through = [when for w, when in regular.items() if w <= week]
        return max(through, default=None)

    if kind == "postseason":
        through = list(regular.values()) + [when for w, when in post.items() if w <= week]
        return max(through, default=None)

    # final / season_to_date: everything played that season.
    return max(list(regular.values()) + list(post.values()), default=None)


# ---------------------------------------------------------------------------
# index build / read
# ---------------------------------------------------------------------------

def build_index(years: Optional[List[int]] = None) -> List[Dict]:
    snapshots = []
    for path in glob.glob(os.path.join(DATA_EXPORTS_DIR, "spi_rankings_*.csv")):
        info = classify_snapshot(path)
        if info and (years is None or info["year"] in years):
            info["path"] = path
            snapshots.append(info)

    by_year: Dict[int, Dict] = {}
    rows = []
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()

    for snap in sorted(snapshots, key=lambda s: (s["year"], s["kind"], s["week"])):
        year = snap["year"]
        if year not in by_year:
            by_year[year] = load_week_kickoffs(year)
        eff = effective_through(snap, by_year[year])
        if eff is None:
            continue

        rows.append(
            {
                "snapshot_label": snap["label"],
                "season_year": year,
                "kind": snap["kind"],
                "week": snap["week"],
                "effective_through_utc": iso(eff),
                "source_path": os.path.relpath(snap["path"], BASE_DIR),
                "sha256": sha256_of(snap["path"]),
                "team_count": row_count(snap["path"]),
                "provenance": "backfilled",
                "indexed_at_utc": stamp,
            }
        )

    rows.sort(key=lambda r: (r["season_year"], r["effective_through_utc"]))
    return rows


def write_index(rows: List[Dict], path: str = INDEX_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_index(path: str = INDEX_PATH) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def resolve_for_kickoff(
    index_rows: List[Dict], year: int, kickoff: dt.datetime
) -> Optional[Dict]:
    """Newest snapshot for ``year`` that was effective strictly before kickoff."""
    if kickoff is None:
        return None
    best = None
    best_eff = None
    for row in index_rows:
        try:
            if int(row["season_year"]) != int(year):
                continue
        except (TypeError, ValueError, KeyError):
            continue
        eff = parse_dt(row.get("effective_through_utc"))
        if eff is None or eff >= kickoff:
            continue
        if best_eff is None or eff > best_eff:
            best, best_eff = row, eff
    return best


def verify_index(rows: Optional[List[Dict]] = None) -> List[Dict]:
    """Report snapshots whose contents no longer match what was indexed."""
    rows = rows if rows is not None else read_index()
    drift = []
    for row in rows:
        path = os.path.join(BASE_DIR, row.get("source_path", ""))
        if not os.path.exists(path):
            drift.append({**row, "issue": "missing"})
            continue
        if sha256_of(path) != row.get("sha256"):
            drift.append({**row, "issue": "content_changed"})
    return drift
