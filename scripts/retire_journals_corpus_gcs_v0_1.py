#!/usr/bin/env python3
"""Move journal corpus prefixes to cold archive in GCS and write audit manifest.

Does NOT delete data — gsutil mv preserves objects under _archive/.
Writes tombstone JSON files at former prefix roots.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = "pathology-annotation-project"
BUCKET = "gs://pathology_hub"
ARCHIVE_BASE = f"{BUCKET}/_archive/retired_journals_20260726"

# Prefixes relative to bucket root (trailing path segment preserved under archive).
PREFIXES = (
    "01_sources/journals",
    "02_normalized/journals",
    "02_normalized/journals_batches",
    "03_indexes/journals",
    "05_html/article_browser",
)

TOMBSTONE = {
    "schema_version": "journals_retired_tombstone.v0_1",
    "retired_at_utc": None,
    "reason": (
        "Local journal RAG corpus retired: AJSP ingest has systematic lowercase-t "
        "corruption; Modern Pathology/Virchows redundant vs live Elsevier/PubMed "
        "abstracts + DOI links. Not loaded by backend when JOURNALS_RETIRED=1."
    ),
    "archive_base": ARCHIVE_BASE,
    "audit_manifest": f"{ARCHIVE_BASE}/RETIRE_AUDIT.json",
}


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def prefix_exists(uri: str) -> bool:
    r = run(["gsutil", "ls", uri], check=False)
    return r.returncode == 0


def du_bytes(uri: str) -> int:
    r = run(["gsutil", "du", "-s", uri], check=False)
    if r.returncode != 0:
        return 0
    try:
        return int(r.stdout.strip().split()[0])
    except (ValueError, IndexError):
        return 0


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    tombstone = dict(TOMBSTONE)
    tombstone["retired_at_utc"] = now

    moves: list[dict] = []
    for rel in PREFIXES:
        src = f"{BUCKET}/{rel}"
        dst = f"{ARCHIVE_BASE}/{rel}"
        entry = {"source": src, "archive": dst, "bytes": 0, "status": "skipped"}
        if not prefix_exists(src):
            entry["status"] = "missing"
            moves.append(entry)
            continue
        entry["bytes"] = du_bytes(src)
        run(["gsutil", "-m", "mv", src, dst])
        entry["status"] = "moved"
        moves.append(entry)
        tomb_uri = f"{BUCKET}/{rel}/RETIRED.json"
        body = json.dumps({**tombstone, "former_prefix": src, "archive_location": dst}, indent=2)
        tmp = Path(f"/tmp/journals_retired_tombstone_{rel.replace('/', '_')}.json")
        tmp.write_text(body, encoding="utf-8")
        run(["gsutil", "cp", str(tmp), tomb_uri])

    audit = {
        "schema_version": "journals_retire_audit.v0_1",
        "generated_at_utc": now,
        "project": PROJECT,
        "archive_base": ARCHIVE_BASE,
        "input_paths": [m["source"] for m in moves],
        "output_paths": [m["archive"] for m in moves if m["status"] == "moved"],
        "moves": moves,
        "total_bytes_moved": sum(m["bytes"] for m in moves if m["status"] == "moved"),
        "counts": {
            "moved": sum(1 for m in moves if m["status"] == "moved"),
            "missing": sum(1 for m in moves if m["status"] == "missing"),
        },
        "known_limitations": [
            "Archive is cold storage only; backend must set JOURNALS_RETIRED=1.",
            "AJSP normalized chunks in archive have lowercase-t corruption at ingest.",
            "Live Cloud Run revision must be redeployed without JOURNAL_* GCS env vars.",
        ],
    }

    audit_local = Path(__file__).resolve().parents[1] / "audits" / "journals_retired_20260726" / "RETIRE_AUDIT.json"
    audit_local.parent.mkdir(parents=True, exist_ok=True)
    audit_local.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    audit_gcs = f"{ARCHIVE_BASE}/RETIRE_AUDIT.json"
    tmp_audit = Path("/tmp/journals_retire_audit.json")
    tmp_audit.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    run(["gsutil", "cp", str(tmp_audit), audit_gcs])

    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
