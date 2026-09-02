"""On-disk cache for CFBD API responses.

``rankings.py`` makes a few hundred sequential CFBD calls per run (one per team
for the Nature and SOR passes), which makes a cold run take 20+ minutes and
gives Cloudflare several hundred chances to hand back a retryable 502. Almost
all of those calls ask about *finished* seasons, whose answers never change.

This module memoizes API responses to ``data_exports/api_cache/<year>/``.
Responses are pickled, so cfbd's pydantic model objects round-trip exactly --
no attribute loss from flattening to CSV.

Freshness rules:

* A season strictly older than the active season is **closed**: cached forever.
* The **active** season honours ``CFB_CACHE_TTL_HOURS`` (default 6), so a weekly
  refresh always re-pulls live results while a single run reuses its own calls.
* ``CFB_NO_CACHE=1`` bypasses reads entirely (entries are still written).
"""

import datetime as dt
import hashlib
import json
import os
import pickle
from typing import Any, Callable, Optional

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_exports", "api_cache")
DEFAULT_TTL_HOURS = 6.0

_STATS = {"hits": 0, "misses": 0, "writes": 0}


def active_season(today: Optional[dt.date] = None) -> int:
    """Season year for a date, matching rankings.py: before Sep 1 is last season."""
    today = today or dt.date.today()
    return today.year if today >= dt.date(today.year, 9, 1) else today.year - 1


def cache_enabled() -> bool:
    return os.environ.get("CFB_NO_CACHE", "").strip().lower() not in ("1", "true", "yes")


def ttl_hours() -> float:
    try:
        return float(os.environ.get("CFB_CACHE_TTL_HOURS", DEFAULT_TTL_HOURS))
    except ValueError:
        return DEFAULT_TTL_HOURS


def _function_name(api_function: Callable) -> str:
    owner = getattr(api_function, "__self__", None)
    owner_name = type(owner).__name__ if owner is not None else ""
    return f"{owner_name}.{getattr(api_function, '__name__', repr(api_function))}".strip(".")


def _cache_path(api_function: Callable, kwargs: dict) -> str:
    name = _function_name(api_function)
    payload = json.dumps(sorted((k, repr(v)) for k, v in kwargs.items()))
    digest = hashlib.md5(f"{name}|{payload}".encode()).hexdigest()[:16]
    year = kwargs.get("year") or "misc"
    short = name.split(".")[-1]
    return os.path.join(CACHE_DIR, str(year), f"{short}_{digest}.pkl")


def _is_fresh(path: str, kwargs: dict) -> bool:
    if not os.path.exists(path):
        return False
    year = kwargs.get("year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None

    # Finished seasons are immutable -- never re-fetch them.
    if year is not None and year < active_season():
        return True

    age_hours = (dt.datetime.now().timestamp() - os.path.getmtime(path)) / 3600.0
    return age_hours < ttl_hours()


def cached_call(api_function: Callable, **kwargs) -> Any:
    """Call ``api_function(**kwargs)``, serving from disk when the entry is fresh."""
    path = _cache_path(api_function, kwargs)

    if cache_enabled() and _is_fresh(path, kwargs):
        try:
            with open(path, "rb") as f:
                _STATS["hits"] += 1
                return pickle.load(f)
        except Exception as exc:  # corrupt or half-written entry
            print(f"[api_cache] Ignoring unreadable entry {os.path.basename(path)}: {exc}")

    _STATS["misses"] += 1
    result = api_function(**kwargs)

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as f:
            pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
        _STATS["writes"] += 1
    except Exception as exc:
        print(f"[api_cache] Could not cache {os.path.basename(path)}: {exc}")

    return result


def stats() -> dict:
    return dict(_STATS)


def summary() -> str:
    total = _STATS["hits"] + _STATS["misses"]
    rate = (100.0 * _STATS["hits"] / total) if total else 0.0
    return (
        f"[api_cache] {_STATS['hits']} hits / {_STATS['misses']} misses "
        f"({rate:.0f}% hit rate), {_STATS['writes']} entries written"
    )
