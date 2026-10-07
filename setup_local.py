"""Download a project-local MongoDB; no Docker, service install or admin needed."""
import hashlib
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "8.0.17"
URL = f"https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-{VERSION}.zip"


def main():
    if sys.platform != "win32":
        raise SystemExit("Install MongoDB 8 separately on Linux/macOS, then edit run.py if needed.")
    runtime = ROOT / ".runtime"
    target = runtime / "mongodb"
    if (target / "bin" / "mongod.exe").exists():
        print("MongoDB already available.")
        return
    runtime.mkdir(exist_ok=True)
    archive = runtime / "mongodb.zip"
    print("Downloading MongoDB portable from mongodb.org (about 756 MiB)...", flush=True)
    with urllib.request.urlopen(URL, timeout=120) as response, archive.open("wb") as out:
        shutil.copyfileobj(response, out)
    expected = urllib.request.urlopen(URL + ".sha256", timeout=30).read().decode().split()[0]
    with archive.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual.lower() != expected.lower():
        raise RuntimeError("MongoDB archive checksum mismatch")
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            parts = Path(name).parts[1:]
            # The distribution includes large debug files; only runtime and licenses are needed.
            if not parts or ".." in parts or name.endswith("/") or name.endswith(".pdb"):
                continue
            dest = target.joinpath(*parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(name) as source, dest.open("wb") as out:
                shutil.copyfileobj(source, out)
    archive.unlink()
    print(f"Ready: {target / 'bin' / 'mongod.exe'}", flush=True)


if __name__ == "__main__":
    main()
