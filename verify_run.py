"""Export measurements of the last real MQTT test run for the report."""
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
import pandas as pd
from settings import DATA, ROOT, SENSORS
from storage import database, raw_records
from preprocess import process_once


def main():
    out = ROOT / "output"
    run = json.loads((out / "last_run.json").read_text())
    db = database()
    start = datetime.fromtimestamp(run["started"] - 1, timezone.utc)
    deadline = time.monotonic() + 30
    while True:
        records = list(raw_records(db, start, "test", run["boot_id"]))
        if len(records) == run["expected_unique"]:
            break
        if time.monotonic() > deadline:
            raise AssertionError(f"Expected {run['expected_unique']} unique records, got {len(records)}")
        time.sleep(.25)
    raw = pd.json_normalize(records)
    processed = process_once(db, minutes=1440, source="test", boot_id=run["boot_id"])
    with sqlite3.connect(DATA / "inbox.sqlite3") as conn:
        inbox = pd.read_sql_query("SELECT * FROM inbox", conn)
        events = dict(conn.execute("SELECT kind,COUNT(*) FROM events WHERE created >= ? AND created <= ? GROUP BY kind",
                                   (run["started"], run["finished"] + 1)).fetchall())
    inbox = inbox[inbox.event_id.isin(raw.event_id)].copy()
    receive_to_db = (inbox.written - inbox.received) * 1000
    ts_map = dict(zip(raw.event_id, pd.to_datetime(raw.timestamp).astype('int64') / 1e6))
    e2e = inbox.written * 1000 - inbox.event_id.map(ts_map)
    measured = db.command("collStats", "sensor_raw")
    options = db.sensor_raw.options()
    stats = {**run, "unique_received": len(raw), "physical_raw_count": db.sensor_raw.count_documents({"meta.boot_id": run["boot_id"]}),
             "processed_windows": len(processed), "events": events,
             "sequence_missing": int(raw.sequence.max() - raw.sequence.min() + 1 - raw.sequence.nunique()),
             "missing_cells": int(raw[list(SENSORS)].isna().sum().sum()),
             "outlier_cells": int(processed[[k + '_outlier' for k in SENSORS]].sum().sum()),
             "receive_to_db_mean_ms": float(receive_to_db.mean()), "receive_to_db_p95_ms": float(receive_to_db.quantile(.95)),
             "publisher_to_db_mean_ms": float(e2e.mean()), "publisher_to_db_p95_ms": float(e2e.quantile(.95)),
             "write_mean_ms": float(inbox.write_ms.mean()), "db_logical_bytes": measured.get("size"),
             "db_storage_bytes": measured.get("storageSize"), "collection_options": options,
             "mongo_version": db.client.server_info()["version"]}
    assert stats["physical_raw_count"] == run["expected_unique"]
    assert stats["sequence_missing"] == 1
    assert events.get("duplicate") == 1 and events.get("rejected") == 3
    assert stats["missing_cells"] == 1 and stats["outlier_cells"] >= 2
    assert options["expireAfterSeconds"] == 604800
    raw.to_csv(out / "telemetry_raw.csv", index=False, encoding="utf-8-sig")
    processed.to_csv(out / "telemetry_processed.csv", index=False, encoding="utf-8-sig")
    (out / "verification.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    main()
