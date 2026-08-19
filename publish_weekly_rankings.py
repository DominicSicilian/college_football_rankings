import argparse
import csv
import datetime as dt
import glob
import os
import re
import shutil
from typing import Dict, List, Optional, Tuple

BASE_DIR = os.path.dirname(__file__)
DATA_EXPORTS_DIR = os.path.join(BASE_DIR, "data_exports")
PUBLISHED_DIR = os.path.join(BASE_DIR, "published_rankings")
MANIFEST_PATH = os.path.join(PUBLISHED_DIR, "manifest.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Snapshot the latest live rankings artifacts into published_rankings/ for git history."
    )
    parser.add_argument(
        "--year",
        type=int,
        default=dt.date.today().year,
        help="Season year to publish (default: current year).",
    )
    parser.add_argument(
        "--label",
        type=str,
        default="",
        help="Optional release label (example: week3_update).",
    )
    parser.add_argument(
        "--source-file",
        type=str,
        default="",
        help="Optional explicit SPI rankings CSV path to publish.",
    )
    return parser.parse_args()


def latest_spi_rankings_file(year: int) -> Optional[str]:
    pattern = os.path.join(DATA_EXPORTS_DIR, "spi_rankings_*.csv")
    files = []
    for path in glob.glob(pattern):
        base = os.path.basename(path).lower()
        if "detailed" in base:
            continue
        if base.startswith("spi_rankings_final"):
            continue
        if str(year) not in base:
            continue
        files.append(path)

    if not files:
        return None

    def classify(path: str) -> Tuple[int, int, float]:
        base = os.path.basename(path)
        tier = 0
        week = 0

        post = re.match(r"spi_rankings_(\d+)_post_w(\d+)\.csv$", base)
        reg = re.match(r"spi_rankings_(\d+)_w(\d+)\.csv$", base)
        pre = re.match(r"spi_rankings_preseason_(\d+)\.csv$", base)
        year_only = re.match(r"spi_rankings_(\d+)\.csv$", base)

        if post:
            tier = 4
            week = int(post.group(2))
        elif reg:
            tier = 3
            week = int(reg.group(2))
        elif pre:
            tier = 2
            week = 0
        elif year_only:
            tier = 1
            week = 0

        return (tier, week, os.path.getmtime(path))

    return max(files, key=classify)


def snapshot_label_from_spi_file(file_name: str) -> str:
    base = file_name
    if base.endswith(".csv"):
        base = base[:-4]
    if base.startswith("spi_rankings_"):
        return base[len("spi_rankings_") :]
    return base


def collect_related_files(snapshot_label: str) -> List[str]:
    prefixes = [
        "spi_rankings_",
        "conference_rankings_",
        "nature_stats_",
        "sor_stats_",
        "team_standings_",
        "cross_conference_standings_",
    ]

    out = []
    for prefix in prefixes:
        candidate = os.path.join(DATA_EXPORTS_DIR, f"{prefix}{snapshot_label}.csv")
        if os.path.exists(candidate):
            out.append(candidate)
    return out


def ensure_manifest_exists() -> None:
    os.makedirs(PUBLISHED_DIR, exist_ok=True)
    if os.path.exists(MANIFEST_PATH):
        return
    with open(MANIFEST_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "published_at_utc",
                "season_year",
                "release_label",
                "snapshot_label",
                "source_spi_file",
                "published_dir",
                "files_count",
            ]
        )


def append_manifest_row(row: Dict[str, str]) -> None:
    ensure_manifest_exists()
    with open(MANIFEST_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                row["published_at_utc"],
                row["season_year"],
                row["release_label"],
                row["snapshot_label"],
                row["source_spi_file"],
                row["published_dir"],
                row["files_count"],
            ]
        )


def main() -> None:
    args = parse_args()
    os.makedirs(PUBLISHED_DIR, exist_ok=True)

    if args.source_file:
        source_spi = args.source_file
        if not os.path.isabs(source_spi):
            source_spi = os.path.join(BASE_DIR, source_spi)
        if not os.path.exists(source_spi):
            raise SystemExit(f"Source file not found: {source_spi}")
    else:
        source_spi = latest_spi_rankings_file(args.year)
        if source_spi is None:
            raise SystemExit(
                f"No spi_rankings_<year>*.csv file found for {args.year} under {DATA_EXPORTS_DIR}."
            )

    source_base = os.path.basename(source_spi)
    snapshot_label = snapshot_label_from_spi_file(source_base)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    clean_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.label.strip()) if args.label else ""
    release_tag = clean_label if clean_label else "weekly_publish"

    publish_dir_name = f"{timestamp}__{snapshot_label}__{release_tag}"
    publish_dir = os.path.join(PUBLISHED_DIR, publish_dir_name)
    os.makedirs(publish_dir, exist_ok=False)

    to_copy = [source_spi]
    to_copy.extend(collect_related_files(snapshot_label))

    copied = []
    seen = set()
    for src in to_copy:
        if src in seen:
            continue
        seen.add(src)
        if not os.path.exists(src):
            continue

        file_name = os.path.basename(src)
        dst = os.path.join(publish_dir, file_name)
        shutil.copy2(src, dst)
        copied.append(file_name)

    metadata_path = os.path.join(publish_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        import json

        json.dump(
            {
                "published_at_utc": timestamp,
                "season_year": args.year,
                "release_label": release_tag,
                "snapshot_label": snapshot_label,
                "source_spi_file": source_base,
                "files": copied,
            },
            f,
            indent=2,
        )

    append_manifest_row(
        {
            "published_at_utc": timestamp,
            "season_year": str(args.year),
            "release_label": release_tag,
            "snapshot_label": snapshot_label,
            "source_spi_file": source_base,
            "published_dir": os.path.relpath(publish_dir, BASE_DIR),
            "files_count": str(len(copied)),
        }
    )

    print("Published weekly rankings snapshot")
    print(f"Source SPI file: {source_base}")
    print(f"Snapshot label: {snapshot_label}")
    print(f"Output folder: {publish_dir}")
    print(f"Files copied: {len(copied)}")


if __name__ == "__main__":
    main()
