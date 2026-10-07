import json
import sqlite3
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import pytest
import collector
from preprocess import interpolate_short, transform


def packet(**updates):
    item = {"device_id": "B23DCAT074", "boot_id": "test-a", "source": "test", "sequence": 1,
            "timestamp_ms": 1800000000000, "uptime_s": 0, "rssi": -60,
            "temperature": 25, "humidity": 50, "distance_cm": 100}
    return json.dumps({**item, **updates}).encode()


@pytest.mark.parametrize("changes", [{"temperature": "25"}, {"humidity": float("nan")},
                                     {"sequence": True}, {"timestamp_ms": 1}, {"source": "unknown"},
                                     {"rssi": 20}, {"boot_id": ""}, {"timestamp_ms": 10**1000},
                                     {"temperature": 10**1000}, {"temperature": None, "humidity": None, "distance_cm": None}])
def test_reject_bad_payload(changes):
    with pytest.raises(ValueError):
        collector.validate(packet(**changes), received=1800000000)


def test_missing_is_allowed_but_infinite_is_not():
    assert collector.validate(packet(humidity=None), 1800000000)["humidity"] is None
    with pytest.raises(ValueError):
        collector.validate(packet(distance_cm=float("inf")), 1800000000)


def test_duplicate_conflict_and_reboot(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "INBOX", tmp_path / "inbox.db")
    with collector.inbox() as conn:
        assert collector.accept(conn, packet(), 1800000000) == "accepted"
        assert collector.accept(conn, packet(), 1800000000) == "duplicate"
        assert collector.accept(conn, packet(temperature=30), 1800000000) == "conflict"
        assert collector.accept(conn, packet(boot_id="test-b"), 1800000000) == "accepted"
        assert conn.execute("SELECT COUNT(*) FROM inbox").fetchone()[0] == 2


def test_interpolation_never_fills_long_or_edge_gaps():
    s = pd.Series([np.nan, 1, np.nan, np.nan, 4, np.nan, np.nan, np.nan, 8, np.nan],
                  index=pd.date_range("2026-01-01", periods=10, freq="10s", tz="UTC"))
    out = interpolate_short(s)
    assert out.iloc[2] == 2 and out.iloc[3] == 3
    assert out.iloc[[0, 5, 6, 7, 9]].isna().all()


def test_outliers_normalization_and_boot_boundaries():
    records = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for boot, base in [("a", 25), ("b", 30)]:
        for i in range(20):
            records.append({"event_id": f"{boot}-{i}", "timestamp": start + timedelta(seconds=5*i),
                            "meta": {"device_id": "d", "boot_id": boot, "source": "test"}, "sequence": i+1,
                            "temperature": 78 if i == 10 else base + (i % 5) * .1,
                            "humidity": 50, "distance_cm": 900 if i == 11 else 100})
    out = transform(records)
    assert out.temperature_outlier.sum() == 2
    assert out.distance_cm_outlier.sum() == 2
    assert out.temperature_missing.sum() == 0
    assert len(out) == 20
    assert out.temperature_normalized.between(0, 1).all()
    assert out.groupby("boot_id").temperature_delta.first().notna().all()
    assert out.groupby("boot_id").head(1).temperature_delta.isna().all()
    assert out[out.boot_id == "b"].temperature.min() >= 30


def test_database_failure_keeps_pending_and_retry_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "INBOX", tmp_path / "inbox.db")
    class Collection:
        def __init__(self):
            self.rows = []
            self.fail = True
        def find_one(self, query, fields):
            return next((x for x in self.rows if x["event_id"] == query["event_id"]), None)
        def insert_one(self, record):
            self.rows.append(record)
            if self.fail:
                self.fail = False
                raise ConnectionError("ambiguous write result")
    class DB:
        sensor_raw = Collection()
    db = DB()
    with collector.inbox() as conn:
        collector.accept(conn, packet(), 1800000000)
        with pytest.raises(ConnectionError):
            collector.drain(conn, db)
        assert conn.execute("SELECT written FROM inbox").fetchone()[0] is None
        assert collector.drain(conn, db) == 1
        assert len(db.sensor_raw.rows) == 1
        assert collector.drain(conn, db) == 0
