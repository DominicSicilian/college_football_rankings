import argparse
import os

import pandas as pd
import requests

BASE_URL = "https://api.collegefootballdata.com"
YEAR = 2026

def fetch_player_recruiting_rankings(year: int, api_key: str) -> list[dict]:
    url = f"{BASE_URL}/recruiting/players"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"year": year, "classification": "HighSchool"}

    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, list):
        raise ValueError("Unexpected response format from CFBD API.")

    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pull recruit-level rankings from CollegeFootballData API"
    )
    parser.add_argument("--year", type=int, default=YEAR, help="Recruiting class year")
    parser.add_argument(
        "--output",
        type=str,
        default=f"recruiting_players_{YEAR}.csv",
        help="CSV output filename",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="How many top recruits to print in terminal",
    )
    args = parser.parse_args()

    api_key = os.getenv("CFBD_API_KEY")
    if not api_key:
        print("Error: CFBD_API_KEY is not set in your environment.")
        return 1

    try:
        rankings = fetch_player_recruiting_rankings(args.year, api_key)
    except requests.HTTPError as exc:
        print(f"API request failed: {exc}")
        return 1
    except Exception as exc:
        print(f"Failed to fetch rankings: {exc}")
        return 1

    if not rankings:
        print(f"No recruit rankings returned for class {args.year}.")
        return 0

    df = pd.DataFrame(rankings)

    sort_col = "ranking" if "ranking" in df.columns else None
    if sort_col:
        df = df.sort_values(sort_col, ascending=True)

    keep_cols = [
        col
        for col in [
            "ranking",
            "name",
            "position",
            "rating",
            "stars",
            "school",
            "committedTo",
            "city",
            "stateProvince",
        ]
        if col in df.columns
    ]
    preview_df = df[keep_cols] if keep_cols else df

    print(f"Top {args.top} recruits for class {args.year}:")
    print(preview_df.head(args.top).to_string(index=False))

    df.to_csv(args.output, index=False)
    print(f"\nSaved {len(df)} rows to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
