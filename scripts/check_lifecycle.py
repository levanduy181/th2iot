"""Manual regression: two full starts/stops must leave no orphan services."""
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from processes import lab_processes
from run import port_busy

for cycle in range(2):
    with (ROOT / "data/logs/lifecycle.log").open("w") as log:
        proc = subprocess.Popen([sys.executable, "-u", "run.py"], cwd=ROOT,
                                stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 45
            while True:
                if proc.poll() is not None:
                    raise RuntimeError("run.py exited; check lifecycle.log")
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8502/_stcore/health", timeout=1) as response:
                        assert response.read() == b"ok"
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(.3)
            time.sleep(2)
            assert proc.poll() is None
            print(f"Cycle {cycle + 1}: dashboard and collector started", flush=True)
        finally:
            subprocess.run([sys.executable, "run.py", "--stop"], cwd=ROOT, check=True)
            proc.wait(timeout=15)
    assert not lab_processes(), "Orphan lab processes remain"
    assert not any(port_busy(p) for p in (1884, 1885, 27018, 8502)), "Port still occupied"
    print(f"Cycle {cycle + 1}: all processes stopped and ports released", flush=True)
