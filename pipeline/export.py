"""Export the probability tables as static JSON for the site (site/public/data/).

- meta.json      data range, weather thresholds/copy, Hessen holidays, attribution
- hub.json       Frankfurt Hbf: overall, per day type and hour (all lines combined), per line
- corridor.json  Frankfurt Hbf ↔ Darmstadt Hbf trips: direction × day type × line × departure hour,
                 plus `conditional`: arrival-delay probability by origin-departure-delay bin (conditional.py)
- ranking.json   observed worst/best lines and trains in the last 7 days of data (ranking.py)

Every forecast carries n (sample size). Cells with n < min_samples have p = null ("데이터 부족").
The site decides today's day type itself, so the export stays valid between data refreshes.

Usage:
    uv run python pipeline/export.py
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import holidays
import pandas as pd
import yaml

from events import load_stations, load_stops, load_trips
from conditional import export_table
from ranking import weekly_ranking

ROOT = Path(__file__).resolve().parent.parent
STATS = ROOT / "data" / "stats"
OUT = ROOT / "site" / "public" / "data"
WEATHER = yaml.safe_load((ROOT / "config" / "weather.yaml").read_text())
MIN_N = WEATHER["min_samples"]
DAYTYPES = ["weekday", "sat", "sun_hol"]
P_COLS = {"p_delay6": "p6", "p_delay15": "p15", "p_delay30": "p30", "p_cancel": "pc"}


def forecast(row) -> dict:
    """One forecast record; probabilities hidden when the sample is too small."""
    n = int(row["n"])
    rec = {"n": n}
    for col, key in P_COLS.items():
        v = row[col]
        rec[key] = None if n < MIN_N or pd.isna(v) else round(float(v), 3)
    return rec


def combine(cells: pd.DataFrame) -> dict:
    """Combine cells (e.g. all lines in one hour) weighting each by its number of trains."""
    n = cells["n"].sum()
    n_all = cells["n_all"].sum()
    row = {"n": n}
    for col in ("p_delay6", "p_delay15", "p_delay30"):
        row[col] = (cells[col] * cells["n"]).sum() / n if n else None
    row["p_cancel"] = (cells["p_cancel"] * cells["n_all"]).sum() / n_all if n_all else None
    return forecast(row)


def export_hub(stops: pd.DataFrame, key: str) -> dict:
    s = stops[stops["station"] == key]
    finest = s[s["level"] == 3]
    by_line = s[s["level"] == 2]
    out = {"station": key, "overall": forecast(s[s["level"] == 0].iloc[0]), "daytypes": {}}
    for d in DAYTYPES:
        f = finest[finest["daytype"] == d]
        lines = by_line[(by_line["daytype"] == d) & (by_line["n"] >= MIN_N)].sort_values("n", ascending=False)
        out["daytypes"][d] = {
            "overall": combine(f),
            "hours": {int(h): combine(g) for h, g in f.groupby("hour")},
            "lines": [{"line": r["line"], **forecast(r)} for _, r in lines.iterrows()],
        }
    return out


def export_corridor(trips: pd.DataFrame, cfg: dict, n_days: int) -> dict:
    # Keep lines that run on average at least once a day in either direction.
    totals = trips[trips["level"] == 1].groupby("line")["n_all"].sum()
    lines = totals[totals >= n_days].sort_values(ascending=False).index.tolist()
    names = {k: v["name"] for k, v in cfg["stations"].items()}
    out = {
        "directions": {
            "ffm_da": {"from": names["frankfurt_hbf"], "to": names["darmstadt_hbf"]},
            "da_ffm": {"from": names["darmstadt_hbf"], "to": names["frankfurt_hbf"]},
        },
        "lines": lines,
        "cells": {},
    }
    finest = trips[(trips["level"] == 3) & trips["line"].isin(lines)]
    by_line = trips[(trips["level"] == 2) & trips["line"].isin(lines)]
    for direction in out["directions"]:
        out["cells"][direction] = {}
        for d in DAYTYPES:
            f = finest[(finest["direction"] == direction) & (finest["daytype"] == d)]
            bl = by_line[(by_line["direction"] == direction) & (by_line["daytype"] == d)]
            out["cells"][direction][d] = {
                line: {
                    "overall": forecast(bl[bl["line"] == line].iloc[0]) if (bl["line"] == line).any() else None,
                    "hours": {int(r["hour"]): forecast(r) for _, r in f[f["line"] == line].iterrows()},
                }
                for line in lines
            }
    return out


def main() -> None:
    stops = pd.read_parquet(STATS / "stop_cells.parquet")
    trips = pd.read_parquet(STATS / "trip_cells.parquet")
    cfg = load_stations()
    data_until = pd.Timestamp(stops["data_until"].iloc[0]).date()
    slim = sorted((ROOT / "data" / "slim").glob("data-*.parquet"))
    data_from = dt.date.fromisoformat(slim[0].stem.removeprefix("data-") + "-01")
    n_days = (data_until - data_from).days + 1

    this_year = dt.date.today().year
    hol = holidays.Germany(subdiv="HE", years=range(this_year - 1, this_year + 3), language="de")
    meta = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "data_from": data_from.isoformat(),
        "data_until": data_until.isoformat(),
        "weather": WEATHER,
        "holidays_he": {d.isoformat(): name for d, name in sorted(hol.items())},
        "stations": {k: v["name"] for k, v in cfg["stations"].items()},
        "live": yaml.safe_load((ROOT / "config" / "live.yaml").read_text()),
        "attribution": {
            "text": "Daten: Deutsche Bahn (CC BY 4.0), via piebro/deutsche-bahn-data",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "source_url": "https://huggingface.co/datasets/piebro/deutsche-bahn-data",
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    events = load_stops()
    trip_events = load_trips(events)
    corridor = export_corridor(trips, cfg, n_days)
    # Phase 5: arrival-delay probability given how late the train already is at its origin.
    corridor["conditional"] = export_table(trip_events, corridor["lines"], MIN_N)
    files = {
        "meta.json": meta,
        "hub.json": export_hub(stops, cfg["hub"]),
        "corridor.json": corridor,
        "ranking.json": weekly_ranking(events, trip_events, cfg["hub"], meta["stations"]),
    }
    for name, obj in files.items():
        path = OUT / name
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
