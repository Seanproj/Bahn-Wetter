"""Hierarchical Beta-Binomial shrinkage with exponential recency weights (HANDOFF §5.2).

Each level is shrunk toward its parent:
    p_level = (k_w + m · p_parent) / (n_w + m)
where k_w / n_w are recency-weighted event counts and m = α + β is the prior strength.
The root is the weighted overall rate. Unseen cells inherit their deepest seen ancestor.

Fitting works on daily counts per finest cell (see `daily_counts`), so refitting for every
backtest fold and hyper-parameter is cheap.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

STOP_LEVELS = [("station",), ("station", "line"), ("station", "line", "daytype"), ("station", "line", "daytype", "hour")]
TRIP_LEVELS = [("direction",), ("direction", "line"), ("direction", "line", "daytype"), ("direction", "line", "daytype", "hour")]


@dataclass
class Fitted:
    levels: list[tuple[str, ...]]
    root: float
    tables: list[pd.DataFrame]  # per level: keys + n + n_w + k_w + p


def daily_counts(events: pd.DataFrame, target: str, levels) -> pd.DataFrame:
    """Events → (finest cell keys, date) with n events and k positives."""
    keys = list(levels[-1]) + ["date"]
    return (events.groupby(keys, observed=True)[target]
            .agg(n="size", k="sum").reset_index())


def fit(counts: pd.DataFrame, levels, ref: pd.Timestamp, half_life: float | None, strength: float) -> Fitted:
    d = counts
    if half_life is None:
        w = np.ones(len(d))
    else:
        age = (ref - d["date"]).dt.days.to_numpy()
        w = 0.5 ** (np.clip(age, 0, None) / half_life)
    d = d.assign(n_w=w * d["n"], k_w=w * d["k"])
    root = d["k_w"].sum() / d["n_w"].sum()
    tables, parent = [], None
    for i, lv in enumerate(levels):
        t = d.groupby(list(lv), observed=True)[["n", "n_w", "k_w"]].sum().reset_index()
        if parent is None:
            prior = root
        else:
            up = list(levels[i - 1])
            t = t.merge(parent[up + ["p"]].rename(columns={"p": "p_parent"}), on=up, how="left")
            prior = t.pop("p_parent").fillna(root)
        t["p"] = (t["k_w"] + strength * prior) / (t["n_w"] + strength)
        tables.append(t)
        parent = t
    return Fitted(list(levels), root, tables)


def predict(model: Fitted, df: pd.DataFrame, with_n: bool = False):
    """Probability per row of df (and, optionally, raw training n of the finest matched cell)."""
    p = np.full(len(df), model.root)
    n = np.zeros(len(df))
    keyed = df[list(model.levels[-1])].reset_index(drop=True)
    for lv, t in zip(model.levels, model.tables):
        got = keyed.merge(t[list(lv) + ["p", "n"]], on=list(lv), how="left")
        hit = got["p"].notna().to_numpy()
        p = np.where(hit, got["p"].to_numpy(), p)
        n = np.where(hit, got["n"].to_numpy(), n) if lv == model.levels[-1] else n
    return (p, n) if with_n else p


def group_mean(train: pd.DataFrame, test: pd.DataFrame, target: str, keys: list[str]) -> np.ndarray:
    """Unweighted training mean per group (baseline); falls back to the overall mean."""
    m = train.groupby(keys, observed=True)[target].mean().rename("p").reset_index()
    p = test[keys].reset_index(drop=True).merge(m, on=keys, how="left")["p"]
    return p.fillna(train[target].mean()).to_numpy()
