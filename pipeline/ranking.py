"""Weekly ranking (HANDOFF §6.4): what actually happened in the last 7 days of data.

Unlike the forecast tables these are observed values, not model estimates:
- Frankfurt Hbf: worst / best lines and trains, biggest single delay of the week
- Corridor: worst / best trains by arrival delay at the destination

A train is (line, train_number). Rates are among trains that ran; cancellations are counted
separately. Minimum run counts keep one bad day from topping the list; the "best" lists also
require a clean record (no cancellation).
"""

from __future__ import annotations

import pandas as pd

DAYS = 7
MIN_LINE_RUNS = 50
MIN_TRAIN_RUNS_HUB = 4
MIN_TRAIN_RUNS_CORRIDOR = 3
MIN_RUNS_BEST = 5  # "most punctual" needs a steadier record, and no cancellations
TOP = 5


def _mode(s: pd.Series):
    m = s.mode()
    return m.iloc[0] if len(m) else None


def _label(line: str, train_type: str | None, number: str) -> str:
    """S-Bahn/regional numbers mean little to riders, so only long-distance trains show them."""
    return f"{line} {number}" if line == train_type else line


def _trains(events: pd.DataFrame, extra_keys: list[str], min_runs: int) -> pd.DataFrame:
    keys = extra_keys + ["line", "train_number"]
    ran = events[~events["canceled"]]
    g = ran.groupby(keys, observed=True)
    out = g.agg(
        runs=("delay", "size"),
        p6=("delayed6", "mean"),
        mean_delay=("delay", "mean"),
        max_delay=("delay", "max"),
        train_type=("train_type", _mode),
        time=("planned", lambda s: _mode(s.dt.strftime("%H:%M"))),
    ).reset_index()
    cancels = events.groupby(keys, observed=True)["canceled"].sum().rename("cancels").reset_index()
    out = out.merge(cancels, on=keys, how="left")
    out = out[out["runs"] >= min_runs]
    # Coupled / through services run under several numbers with identical records (IC 60403 = NJ 403).
    return out.drop_duplicates(subset=extra_keys + ["time", "runs", "mean_delay", "max_delay"])


def _best(trains: pd.DataFrame) -> pd.DataFrame:
    ok = trains[(trains["runs"] >= MIN_RUNS_BEST) & (trains["cancels"] == 0)]
    ok = ok.sort_values(["p6", "mean_delay", "runs"], ascending=[True, True, False])
    return ok.drop_duplicates(["line", "train_number"]).head(TOP)  # one entry per train across routes


def _records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    recs = []
    for _, r in df.iterrows():
        rec = {c: r[c] for c in cols}
        rec["label"] = _label(r["line"], r["train_type"], r["train_number"])
        rec["p6"] = round(float(r["p6"]), 3)
        rec["mean_delay"] = round(float(r["mean_delay"]), 1)
        rec["max_delay"] = int(r["max_delay"])
        rec["runs"] = int(r["runs"])
        rec["cancels"] = int(r["cancels"])
        recs.append(rec)
    return recs


def weekly_ranking(stops: pd.DataFrame, trips: pd.DataFrame, hub: str, names: dict) -> dict:
    end = stops["date"].max()
    start = end - pd.Timedelta(days=DAYS - 1)
    week = stops[(stops["date"] >= start) & (stops["station"] == hub)].copy()
    week["destination"] = week["destination"].fillna("")

    # Lines at the hub
    ran = week[~week["canceled"]]
    lines = ran.groupby("line").agg(runs=("delay", "size"), p6=("delayed6", "mean"), mean_delay=("delay", "mean")).reset_index()
    lines = lines.merge(week.groupby("line")["canceled"].mean().rename("cancel_rate").reset_index(), on="line")
    lines = lines[lines["runs"] >= MIN_LINE_RUNS]
    line_rec = lambda df: [
        {"line": r["line"], "runs": int(r["runs"]), "p6": round(float(r["p6"]), 3),
         "mean_delay": round(float(r["mean_delay"]), 1), "cancel_rate": round(float(r["cancel_rate"]), 3)}
        for _, r in df.iterrows()
    ]

    # Trains at the hub (time = planned time at Frankfurt Hbf, destination = most common one)
    trains = _trains(week, [], MIN_TRAIN_RUNS_HUB)
    dest = week.groupby(["line", "train_number"])["destination"].agg(_mode).rename("destination").reset_index()
    trains = trains.merge(dest, on=["line", "train_number"], how="left")
    cols = ["line", "train_number", "time", "destination"]
    worst = trains.sort_values(["p6", "mean_delay"], ascending=[False, False]).head(TOP)
    best = _best(trains)

    big = ran.loc[ran["delay"].idxmax()]
    biggest = {
        "label": _label(big["line"], big["train_type"], big["train_number"]),
        "line": big["line"],
        "date": big["date"].date().isoformat(),
        "time": big["planned"].strftime("%H:%M"),
        "destination": big["destination"],
        "delay": int(big["delay"]),
    }

    # Corridor trains (time = planned departure at the origin)
    tw = trips[trips["date"] >= start].copy()
    ctrains = _trains(tw, ["direction"], MIN_TRAIN_RUNS_CORRIDOR)
    ccols = ["direction", "line", "train_number", "time"]
    # A run serving several routes (S8: airport, Mainz, Wiesbaden) should appear only once per list.
    once = lambda df: df.drop_duplicates(["line", "train_number"])
    cworst = once(ctrains.sort_values(["p6", "mean_delay"], ascending=[False, False])).head(TOP)
    cbest = _best(ctrains)

    return {
        "window": {"from": start.date().isoformat(), "to": end.date().isoformat()},
        "station": names[hub],
        "hub": {
            "lines_worst": line_rec(lines.sort_values("p6", ascending=False).head(3)),
            "lines_best": line_rec(lines.sort_values("p6").head(3)),
            "trains_worst": _records(worst, cols),
            "trains_best": _records(best, cols),
            "biggest": biggest,
        },
        "corridor": {
            "trains_worst": _records(cworst, ccols),
            "trains_best": _records(cbest, ccols),
        },
    }
