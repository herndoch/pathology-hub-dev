#!/usr/bin/env python3
"""Batch-convert a lecture family from content_library → deck sidecars.

Default family: Breast_Lecture (complete MP4 + assets + content triad).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from google.cloud.storage import Client

from build_lecture_deck_package_from_content_library_v0_1 import (  # noqa: E402
    CONTENT_PREFIX,
    build_package,
    slugify,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_family_stems(client: Client, family_prefix: str) -> list[str]:
    hub0 = client.bucket("pathology-hub-0")
    stems: set[str] = set()
    for b in hub0.list_blobs(prefix=CONTENT_PREFIX, max_results=20000):
        name = b.name[len(CONTENT_PREFIX) :]
        if "/" in name:
            continue
        if not name.endswith(".json"):
            continue
        if name.endswith("_MASTER.json") or name.endswith("_RAW.json"):
            continue
        stem = name[: -len(".json")]
        if stem.startswith(family_prefix):
            stems.add(stem)
    return sorted(stems)


def upload_package(client: Client, local_dir: Path, package_id: str) -> list[str]:
    hub = client.bucket("pathology_hub")
    uploaded: list[str] = []
    for name in (
        "manifest.json",
        "segments.jsonl",
        "frames.jsonl",
        "audit.json",
        "segments_indexable.jsonl",
        "chunks_indexable.jsonl",
    ):
        path = local_dir / name
        if not path.is_file():
            continue
        blob_name = f"02_normalized/lectures/deck_packages/{package_id}/{name}"
        hub.blob(blob_name).upload_from_filename(str(path))
        uploaded.append(f"gs://pathology_hub/{blob_name}")
    return uploaded


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family-prefix", default="Breast_Lecture")
    p.add_argument("--root", default="Breast")
    p.add_argument("--out-root", type=Path, default=Path("outputs/lecture_deck_packages_v0_1"))
    p.add_argument("--audit-dir", type=Path, default=Path("audits/lecture_deck_content_library_batch"))
    p.add_argument("--upload", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Optional cap for smoke runs")
    p.add_argument("--stems", nargs="*", default=None, help="Optional explicit stem list")
    args = p.parse_args()

    client = Client()
    stems = args.stems or list_family_stems(client, args.family_prefix)
    if args.limit and args.limit > 0:
        stems = stems[: args.limit]

    results: list[dict[str, Any]] = []
    for stem in stems:
        package_id = f"{slugify(stem)}_v0_1"
        out_dir = args.out_root / package_id
        try:
            built = build_package(stem, out_dir=out_dir, client=client, package_id=package_id, root=args.root)
            uploaded: list[str] = []
            if args.upload:
                uploaded = upload_package(client, out_dir, package_id)
            results.append(
                {
                    "stem": stem,
                    "package_id": package_id,
                    "ok": True,
                    "counts": built["manifest"]["counts"],
                    "join_basis": built["manifest"].get("raw_source_join_basis"),
                    "video_file": built["manifest"].get("video_file_declared"),
                    "uploaded": uploaded,
                }
            )
            print(json.dumps({"stem": stem, "ok": True, "counts": built["manifest"]["counts"]}, indent=2))
        except Exception as exc:  # noqa: BLE001 — batch continues
            results.append({"stem": stem, "ok": False, "error": str(exc)})
            print(json.dumps({"stem": stem, "ok": False, "error": str(exc)}, indent=2))

    args.audit_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audit = {
        "schema_version": "lecture_deck_content_library_batch_audit.v0_1",
        "created_at_utc": utc_now(),
        "family_prefix": args.family_prefix,
        "root": args.root,
        "input_paths": [f"gs://pathology-hub-0/{CONTENT_PREFIX}{args.family_prefix}*"],
        "output_paths": [str(args.out_root / f"{slugify(s)}_v0_1") for s in stems],
        "counts": {
            "stems_attempted": len(stems),
            "ok": sum(1 for r in results if r.get("ok")),
            "failed": sum(1 for r in results if not r.get("ok")),
            "segments_total": sum((r.get("counts") or {}).get("segments", 0) for r in results if r.get("ok")),
            "frames_total": sum((r.get("counts") or {}).get("frames", 0) for r in results if r.get("ok")),
            "mp4_joined": sum(1 for r in results if r.get("join_basis") == "filename_match_source_videos"),
        },
        "results": results,
        "known_limitations": [
            "Legacy slide-aligned transcripts — coarser than chatgpt_readable Whisper crumbs.",
            "Sidecars only; semantic gating / vector rebuild are separate steps.",
        ],
    }
    audit_path = args.audit_dir / f"batch_{stamp}.json"
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    if args.upload:
        hub = client.bucket("pathology_hub")
        gcs_audit = f"06_audits/lectures/deck_packages/content_library_batch_{stamp}/audit.json"
        hub.blob(gcs_audit).upload_from_filename(str(audit_path))
        print(json.dumps({"audit_gcs": f"gs://pathology_hub/{gcs_audit}"}, indent=2))

    print(json.dumps({"ok": True, "audit": str(audit_path), "counts": audit["counts"]}, indent=2))


if __name__ == "__main__":
    main()
