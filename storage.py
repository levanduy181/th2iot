from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import CollectionInvalid
from settings import CONFIG


def database():
    return MongoClient(CONFIG["mongo_uri"], serverSelectionTimeoutMS=3000,
                       tz_aware=True, w=1, journal=True)[CONFIG["database"]]


def initialize(db):
    ttl = int(CONFIG["retention_days"] * 86400)
    try:
        db.create_collection("sensor_raw", timeseries={"timeField": "timestamp", "metaField": "meta",
                                                       "granularity": "seconds"}, expireAfterSeconds=ttl)
    except CollectionInvalid:
        pass
    db.sensor_raw.create_index("event_id")
    db.sensor_processed.create_index("timestamp", expireAfterSeconds=ttl)
    db.sensor_processed.create_index([("meta.device_id", 1), ("meta.source", 1), ("timestamp", 1)])


def utcnow():
    return datetime.now(timezone.utc)


def raw_records(db, start, source=None, boot_id=None):
    query = {"timestamp": {"$gte": start}}
    if source:
        query["meta.source"] = source
    if boot_id:
        query["meta.boot_id"] = boot_id
    # Time-series collections do not enforce unique event IDs. Keep reads
    # idempotent even after recovery from an ambiguous database write.
    seen = set()
    for row in db.sensor_raw.find(query, {"_id": 0}).sort("timestamp", 1):
        if row["event_id"] not in seen:
            seen.add(row["event_id"])
            yield row
