"""Incrementally download monthly_processed_data parquet files from Hugging Face.

Usage:
    uv run python pipeline/download.py --months 3          # latest 3 months
    uv run python pipeline/download.py --since 2025-11     # every month from 2025-11 on
    uv run python pipeline/download.py --months 3 --force  # re-download even if present
    uv run python pipeline/download.py --since 2025-11 --skip-slimmed  # CI: only months not in data/slim/
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

REPO_ID = "piebro/deutsche-bahn-data"
PREFIX = "monthly_processed_data/"
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MONTH_RE = re.compile(rf"^{PREFIX}data-(\d{{4}}-\d{{2}})\.parquet$")


def available_months(api: HfApi) -> dict[str, str]:
    """Map YYYY-MM → repo path for every monthly processed file on the Hub."""
    out = {}
    for path in api.list_repo_files(REPO_ID, repo_type="dataset"):
        m = MONTH_RE.match(path)
        if m:
            out[m.group(1)] = path
    return dict(sorted(out.items()))


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--months", type=int, default=3, help="download the latest N months")
    g.add_argument("--since", help="download every month >= YYYY-MM")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--skip-slimmed", action="store_true",
                    help="skip months whose slim cache (data/slim/) already exists")
    args = ap.parse_args()

    api = HfApi()
    months = available_months(api)
    if not months:
        raise SystemExit(f"no files matching {PREFIX}data-YYYY-MM.parquet in {REPO_ID}")
    print(f"available: {next(iter(months))} … {next(reversed(months))} ({len(months)} files)")

    wanted = [m for m in months if m >= args.since] if args.since else list(months)[-args.months:]
    for month in wanted:
        target = DATA_DIR / months[month]
        if args.skip_slimmed and (DATA_DIR / "slim" / target.name).exists():
            print(f"skip {month} (slim cache exists)")
            continue
        if target.exists() and not args.force:
            print(f"skip {month} (exists, {target.stat().st_size / 1e6:.0f} MB)")
            continue
        print(f"download {month} …", flush=True)
        path = hf_hub_download(
            REPO_ID, months[month], repo_type="dataset", local_dir=DATA_DIR, force_download=args.force
        )
        print(f"  → {path} ({Path(path).stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
