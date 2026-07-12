#!/usr/bin/env python3
"""Batch tag+consolidate Heme SH deck packages with canonical Heme::* leaves."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import storage

HUB = "pathology_hub"
DECK_PREFIX = "02_normalized/lectures/deck_packages/"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--local-root", type=Path, default=Path("outputs/lecture_deck_packages_v0_1"))
    p.add_argument("--upload", action="store_true")
    p.add_argument("--project", default="pathology-annotation-project")
    p.add_argument("--audit-dir", type=Path, default=Path("audits/lecture_deck_heme_browse_tag_batch"))
    p.add_argument("--only", nargs="*", default=None, help="Optional package_id filter")
    args = p.parse_args()

    scripts = Path(__file__).resolve().parent
    tagger = scripts / "tag_lecture_deck_package_heme_browse_v0_1.py"
    consolidator = scripts / "consolidate_lecture_deck_chunks_v0_1.py"

    pkgs = sorted(
        d for d in args.local_root.iterdir()
        if d.is_dir() and d.name.startswith("heme_sh_") and not d.name.endswith("_tagged")
        and (d / "segments.jsonl").is_file()
    )
    if args.only:
        want = set(args.only)
        pkgs = [d for d in pkgs if d.name in want]

    results = []
    client = storage.Client(project=args.project) if args.upload else None
    hub = client.bucket(HUB) if client else None

    for pkg in pkgs:
        print("TAG", pkg.name, flush=True)
        subprocess.check_call([sys.executable, str(tagger), "--package-dir", str(pkg)])
        print("CHUNK", pkg.name, flush=True)
        subprocess.check_call([sys.executable, str(consolidator), "--package-dir", str(pkg)])
        man = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        counts = man.get("counts") or {}
        row = {
            "package_id": pkg.name,
            "segments_indexable": counts.get("segments_indexable"),
            "chunks_indexable": counts.get("chunks_indexable"),
            "top_tags": list((counts.get("by_tag") or {}).items())[:10],
            "chunk_by_tag": counts.get("chunks_by_tag"),
            "chunk_duration_sec_median": counts.get("chunk_duration_sec_median"),
        }
        uploaded = []
        if hub is not None:
            for name in (
                "manifest.json",
                "segments.jsonl",
                "segments_indexable.jsonl",
                "frames.jsonl",
                "chunks_indexable.jsonl",
                "tag_audit.json",
                "chunk_audit.json",
            ):
                path = pkg / name
                if not path.is_file():
                    continue
                dest = f"{DECK_PREFIX}{pkg.name}/{name}"
                hub.blob(dest).upload_from_filename(str(path))
                uploaded.append(f"gs://{HUB}/{dest}")
        row["uploaded"] = uploaded
        results.append(row)
        print(
            json.dumps(
                {
                    "package_id": pkg.name,
                    "indexable": row["segments_indexable"],
                    "chunks": row["chunks_indexable"],
                }
            ),
            flush=True,
        )

    audit = {
        "schema_version": "lecture_deck_heme_browse_tag_batch_audit.v0_1",
        "created_at_utc": utc_now(),
        "input_paths": [str(args.local_root)],
        "output_paths": [f"gs://{HUB}/{DECK_PREFIX}*/chunks_indexable.jsonl"],
        "counts": {
            "packages": len(results),
            "packages_with_chunks": sum(1 for r in results if (r.get("chunks_indexable") or 0) > 0),
            "total_chunks": sum(r.get("chunks_indexable") or 0 for r in results),
        },
        "packages": results,
        "known_limitations": [
            "Tags restricted to canonical Heme::* browse leaves (best-of heuristic).",
            "Not a lecture vector rebuild; not API-exposed.",
            "Aggressive B-Cell previously had a hand-tuned rule pack; this batch uses the shared browse scorer.",
        ],
    }
    args.audit_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = args.audit_dir / f"batch_{stamp}.json"
    path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    if hub is not None:
        dest = f"06_audits/lectures/deck_packages/heme_browse_tag_batch_{stamp}/audit.json"
        hub.blob(dest).upload_from_filename(str(path))
        audit["audit_gcs"] = f"gs://{HUB}/{dest}"
        path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "audit": str(path), "counts": audit["counts"]}, indent=2))


if __name__ == "__main__":
    main()
