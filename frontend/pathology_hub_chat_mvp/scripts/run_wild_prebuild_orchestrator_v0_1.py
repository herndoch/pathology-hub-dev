#!/usr/bin/env python3
"""Run scheduled wild prebuild batches (sample → prebuild → GCS upload).

Reads:
  outputs/chat_mvp_topic_prepop_v0_1/wild_prebuild_manifest_v0_1.json

Writes per-batch audits plus:
  outputs/chat_mvp_topic_prepop_v0_1/wild_prebuild_orchestrator_audit_v0_1.json
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
MANIFEST = OUT / "wild_prebuild_manifest_v0_1.json"
SUMMARY_PATH = OUT / "wild_prebuild_orchestrator_audit_v0_1.json"
LOG_PATH = OUT / "wild_prebuild_orchestrator.log"


def run(cmd: list[str]) -> int:
    print(">>", " ".join(cmd), flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(">> " + " ".join(cmd) + "\n")
        proc = subprocess.run(cmd, cwd=str(APP_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        sys.stdout.write(proc.stdout)
        log.write(proc.stdout)
        log.write(f"rc={proc.returncode}\n")
    return proc.returncode


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    batches = manifest.get("batches") or []
    summary = {
        "schema_version": "wild_prebuild_orchestrator_audit.v0_1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_paths": [str(MANIFEST.relative_to(REPO_ROOT))],
        "output_paths": [],
        "batches": [],
        "counts": {
            "n_batches": len(batches),
            "n_requested": 0,
            "n_ok": 0,
            "n_failed": 0,
            "n_uploaded": 0,
        },
        "known_limitations": [
            "parallel=2 to avoid textbook hybrid degradation under load",
            "Skipped forensic root for this burn",
            "WHO/both already fully covered locally before this run",
        ],
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"\n==== start {summary['created_at_utc']} batches={len(batches)} ====\n")

    py = sys.executable
    for batch in batches:
        sample_name = batch["file"]
        sample = OUT / sample_name
        audit = OUT / sample_name.replace(".json", "_prebuild_audit.json")
        upload_audit = OUT / sample_name.replace(".json", "_gcs_upload_audit.json")
        print(f"\n===== BATCH {sample_name} n={batch['n']} =====", flush=True)
        rc = run(
            [
                py,
                "scripts/prebuild_topic_pages_pilot_v0_1.py",
                "--sample",
                str(sample),
                "--parallel",
                "2",
                "--timeout-s",
                "360",
                "--audit-out",
                str(audit),
            ]
        )
        batch_rec = {
            "file": sample_name,
            "n": batch["n"],
            "prebuild_rc": rc,
            "prebuild_audit": str(audit.relative_to(REPO_ROOT)),
        }
        if audit.exists():
            counts = (json.loads(audit.read_text(encoding="utf-8")).get("counts") or {})
            batch_rec["prebuild_counts"] = counts
            summary["counts"]["n_requested"] += int(counts.get("n_requested") or 0)
            summary["counts"]["n_ok"] += int(counts.get("n_ok") or 0)
            summary["counts"]["n_failed"] += int(counts.get("n_failed") or 0)

        urc = run(
            [
                py,
                "scripts/upload_topic_prebuilds_to_gcs_v0_1.py",
                "--sample",
                str(sample),
                "--audit-out",
                str(upload_audit),
            ]
        )
        batch_rec["upload_rc"] = urc
        batch_rec["upload_audit"] = str(upload_audit.relative_to(REPO_ROOT))
        if upload_audit.exists():
            ucounts = (json.loads(upload_audit.read_text(encoding="utf-8")).get("counts") or {})
            batch_rec["upload_counts"] = ucounts
            summary["counts"]["n_uploaded"] += int(ucounts.get("n_uploaded") or 0)

        summary["batches"].append(batch_rec)
        summary["output_paths"].extend(
            [batch_rec["prebuild_audit"], batch_rec["upload_audit"]]
        )
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(batch_rec, indent=2), flush=True)

    summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("ALL DONE", json.dumps(summary["counts"], indent=2), flush=True)


if __name__ == "__main__":
    main()
