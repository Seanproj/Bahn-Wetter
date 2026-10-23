"""pipeline/live.py against saved Timetables API responses (2026-09-09, snapshot 20:36 Berlin).

The fixtures are real API responses taken from piebro/deutsche-bahn-data raw_data
(Deutsche Bahn, CC BY 4.0), cut down to Frankfurt Hbf (08000105, 08098105) and Darmstadt Hbf (08000068).
"""

import datetime as dt
import gzip
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import live  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "timetables"
NOW = dt.datetime(2026, 9, 9, 20, 36)


def xml(name: str) -> str:
    return gzip.decompress((FIXTURES / f"{name}.xml.gz").read_bytes()).decode()


@pytest.fixture(scope="module")
def snap():
    return live.snapshot(live.FixtureSource(FIXTURES), NOW, "fixtures")


def test_parse_plan_reads_trains_and_times():
    stops = live.parse_plan(xml("plan_08098105_260909_20"))
    assert stops, "plan should contain stops"
    s = stops[0]
    assert s["id"] and s["train_type"] == "S" and s["number"]
    assert s["ar_pt"].date() == dt.date(2026, 9, 9) and s["ar_pt"].hour == 20


def test_merge_applies_changed_time_and_cancellation():
    plan = [{"id": "x-2609092000-3", "train_type": "RE", "number": "1", "line_raw": "60",
             "ar_pt": dt.datetime(2026, 9, 9, 20, 10), "dp_pt": dt.datetime(2026, 9, 9, 20, 12)}]
    changes = {"x-2609092000-3": {"ar_ct": dt.datetime(2026, 9, 9, 20, 17), "dp_cs": "c"}}
    (s,) = live.merge(plan, changes, "test")
    assert s["line"] == "RE60"                      # bare number gets the train type
    assert s["ar_delay"] == 7 and s["delay"] == 7   # measured on arrival
    assert s["dp_delay"] == 0 and s["dp_canceled"] and not s["ar_canceled"]


def test_no_change_entry_means_on_time():
    plan = [{"id": "y-1-1", "train_type": "ICE", "number": "5", "line_raw": None,
             "ar_pt": None, "dp_pt": dt.datetime(2026, 9, 9, 21, 0)}]
    (s,) = live.merge(plan, {}, "test")
    assert s["line"] == "ICE" and s["delay"] == 0 and not s["canceled"]


def test_corridor_runs_match_historical_record(snap):
    c = snap["corridor"]
    # Cross-checked against monthly_processed_data for the same evening: 7 southbound, 8 northbound.
    assert len(c["ffm_da"]) == 7 and len(c["da_ffm"]) == 8
    assert {t["line"] for t in c["ffm_da"] + c["da_ffm"]} <= {"S6", "RB68", "RE60", "ICE", "RB67"}
    canceled = [t for t in c["ffm_da"] if t["canceled"]]
    assert [(t["line"], t["dep_planned"]) for t in canceled] == [("RE60", "20:34")]
    assert all(t["p6"] is None for t in canceled)


def test_corridor_trains_sorted_with_probabilities(snap):
    for trains in snap["corridor"].values():
        times = [t["dep_planned"] for t in trains]
        assert times == sorted(times)
        for t in trains:
            assert t["canceled"] or 0 <= t["p6"] <= 1


def test_hub_now_counts_window(snap):
    hub = snap["hub"]
    assert hub["n"] > 50 and 0 <= hub["delayed6"] <= hub["n"] and hub["canceled"] >= 0
    assert 0 <= hub["p6"] <= 1


def test_without_key_exits_cleanly(tmp_path, monkeypatch):
    monkeypatch.delenv("DB_CLIENT_ID", raising=False)
    monkeypatch.delenv("DB_API_KEY", raising=False)
    monkeypatch.setattr(live, "load_dotenv", lambda: None)
    out = tmp_path / "live.json"
    assert live.main(["--out", str(out)]) == 0
    assert not out.exists()


def test_fixture_cli_writes_json(tmp_path):
    out = tmp_path / "live.json"
    assert live.main(["--fixtures", str(FIXTURES), "--now", "2026-09-09T20:36", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["source"] == "fixtures" and data["snapshot"] == "2026-09-09T20:36"


def test_every_route_direction_is_reported(snap):
    import yaml
    cfg = yaml.safe_load((ROOT / "config" / "stations.yaml").read_text())
    keys = {k for r in cfg["routes"] for k in (f"ffm_{r['code']}", f"{r['code']}_ffm")}
    assert set(snap["corridor"]) == keys  # routes without fixtures are present, just empty
