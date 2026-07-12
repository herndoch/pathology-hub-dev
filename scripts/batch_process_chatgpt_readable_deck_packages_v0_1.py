#!/usr/bin/env python3
"""Inventory + convert ChatGPT-readable lecture zips from GCS.

Policy:
- Look for `*_chatgpt_readable_package.zip` under gs://pathology_hub/ (bucket root by default).
- Canonical MP4 = declared `video_file` (preferred) or zip stem with suffix stripped.
- Point every package at gs://pathology-hub-0/source_videos/<Canonical>.mp4
  with join_basis canonical_name_pending_upload when the object is missing.
- Do not rewrite to legacy Other_* names.
- Sidecar only — no FAISS/API claims.
- Frame JPG promotion to durable asset prefixes is a separate Colab/operator TODO.

Optional: if --run-heme-aggressive-pipeline is set and the Aggressive B-Cell zip
is present, also run the existing tag + consolidate scripts for that package.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.cloud import storage

# Local sibling import (script directory)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_lecture_deck_package_from_chatgpt_readable_v0_1 import build_package, slugify  # noqa: E402


BUCKET = "pathology_hub"
VIDEO_BUCKET = "pathology-hub-0"
VIDEO_PREFIX = "source_videos/"
ZIP_SUFFIX = "_chatgpt_readable_package.zip"
SCHEMA = "lecture_deck_batch_inventory.v0_1"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def infer_root(video_file: str) -> str:
    stem = Path(video_file).stem
    prefix = stem.split("_", 1)[0]
    known = {
        "Heme": "Heme",
        "Breast": "Breast",
        "BST": "BST",
        "Derm": "Skin",
        "Skin": "Skin",
        "GI": "GI",
        "GU": "GU",
        "GYN": "GYN",
        "HN": "HN",
        "Cyto": "Cyto",
        "ASC": "Cyto",
        "Molecular": "Molecular",
        "Neuro": "Neuro",
        "Peds": "Peds",
        "Thorax": "Thorax",
    }
    return known.get(prefix, prefix or "General")


def canonical_from_zip_name(name: str) -> str:
    base = Path(name).name
    if base.endswith(ZIP_SUFFIX):
        return base[: -len(ZIP_SUFFIX)] + ".mp4"
    return Path(base).stem + ".mp4"


def list_chatgpt_zips(client: storage.Client, prefix: str = "") -> list[storage.Blob]:
    blobs = []
    for blob in client.list_blobs(BUCKET, prefix=prefix):
        name = blob.name
        if "/" in name.rstrip("/") and prefix == "":
            # Default: bucket-root zips only (matches how the pilot was dropped).
            continue
        if name.endswith(ZIP_SUFFIX) or (
            name.endswith(".zip") and "chatgpt_readable" in name.lower()
        ):
            blobs.append(blob)
    return sorted(blobs, key=lambda b: b.name)


def video_exists(client: storage.Client, canonical_mp4: str) -> bool:
    blob = client.bucket(VIDEO_BUCKET).blob(f"{VIDEO_PREFIX}{canonical_mp4}")
    return blob.exists()


def download_and_extract(blob: storage.Blob, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / Path(blob.name).name
    blob.download_to_filename(str(zip_path))
    extract_dir = dest / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    # Package may extract to a nested folder; find lecture_index.json
    matches = list(extract_dir.rglob("lecture_index.json"))
    if not matches:
        raise FileNotFoundError(f"No lecture_index.json in {blob.name}")
    return matches[0].parent


def process_one(
    client: storage.Client,
    blob: storage.Blob,
    *,
    out_root: Path,
    upload: bool,
    run_heme_pipeline: bool,
    repo_scripts: Path,
) -> dict[str, Any]:
    zip_name = Path(blob.name).name
    with tempfile.TemporaryDirectory(prefix="deck_pkg_") as tmp:
        src_dir = download_and_extract(blob, Path(tmp))
        index = json.loads((src_dir / "lecture_index.json").read_text(encoding="utf-8"))
        declared = index.get("video_file") or canonical_from_zip_name(zip_name)
        canonical_mp4 = Path(str(declared)).name
        if not canonical_mp4.endswith(".mp4"):
            canonical_mp4 = canonical_from_zip_name(zip_name)

        exists = video_exists(client, canonical_mp4)
        gcs_uri = f"gs://{VIDEO_BUCKET}/{VIDEO_PREFIX}{canonical_mp4}"
        join_basis = "filename_match_source_videos" if exists else "canonical_name_pending_upload"

        package_id = f"{slugify(Path(canonical_mp4).stem)}_v0_1"
        out_dir = out_root / package_id
        root = infer_root(canonical_mp4)

        result = build_package(
            src_dir,
            out_dir,
            package_id=package_id,
            root=root,
            raw_source_gcs_uri=gcs_uri,
            title=Path(canonical_mp4).stem.replace("_", " "),
        )
        # Patch join basis honesty onto outputs
        manifest_path = out_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["raw_source_join_basis"] = join_basis
        manifest["canonical_video_file"] = canonical_mp4
        manifest["source_zip_gcs"] = f"gs://{BUCKET}/{blob.name}"
        limitations = list(manifest.get("known_limitations") or [])
        pending_note = (
            f"Canonical MP4 {canonical_mp4} pending upload under {VIDEO_PREFIX}"
            if not exists
            else f"Canonical MP4 {canonical_mp4} present in source_videos"
        )
        if pending_note not in limitations:
            limitations.insert(0, pending_note)
        pic_note = (
            "Frame JPG bytes stay in the source zip for now; durable asset upload is a Colab/operator TODO."
        )
        if pic_note not in limitations:
            limitations.append(pic_note)
        manifest["known_limitations"] = limitations
        for row_path_name in ("segments.jsonl", "frames.jsonl"):
            rows = []
            p = out_dir / row_path_name
            for ln in p.read_text(encoding="utf-8").splitlines():
                if not ln.strip():
                    continue
                row = json.loads(ln)
                row["raw_source_join_basis"] = join_basis
                rows.append(row)
            with p.open("w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        heme_extra: dict[str, Any] = {"ran": False}
        is_aggressive = "Aggressive_B_Cell" in zip_name or "aggressive_b_cell" in package_id
        if run_heme_pipeline and is_aggressive:
            tagged = out_root / f"{package_id}_tagged"
            tag_script = repo_scripts / "tag_lecture_deck_package_heme_aggressive_b_v0_1.py"
            cons_script = repo_scripts / "consolidate_lecture_deck_chunks_v0_1.py"
            subprocess.check_call(
                [
                    sys.executable,
                    str(tag_script),
                    "--package-dir",
                    str(out_dir),
                    "--out-dir",
                    str(tagged),
                ]
            )
            subprocess.check_call(
                [sys.executable, str(cons_script), "--package-dir", str(tagged)]
            )
            # Prefer tagged tree as the published package dir contents
            for name in (
                "manifest.json",
                "segments.jsonl",
                "segments_indexable.jsonl",
                "frames.jsonl",
                "chunks_indexable.jsonl",
                "audit.json",
                "chunk_audit.json",
            ):
                src = tagged / name
                if src.is_file():
                    (out_dir / name).write_bytes(src.read_bytes())
            heme_extra = {"ran": True, "tagged_dir": str(tagged)}

        gcs_prefix = f"gs://{BUCKET}/02_normalized/lectures/deck_packages/{package_id}/"
        uploaded = []
        if upload:
            bucket = client.bucket(BUCKET)
            for path in sorted(out_dir.iterdir()):
                if path.is_file():
                    dest = f"02_normalized/lectures/deck_packages/{package_id}/{path.name}"
                    bucket.blob(dest).upload_from_filename(str(path))
                    uploaded.append(f"gs://{BUCKET}/{dest}")

        return {
            "zip": f"gs://{BUCKET}/{blob.name}",
            "zip_size": blob.size,
            "zip_updated": blob.updated.isoformat() if blob.updated else None,
            "package_id": package_id,
            "canonical_mp4": canonical_mp4,
            "raw_source_gcs_uri": gcs_uri,
            "raw_source_join_basis": join_basis,
            "video_object_exists": exists,
            "root": root,
            "local_out": str(out_dir),
            "gcs_prefix": gcs_prefix,
            "uploaded": uploaded,
            "counts": result["manifest"]["counts"],
            "heme_pipeline": heme_extra,
            "frames_asset_upload": "colab_operator_todo",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="", help="GCS prefix under pathology_hub (default: root)")
    parser.add_argument(
        "--out-root",
        type=Path,
        default=Path("outputs/lecture_deck_packages_v0_1"),
    )
    parser.add_argument("--audit-dir", type=Path, default=Path("audits/lecture_deck_batch_inventory"))
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--run-heme-aggressive-pipeline", action="store_true")
    parser.add_argument(
        "--process",
        action="store_true",
        help="Download+convert found zips (default inventory-only)",
    )
    parser.add_argument("--project", default="pathology-annotation-project")
    args = parser.parse_args()

    client = storage.Client(project=args.project)
    zips = list_chatgpt_zips(client, prefix=args.prefix)
    inventory = {
        "schema_version": SCHEMA,
        "created_at_utc": utc_now(),
        "input_paths": [f"gs://{BUCKET}/{args.prefix}" if args.prefix else f"gs://{BUCKET}/"],
        "zip_suffix": ZIP_SUFFIX,
        "counts": {"zips_found": len(zips)},
        "zips": [
            {
                "name": b.name,
                "gcs_uri": f"gs://{BUCKET}/{b.name}",
                "size": b.size,
                "updated": b.updated.isoformat() if b.updated else None,
                "inferred_canonical_mp4": canonical_from_zip_name(b.name),
            }
            for b in zips
        ],
        "policy": {
            "canonical_video_uri_template": f"gs://{VIDEO_BUCKET}/{VIDEO_PREFIX}<CanonicalName>.mp4",
            "join_basis_if_missing": "canonical_name_pending_upload",
            "do_not_use_legacy_other_names": True,
            "frames_asset_upload": "colab_operator_todo",
            "index_artifact_when_tagged": "chunks_indexable.jsonl",
            "not_vectorized_unless_rebuild_audit_proves_it": True,
        },
        "known_limitations": [
            "Inventory reflects objects visible to the service account at audit time.",
            "Entity tagging remains lecture-specific; only Aggressive B-Cell has a committed rule pack.",
            "Frame/picture durable upload is intentionally deferred to Colab/operator.",
        ],
        "processed": [],
    }

    if args.process:
        args.out_root.mkdir(parents=True, exist_ok=True)
        scripts_dir = Path(__file__).resolve().parent
        for blob in zips:
            inventory["processed"].append(
                process_one(
                    client,
                    blob,
                    out_root=args.out_root,
                    upload=args.upload,
                    run_heme_pipeline=args.run_heme_aggressive_pipeline,
                    repo_scripts=scripts_dir,
                )
            )
        inventory["counts"]["packages_processed"] = len(inventory["processed"])

    args.audit_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    audit_path = args.audit_dir / f"inventory_{stamp}.json"
    audit_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    if args.upload:
        dest = f"06_audits/lectures/deck_packages/batch_{stamp}/inventory.json"
        client.bucket(BUCKET).blob(dest).upload_from_filename(str(audit_path))
        inventory["audit_gcs"] = f"gs://{BUCKET}/{dest}"
        audit_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"ok": True, "zips_found": len(zips), "audit": str(audit_path), "names": [b.name for b in zips]}, indent=2))


if __name__ == "__main__":
    main()
