"""Fit the final probability tables on all data with the hyper-parameters chosen by backtest.py.

Writes data/stats/{stop,trip}_cells.parquet: one row per cell at every hierarchy level, with
p_delay6 / p_delay15 / p_delay30 (among trains that ran), p_cancel, the raw sample size n,
a `level` column (0 = coarsest) and `data_until`. Cells with n < MIN_SAMPLES are flagged `insufficient`.

Usage:
    uv run python pipeline/build_stats.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from events import load_stops, load_trips
from model import STOP_LEVELS, TRIP_LEVELS, daily_counts, fit

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "stats"
MODEL_CFG = ROOT / "config" / "model.yaml"
MIN_SAMPLES = yaml.safe_load((ROOT / "config" / "weather.yaml").read_text())["min_samples"]


def build(events: pd.DataFrame, levels, cfg: dict, prefix: str) -> pd.DataFrame:
    ref = events["date"].max() + pd.Timedelta(days=1)
    ran = events[~events["canceled"]]
    d = cfg[f"{prefix}_delay6"]
    c = cfg[f"{prefix}_cancel"]
    fits = {
        "p_delay6": fit(daily_counts(ran, "delayed6", levels), levels, ref, d["half_life_days"], d["prior_strength"]),
        "p_delay15": fit(daily_counts(ran, "delayed15", levels), levels, ref, d["half_life_days"], d["prior_strength"]),
        "p_delay30": fit(daily_counts(ran, "delayed30", levels), levels, ref, d["half_life_days"], d["prior_strength"]),
        "p_cancel": fit(daily_counts(events, "canceled", levels), levels, ref, c["half_life_days"], c["prior_strength"]),
    }
    out = []
    for i, lv in enumerate(levels):
        keys = list(lv)
        t = fits["p_cancel"].tables[i][keys + ["n", "p"]].rename(columns={"n": "n_all", "p": "p_cancel"})
        for col in ("p_delay6", "p_delay15", "p_delay30"):
            ft = fits[col].tables[i][keys + ["n", "p"]].rename(columns={"p": col, "n": "n"})
            t = t.merge(ft if col == "p_delay6" else ft.drop(columns="n"), on=keys, how="left")
        t["n"] = t["n"].fillna(0).astype(int)  # trains that ran (denominator of p_delay*)
        t["level"] = i
        out.append(t)
    df = pd.concat(out, ignore_index=True)
    if "hour" in df:
        df["hour"] = df["hour"].astype("Int64")  # null on coarser levels
    df["insufficient"] = df["n"] < MIN_SAMPLES
    df["data_until"] = ref - pd.Timedelta(days=1)
    return df


def main() -> None:
    cfg = yaml.safe_load(MODEL_CFG.read_text())["tasks"]
    stops = load_stops()
    trips = load_trips(stops)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, events, levels in (("stop", stops, STOP_LEVELS), ("trip", trips, TRIP_LEVELS)):
        df = build(events, levels, cfg, name)
        path = OUT / f"{name}_cells.parquet"
        df.to_parquet(path, index=False)
        finest = df[df["level"] == len(levels) - 1]
        print(f"{path.relative_to(ROOT)}: {len(df):,} rows, finest cells {len(finest):,} "
              f"({finest['insufficient'].mean():.1%} with n<{MIN_SAMPLES}), data until {df['data_until'].iloc[0].date()}")


if __name__ == "__main__":
    main()
