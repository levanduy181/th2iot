from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
target = root.parent / "Bai2_Le_Van_Duy_B23DCAT074.zip"
excluded = {".venv", ".runtime", "data", ".pio", "__pycache__", ".pytest_cache", "qa"}
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and not excluded.intersection(relative.parts) and path.suffix not in (".log", ".pyc"):
            bundle.write(path, Path("iot_lab2") / relative)
print(target)
