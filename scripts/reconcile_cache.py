"""Purge active-season game-cache entries that live results have made stale.

The API cache assumes a cached response stays valid until its TTL elapses. That
holds for closed seasons (immutable) but breaks for the *active* season: a
team's game list changes the moment a game goes final, and across a CI
``actions/cache`` restore the mtime-based freshness check can keep serving a
snapshot taken before the game finished. FSU beat... lost to SMU on a Sunday
night while the cache still held that game as ``completed=False``, and every
rerun kept reading the frozen copy.

This reconciler makes ONE cheap pass:

* Fetch the active season's full slate directly from the API (1-2 calls total,
  bypassing the cache) to get ground truth for which games are final.
* Walk the on-disk game-cache entries for that season and delete any that hold a
  game the API now reports as completed but the cached copy still shows as not
  completed (or with no score). Only stale entries are removed.

The next rankings run then re-fetches just those teams. Net API cost: 1-2 calls
here, plus a re-fetch of only the genuinely stale entries -- the cache's real
value (thousands of immutable closed-season calls, and within-run reuse) is
untouched.
"""

import argparse
import glob
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cfbd  # noqa: E402

import api_cache  # noqa: E402

JSON_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_exports", "cache"
)


def game_key(home, away, week):
    return (str(week), str(home or "").strip().lower(), str(away or "").strip().lower())


def attr(g, *names):
    for n in names:
        v = getattr(g, n, None) if not isinstance(g, dict) else g.get(n)
        if v is not None:
            return v
    return None


def is_final(g):
    hp = attr(g, "home_points", "homePoints")
    ap = attr(g, "away_points", "awayPoints")
    completed = attr(g, "completed")
    return bool(completed) and hp is not None and ap is not None


def fetch_truth(year, api):
    """Set of game keys the API now reports as final, for the active season."""
    final_keys = set()
    for season_type in ("regular", "postseason"):
        try:
            games = api.get_games(year=year, season_type=season_type)
        except Exception as exc:
            print(f"  reconcile: could not fetch {season_type} slate ({exc})", file=sys.stderr)
            continue
        for g in games:
            if is_final(g):
                final_keys.add(game_key(attr(g, "home_team", "homeTeam"),
                                        attr(g, "away_team", "awayTeam"),
                                        attr(g, "week")))
    return final_keys


def _load(path):
    try:
        if path.endswith(".json"):
            import json
            return json.load(open(path, encoding="utf-8"))
        return pickle.load(open(path, "rb"))
    except Exception:
        return None


def entry_is_stale(path, final_keys):
    """True if this cached game list holds a now-final game as not-yet-final."""
    obj = _load(path)
    if not isinstance(obj, list):
        return False
    for g in obj:
        home = attr(g, "home_team", "homeTeam")
        away = attr(g, "away_team", "awayTeam")
        if home is None and away is None:
            return False  # not a game list
        if game_key(home, away, attr(g, "week")) in final_keys and not is_final(g):
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, default=api_cache.active_season())
    ap.add_argument("--dry-run", action="store_true", help="Report stale entries without deleting.")
    args = ap.parse_args()

    key = (os.environ.get("CFBD_API_KEY") or "").strip()
    if not key:
        print("reconcile: CFBD_API_KEY not set; skipping.", file=sys.stderr)
        return

    year_dir = os.path.join(api_cache.CACHE_DIR, str(args.year))
    entries = glob.glob(os.path.join(year_dir, "*.pkl"))
    # The backtest keeps its own JSON game cache keyed by week; those go stale the
    # same way. Only the active season's files can change, so scope to this year.
    entries += glob.glob(os.path.join(JSON_CACHE_DIR, f"games_{args.year}_*.json"))
    if not entries:
        print(f"reconcile: no cache entries for {args.year}; nothing to do.")
        return

    config = cfbd.Configuration(host="https://api.collegefootballdata.com", access_token=key)
    api = cfbd.GamesApi(cfbd.ApiClient(config))

    final_keys = fetch_truth(args.year, api)
    if not final_keys:
        print(f"reconcile: API reports no final {args.year} games yet; nothing to purge.")
        return

    stale = [p for p in entries if entry_is_stale(p, final_keys)]
    verb = "Would purge" if args.dry_run else "Purged"
    for p in stale:
        if not args.dry_run:
            os.remove(p)
        print(f"  {verb}: {os.path.basename(p)}")
    print(f"reconcile: {len(final_keys)} final games known; "
          f"{verb.lower()} {len(stale)} of {len(entries)} cached {args.year} game entries.")


if __name__ == "__main__":
    main()
