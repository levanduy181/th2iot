"""Durable MQTT inbox, validation and one database writer per project."""
import hashlib
import json
import logging
import math
import re
import signal
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from settings import CONFIG, DATA, SENSORS
from storage import database, initialize

LOG = logging.getLogger("collector")
INBOX = DATA / "inbox.sqlite3"
TIME_REQUEST = CONFIG["mqtt_topic"] + "/time/request"


def reply_clock(client, payload):
    # Only a bounded boot identifier may form the local reply topic.
    if not re.fullmatch(rb"[A-Za-z0-9_-]{1,64}", payload):
        return
    reply = CONFIG["mqtt_topic"] + "/time/" + payload.decode("ascii")
    client.publish(reply, str(time.time_ns() // 1_000_000), qos=0, retain=False)


def inbox():
    conn = sqlite3.connect(INBOX, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("""CREATE TABLE IF NOT EXISTS inbox (
        event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, received REAL NOT NULL,
        written REAL, write_ms REAL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY, created REAL, kind TEXT, detail TEXT)""")
    conn.commit()
    return conn


def validate(payload, received=None):
    received = time.time() if received is None else received
    if len(payload) > 4096:
        raise ValueError("payload exceeds 4096 bytes")
    try:
        item = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid JSON") from exc
    if not isinstance(item, dict):
        raise ValueError("expected JSON object")
    for key in ("device_id", "boot_id"):
        if not isinstance(item.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", item[key]):
            raise ValueError(f"invalid {key}")
    if item.get("source") not in ("wokwi", "test"):
        raise ValueError("source must be wokwi or test")
    for key in ("sequence", "timestamp_ms", "uptime_s"):
        if type(item.get(key)) is not int or item[key] < 0:
            raise ValueError(f"invalid {key}")
    if item["sequence"] < 1 or item["sequence"] > 2**32 - 1:
        raise ValueError("sequence outside uint32 range")
    if item["timestamp_ms"] > 2**63 - 1 or item["uptime_s"] > 2**32 - 1:
        raise ValueError("timestamp or uptime overflow")
    # Retention bounds also prevent invalid timestamps from polluting the series.
    age = received - item["timestamp_ms"] / 1000
    if age < -30 or age > CONFIG["retention_days"] * 86400:
        raise ValueError("timestamp outside accepted clock/retention window")
    clean = {k: item[k] for k in ("device_id", "boot_id", "source", "sequence", "timestamp_ms", "uptime_s")}
    for key in SENSORS:
        value = item.get(key)
        if value is not None and (type(value) not in (int, float) or abs(value) > 1e9 or not math.isfinite(value)):
            raise ValueError(f"{key} must be finite number or null")
        clean[key] = float(value) if value is not None else None
    if all(clean[k] is None for k in SENSORS):
        raise ValueError("all sensor readings missing")
    if type(item.get("rssi")) is not int or not -127 <= item["rssi"] <= 0:
        raise ValueError("invalid rssi")
    clean["rssi"] = item["rssi"]
    identity = f"{item['device_id']}:{item['boot_id']}:{item['sequence']}"
    clean["event_id"] = hashlib.sha256(identity.encode()).hexdigest()
    return clean


def accept(conn, payload, received=None):
    received = time.time() if received is None else received
    try:
        item = validate(payload, received)
    except ValueError as exc:
        conn.execute("INSERT INTO events(created,kind,detail) VALUES(?,?,?)", (received, "rejected", str(exc)))
        conn.commit()
        return "rejected"
    text = json.dumps(item, sort_keys=True, allow_nan=False)
    previous = conn.execute("SELECT payload FROM inbox WHERE event_id=?", (item["event_id"],)).fetchone()
    if previous:
        kind = "duplicate" if previous[0] == text else "conflict"
        conn.execute("INSERT INTO events(created,kind,detail) VALUES(?,?,?)", (received, kind, item["event_id"]))
    else:
        kind = "accepted"
        conn.execute("INSERT INTO inbox(event_id,payload,received) VALUES(?,?,?)", (item["event_id"], text, received))
    conn.commit()
    return kind


def drain(conn, db):
    rows = conn.execute("SELECT event_id,payload,received FROM inbox WHERE written IS NULL ORDER BY received LIMIT 100").fetchall()
    for event_id, text, received in rows:
        item = json.loads(text)
        started = time.perf_counter()
        if not db.sensor_raw.find_one({"event_id": event_id}, {"event_id": 1}):
            record = {key: item[key] for key in (*SENSORS, "sequence", "uptime_s", "rssi", "event_id")}
            record.update(
                meta={key: item[key] for key in ("device_id", "boot_id", "source")},
                timestamp=datetime.fromtimestamp(item["timestamp_ms"] / 1000, timezone.utc),
                received_at=datetime.fromtimestamp(received, timezone.utc),
                received_latency_ms=received * 1000 - item["timestamp_ms"],
                write_started_at=datetime.now(timezone.utc),
            )
            db.sensor_raw.insert_one(record)
        written = time.time()
        conn.execute("UPDATE inbox SET written=?,write_ms=? WHERE event_id=?",
                     (written, (time.perf_counter() - started) * 1000, event_id))
        conn.commit()
    return len(rows)


def main():
    # A loopback socket prevents two local writers racing on a time-series insert.
    import socket
    guard = socket.socket()
    try:
        guard.bind(("127.0.0.1", 1885))
    except OSError as exc:
        guard.close()
        raise SystemExit("Collector already running or port 1885 busy. Stop the old collector, or run python run.py --stop.") from exc
    guard.listen(8)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(CONFIG["mqtt_topic"], qos=1)
            client.subscribe(TIME_REQUEST, qos=0)
            LOG.info("Subscribed %s", CONFIG["mqtt_topic"])
        else:
            LOG.error("MQTT rejected: %s", reason_code)

    def on_message(client, userdata, message):
        if message.topic == TIME_REQUEST:
            reply_clock(client, message.payload)
            client.ack(message.mid, message.qos)
            return
        # ACK only after durable local commit. Do not log raw payloads or secrets.
        try:
            with closing(inbox()) as conn:
                kind = accept(conn, message.payload)
            client.ack(message.mid, message.qos)
            LOG.info("MQTT %s", kind)
        except Exception:
            LOG.exception("Local inbox failure; disconnect without acknowledging")
            client.disconnect()
            stop.set()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="lab2-collector",
                         clean_session=False, manual_ack=True)
    client.on_connect, client.on_message = on_connect, on_message
    client.reconnect_delay_set(1, 15)
    client.connect_async(CONFIG["mqtt_host"], CONFIG["mqtt_port"], 30)
    client.loop_start()
    conn, db = inbox(), database()
    ready = False
    last_cleanup = 0
    try:
        while not stop.is_set():
            try:
                if not ready:
                    initialize(db)
                    ready = True
                drain(conn, db)
                if time.time() - last_cleanup > 3600:
                    cutoff = time.time() - CONFIG["retention_days"] * 86400
                    conn.execute("DELETE FROM inbox WHERE received < ? AND written IS NOT NULL", (cutoff,))
                    conn.execute("DELETE FROM events WHERE created < ?", (cutoff,))
                    conn.commit()
                    last_cleanup = time.time()
            except Exception as exc:
                LOG.warning("Database unavailable, inbox retained: %s", str(exc)[:160])
                stop.wait(2)
            stop.wait(.2)
    finally:
        client.disconnect()
        client.loop_stop()
        conn.close()
        db.client.close()
        guard.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
