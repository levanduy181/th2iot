"""Identify only this project's services and stop their Windows process trees."""
from pathlib import Path
import os
import psutil
from settings import ROOT


def lab_processes():
    current = psutil.Process()
    excluded = {os.getpid(), *(p.pid for p in current.parents())}
    found = []
    for proc in psutil.process_iter():
        try:
            if proc.pid in excluded or Path(proc.cwd()).resolve() != ROOT.resolve():
                continue
            args = proc.cmdline()
            if not args:
                continue
            name = proc.name().lower()
            scripts = {Path(arg).name for arg in args[1:]}
            python_service = name in ("python.exe", "pythonw.exe", "python", "python3") and (
                bool(scripts & {"collector.py", "broker.py", "preprocess.py", "run.py"})
                or ("streamlit" in args and "app.py" in scripts)
            )
            mongo_service = Path(proc.exe()).resolve() == (ROOT / ".runtime/mongodb/bin/mongod.exe").resolve()
            if (python_service and "--stop" not in args) or mongo_service:
                found.append(proc)
        except (psutil.Error, OSError):
            continue
    return found


def stop_trees(roots):
    # Snapshot descendants before terminating the venv launcher: afterwards
    # Windows can leave the real interpreter orphaned and lose that relationship.
    targets = {}
    for proc in roots:
        try:
            targets[proc.pid] = proc
            for child in proc.children(recursive=True):
                targets[child.pid] = child
        except psutil.NoSuchProcess:
            pass
    for proc in targets.values():
        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(list(targets.values()), timeout=5)
    for proc in alive:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(alive, timeout=5)
    if alive:
        raise RuntimeError(f"Could not stop lab PIDs: {[p.pid for p in alive]}")
    return len(targets)
