"""Phase 0 exploration: schema check, station resolution, corridor analysis, sanity check.

Reads every data/monthly_processed_data/data-*.parquet, writes
  - config/stations.yaml          (resolved stations + EVA)
  - reports/phase0_exploration.md (findings)

Usage:
    uv run python pipeline/explore.py
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parent.parent
MONTHLY_GLOB = ROOT / "data" / "monthly_processed_data" / "data-*.parquet"
SEARCH_CFG = ROOT / "config" / "station_search.yaml"
STATIONS_OUT = ROOT / "config" / "stations.yaml"
REPORT_OUT = ROOT / "reports" / "phase0_exploration.md"

# Columns HANDOFF.md §3.1 expects. Anything missing or extra is reported.
HANDOFF_COLUMNS = [
    "station_name", "eva", "train_type", "train_number", "line_number",
    "final_destination_station", "delay_in_min", "arrival_planned_time", "arrival_change_time",
    "departure_planned_time", "departure_change_time", "arrival_is_canceled",
    "departure_is_canceled", "train_line_ride_id", "train_line_station_num", "time", "id",
]


def md_table(rows: list[tuple], headers: list[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        lines.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    return "\n".join(lines)


def main() -> None:
    files = sorted(MONTHLY_GLOB.parent.glob(MONTHLY_GLOB.name))
    if not files:
        raise SystemExit(f"no files at {MONTHLY_GLOB} — run pipeline/download.py first")
    con = duckdb.connect()
    report: list[str] = [
        "# Phase 0 — 데이터 탐색 결과",
        "",
        f"생성: {dt.datetime.now():%Y-%m-%d %H:%M} · 파일: "
        + ", ".join(f"`{f.name}`" for f in files),
        "",
    ]

    # ── 1. Schema per file ────────────────────────────────────────────────
    report += ["## 1. 실제 스키마", ""]
    schemas = {}
    for f in files:
        schemas[f.name] = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{f}')").fetchall()
    first = schemas[files[0].name]
    report.append(md_table([(c[0], c[1]) for c in first], ["column", "type"]))
    report.append("")
    for name, sch in schemas.items():
        if [(c[0], c[1]) for c in sch] != [(c[0], c[1]) for c in first]:
            report.append(f"⚠️ `{name}` 스키마가 `{files[0].name}`와 다름: "
                          + ", ".join(f"{c[0]}:{c[1]}" for c in sch))
    cols = {c[0] for c in first}
    missing = [c for c in HANDOFF_COLUMNS if c not in cols]
    extra = sorted(cols - set(HANDOFF_COLUMNS))
    report += [
        "",
        f"- HANDOFF에 있으나 데이터에 없는 컬럼: {missing or '없음'}",
        f"- 데이터에 있으나 HANDOFF에 없는 컬럼: {extra or '없음'}",
        "",
    ]

    con.execute(f"CREATE VIEW stops AS SELECT * FROM read_parquet({[str(f) for f in files]}, union_by_name=true)")
    total, tmin, tmax = con.execute(
        "SELECT count(*), min(coalesce(arrival_planned_time, departure_planned_time)),"
        " max(coalesce(arrival_planned_time, departure_planned_time)) FROM stops"
    ).fetchone()
    report += [f"- 전체 행: {total:,} · 계획 시각 범위: {tmin} ~ {tmax}", ""]

    # How delay_in_min relates to the timestamps (arrival vs departure based).
    delay_def = con.execute("""
        SELECT
          avg((delay_in_min = date_diff('minute', arrival_planned_time, time))::INT)
            FILTER (WHERE arrival_planned_time IS NOT NULL),
          avg((delay_in_min = date_diff('minute', departure_planned_time, time))::INT)
            FILTER (WHERE departure_planned_time IS NOT NULL),
          avg((delay_in_min IS NULL)::INT)
        FROM stops
    """).fetchone()
    report += [
        "### delay_in_min 정의 확인",
        f"- `delay_in_min == time − arrival_planned_time` 일치율: {delay_def[0]:.1%}",
        f"- `delay_in_min == time − departure_planned_time` 일치율: {delay_def[1]:.1%}",
        f"- `delay_in_min` null 비율: {delay_def[2]:.1%}",
        "",
    ]

    # ── 2. Station resolution ─────────────────────────────────────────────
    search = yaml.safe_load(SEARCH_CFG.read_text())
    report += ["## 2. 역 검색 → EVA 확정", ""]
    resolved: dict[str, dict] = {}
    rows = []
    for entry in search["corridor"]:
        hits = con.execute("""
            SELECT station_name, eva, count(*) AS n
            FROM stops WHERE station_name ILIKE ?
            GROUP BY ALL ORDER BY n DESC
        """, [entry["pattern"]]).fetchall()
        for name, eva, n in hits:
            rows.append((entry["key"], entry["pattern"], name, eva, f"{n:,}"))
        if not hits:
            rows.append((entry["key"], entry["pattern"], "❌ 없음", None, 0))
            continue
        resolved[entry["key"]] = {
            "name": hits[0][0],
            "eva": sorted({h[1] for h in hits if h[0] == hits[0][0]}),
            "rows": int(sum(h[2] for h in hits if h[0] == hits[0][0])),
        }
    report += [md_table(rows, ["key", "pattern", "station_name", "eva", "rows"]), ""]

    # ── 3. Corridor runs ──────────────────────────────────────────────────
    ffm = resolved.get("frankfurt_hbf", {}).get("eva", [])
    da = resolved.get("darmstadt_hbf", {}).get("eva", [])
    report += ["## 3. 코리도어 운행 (같은 train_line_ride_id로 Frankfurt Hbf + Darmstadt Hbf 모두 경유)", ""]
    corridor_rows = []
    if ffm and da:
        con.execute("""
            CREATE TEMP TABLE corridor AS
            WITH f AS (SELECT train_line_ride_id, min(train_line_station_num) AS f_num
                       FROM stops WHERE eva IN (SELECT unnest(?)) GROUP BY 1),
                 d AS (SELECT train_line_ride_id, min(train_line_station_num) AS d_num
                       FROM stops WHERE eva IN (SELECT unnest(?)) GROUP BY 1)
            SELECT f.train_line_ride_id,
                   CASE WHEN f_num < d_num THEN 'FFM→DA' ELSE 'DA→FFM' END AS direction
            FROM f JOIN d USING (train_line_ride_id)
        """, [ffm, da])
        corridor_rows = con.execute("""
            WITH r AS (
              SELECT DISTINCT c.train_line_ride_id, c.direction, s.train_type,
                     coalesce(s.line_number, s.train_type) AS line
              FROM corridor c JOIN stops s USING (train_line_ride_id)
              WHERE s.eva IN (SELECT unnest(?))
            )
            SELECT train_type, line,
                   count(*) FILTER (WHERE direction = 'FFM→DA') AS ffm_da,
                   count(*) FILTER (WHERE direction = 'DA→FFM') AS da_ffm,
                   count(*) AS total
            FROM r GROUP BY ALL ORDER BY total DESC
        """, [ffm]).fetchall()
        report.append(md_table(corridor_rows, ["train_type", "line_number (장거리는 train_type)",
                                               "FFM→DA", "DA→FFM", "운행 수"]))
        n_days = con.execute("SELECT count(DISTINCT CAST(coalesce(arrival_planned_time, departure_planned_time) AS DATE)) FROM stops").fetchone()[0]
        report += ["", f"- 기간 내 날짜 수: {n_days} → 하루 평균 운행은 위 운행 수 ÷ {n_days}", ""]

        # Which corridor stations do corridor runs actually serve?
        served = con.execute("""
            SELECT s.station_name, s.eva, count(DISTINCT s.train_line_ride_id) AS rides
            FROM corridor c JOIN stops s USING (train_line_ride_id)
            WHERE s.eva IN (SELECT unnest(?))
            GROUP BY ALL ORDER BY rides DESC
        """, [[e for v in resolved.values() for e in v["eva"]]]).fetchall()
        report += ["### 코리도어 운행이 정차하는 후보 역", "",
                   md_table(served, ["station_name", "eva", "코리도어 운행 수"]), ""]
    else:
        report.append("❌ Frankfurt Hbf 또는 Darmstadt Hbf를 찾지 못해 분석 불가")

    # ── 4. Sanity check: Frankfurt Hbf delay rate ─────────────────────────
    report += ["## 4. Sanity check — Frankfurt Hbf 지연률", ""]
    if ffm:
        san = con.execute("""
            SELECT eva, count(*) AS n,
                   avg((delay_in_min >= 6)::INT) FILTER (WHERE NOT coalesce(arrival_is_canceled OR departure_is_canceled, false)) AS p6,
                   avg((delay_in_min >= 15)::INT) FILTER (WHERE NOT coalesce(arrival_is_canceled OR departure_is_canceled, false)) AS p15,
                   avg((delay_in_min >= 30)::INT) FILTER (WHERE NOT coalesce(arrival_is_canceled OR departure_is_canceled, false)) AS p30,
                   avg(coalesce(arrival_is_canceled OR departure_is_canceled, false)::INT) AS cancel
            FROM stops WHERE eva IN (SELECT unnest(?))
            GROUP BY ROLLUP (eva) ORDER BY eva NULLS LAST
        """, [ffm]).fetchall()
        report.append(md_table(
            [(e or "전체", f"{n:,}", f"{p6:.1%}", f"{p15:.1%}", f"{p30:.1%}", f"{c:.1%}") for e, n, p6, p15, p30, c in san],
            ["eva", "n", "≥6분", "≥15분", "≥30분", "취소율"]))
        p6_all = san[-1][2]
        verdict = "✅ 상식 범위(20~45%)" if 0.20 <= p6_all <= 0.45 else "⚠️ 상식 범위(20~45%) 밖 — 원인 확인 필요"
        report += ["", f"- 판정: {verdict}", ""]

        by_type = con.execute("""
            SELECT train_type, count(*) AS n, avg((delay_in_min >= 6)::INT) AS p6
            FROM stops WHERE eva IN (SELECT unnest(?))
              AND NOT coalesce(arrival_is_canceled OR departure_is_canceled, false)
            GROUP BY 1 ORDER BY n DESC LIMIT 15
        """, [ffm]).fetchall()
        report += ["### train_type별 (취소 제외)", "",
                   md_table([(t, f"{n:,}", f"{p:.1%}") for t, n, p in by_type], ["train_type", "n", "≥6분"]), ""]

    # ── Write outputs ─────────────────────────────────────────────────────
    stations = {
        "generated_by": "pipeline/explore.py",
        "generated_at": dt.date.today().isoformat(),
        "source_files": [f.name for f in files],
        "hub": "frankfurt_hbf",
        "corridor_order": [e["key"] for e in search["corridor"] if e["key"] in resolved],
        "stations": {k: {"name": v["name"], "eva": v["eva"]} for k, v in resolved.items()},
        "corridor_lines": [
            {"train_type": t, "line": l, "rides_ffm_da": a, "rides_da_ffm": b}
            for t, l, a, b, _ in corridor_rows
        ],
    }
    STATIONS_OUT.write_text(yaml.safe_dump(stations, allow_unicode=True, sort_keys=False))
    REPORT_OUT.write_text("\n".join(report) + "\n")
    print(f"wrote {STATIONS_OUT.relative_to(ROOT)} and {REPORT_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
