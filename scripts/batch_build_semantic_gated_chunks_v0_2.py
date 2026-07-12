#!/usr/bin/env python3
"""Batch-build gated semantic indexable chunks for deck packages."""

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
    p.add_argument("--prefix", default="heme_sh_", help="Package dir name prefix to include")
    p.add_argument("--leaf-dir", type=Path, default=Path("outputs/heme_browse_leaf_embeddings_v0_1"))
    p.add_argument("--root", default=None, help="Browse root label passed to gate script")
    p.add_argument("--upload", action="store_true")
    p.add_argument("--project", default="pathology-annotation-project")
    p.add_argument("--audit-dir", type=Path, default=Path("audits/lecture_deck_semantic_gated_v0_2"))
    p.add_argument("--min-sim", type=float, default=0.50)
    p.add_argument("--min-margin", type=float, default=0.035)
    args = p.parse_args()

    scripts = Path(__file__).resolve().parent
    builder = scripts / "build_lecture_deck_semantic_indexable_chunks_v0_2.py"
    pkgs = sorted(
        d
        for d in args.local_root.iterdir()
        if d.is_dir()
        and d.name.startswith(args.prefix)
        and not d.name.endswith("_tagged")
        and (d / "segments.jsonl").is_file()
    )

    client = storage.Client(project=args.project) if args.upload else None
    hub = client.bucket(HUB) if client else None
    results = []

    for pkg in pkgs:
        print("GATE", pkg.name, flush=True)
        cmd = [
            sys.executable,
            str(builder),
            "--package-dir",
            str(pkg),
            "--leaf-dir",
            str(args.leaf_dir),
            "--min-sim",
            str(args.min_sim),
            "--min-margin",
            str(args.min_margin),
        ]
        if args.root:
            cmd.extend(["--root", args.root])
        subprocess.check_call(cmd)
        man = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        counts = man.get("counts") or {}
        row = {
            "package_id": pkg.name,
            "chunks_indexable": counts.get("chunks_indexable"),
            "sim_median": counts.get("semantic_similarity_median"),
            "margin_median": counts.get("semantic_margin_median"),
            "rejects": counts.get("gate_rejects"),
            "top_tags": list((counts.get("chunks_by_tag") or {}).items())[:8],
            "method": (man.get("tagging") or {}).get("method"),
        }
        uploaded = []
        if hub is not None:
            for name in (
                "manifest.json",
                "segments.jsonl",
                "segments_indexable.jsonl",
                "chunks_indexable.jsonl",
                "chunk_audit.json",
                "frames.jsonl",
                "audit.json",
            ):
                path = pkg / name
                if path.is_file():
                    dest = f"{DECK_PREFIX}{pkg.name}/{name}"
                    hub.blob(dest).upload_from_filename(str(path))
                    uploaded.append(f"gs://{HUB}/{dest}")
        row["uploaded"] = uploaded
        results.append(row)
        print(
            json.dumps(
                {"package_id": pkg.name, "chunks": row["chunks_indexable"], "sim_med": row["sim_median"]}
            ),
            flush=True,
        )

    audit = {
        "schema_version": "lecture_deck_semantic_gated_batch_audit.v0_2",
        "created_at_utc": utc_now(),
        "input_paths": [str(args.local_root), str(args.leaf_dir)],
        "output_paths": [f"gs://{HUB}/{DECK_PREFIX}*/chunks_indexable.jsonl"],
        "params": {
            "min_sim": args.min_sim,
            "min_margin": args.min_margin,
            "prefix": args.prefix,
            "root": args.root,
        },
        "counts": {
            "packages": len(results),
            "packages_with_chunks": sum(1 for r in results if (r.get("chunks_indexable") or 0) > 0),
            "total_chunks": sum(r.get("chunks_indexable") or 0 for r in results),
        },
        "packages": results,
        "known_limitations": [
            "Every retained chunk passed usefulness gates (sim, margin, size, not agenda).",
            "Rejected windows are omitted from the index on purpose.",
            "Still not human gold labels.",
            "Not FAISS/API exposed until a separate rebuild.",
        ],
    }
    args.audit_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = args.audit_dir / f"batch_{stamp}.json"
    path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    if hub is not None:
        dest = f"06_audits/lectures/deck_packages/semantic_gated_v0_2_{stamp}/audit.json"
        hub.blob(dest).upload_from_filename(str(path))
        audit["audit_gcs"] = f"gs://{HUB}/{dest}"
        path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "audit": str(path), "counts": audit["counts"]}, indent=2))


if __name__ == "__main__":
    main()
