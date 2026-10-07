import argparse
import hashlib
import logging
import time
from datetime import timedelta
import numpy as np
import pandas as pd
from pymongo import ReplaceOne
from settings import BOUNDS, CONFIG, SENSORS
from storage import database, initialize, raw_records, utcnow


def interpolate_short(series, max_gap=2):
    missing = series.isna()
    groups = missing.ne(missing.shift()).cumsum()
    lengths = missing.groupby(groups).transform("sum")
    eligible = missing & lengths.le(max_gap)
    candidate = series.interpolate(method="time", limit_area="inside")
    return series.mask(eligible, candidate)


def transform(records, resample_s=None):
    """Process each boot independently, preserving gaps and quality flags."""
    if not records:
        return pd.DataFrame()
    frame = pd.json_normalize(records)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frames = []
    step = resample_s or CONFIG["resample_s"]
    for identity, group in frame.groupby(["meta.device_id", "meta.boot_id", "meta.source"]):
        group = group.drop_duplicates("event_id").sort_values("timestamp").set_index("timestamp")
        clean = group[list(SENSORS)].apply(pd.to_numeric, errors="coerce")
        flags = pd.DataFrame(index=clean.index)
        for key, (lo, hi) in BOUNDS.items():
            values = clean[key].copy()
            physical = values.notna() & ~values.between(lo, hi)
            clean.loc[physical, key] = np.nan
            valid = clean[key].dropna()
            statistical = pd.Series(False, index=clean.index)
            if len(valid) >= 8:
                q1, q3 = valid.quantile([.25, .75])
                iqr = q3 - q1
                if iqr > 1e-9:
                    statistical = clean[key].lt(q1 - 1.5 * iqr) | clean[key].gt(q3 + 1.5 * iqr)
                    clean.loc[statistical, key] = np.nan
            flags[key + "_outlier"] = (physical | statistical).astype(int)
            flags[key + "_missing"] = values.isna().astype(int)
        freq = f"{step}s"
        result = clean.resample(freq).mean()
        result["sample_count"] = group["sequence"].resample(freq).count()
        result = result.join(flags.resample(freq).sum())
        for key, (lo, hi) in BOUNDS.items():
            before = result[key].copy()
            result[key] = interpolate_short(before)
            result[key + "_imputed"] = (before.isna() & result[key].notna()).astype(int)
            result[key + "_rolling"] = result[key].rolling(3, min_periods=1).mean().where(result[key].notna())
            result[key + "_delta"] = result[key].diff()
            # Fixed physical bounds avoid refitting a scaler differently on every refresh.
            result[key + "_normalized"] = (result[key] - lo) / (hi - lo)
        for key, value in zip(("device_id", "boot_id", "source"), identity):
            result[key] = value
        result["window_s"] = step
        frames.append(result.reset_index())
    return pd.concat(frames, ignore_index=True)


def process_once(db, minutes=60, source=None, boot_id=None):
    records = list(raw_records(db, utcnow() - timedelta(minutes=minutes), source, boot_id))
    frame = transform(records)
    ops = []
    for row in frame.to_dict("records"):
        stamp = row.pop("timestamp").to_pydatetime()
        meta = {k: row.pop(k) for k in ("device_id", "boot_id", "source")}
        identity = f"{meta}:{stamp.isoformat()}:{row['window_s']}"
        key = hashlib.sha256(identity.encode()).hexdigest()
        values = {k: None if pd.isna(v) else v for k, v in row.items()}
        doc = {"_id": key, "timestamp": stamp, "meta": meta, "processed_at": utcnow(), **values}
        ops.append(ReplaceOne({"_id": key}, doc, upsert=True))
    if ops:
        db.sensor_processed.bulk_write(ops, ordered=False)
    return frame


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--minutes", type=int, default=60)
    args = parser.parse_args()
    db = database()
    while True:
        try:
            initialize(db)
            print(f"Processed {len(process_once(db, args.minutes))} windows", flush=True)
        except Exception as exc:
            logging.warning("Processing failed: %s", exc)
            if not args.watch:
                raise
        if not args.watch:
            break
        time.sleep(5)
