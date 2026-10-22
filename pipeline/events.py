"""Load the slim cache into clean event tables shared by build_stats.py and backtest.py.

Rules (HANDOFF §5.1 + Phase 0 decisions, see reports/phase0_summary.md):
- Drop rows without a plan record (no planned time/delay/type; includes all replacement trains)
  and unplanned additional stops.
- A stop is measured on arrival when it has a planned arrival, otherwise (train starts here)
  on departure. Delay = change time − planned time in minutes.
- A planned train that was replaced by another train number at the same station and day counts
  as canceled.
- Planned rail-replacement buses (train_type "Bus") are not trains and are dropped.
- Bare numeric line numbers are prefixed with the train type ("6" → "S6").
- Day type: weekday / sat / sun_hol (Sundays + Hessen public holidays).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import holidays
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
SLIM_GLOB = ROOT / "data" / "slim" / "data-*.parquet"
STATIONS = ROOT / "config" / "stations.yaml"
DELAY_MIN = 6


def load_stations() -> dict:
    return yaml.safe_load(STATIONS.read_text())


def day_type(dates: pd.Series) -> pd.Series:
    years = range(dates.dt.year.min(), dates.dt.year.max() + 1)
    hol = {pd.Timestamp(d) for d in holidays.Germany(subdiv="HE", years=years)}
    out = pd.Series("weekday", index=dates.index)
    out[dates.dt.dayofweek == 5] = "sat"
    out[(dates.dt.dayofweek == 6) | dates.isin(hol)] = "sun_hol"
    return out


def load_stops() -> pd.DataFrame:
    """One row per planned stop at a target station."""
    cfg = load_stations()
    eva_to_key = {e: k for k, s in cfg["stations"].items() for e in s["eva"]}
    con = duckdb.connect()
    df = con.execute(f"""
        WITH s AS (
          SELECT *, regexp_replace(id, '-[0-9]+$', '') AS ride_key
          FROM read_parquet('{SLIM_GLOB}')
        ),
        replaced AS (
          SELECT DISTINCT eva, replaced_train_number AS train_number,
                 CAST(coalesce(departure_planned_time, arrival_planned_time) AS DATE) AS d
          FROM s WHERE is_replacement_train AND replaced_train_number IS NOT NULL
        )
        SELECT s.ride_key, s.eva, s.train_type, s.train_number,
               -- 2025-11/12 files carry bare numbers ("6", "68"); later ones "S6", "RB68".
               CASE WHEN regexp_matches(s.line_number, '^[0-9]+$') THEN s.train_type || s.line_number
                    ELSE coalesce(s.line_number, s.train_type) END AS line,
               s.train_line_station_num AS stop_num,
               s.final_destination_station AS destination,
               coalesce(s.arrival_planned_time, s.departure_planned_time) AS planned,
               CASE WHEN s.arrival_planned_time IS NOT NULL
                    THEN date_diff('minute', s.arrival_planned_time, s.arrival_change_time)
                    ELSE date_diff('minute', s.departure_planned_time, s.departure_change_time) END AS delay,
               (CASE WHEN s.arrival_planned_time IS NOT NULL THEN s.arrival_is_canceled
                     ELSE s.departure_is_canceled END
                OR r.eva IS NOT NULL) AS canceled,
               s.departure_planned_time AS dep_planned,
               date_diff('minute', s.departure_planned_time, s.departure_change_time) AS dep_delay,
               (s.departure_is_canceled OR r.eva IS NOT NULL) AS dep_canceled
        FROM s
        LEFT JOIN replaced r
          ON r.eva = s.eva AND r.train_number = s.train_number
         AND r.d = CAST(coalesce(s.departure_planned_time, s.arrival_planned_time) AS DATE)
        WHERE s.has_plan_record
          AND NOT coalesce(s.is_additional_stop, false)
          AND NOT coalesce(s.is_replacement_train, false)
          AND coalesce(s.train_type, '') <> 'Bus'
    """).df()
    df["station"] = df["eva"].map(eva_to_key)
    df["planned"] = pd.to_datetime(df["planned"])
    df["date"] = df["planned"].dt.normalize()
    df["hour"] = df["planned"].dt.hour
    df["daytype"] = day_type(df["date"])
    df["canceled"] = df["canceled"].fillna(False).astype(bool)
    df["delayed6"] = (df["delay"] >= DELAY_MIN) & ~df["canceled"]
    df["delayed15"] = (df["delay"] >= 15) & ~df["canceled"]
    df["delayed30"] = (df["delay"] >= 30) & ~df["canceled"]
    return df


def load_trips(stops: pd.DataFrame) -> pd.DataFrame:
    """One row per corridor run (same ride_key at Frankfurt Hbf and Darmstadt Hbf).

    Forecast target for the commuter grid: delay/cancellation on arrival at the destination,
    keyed by the planned departure hour at the origin.
    """
    ffm = stops[stops["station"] == "frankfurt_hbf"]
    da = stops[stops["station"] == "darmstadt_hbf"]
    cols = ["ride_key", "stop_num", "dep_planned", "dep_delay", "dep_canceled", "planned", "delay", "canceled", "line", "train_type", "train_number"]
    m = ffm[cols].merge(da[cols], on="ride_key", suffixes=("_ffm", "_da"))
    south = m["stop_num_ffm"] < m["stop_num_da"]
    o = lambda c: m[f"{c}_ffm"].where(south, m[f"{c}_da"])  # origin side
    d = lambda c: m[f"{c}_da"].where(south, m[f"{c}_ffm"])  # destination side
    trips = pd.DataFrame({
        "ride_key": m["ride_key"],
        "direction": south.map({True: "ffm_da", False: "da_ffm"}),
        "line": m["line_ffm"],
        "train_type": m["train_type_ffm"],
        "train_number": m["train_number_ffm"],
        "planned": pd.to_datetime(o("dep_planned")),
        "arr_planned": pd.to_datetime(d("planned")),
        "dep_delay": o("dep_delay"),  # departure delay at the origin (the live "delayed now" signal)
        "delay": d("delay"),
        "canceled": (o("dep_canceled").fillna(False) | d("canceled").fillna(False)).astype(bool),
    })
    trips = trips.dropna(subset=["planned", "line"])
    trips["date"] = trips["planned"].dt.normalize()
    trips["hour"] = trips["planned"].dt.hour
    trips["daytype"] = day_type(trips["date"])
    trips["delayed6"] = (trips["delay"] >= DELAY_MIN) & ~trips["canceled"]
    trips["delayed15"] = (trips["delay"] >= 15) & ~trips["canceled"]
    trips["delayed30"] = (trips["delay"] >= 30) & ~trips["canceled"]
    return trips.reset_index(drop=True)
