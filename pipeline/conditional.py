"""P(late arrival | delay at departure) for route trips — the Phase 5 "already X min late" signal.

The live feed (pipeline/live.py) knows how late a corridor train is at its origin right now. This
table turns that into the probability of arriving ≥6 / ≥15 min late at the destination:
direction × line × origin-departure-delay bin, Beta-Binomial-shrunk toward direction × bin
(all lines). Trains canceled on the way are excluded — the live feed reports cancellations itself.

`main` backtests it against the unconditional hourly forecast on the same rolling holdout months
as backtest.py and writes reports/conditional_backtest.md.

Usage:
    uv run python pipeline/conditional.py
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "conditional_backtest.md"
MODEL_CFG = ROOT / "config" / "model.yaml"

# Origin departure delay bins (minutes). Lower edges after the first; labels are shown in the UI.
EDGES = [2, 4, 6, 10, 15, 30]
LABELS = ["≤1분", "2–3분", "4–5분", "6–9분", "10–14분", "15–29분", "30분+"]
STRENGTH = 20
N_HOLDOUT = 4


def bin_index(delay) -> np.ndarray:
    return np.digitize(np.asarray(delay, dtype=float), EDGES)


def fit_table(trips: pd.DataFrame, strength: float = STRENGTH) -> pd.DataFrame:
    """direction × line × bin → n, p6, p15 (shrunk toward direction × bin)."""
    d = trips[~trips["canceled"] & trips["dep_delay"].notna()].assign(bin=lambda x: bin_index(x["dep_delay"]))
    d = d.assign(y6=d["delay"] >= 6, y15=d["delay"] >= 15)
    prior = d.groupby(["direction", "bin"])[["y6", "y15"]].mean().add_prefix("prior_").reset_index()
    t = d.groupby(["direction", "line", "bin"]).agg(n=("y6", "size"), k6=("y6", "sum"), k15=("y15", "sum")).reset_index()
    t = t.merge(prior, on=["direction", "bin"])
    t["p6"] = (t["k6"] + strength * t["prior_y6"]) / (t["n"] + strength)
    t["p15"] = (t["k15"] + strength * t["prior_y15"]) / (t["n"] + strength)
    return t[["direction", "line", "bin", "n", "p6", "p15"]]


def predict(table: pd.DataFrame, trips: pd.DataFrame) -> np.ndarray:
    keyed = trips[["direction", "line"]].assign(bin=bin_index(trips["dep_delay"])).reset_index(drop=True)
    return keyed.merge(table, on=["direction", "line", "bin"], how="left")["p6"].to_numpy()


def export_table(trips: pd.DataFrame, lines_by_direction: dict[str, list[str]], min_n: int) -> dict:
    """JSON for corridor.json: per direction and line, one {n, p6, p15} (or null) per bin."""
    t = fit_table(trips)
    out = {"bins": LABELS, "edges": EDGES, "cells": {}}
    for direction, lines in lines_by_direction.items():
        out["cells"][direction] = {}
        for line in lines:
            rows = t[(t["direction"] == direction) & (t["line"] == line)].set_index("bin")
            cells = []
            for b in range(len(LABELS)):
                if b in rows.index and rows.at[b, "n"] >= min_n:
                    r = rows.loc[b]
                    cells.append({"n": int(r["n"]), "p6": round(float(r["p6"]), 3), "p15": round(float(r["p15"]), 3)})
                else:
                    cells.append(None)
            out["cells"][direction][line] = cells
    return out


def main() -> None:
    from events import load_stops, load_trips
    from model import TRIP_LEVELS, daily_counts, fit
    from model import predict as predict_cells

    cfg = yaml.safe_load(MODEL_CFG.read_text())["tasks"]["trip_delay6"]
    trips = load_trips(load_stops())
    ran = trips[~trips["canceled"] & trips["dep_delay"].notna()]
    months = sorted(ran["planned"].dt.strftime("%Y-%m").unique())[-N_HOLDOUT:]
    brier = lambda p, y: float(np.mean((p - y) ** 2))

    rows, P_c, P_u, Y, B = [], [], [], [], []
    for month in months:
        start = pd.Timestamp(month + "-01")
        end = start + pd.offsets.MonthBegin(1)
        train = ran[ran["planned"] < start]
        test = ran[(ran["planned"] >= start) & (ran["planned"] < end)].reset_index(drop=True)
        y = test["delayed6"].to_numpy(dtype=float)
        pc = predict(fit_table(train), test)
        pu = predict_cells(fit(daily_counts(train, "delayed6", TRIP_LEVELS), TRIP_LEVELS, start,
                               cfg["half_life_days"], cfg["prior_strength"]), test)
        pc = np.where(np.isnan(pc), pu, pc)  # unseen line × bin: fall back to the hourly forecast
        rows.append((month, len(y), y.mean(), brier(pu, y), brier(pc, y)))
        P_c.append(pc); P_u.append(pu); Y.append(y); B.append(bin_index(test["dep_delay"]))
    pc, pu, y, b = (np.concatenate(x) for x in (P_c, P_u, Y, B))
    bu, bc = brier(pu, y), brier(pc, y)

    table = fit_table(ran)
    report = [
        "# Phase 5 — 출발 지연을 알 때의 도착 지연 예보 (백테스트)", "",
        f"생성: {dt.datetime.now():%Y-%m-%d %H:%M} · 홀드아웃 {months[0]} ~ {months[-1]} · 노선 운행 (취소 제외)", "",
        "실시간 피드가 \"지금 출발역에서 X분 지연\"을 알려줄 때, 도착역 6분 이상 지연 확률을 얼마나 더 잘 맞히는지.", "",
        "| 월 | n | 실제 | 시간대 예보 Brier | 출발 지연 조건부 Brier |", "|---|---|---|---|---|",
        *[f"| {m} | {n:,} | {r:.1%} | {u:.4f} | {c:.4f} |" for m, n, r, u, c in rows],
        f"| **전체** | {len(y):,} | {y.mean():.1%} | {bu:.4f} | **{bc:.4f}** |", "",
        f"- Brier skill vs 시간대 예보: **{1 - bc / bu:+.1%}**", "",
        "## 출발 지연 구간별 (홀드아웃)", "",
        "| 출발 지연 | n | 실제 도착 지연 비율 | 조건부 예측 평균 | 시간대 예보 평균 |", "|---|---|---|---|---|",
    ]
    for i, label in enumerate(LABELS):
        m = b == i
        if m.any():
            report.append(f"| {label} | {m.sum():,} | {y[m].mean():.1%} | {pc[m].mean():.1%} | {pu[m].mean():.1%} |")
    report += ["", "## 전체 데이터 기준 표 (방향 × 노선, 도착 6분 이상 지연 확률)", ""]
    for direction in sorted(table["direction"].unique()):
        sub = table[table["direction"] == direction]
        lines = sub.groupby("line")["n"].sum().sort_values(ascending=False)
        lines = lines[lines >= 300].index
        report += [f"### {direction}", "", "| 노선 | " + " | ".join(LABELS) + " |", "|---|" + "---|" * len(LABELS)]
        for line in lines:
            r = sub[sub["line"] == line].set_index("bin")
            report.append(f"| {line} | " + " | ".join(
                f"{r.at[i, 'p6']:.0%} (n={int(r.at[i, 'n'])})" if i in r.index else "–" for i in range(len(LABELS))) + " |")
        report.append("")
    REPORT.write_text("\n".join(report) + "\n")
    print(f"wrote {REPORT.relative_to(ROOT)} · Brier hourly {bu:.4f} → conditional {bc:.4f} ({1 - bc / bu:+.1%})")


if __name__ == "__main__":
    main()
