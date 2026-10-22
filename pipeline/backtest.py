"""Time-split backtest (HANDOFF §5.4).

For every test month M: train on all data before M (expanding window, recency weights relative
to the first day of M), predict every event in M, score with Brier / log loss / calibration.

Hyper-parameters (half-life, prior strength) are chosen on the tuning folds only and reported on
the later held-out folds, so the headline numbers are not tuned on the data they are scored on.

Writes reports/backtest.md and config/model.yaml (chosen hyper-parameters per task).

Usage:
    uv run python pipeline/backtest.py
"""

from __future__ import annotations

import datetime as dt
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from events import load_stops, load_trips
from model import STOP_LEVELS, TRIP_LEVELS, daily_counts, fit, group_mean, predict

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "backtest.md"
MODEL_CFG = ROOT / "config" / "model.yaml"

TUNE_MONTHS = ["2026-02", "2026-03", "2026-04", "2026-05"]
HOLDOUT_MONTHS = ["2026-06", "2026-07", "2026-08", "2026-09"]
HALF_LIVES = [7, 14, 21, 42, 90, None]
STRENGTHS = [1, 5, 20, 50, 200]
EPS = 1e-6


def brier(p, y) -> float:
    return float(np.mean((p - y) ** 2))


def logloss(p, y) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fmt_hl(h) -> str:
    return "∞" if h is None else str(h)


def tasks(stops: pd.DataFrame, trips: pd.DataFrame) -> dict:
    """Task name → (events, target, levels, baseline-a keys, baseline-b keys)."""
    return {
        "stop_delay6": (stops[~stops["canceled"]], "delayed6", STOP_LEVELS, ["station"], ["station", "line"]),
        "stop_cancel": (stops, "canceled", STOP_LEVELS, ["station"], ["station", "line"]),
        "trip_delay6": (trips[~trips["canceled"]], "delayed6", TRIP_LEVELS, ["direction"], ["direction", "line"]),
        "trip_cancel": (trips, "canceled", TRIP_LEVELS, ["direction"], ["direction", "line"]),
    }


def run_fold(events, target, levels, month, configs):
    start = pd.Timestamp(month + "-01")
    end = start + pd.offsets.MonthBegin(1)
    train = events[events["planned"] < start]
    test = events[(events["planned"] >= start) & (events["planned"] < end)].reset_index(drop=True)
    counts = daily_counts(train, target, levels)
    y = test[target].to_numpy(dtype=float)
    preds = {cfg: predict(fit(counts, levels, start, *cfg), test) for cfg in configs}
    return train, test, y, preds


def main() -> None:
    stops = load_stops()
    trips = load_trips(stops)
    configs = list(itertools.product(HALF_LIVES, STRENGTHS))
    report = [
        "# Phase 1 — 백테스트 결과",
        "",
        f"생성: {dt.datetime.now():%Y-%m-%d %H:%M} · 데이터 {stops['planned'].min():%Y-%m-%d} ~ {stops['planned'].max():%Y-%m-%d}",
        f"정차 이벤트 {len(stops):,}건 (12개 역) · 코리도어 운행 {len(trips):,}건",
        "",
        "## 방법",
        "",
        "- 모델: 계층 Beta-Binomial 축소 + 지수 최근성 가중. "
        "정차: 역 → 역×노선 → 역×노선×요일구분 → 역×노선×요일구분×시간대. "
        "운행(코리도어): 방향 → 방향×노선 → … → 방향×노선×요일구분×출발시간대.",
        "- 정차 지연은 도착 기준(출발역만 출발 기준), 코리도어 운행은 **도착역 도착 지연** 기준.",
        "- 분할: 시험월 M마다 M 이전 전체로 학습(확장 윈도우), M 한 달 전체 예측.",
        f"- 튜닝 폴드 {TUNE_MONTHS[0]}~{TUNE_MONTHS[-1]}에서 half-life × prior 강도 선택, "
        f"**보고 수치는 홀드아웃 폴드 {HOLDOUT_MONTHS[0]}~{HOLDOUT_MONTHS[-1]}**.",
        "- 베이스라인 (a) 역 평균 / 방향 평균, (b) 역×노선 평균 / 방향×노선 평균 (학습 기간 단순 평균).",
        "- BSS = 1 − Brier/Brier_baseline (양수면 베이스라인보다 나음).",
        "",
    ]
    chosen = {}
    summary_rows = []
    for name, (events, target, levels, base_a, base_b) in tasks(stops, trips).items():
        print(f"[{name}] tuning …", flush=True)
        # ── Tune ─────────────────────────────────────────────────────────
        scores = {cfg: [] for cfg in configs}
        for month in TUNE_MONTHS:
            _, test, y, preds = run_fold(events, target, levels, month, configs)
            for cfg, p in preds.items():
                scores[cfg].append((brier(p, y), len(y)))
        tune = {cfg: sum(b * n for b, n in v) / sum(n for _, n in v) for cfg, v in scores.items()}
        best = min(tune, key=tune.get)
        chosen[name] = {"half_life_days": best[0], "prior_strength": best[1]}

        # ── Held-out evaluation ──────────────────────────────────────────
        print(f"[{name}] holdout with {best} …", flush=True)
        default_cfg = (21, 20)  # HANDOFF starting point
        rows = []
        acc = {k: [] for k in ("p", "pd", "pa", "pb", "y", "n", "seg")}
        for month in HOLDOUT_MONTHS:
            start = pd.Timestamp(month + "-01")
            train, test, y, _ = run_fold(events, target, levels, month, [])
            counts = daily_counts(train, target, levels)
            p, n_cell = predict(fit(counts, levels, start, *best), test, with_n=True)
            pd_ = predict(fit(counts, levels, start, *default_cfg), test)
            pa = group_mean(train, test, target, base_a)
            pb = group_mean(train, test, target, base_b)
            rows.append((month, len(y), y.mean(), brier(p, y), brier(pd_, y), brier(pa, y), brier(pb, y)))
            for k, v in (("p", p), ("pd", pd_), ("pa", pa), ("pb", pb), ("y", y), ("n", n_cell),
                         ("seg", test[levels[0][0]].to_numpy())):
                acc[k].append(v)
        P, PD, PA, PB, Y, N, S = (np.concatenate(acc[k]) for k in ("p", "pd", "pa", "pb", "y", "n", "seg"))
        b_m, b_d, b_a, b_b = brier(P, Y), brier(PD, Y), brier(PA, Y), brier(PB, Y)
        summary_rows.append((name, f"{len(Y):,}", f"{Y.mean():.1%}", f"{b_m:.4f}", f"{b_a:.4f}", f"{b_b:.4f}",
                             f"{1 - b_m / b_a:+.1%}", f"{1 - b_m / b_b:+.1%}",
                             f"{fmt_hl(best[0])} / {best[1]}"))

        report += [f"## {name}", "",
                   f"- 대상: `{target}` · 선택된 설정: half-life **{fmt_hl(best[0])}일**, prior 강도 **{best[1]}** "
                   f"(HANDOFF 시작값 21일/20)", ""]
        # Tuning grid
        report += ["### 튜닝 그리드 (튜닝 폴드 Brier, 낮을수록 좋음)", "",
                   "| half-life \\ 강도 | " + " | ".join(map(str, STRENGTHS)) + " |",
                   "|---|" + "---|" * len(STRENGTHS)]
        for h in HALF_LIVES:
            report.append(f"| {fmt_hl(h)} | " + " | ".join(
                ("**" if (h, s) == best else "") + f"{tune[(h, s)]:.4f}" + ("**" if (h, s) == best else "")
                for s in STRENGTHS) + " |")
        report.append("")
        # Per-fold
        report += ["### 홀드아웃 월별 Brier", "",
                   "| 월 | n | 실제 비율 | 모델 | 시작값 21/20 | 베이스라인 (a) | 베이스라인 (b) |",
                   "|---|---|---|---|---|---|---|"]
        for r in rows:
            report.append(f"| {r[0]} | {r[1]:,} | {r[2]:.1%} | {r[3]:.4f} | {r[4]:.4f} | {r[5]:.4f} | {r[6]:.4f} |")
        report += [f"| **전체** | {len(Y):,} | {Y.mean():.1%} | **{b_m:.4f}** | {b_d:.4f} | {b_a:.4f} | {b_b:.4f} |", "",
                   f"- Log loss: 모델 {logloss(P, Y):.4f} · (a) {logloss(PA, Y):.4f} · (b) {logloss(PB, Y):.4f}",
                   f"- 학습 표본 n<10인 셀에 해당한 시험 이벤트: {np.mean(N < 10):.1%} (UI에서는 '데이터 부족')", ""]
        # Calibration
        edges = [0, .05, .1, .15, .2, .25, .3, .35, .4, .45, .5, .6, .7, 1.0001]
        bins = np.digitize(P, edges) - 1
        report += ["### 캘리브레이션 (홀드아웃)", "", "| 예측 구간 | 이벤트 수 | 평균 예측 | 실제 비율 | 차이 |", "|---|---|---|---|---|"]
        for i in range(len(edges) - 1):
            m = bins == i
            if m.sum() == 0:
                continue
            report.append(f"| {edges[i]:.0%}–{min(edges[i + 1], 1):.0%} | {m.sum():,} | {P[m].mean():.1%} | {Y[m].mean():.1%} | {Y[m].mean() - P[m].mean():+.1%} |")
        report.append("")
        # Segment breakdown
        report += ["### 세그먼트별 (홀드아웃)", "", "| " + levels[0][0] + " | n | 실제 | 모델 Brier | (a) | (b) | BSS vs (b) |", "|---|---|---|---|---|---|---|"]
        for sval in pd.unique(S):
            m = S == sval
            bm, ba, bb = brier(P[m], Y[m]), brier(PA[m], Y[m]), brier(PB[m], Y[m])
            report.append(f"| {sval} | {m.sum():,} | {Y[m].mean():.1%} | {bm:.4f} | {ba:.4f} | {bb:.4f} | {1 - bm / bb:+.1%} |")
        report.append("")

    report[report.index("## 방법"):report.index("## 방법")] = [
        "## 요약 (홀드아웃)", "",
        "| 과제 | 이벤트 | 실제 비율 | 모델 Brier | (a) | (b) | BSS vs (a) | BSS vs (b) | half-life / 강도 |",
        "|---|---|---|---|---|---|---|---|---|",
        *["| " + " | ".join(r) + " |" for r in summary_rows], "",
    ]
    REPORT.write_text("\n".join(report) + "\n")
    MODEL_CFG.write_text(
        "# Chosen by pipeline/backtest.py on the tuning folds — do not edit by hand.\n"
        + yaml.safe_dump({"generated_at": dt.date.today().isoformat(), "tasks": chosen}, sort_keys=False)
    )
    print(f"wrote {REPORT.relative_to(ROOT)} and {MODEL_CFG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
