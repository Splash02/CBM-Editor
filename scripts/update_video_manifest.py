import argparse
import hashlib
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("platform", choices=("windows-x64", "linux-x86_64"))
parser.add_argument("artifact")
parser.add_argument("--scan", default="")
args = parser.parse_args()

root = Path(__file__).resolve().parents[1]
manifest_path = root / "cbm_editor" / "vendor" / "video" / "manifest.json"
artifact = Path(args.artifact).resolve()
digest = hashlib.sha256()
with artifact.open("rb") as handle:
    for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
        digest.update(chunk)

with manifest_path.open("r", encoding="utf-8") as handle:
    manifest = json.load(handle)
entry = manifest["artifacts"][args.platform]
entry["sha256"] = digest.hexdigest()
entry["size"] = artifact.stat().st_size
entry["scan"] = args.scan
with manifest_path.open("w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2)
    handle.write("\n")
