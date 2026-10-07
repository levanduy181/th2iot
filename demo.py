"""Publish a labelled, reproducible fault-injection run through real MQTT."""
import argparse
import json
import math
import threading
import time
import uuid
from pathlib import Path
import paho.mqtt.client as mqtt
from settings import CONFIG, ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--interval", type=float, default=5)
    args = parser.parse_args()
    if args.interval <= 0 or args.count < 30:
        parser.error("count >= 30 and interval > 0 required")
    ready = threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="lab2-test-" + uuid.uuid4().hex[:8])
    client.on_connect = lambda c, u, f, reason, p: ready.set() if reason == 0 else None
    client.connect(CONFIG["mqtt_host"], CONFIG["mqtt_port"], 30)
    client.loop_start()
    if not ready.wait(10):
        raise RuntimeError("MQTT connection timeout")
    boot = "test-" + uuid.uuid4().hex[:12]
    sent = []
    start = time.time()
    try:
        for seq in range(1, args.count + 1):
            due = start + (seq - 1) * args.interval
            time.sleep(max(0, due - time.time()))
            if seq == 22:
                continue
            payload = {"device_id": "B23DCAT074", "boot_id": boot, "source": "test", "sequence": seq,
                       "timestamp_ms": int(time.time() * 1000), "uptime_s": int(time.time() - start), "rssi": -55,
                       "temperature": round(25 + math.sin(seq / 5) * 1.4, 2),
                       "humidity": round(50 + math.cos(seq / 7) * 4, 2),
                       "distance_cm": round(100 + math.sin(seq / 9) * 20, 2)}
            if seq == 12:
                payload["humidity"] = None
            if seq == 18:
                payload["temperature"] = 78.0
            if seq == 30:
                payload["distance_cm"] = 900.0
            text = json.dumps(payload, allow_nan=False)
            client.publish(CONFIG["mqtt_topic"], text, qos=1).wait_for_publish(10)
            sent.append(payload)
            if seq == 10:
                client.publish(CONFIG["mqtt_topic"], text, qos=1).wait_for_publish(10)
            print(f"test sequence={seq}", flush=True)
        for bad in ("{not-json}", json.dumps({"temperature": 25}), json.dumps({**sent[-1], "sequence": args.count + 1, "temperature": "NaN"})):
            client.publish(CONFIG["mqtt_topic"], bad, qos=1).wait_for_publish(10)
    finally:
        client.disconnect()
        client.loop_stop()
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    manifest = {"boot_id": boot, "source": "Python MQTT test publisher", "started": start, "finished": time.time(),
                "interval_s": args.interval, "nominal_count": args.count, "expected_unique": args.count - 1,
                "injected": {"missing_sequence": 22, "duplicate_sequence": 10, "missing_humidity": 12,
                             "temperature_outlier": 18, "distance_outlier": 30, "rejected_messages": 3}}
    (output / "last_run.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
