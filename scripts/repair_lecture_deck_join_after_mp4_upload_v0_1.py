#!/usr/bin/env python3
"""Flip deck package video join basis after canonical MP4s land.

Also verifies _asset_library slide objects exist for frames.jsonl rows.
Sidecar-only repair — does not rebuild indexes or claim API exposure.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from google.cloud import storage

HUB = "pathology_hub"
VIDEO_BUCKET = "pathology-hub-0"
VIDEO_PREFIX = "source_videos/"
ASSET_PREFIX = "_asset_library/lectures/"
DECK_PREFIX = "02_normalized/lectures/deck_packages/"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gcs_to_https(gcs_uri: str) -> str:
    without = gcs_uri[len("gs://") :]
    bucket, _, key = without.partition("/")
    return f"https://storage.googleapis.com/{bucket}/{quote(key, safe='/')}"


def load_jsonl(text: str) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in text.splitlines() if ln.strip()]


def dump_jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def repair_package(
    client: storage.Client,
    package_id: str,
    *,
    local_out: Path | None,
    upload: bool,
) -> dict[str, Any]:
    hub = client.bucket(HUB)
    videos = client.bucket(VIDEO_BUCKET)
    prefix = f"{DECK_PREFIX}{package_id}/"
    man_blob = hub.blob(prefix + "manifest.json")
    if not man_blob.exists():
        return {"package_id": package_id, "status": "missing_manifest"}

    manifest = json.loads(man_blob.download_as_text())
    canonical = manifest.get("canonical_video_file") or Path(
        str(manifest.get("video_file_declared") or "")
    ).name
    if not canonical.endswith(".mp4"):
        # infer from package_id stem
        stem = package_id.replace("_v0_1", "")
        # package_id is slug lowercase with underscores; prefer declared
        canonical = Path(str(manifest.get("raw_source_gcs_uri") or "")).name or canonical

    video_key = f"{VIDEO_PREFIX}{canonical}"
    video_exists = videos.blob(video_key).exists()
    gcs_uri = f"gs://{VIDEO_BUCKET}/{video_key}"
    video_url = gcs_to_https(gcs_uri)
    join_basis = "filename_match_source_videos" if video_exists else "canonical_name_pending_upload"

    # sample-check assets from frames.jsonl
    frames_blob = hub.blob(prefix + "frames.jsonl")
    frames = load_jsonl(frames_blob.download_as_text()) if frames_blob.exists() else []
    asset_ok = 0
    asset_missing = 0
    for fr in frames:
        asset = fr.get("asset_gcs_uri")
        if not asset:
            # synthesize from image_path
            ip = fr.get("image_path")
            if ip:
                asset = f"gs://{VIDEO_BUCKET}/{ASSET_PREFIX}{ip}"
                fr["asset_gcs_uri"] = asset
                fr["image_url"] = gcs_to_https(asset)
                if "image_path" not in fr and ip:
                    fr["image_path"] = ip
        if asset and asset.startswith(f"gs://{VIDEO_BUCKET}/"):
            key = asset[len(f"gs://{VIDEO_BUCKET}/") :]
            if videos.blob(key).exists():
                asset_ok += 1
            else:
                asset_missing += 1
        else:
            asset_missing += 1

        fr["raw_source_gcs_uri"] = gcs_uri
        fr["video_url"] = video_url if video_exists else fr.get("video_url")
        fr["raw_source_join_basis"] = join_basis
        # refresh video_time_url
        start = fr.get("start_sec")
        if video_exists and start is not None:
            try:
                s = float(start)
                fr["video_time_url"] = f"{video_url}#t={s:g}"
            except (TypeError, ValueError):
                pass

    def patch_rows(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            r["raw_source_gcs_uri"] = gcs_uri
            r["raw_source_join_basis"] = join_basis
            if video_exists:
                r["video_url"] = video_url
                start, end = r.get("start_sec"), r.get("end_sec")
                try:
                    s = float(start)
                    if end is not None:
                        e = float(end)
                        r["video_time_url"] = f"{video_url}#t={s:g},{e:g}"
                    else:
                        r["video_time_url"] = f"{video_url}#t={s:g}"
                except (TypeError, ValueError):
                    pass

    artifacts = {}
    for name in (
        "segments.jsonl",
        "segments_indexable.jsonl",
        "chunks_indexable.jsonl",
        "frames.jsonl",
    ):
        blob = hub.blob(prefix + name)
        if not blob.exists():
            continue
        if name == "frames.jsonl":
            rows = frames
        else:
            rows = load_jsonl(blob.download_as_text())
            patch_rows(rows)
        artifacts[name] = rows

    manifest["raw_source_gcs_uri"] = gcs_uri
    manifest["video_url"] = video_url if video_exists else manifest.get("video_url")
    manifest["raw_source_join_basis"] = join_basis
    manifest["canonical_video_file"] = canonical
    manifest["asset_library_prefix"] = f"gs://{VIDEO_BUCKET}/{ASSET_PREFIX}{Path(canonical).stem}/"
    counts = dict(manifest.get("counts") or {})
    counts["frames_asset_objects_present"] = asset_ok
    counts["frames_asset_objects_missing"] = asset_missing
    counts["canonical_mp4_present"] = video_exists
    manifest["counts"] = counts
    limitations = list(manifest.get("known_limitations") or [])
    note = (
        f"Canonical MP4 present: {canonical}"
        if video_exists
        else f"Canonical MP4 still pending: {canonical}"
    )
    # replace pending notes
    limitations = [x for x in limitations if "pending upload" not in x.lower() and "Canonical MP4" not in x]
    limitations.insert(0, note)
    if asset_missing:
        limitations.append(f"{asset_missing}/{len(frames)} frame asset objects missing under _asset_library.")
    else:
        limitations = [x for x in limitations if "Frame JPG bytes target" not in x]
        limitations.append(
            f"All {asset_ok} frame assets present under _asset_library/lectures/{Path(canonical).stem}/."
        )
    manifest["known_limitations"] = limitations
    manifest["join_repaired_at_utc"] = utc_now()

    written = []
    if upload:
        hub.blob(prefix + "manifest.json").upload_from_string(
            json.dumps(manifest, indent=2) + "\n", content_type="application/json"
        )
        written.append(f"gs://{HUB}/{prefix}manifest.json")
        for name, rows in artifacts.items():
            hub.blob(prefix + name).upload_from_string(dump_jsonl(rows), content_type="application/x-ndjson")
            written.append(f"gs://{HUB}/{prefix}{name}")

    if local_out:
        local_out.mkdir(parents=True, exist_ok=True)
        (local_out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        for name, rows in artifacts.items():
            (local_out / name).write_text(dump_jsonl(rows), encoding="utf-8")

    return {
        "package_id": package_id,
        "status": "repaired",
        "canonical_mp4": canonical,
        "video_exists": video_exists,
        "join_basis": join_basis,
        "frames": len(frames),
        "asset_ok": asset_ok,
        "asset_missing": asset_missing,
        "uploaded": written,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upload", action="store_true")
    p.add_argument("--project", default="pathology-annotation-project")
    p.add_argument("--audit-dir", type=Path, default=Path("audits/lecture_deck_join_repair"))
    p.add_argument("--local-root", type=Path, default=Path("outputs/lecture_deck_packages_v0_1"))
    args = p.parse_args()

    client = storage.Client(project=args.project)
    # discover package ids
    pkgs = sorted(
        {
            blob.name.split("/")[3]
            for blob in client.list_blobs(HUB, prefix=DECK_PREFIX)
            if blob.name.count("/") >= 4
        }
    )
    results = []
    for pid in pkgs:
        results.append(
            repair_package(
                client,
                pid,
                local_out=args.local_root / pid,
                upload=args.upload,
            )
        )

    audit = {
        "schema_version": "lecture_deck_join_repair_audit.v0_1",
        "created_at_utc": utc_now(),
        "input_paths": [f"gs://{HUB}/{DECK_PREFIX}", f"gs://{VIDEO_BUCKET}/{VIDEO_PREFIX}Heme_SH_*.mp4"],
        "output_paths": [f"gs://{HUB}/{DECK_PREFIX}*/manifest.json"],
        "counts": {
            "packages": len(results),
            "video_present": sum(1 for r in results if r.get("video_exists")),
            "join_filename_match": sum(1 for r in results if r.get("join_basis") == "filename_match_source_videos"),
            "all_assets_ok": sum(1 for r in results if r.get("asset_missing") == 0),
            "packages_with_missing_assets": sum(1 for r in results if (r.get("asset_missing") or 0) > 0),
        },
        "packages": results,
        "known_limitations": [
            "Does not rebuild FAISS/docstore or claim API/Videos exposure.",
            "Tagging/consolidation still pending for packages other than Aggressive B-Cell.",
        ],
    }
    args.audit_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = args.audit_dir / f"join_repair_{stamp}.json"
    path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    if args.upload:
        dest = f"06_audits/lectures/deck_packages/join_repair_{stamp}/audit.json"
        client.bucket(HUB).blob(dest).upload_from_filename(str(path))
        audit["audit_gcs"] = f"gs://{HUB}/{dest}"
        path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"ok": True, "audit": str(path), "counts": audit["counts"]}, indent=2))


if __name__ == "__main__":
    main()
