#!/usr/bin/env python3
"""After Colab YouTube ingest: download deck package from GCS, semantic-gate, re-upload.

Example:
  python scripts/gate_youtube_deck_package_from_gcs_v0_1.py \\
    --package-id yt_nicole_cipriani_..._v0_1 \\
    --root BST \\
    --leaf-dir outputs/bst_browse_leaf_embeddings_v0_1
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.cloud.storage import Client


SIDECAR_NAMES = (
    "manifest.json",
    "segments.jsonl",
    "frames.jsonl",
    "audit.json",
    "segments_indexable.jsonl",
    "chunks_indexable.jsonl",
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def download_package(client: Client, package_id: str, out_dir: Path) -> Path:
    hub = client.bucket("pathology_hub")
    pkg = out_dir / package_id
    pkg.mkdir(parents=True, exist_ok=True)
    prefix = f"02_normalized/lectures/deck_packages/{package_id}/"
    found = 0
    for name in SIDECAR_NAMES:
        blob = hub.blob(prefix + name)
        if not blob.exists():
            continue
        blob.download_to_filename(str(pkg / name))
        found += 1
    if found == 0:
        raise FileNotFoundError(f"No sidecar objects under gs://pathology_hub/{prefix}")
    # optional frames/ not required for gating
    return pkg


def upload_gated(client: Client, pkg: Path, package_id: str) -> list[str]:
    hub = client.bucket("pathology_hub")
    uploaded = []
    for name in ("chunks_indexable.jsonl", "chunk_audit.json", "manifest.json", "segments.jsonl"):
        path = pkg / name
        if not path.is_file():
            continue
        dest = f"02_normalized/lectures/deck_packages/{package_id}/{name}"
        hub.blob(dest).upload_from_filename(str(path))
        uploaded.append(f"gs://pathology_hub/{dest}")
    return uploaded


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package-id", required=True)
    p.add_argument("--root", default="BST")
    p.add_argument("--leaf-dir", type=Path, default=Path("outputs/bst_browse_leaf_embeddings_v0_1"))
    p.add_argument("--out-root", type=Path, default=Path("outputs/lecture_deck_packages_v0_1"))
    p.add_argument("--skip-upload", action="store_true")
    args = p.parse_args()

    client = Client()
    pkg = download_package(client, args.package_id, args.out_root)
    print("downloaded", pkg, flush=True)

    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent / "build_lecture_deck_semantic_indexable_chunks_v0_2.py"),
        "--package-dir",
        str(pkg),
        "--leaf-dir",
        str(args.leaf_dir),
        "--root",
        args.root,
    ]
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)

    chunks_path = pkg / "chunks_indexable.jsonl"
    n_chunks = sum(1 for _ in chunks_path.open()) if chunks_path.is_file() else 0

    uploaded: list[str] = []
    if not args.skip_upload:
        uploaded = upload_gated(client, pkg, args.package_id)
        audit = {
            "schema_version": "lecture_deck_youtube_post_colab_gate_audit.v0_1",
            "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "package_id": args.package_id,
            "input_paths": [f"gs://pathology_hub/02_normalized/lectures/deck_packages/{args.package_id}/"],
            "output_paths": uploaded,
            "counts": {"chunks_indexable": n_chunks},
            "known_limitations": [
                "Does not rebuild FAISS; run build_lecture_vector_from_deck_packages_v0_1.py separately.",
                "Does not refresh Cloud Run.",
            ],
        }
        key = f"06_audits/lectures/deck_packages/youtube_post_colab_gate_{utc_stamp()}/audit.json"
        client.bucket("pathology_hub").blob(key).upload_from_string(
            json.dumps(audit, indent=2) + "\n", content_type="application/json"
        )
        uploaded.append(f"gs://pathology_hub/{key}")

    print(
        json.dumps(
            {
                "ok": True,
                "package_id": args.package_id,
                "chunks_indexable": n_chunks,
                "uploaded": uploaded,
                "next": "python scripts/build_lecture_vector_from_deck_packages_v0_1.py --upload --promote-live",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
