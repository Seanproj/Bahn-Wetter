"""Per-line delay profiles for the playful views (observed values, not model estimates).

- characters: per line shown on any route, all its route trips together — delay/cancel rates, mean delay, 95th
  percentile, worst delay and how often it arrives early. The site turns these into a persona for the
  character cards (랭킹 tab).
- dist: per direction × line, 101 quantiles of the arrival delay among trains that ran. The delay gacha
  (출퇴근 detail sheet) picks a delay bucket from the tapped cell's own probabilities, then draws a
  realistic minute value from these quantiles within that bucket.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _r(x: float, nd: int = 3) -> float:
    return round(float(x), nd)


def line_profiles(trips: pd.DataFrame, lines_by_direction: dict[str, list[str]], min_n: int) -> dict:
    """characters: every line shown on some route, measured over all its route trips."""
    characters, dist = {}, {d: {} for d in lines_by_direction}
    for line in sorted({l for lines in lines_by_direction.values() for l in lines}):
        # One S8 run can serve several routes (airport, Mainz, Wiesbaden); count each run once here.
        t = trips[trips["line"] == line].drop_duplicates("ride_key")
        ran = t[~t["canceled"] & t["delay"].notna()]
        if len(ran) < min_n:
            continue
        d = ran["delay"]
        characters[line] = {
            "n": int(len(t)),
            "p6": _r((d >= 6).mean()),
            "p15": _r((d >= 15).mean()),
            "p30": _r((d >= 30).mean()),
            "cancel": _r(t["canceled"].mean()),
            "mean": _r(d.mean(), 1),
            "p95": int(d.quantile(0.95)),
            "max": int(d.max()),
            "early": _r((d < 0).mean()),
        }
        for direction in (k for k, lines in lines_by_direction.items() if line in lines):
            per_dir = trips[(trips["line"] == line) & (trips["direction"] == direction)]
            dd = per_dir.loc[~per_dir["canceled"] & per_dir["delay"].notna(), "delay"]
            if len(dd) >= min_n:
                dist[direction][line] = [int(q) for q in np.quantile(dd, np.linspace(0, 1, 101), method="nearest")]
    return {"characters": characters, "dist": dist}
