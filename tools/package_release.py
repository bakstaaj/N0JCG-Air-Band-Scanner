from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
version = (ROOT / "VERSION").read_text().strip()
output = ROOT / "release" / f"N0JCG-Air-Band-Scanner-v{version}.tar.gz"
output.parent.mkdir(exist_ok=True)
with tarfile.open(output, "w:gz") as archive:
    for path in ROOT.iterdir():
        if path.name not in {"release", ".git", ".venv", ".pytest_cache", "runtime"}:
            archive.add(path, arcname=f"N0JCG-Air-Band-Scanner-v{version}/{path.name}")
print(output)
