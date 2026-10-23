"""Live snapshot from the DB Timetables API → live.json (HANDOFF §3.2, Phase 5).

For Frankfurt Hbf (both EVAs) and every route endpoint in config/stations.yaml → routes (Darmstadt Hbf,
the airport, …) it fetches the hourly plans around now plus the full change feed (fchg), and writes:
- hub:      how many Frankfurt Hbf trains within ±30 min are ≥6 min late / canceled right now ("실황")
- corridor: upcoming departures per route direction with their current delay and the probability of
            arriving ≥6 min late given that delay (conditional table from corridor.json)

Route runs are found the same way as in the historical data: the same run (stop id without its
trailing stop number) appears at Frankfurt Hbf and at the route endpoint; direction from stop order.

Credentials: DB_CLIENT_ID and DB_API_KEY (environment or .env). Without them the script exits 0 and
writes nothing, so the scheduled workflow stays green until a key is added.

Usage:
    uv run python pipeline/live.py --out live/live.json
    uv run python pipeline/live.py --fixtures tests/fixtures/timetables --now 2026-09-09T20:36 --out /tmp/live.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
API = "https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1"
BERLIN = ZoneInfo("Europe/Berlin")
STATIONS = ROOT / "config" / "stations.yaml"
CORRIDOR_JSON = ROOT / "site" / "public" / "data" / "corridor.json"

HUB_WINDOW = dt.timedelta(minutes=30)       # ± around now for the hub "실황"
CORRIDOR_PAST = dt.timedelta(minutes=15)    # keep just-departed trains briefly
CORRIDOR_AHEAD = dt.timedelta(minutes=90)
PLAN_HOURS = range(-1, 3)                   # plan hours relative to now (arrivals at DA come later)


# ── Parsing ────────────────────────────────────────────────────────────────

def parse_time(value: str | None) -> dt.datetime | None:
    return dt.datetime.strptime(value, "%y%m%d%H%M") if value else None


def ride_key(stop_id: str) -> str:
    return re.sub(r"-\d+$", "", stop_id)


def stop_num(stop_id: str) -> int:
    return int(stop_id.rsplit("-", 1)[1])


def norm_line(line: str | None, train_type: str | None) -> str | None:
    """Same rule as events.py: bare numbers get the train type, long-distance trains use the type."""
    if line and line.isdigit():
        return f"{train_type}{line}"
    return line or train_type


def parse_plan(xml: str) -> list[dict]:
    stops = []
    for s in ET.fromstring(xml).findall("s"):
        tl, ar, dp = s.find("tl"), s.find("ar"), s.find("dp")
        event = ar if ar is not None else dp
        stops.append({
            "id": s.get("id"),
            "train_type": tl.get("c") if tl is not None else None,
            "number": tl.get("n") if tl is not None else None,
            "line_raw": event.get("l") if event is not None else None,
            "ar_pt": parse_time(ar.get("pt")) if ar is not None else None,
            "dp_pt": parse_time(dp.get("pt")) if dp is not None else None,
        })
    return stops


def parse_changes(xml: str) -> dict[str, dict]:
    """stop id → changed times and statuses (cs="c" = canceled). Later entries win."""
    out: dict[str, dict] = {}
    for s in ET.fromstring(xml).findall("s"):
        rec = out.setdefault(s.get("id"), {})
        for tag in ("ar", "dp"):
            e = s.find(tag)
            if e is None:
                continue
            if e.get("ct"):
                rec[f"{tag}_ct"] = parse_time(e.get("ct"))
            if e.get("cs"):
                rec[f"{tag}_cs"] = e.get("cs")
    return out


def merge(plan: list[dict], changes: dict[str, dict], station: str) -> list[dict]:
    """Planned stops with current delays. No change entry means running on time."""
    out = []
    seen = set()
    for p in plan:
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        c = changes.get(p["id"], {})
        stop = {**p, "station": station, "line": norm_line(p["line_raw"], p["train_type"])}
        for tag in ("ar", "dp"):
            pt = p[f"{tag}_pt"]
            ct = c.get(f"{tag}_ct") or pt
            stop[f"{tag}_delay"] = int((ct - pt).total_seconds() // 60) if pt else None
            stop[f"{tag}_canceled"] = c.get(f"{tag}_cs") == "c"
        # Same measurement rule as events.py: arrival if the train arrives here, else departure.
        tag = "ar" if p["ar_pt"] else "dp"
        stop["planned"] = p[f"{tag}_pt"]
        stop["delay"] = stop[f"{tag}_delay"]
        stop["canceled"] = stop[f"{tag}_canceled"]
        out.append(stop)
    return out


# ── Snapshot ───────────────────────────────────────────────────────────────

def hub_now(stops: list[dict], now: dt.datetime) -> dict:
    window = [s for s in stops if s["planned"] and abs(s["planned"] - now) <= HUB_WINDOW and s["train_type"] != "Bus"]
    ran = [s for s in window if not s["canceled"]]
    late = sum(1 for s in ran if s["delay"] >= 6)
    return {
        "window_min": int(HUB_WINDOW.total_seconds() // 60),
        "n": len(window),
        "delayed6": late,
        "canceled": len(window) - len(ran),
        "p6": round(late / len(ran), 3) if ran else None,
    }


def conditional_lookup(conditional: dict, direction: str, line: str, delay: int) -> dict | None:
    edges = conditional["edges"]
    b = sum(delay >= e for e in edges)
    cells = conditional["cells"].get(direction, {}).get(line)
    return cells[b] if cells else None


def corridor_now(ffm: list[dict], dest_stops: list[dict], route: dict, now: dt.datetime, conditional: dict) -> dict:
    """Upcoming runs of one route (Frankfurt Hbf ↔ route endpoint), keyed by direction."""
    out_key, in_key = f"ffm_{route['code']}", f"{route['code']}_ffm"
    by_ride = {}
    for s in ffm:
        by_ride.setdefault(ride_key(s["id"]), {})["ffm"] = s
    for s in dest_stops:
        by_ride.setdefault(ride_key(s["id"]), {}).setdefault("to", s)  # first EVA wins if a run shows twice
    found: dict[str, list] = {out_key: [], in_key: []}
    for pair in by_ride.values():
        if "ffm" not in pair or "to" not in pair:
            continue
        outbound = stop_num(pair["ffm"]["id"]) < stop_num(pair["to"]["id"])
        origin, dest = (pair["ffm"], pair["to"]) if outbound else (pair["to"], pair["ffm"])
        if origin["dp_pt"] is None or dest["ar_pt"] is None or origin["train_type"] == "Bus":
            continue
        if not (now - CORRIDOR_PAST <= origin["dp_pt"] <= now + CORRIDOR_AHEAD):
            continue
        direction = out_key if outbound else in_key
        delay = origin["dp_delay"]
        canceled = origin["dp_canceled"] or dest["ar_canceled"]
        cell = None if canceled else conditional_lookup(conditional, direction, origin["line"], delay)
        expected = origin["dp_pt"] + dt.timedelta(minutes=delay)
        found[direction].append((origin["dp_pt"], {
            "line": origin["line"],
            "train_type": origin["train_type"],
            "number": origin["number"],
            "dep_planned": origin["dp_pt"].strftime("%H:%M"),
            "dep_expected": expected.strftime("%H:%M"),
            "arr_planned": dest["ar_pt"].strftime("%H:%M"),
            "delay_now": delay,
            "departed": expected < now,
            "canceled": canceled,
            "p6": cell["p6"] if cell else None,
            "p15": cell["p15"] if cell else None,
            "n": cell["n"] if cell else None,
        }))
    # Sort by the real departure datetime (HH:MM alone would misorder around midnight).
    return {d: [t for _, t in sorted(trains, key=lambda x: x[0])] for d, trains in found.items()}


# ── Fetching ───────────────────────────────────────────────────────────────

def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class ApiSource:
    MIN_INTERVAL = 1.1  # seconds between requests: ~40 per run stays under the free plan's per-minute limit

    def __init__(self, client_id: str, api_key: str):
        self.headers = {"DB-Client-Id": client_id, "DB-Api-Key": api_key, "Accept": "application/xml"}
        self.last = 0.0

    def get(self, path: str) -> str | None:
        """XML body, or None when the API has nothing for this path (404)."""
        for attempt in range(3):
            time.sleep(max(0.0, self.last + self.MIN_INTERVAL - time.monotonic()))
            self.last = time.monotonic()
            try:
                req = urllib.request.Request(f"{API}/{path}", headers=self.headers)
                with urllib.request.urlopen(req, timeout=20) as res:
                    return res.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code in (401, 403):
                    raise SystemExit(f"API rejected the credentials (HTTP {e.code})") from e
                if attempt == 2:
                    raise
            except urllib.error.URLError:
                if attempt == 2:
                    raise
            time.sleep(2 * (attempt + 1))
        return None


class FixtureSource:
    """Saved API responses named like the URL path: fchg_<eva>.xml.gz, plan_<eva>_<yymmdd>_<HH>.xml.gz."""

    def __init__(self, directory: Path):
        self.directory = directory

    def get(self, path: str) -> str | None:
        f = self.directory / (path.replace("/", "_") + ".xml.gz")
        return gzip.decompress(f.read_bytes()).decode("utf-8") if f.exists() else None


def station_stops(source, eva: str, station: str, now: dt.datetime) -> list[dict]:
    plan = []
    for offset in PLAN_HOURS:
        t = now + dt.timedelta(hours=offset)
        xml = source.get(f"plan/{eva}/{t:%y%m%d}/{t:%H}")
        if xml:
            plan += parse_plan(xml)
    changes = source.get(f"fchg/{eva}")
    return merge(plan, parse_changes(changes) if changes else {}, station)


def snapshot(source, now: dt.datetime, mode: str) -> dict:
    cfg = yaml.safe_load(STATIONS.read_text())
    conditional = json.loads(CORRIDOR_JSON.read_text())["conditional"]
    stops = lambda key: [s for eva in cfg["stations"][key]["eva"] for s in station_stops(source, eva, key, now)]
    ffm = stops(cfg["hub"])
    corridor = {}
    for route in cfg["routes"]:
        corridor.update(corridor_now(ffm, stops(route["to"]), route, now, conditional))
    return {
        "generated_at": now.replace(tzinfo=BERLIN).isoformat(timespec="seconds"),
        "snapshot": now.strftime("%Y-%m-%dT%H:%M"),
        "source": mode,
        "hub": hub_now(ffm, now),
        "corridor": corridor,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fixtures", type=Path, help="replay saved responses instead of calling the API")
    ap.add_argument("--now", help="Berlin local time YYYY-MM-DDTHH:MM (default: now)")
    args = ap.parse_args(argv)

    now = dt.datetime.fromisoformat(args.now) if args.now else dt.datetime.now(BERLIN).replace(tzinfo=None)
    now = now.replace(second=0, microsecond=0)
    if args.fixtures:
        source, mode = FixtureSource(args.fixtures), "fixtures"
    else:
        load_dotenv()
        client_id, api_key = os.environ.get("DB_CLIENT_ID"), os.environ.get("DB_API_KEY")
        if not (client_id and api_key):
            print("DB_CLIENT_ID / DB_API_KEY not set — skipping live snapshot")
            return 0
        source, mode = ApiSource(client_id, api_key), "api"

    data = snapshot(source, now, mode)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    c = data["corridor"]
    print(f"wrote {args.out} · hub n={data['hub']['n']} p6={data['hub']['p6']} · "
          + " · ".join(f"{k} {len(v)}" for k, v in c.items()) + " trains")
    return 0


if __name__ == "__main__":
    sys.exit(main())
