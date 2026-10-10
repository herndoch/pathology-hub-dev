#!/usr/bin/env python3
"""Build an allowlisted portable map package without source libraries or credentials."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "frontend/pathology_hub_map_hub_v0_1"

def package(output):
    files = [HUB / name for name in ("serve.py", "index.html")]
    for folder in ("static", "content", "lectures"):
        files += [p for p in (HUB / folder).rglob("*") if p.is_file()
                  and not any(part.startswith(".") or part == "__pycache__" for part in p.relative_to(HUB).parts)
                  and p.suffix in {".html", ".js", ".css", ".json", ".csv"}]
    payloads = {str(p.relative_to(HUB)): p.read_bytes() for p in sorted(files)}
    payloads["README.md"] = b"""# Pathology Knowledge Hub maps

Extract this ZIP. With Python 3.11 or later, run `python3 serve.py`
(Windows: `py serve.py`) and open http://127.0.0.1:8770/.
No extra packages or credentials are needed for the maps.

To share with someone else, use https://map.pathologynotebook.com/.
Select a topic, lecture or clip there and use its Copy link button.
A localhost link works only on your own computer.

External figures, recordings, the reference library and assistant preview
need network access and retain their own source access requirements.
The backend and source library are not bundled. Mappings are automated.

MANIFEST.json records the SHA-256 hash of each packaged file.
Source and release notes: https://github.com/herndoch/pathology-hub-dev
"""
    manifest = {"schema_version": "1.0", "files": {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()},
                "known_limitations": ["Map package only; hosted app, external media and source library are not bundled."]}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
        archive.writestr("MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        for name, sha in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == sha
    return manifest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = package(args.output)
    print(f"Verified {len(result['files'])} files: {args.output}")
