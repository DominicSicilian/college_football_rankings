"""Scrape ThePredictionTracker's NCAA season results into CSV.

thepredictiontracker.com publishes season-long accuracy for ~50 public college
football rating systems, including ESPN FPI and the Vegas line. That is the
natural benchmark for this repo's SPI model.

    python scripts/fetch_prediction_tracker.py --year 2025
    python scripts/fetch_prediction_tracker.py --year 2021 --year 2022 ...

Writes data_exports/benchmarks/prediction_tracker_<year>.csv. Responses are
cached to data_exports/benchmarks/raw/ so reruns do not re-hit the site; pass
--refresh to force a new request.

Comparability note: the site scores FBS-vs-FBS games only (games with a betting
line). Compare against the same subset of this repo's ledger, not its headline
number, which also counts FBS-vs-FCS games.
"""

import argparse
import csv
import datetime as dt
import html
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH_DIR = os.path.join(BASE_DIR, "data_exports", "benchmarks")
RAW_DIR = os.path.join(BENCH_DIR, "raw")

URL_TEMPLATE = "https://www.thepredictiontracker.com/ncaaresults.php?year={yy:02d}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

FIELDS = [
    "season_year",
    "rank",
    "system",
    "pct_correct",
    "against_spread",
    "absolute_error",
    "bias",
    "mean_square_error",
    "games",
    "su_wins",
    "su_losses",
    "ats_wins",
    "ats_losses",
    "source_url",
    "fetched_at_utc",
]

TAG_RE = re.compile(r"<[^>]+>")
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)


def clean(cell: str) -> str:
    text = TAG_RE.sub("", cell)
    text = html.unescape(text)
    return " ".join(text.split())


def to_num(value: str):
    value = (value or "").strip()
    if not value:
        return ""
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return ""


def fetch_html(year: int, refresh: bool) -> str:
    yy = year % 100
    url = URL_TEMPLATE.format(yy=yy)
    os.makedirs(RAW_DIR, exist_ok=True)
    cache_path = os.path.join(RAW_DIR, f"ncaaresults_{year}.html")

    if os.path.exists(cache_path) and not refresh:
        with open(cache_path, encoding="utf-8") as f:
            return f.read()

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read().decode("utf-8", "replace")

    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(body)
    return body


def parse_results(page: str, year: int, url: str) -> list:
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    rows = []

    for raw_row in ROW_RE.findall(page):
        cells = [clean(c) for c in CELL_RE.findall(raw_row)]
        if len(cells) < 11:
            continue
        # Data rows lead with an integer rank; the header row does not.
        if not re.fullmatch(r"\d+", cells[0]):
            continue

        rows.append(
            {
                "season_year": year,
                "rank": int(cells[0]),
                "system": cells[1],
                "pct_correct": to_num(cells[2]),
                "against_spread": to_num(cells[3]),
                "absolute_error": to_num(cells[4]),
                "bias": to_num(cells[5]),
                "mean_square_error": to_num(cells[6]),
                "games": to_num(cells[7]),
                "su_wins": to_num(cells[8]),
                "su_losses": to_num(cells[9]),
                "ats_wins": to_num(cells[10]) if len(cells) > 10 else "",
                "ats_losses": to_num(cells[11]) if len(cells) > 11 else "",
                "source_url": url,
                "fetched_at_utc": stamp,
            }
        )

    rows.sort(key=lambda r: r["rank"])
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, action="append", dest="years", required=False)
    parser.add_argument("--refresh", action="store_true", help="Ignore the cached HTML.")
    args = parser.parse_args()

    years = args.years or [dt.date.today().year]
    os.makedirs(BENCH_DIR, exist_ok=True)

    for i, year in enumerate(years):
        url = URL_TEMPLATE.format(yy=year % 100)
        try:
            page = fetch_html(year, args.refresh)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"{year}: fetch failed ({exc})", file=sys.stderr)
            continue

        rows = parse_results(page, year, url)
        if not rows:
            print(f"{year}: no result rows parsed", file=sys.stderr)
            continue

        out_path = os.path.join(BENCH_DIR, f"prediction_tracker_{year}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        fpi = next((r for r in rows if "FPI" in r["system"].upper()), None)
        fpi_note = f", ESPN FPI {fpi['pct_correct']:.5f} (rank {fpi['rank']})" if fpi else ""
        print(f"{year}: {len(rows)} systems -> {os.path.relpath(out_path, BASE_DIR)}{fpi_note}")

        if i < len(years) - 1 and args.refresh:
            time.sleep(2)  # be polite when pulling several seasons


if __name__ == "__main__":
    main()
