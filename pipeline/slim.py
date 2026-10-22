"""Filter monthly files down to the target stations in config/stations.yaml.

Writes data/slim/data-YYYY-MM.parquet (skips months already present unless --force).

Usage:
    uv run python pipeline/slim.py [--delete-source]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parent.parent
MONTHLY_DIR = ROOT / "data" / "monthly_processed_data"
SLIM_DIR = ROOT / "data" / "slim"
STATIONS = ROOT / "config" / "stations.yaml"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--delete-source", action="store_true",
                    help="delete each full monthly file after slimming it (saves disk in CI)")
    args = ap.parse_args()

    cfg = yaml.safe_load(STATIONS.read_text())
    evas = sorted({e for s in cfg["stations"].values() for e in s["eva"]})
    SLIM_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for src in sorted(MONTHLY_DIR.glob("data-*.parquet")):
        dst = SLIM_DIR / src.name
        if dst.exists() and not args.force:
            print(f"skip {src.name}")
            continue
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{src}') WHERE eva IN (SELECT unnest(?)))"
            f" TO '{dst}' (FORMAT parquet, COMPRESSION zstd)",
            [evas],
        )
        n = con.execute(f"SELECT count(*) FROM read_parquet('{dst}')").fetchone()[0]
        print(f"{src.name}: {n:,} rows, {src.stat().st_size / 1e6:.0f} MB → {dst.stat().st_size / 1e6:.1f} MB")
        if args.delete_source:
            src.unlink()


if __name__ == "__main__":
    main()
