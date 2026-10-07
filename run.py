"""Start all services with: python run.py. Ctrl+C stops owned processes."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import psutil
from settings import CONFIG, DATA, ROOT
from processes import lab_processes, stop_trees


def listening(port):
    with socket.socket() as sock:
        sock.settimeout(.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def port_busy(port):
    with socket.socket() as sock:
        if os.name == "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-dashboard", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    if args.stop:
        path = DATA / "processes.json"
        count = stop_trees(lab_processes())
        print(f"Stopped {count} lab processes (including child interpreters).")
        path.unlink(missing_ok=True)
        return
    mongod = ROOT / ".runtime/mongodb/bin/mongod.exe"
    if not mongod.exists():
        raise SystemExit("Run python setup_local.py first.")
    ports = [1884, 1885, 27018] + ([] if args.no_dashboard else [CONFIG["dashboard_port"]])
    for port in ports:
        if port_busy(port):
            raise SystemExit(f"Port {port} is busy. Run: python run.py --stop, then python run.py")
    (DATA / "mongo").mkdir(exist_ok=True)
    (DATA / "logs").mkdir(exist_ok=True)
    commands = [
        ("mongodb", [str(mongod), "--dbpath", str(DATA / "mongo"), "--bind_ip", "127.0.0.1", "--port", "27018",
                     "--wiredTigerCacheSizeGB", "0.25", "--logpath", str(DATA / "logs/mongodb-server.log"), "--logappend"]),
        ("broker", [sys.executable, "-u", "broker.py"]),
        ("collector", [sys.executable, "-u", "collector.py"]),
        ("preprocess", [sys.executable, "-u", "preprocess.py", "--watch"]),
    ]
    if not args.no_dashboard:
        commands.append(("dashboard", [sys.executable, "-m", "streamlit", "run", "app.py", "--server.address", "127.0.0.1",
                                      "--server.port", str(CONFIG["dashboard_port"]), "--server.headless", "true",
                                      "--browser.gatherUsageStats", "false"]))
    processes, handles = [], []
    try:
        for name, command in commands:
            handle = (DATA / f"logs/{name}.log").open("a", encoding="utf-8")
            handles.append(handle)
            env = {**os.environ, "PYTHONUTF8": "1"}
            proc = subprocess.Popen(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, env=env,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            processes.append((name, proc))
            readiness_ports = {"mongodb": 27018, "broker": CONFIG["mqtt_port"],
                               "collector": 1885, "dashboard": CONFIG["dashboard_port"]}
            if name in readiness_ports:
                port = readiness_ports[name]
                deadline = time.monotonic() + 45
                while not listening(port):
                    if proc.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"{name} failed. Read data/logs/{name}.log")
                    time.sleep(.2)
        time.sleep(1)
        for name, proc in processes:
            if proc.poll() is not None:
                raise RuntimeError(f"{name} failed to start. Read data/logs/{name}.log")
        owned = {"runner": {"pid": os.getpid(), "created": psutil.Process().create_time()}}
        owned.update({name: {"pid": proc.pid, "created": psutil.Process(proc.pid).create_time()} for name, proc in processes})
        (DATA / "processes.json").write_text(json.dumps(owned), encoding="utf-8")
        print(f"Ready: http://127.0.0.1:{CONFIG['dashboard_port']} | MQTT 1884 | MongoDB 27018", flush=True)
        print("Data source: start Wokwi or run python demo.py. Ctrl+C stops this lab.", flush=True)
        while True:
            for name, proc in processes:
                if proc.poll() is not None:
                    raise RuntimeError(f"{name} stopped. Read data/logs/{name}.log")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping lab...")
    finally:
        roots = []
        for _, proc in reversed(processes):
            try:
                if proc.poll() is None:
                    roots.append(psutil.Process(proc.pid))
            except psutil.NoSuchProcess:
                pass
        stop_trees(roots)
        for _, proc in processes:
            proc.wait(timeout=10)
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    main()
