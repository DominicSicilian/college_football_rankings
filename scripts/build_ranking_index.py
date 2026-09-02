"""Build or refresh published_rankings/ranking_index.csv.

Run after any ranking release so the prediction ledger can resolve, for any
kickoff, which snapshot was the newest one available at the time.

    python scripts/build_ranking_index.py              # all seasons
    python scripts/build_ranking_index.py --year 2026  # one season
    python scripts/build_ranking_index.py --verify     # check for drift
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ranking_index as ri  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, action="append", dest="years")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only check the existing index for missing or altered snapshots.",
    )
    args = parser.parse_args()

    if args.verify:
        drift = ri.verify_index()
        if not drift:
            rows = ri.read_index()
            print(f"Index clean: {len(rows)} snapshots, all hashes match.")
            return
        print(f"Index drift detected in {len(drift)} snapshot(s):")
        for row in drift:
            print(f"  {row['issue']:16} {row['snapshot_label']:24} {row['source_path']}")
        raise SystemExit(1)

    rows = ri.build_index(args.years)
    if not rows:
        raise SystemExit("No ranking snapshots found to index.")
    ri.write_index(rows)

    by_year = {}
    for row in rows:
        by_year.setdefault(row["season_year"], 0)
        by_year[row["season_year"]] += 1

    print(f"Indexed {len(rows)} ranking snapshots -> {os.path.relpath(ri.INDEX_PATH, ri.BASE_DIR)}")
    for year in sorted(by_year):
        print(f"  {year}: {by_year[year]} snapshots")


if __name__ == "__main__":
    main()
