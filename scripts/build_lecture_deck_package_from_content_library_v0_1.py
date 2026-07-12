#!/usr/bin/env python3
"""Convert legacy pathology-hub-0 content_library lecture JSON → deck sidecar.

Input (per lecture stem):
  gs://pathology-hub-0/_content_library/lectures/<stem>.json
  optional: .../<stem>/final_ENHANCED_data.json  (preferred when slide paths resolve)
  gs://pathology-hub-0/source_videos/<mp4>
  gs://pathology-hub-0/_asset_library/lectures/<stem>/<stem>_slide_NNNN.jpg

Output (sidecar only — does not overwrite normalized lecture JSONL):
  manifest.json, segments.jsonl, frames.jsonl, audit.json

Does NOT rebuild FAISS / claim API exposure.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from google.cloud.storage import Client


SCHEMA_VERSION = "lecture_deck_package.v0_1"
PUBLIC_VIDEO_BASE = "https://storage.googleapis.com/pathology-hub-0/"
CONTENT_PREFIX = "_content_library/lectures/"
ASSET_PREFIX = "_asset_library/lectures/"
VIDEO_PREFIX = "source_videos/"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gcs_to_https(gcs_uri: str) -> str:
    without = gcs_uri[len("gs://") :]
    bucket, _, key = without.partition("/")
    return f"https://storage.googleapis.com/{bucket}/{quote(key, safe='/')}"


def make_video_time_url(video_url: Optional[str], start: Any, end: Any) -> Optional[str]:
    if not video_url:
        return None
    try:
        s = float(start) if start is not None else None
    except (TypeError, ValueError):
        s = None
    if s is None:
        return None
    try:
        e = float(end) if end is not None else None
    except (TypeError, ValueError):
        e = None
    if e is not None:
        return f"{video_url}#t={s:g},{e:g}"
    return f"{video_url}#t={s:g}"


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_").lower()
    return s or "lecture"


def infer_root(stem: str) -> str:
    s = stem.lower()
    if s.startswith("breast"):
        return "Breast"
    if s.startswith("derm") or s.startswith("yt_skin") or s.startswith("other_skin"):
        return "Skin"
    if s.startswith("gi_") or s.startswith("yt_gi"):
        return "GI"
    if s.startswith("gu_"):
        return "GU"
    if s.startswith("gyn"):
        return "GYN"
    if s.startswith("hn_") or s.startswith("yt_hn"):
        return "HN"
    if s.startswith("bst") or s.startswith("yt_bst"):
        return "BST"
    if s.startswith("thoracic") or s.startswith("lung") or s.startswith("yt_lung"):
        return "Thorax_Mediastinum"
    if s.startswith("yt_cyto") or s.startswith("asc_cyto") or s.startswith("cyto"):
        return "Cytopathology"
    if s.startswith("heme") or s.startswith("other_heme"):
        return "Heme"
    return "Unknown"


def normalize_image_rel(image_path: Optional[str], stem: str) -> Optional[str]:
    if not image_path or not isinstance(image_path, str):
        return None
    p = image_path.strip().lstrip("/")
    if p.startswith("_asset_library/lectures/"):
        p = p[len("_asset_library/lectures/") :]
    if p.startswith("gs://"):
        # gs://pathology-hub-0/_asset_library/lectures/STEM/...
        marker = "/_asset_library/lectures/"
        if marker in p:
            p = p.split(marker, 1)[1]
    # Ensure stem/ prefix
    if "/" not in p:
        p = f"{stem}/{p}"
    return p


def load_records(client: Client, stem: str) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Prefer ENHANCED when present; fall back to top-level list JSON."""
    hub0 = client.bucket("pathology-hub-0")
    inputs: list[str] = []
    enhanced_uri = f"{CONTENT_PREFIX}{stem}/final_ENHANCED_data.json"
    top_uri = f"{CONTENT_PREFIX}{stem}.json"
    records: Optional[list] = None
    source = ""

    enh = hub0.blob(enhanced_uri)
    if enh.exists():
        inputs.append(f"gs://pathology-hub-0/{enhanced_uri}")
        data = json.loads(enh.download_as_text())
        if isinstance(data, list) and data:
            records = data
            source = "final_ENHANCED_data.json"

    top = hub0.blob(top_uri)
    if top.exists():
        inputs.append(f"gs://pathology-hub-0/{top_uri}")
        if records is None:
            data = json.loads(top.download_as_text())
            if isinstance(data, list) and data:
                records = data
                source = f"{stem}.json"

    if not records:
        raise FileNotFoundError(f"No content_library records for stem={stem}")
    return records, source, inputs


def resolve_video(client: Client, stem: str, mp4_override: Optional[str] = None) -> tuple[Optional[str], str, Optional[str]]:
    """Return (gcs_uri, join_basis, file_name)."""
    hub0 = client.bucket("pathology-hub-0")
    candidates: list[str] = []
    if mp4_override:
        candidates.append(mp4_override if mp4_override.endswith(".mp4") else f"{mp4_override}.mp4")
    candidates.append(f"{stem}.mp4")
    # Common Breast quirk: Epithelial Part 1_Chen
    if stem == "Breast_Lecture_Epithelial":
        candidates.insert(0, "Breast_Lecture_Epithelial Part 1_Chen.mp4")

    # Fuzzy: any source_videos blob starting with stem
    for b in hub0.list_blobs(prefix=f"{VIDEO_PREFIX}{stem}", max_results=20):
        name = b.name.split("/")[-1]
        if name.lower().endswith(".mp4") and name not in candidates:
            candidates.append(name)

    for name in candidates:
        blob = hub0.blob(f"{VIDEO_PREFIX}{name}")
        if blob.exists():
            uri = f"gs://pathology-hub-0/{VIDEO_PREFIX}{name}"
            return uri, "filename_match_source_videos", name
    return None, "canonical_name_pending_upload", candidates[0] if candidates else f"{stem}.mp4"


def asset_exists(client: Client, rel: str) -> bool:
    return client.bucket("pathology-hub-0").blob(f"{ASSET_PREFIX}{rel}").exists()


def build_package(
    stem: str,
    *,
    out_dir: Path,
    client: Optional[Client] = None,
    mp4_override: Optional[str] = None,
    package_id: Optional[str] = None,
    root: Optional[str] = None,
) -> dict[str, Any]:
    client = client or Client()
    records, source_name, input_paths = load_records(client, stem)
    video_uri, join_basis, video_file = resolve_video(client, stem, mp4_override)
    video_url = gcs_to_https(video_uri) if video_uri else None
    package_id = package_id or f"{slugify(stem)}_v0_1"
    root = root or infer_root(stem)
    out_dir.mkdir(parents=True, exist_ok=True)

    # duration from last end_time
    ends = []
    for r in records:
        try:
            ends.append(float(r.get("end_time")))
        except (TypeError, ValueError):
            pass
    duration_seconds = max(ends) if ends else None

    segments: list[dict[str, Any]] = []
    for i, r in enumerate(records):
        try:
            start = float(r.get("start_time") if r.get("start_time") is not None else r.get("start_sec") or 0.0)
            end = float(r.get("end_time") if r.get("end_time") is not None else r.get("end_sec") or start)
        except (TypeError, ValueError):
            continue
        text = (r.get("cleaned_transcript") or r.get("text") or "").strip()
        title = r.get("title")
        seg_id = r.get("segment_id")
        if seg_id is None:
            seg_id = i
        segment_id = f"{package_id}::seg_{int(seg_id):05d}"
        segments.append(
            {
                "schema_version": "lecture_deck_segment.v0_1",
                "package_id": package_id,
                "segment_id": segment_id,
                "start_sec": start,
                "end_sec": end,
                "text": text,
                "title": title if isinstance(title, str) else None,
                "language": "en",
                "video_id": package_id,
                "video_url": video_url,
                "video_time_url": make_video_time_url(video_url, start, end),
                "raw_source_gcs_uri": video_uri,
                "raw_source_join_basis": join_basis,
                "primary_tag": None,
                "tag_status": "untagged",
                "root": root,
                "indexable": False,
                "source_format": "content_library_slide_aligned",
                "legacy_segment_id": seg_id,
            }
        )

    # Frames: unique image paths in order of first appearance
    frames: list[dict[str, Any]] = []
    seen_imgs: set[str] = set()
    present = 0
    missing = 0
    for i, r in enumerate(records):
        rel = normalize_image_rel(r.get("image_path"), stem)
        if not rel or rel in seen_imgs:
            continue
        seen_imgs.add(rel)
        exists = asset_exists(client, rel)
        if exists:
            present += 1
        else:
            missing += 1
        m = re.search(r"_slide_(\d+)\.", rel)
        frame_index = int(m.group(1)) if m else len(frames)
        try:
            start = float(r.get("start_time") or 0.0)
        except (TypeError, ValueError):
            start = 0.0
        gcs = f"gs://pathology-hub-0/{ASSET_PREFIX}{rel}"
        frames.append(
            {
                "schema_version": "lecture_deck_frame.v0_1",
                "package_id": package_id,
                "frame_index": frame_index,
                "start_sec": start,
                "title": r.get("title"),
                "transcript_context": (r.get("cleaned_transcript") or "")[:400],
                "image_path": rel,
                "asset_gcs_uri": gcs,
                "image_url": gcs_to_https(gcs),
                "asset_object_present": exists,
                "video_id": package_id,
                "video_url": video_url,
                "video_time_url": make_video_time_url(video_url, start, None),
                "raw_source_gcs_uri": video_uri,
                "raw_source_join_basis": join_basis,
            }
        )

    if video_uri:
        input_paths.append(video_uri)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_id": package_id,
        "title": stem.replace("_", " "),
        "root": root,
        "source_format": "content_library_legacy_v0",
        "content_library_stem": stem,
        "content_library_source": source_name,
        "video_file_declared": video_file,
        "duration_seconds": duration_seconds,
        "video_id": package_id,
        "raw_source_gcs_uri": video_uri,
        "video_url": video_url,
        "raw_source_join_basis": join_basis,
        "counts": {
            "segments": len(segments),
            "frames": len(frames),
            "segments_with_video_time_url": sum(1 for s in segments if s.get("video_time_url")),
            "frames_with_video_time_url": sum(1 for f in frames if f.get("video_time_url")),
            "frames_asset_objects_present": present,
            "frames_asset_objects_missing": missing,
            "canonical_mp4_present": bool(video_uri),
        },
        "created_at_utc": utc_now(),
        "known_limitations": [
            "Converted from legacy slide-aligned content_library JSON (coarser than Whisper crumbs).",
            "Titles may be noisy or 'Error - Image Missing'; transcript text is cleaned_transcript.",
            "Sidecar only — not vectorized / not API-exposed until rebuild + audit.",
        ],
    }

    audit = {
        "schema_version": "lecture_deck_package_build_audit.v0_1",
        "created_at_utc": utc_now(),
        "package_id": package_id,
        "input_paths": input_paths,
        "output_paths": [
            str(out_dir / "manifest.json"),
            str(out_dir / "segments.jsonl"),
            str(out_dir / "frames.jsonl"),
            str(out_dir / "audit.json"),
        ],
        "counts": manifest["counts"],
        "join": {
            "raw_source_gcs_uri": video_uri,
            "video_url": video_url,
            "raw_source_join_basis": join_basis,
            "video_file": video_file,
        },
        "format_notes": {
            "content_library": {
                "preferred": "final_ENHANCED_data.json when present",
                "fallback": f"{stem}.json",
                "used": source_name,
            }
        },
        "known_limitations": manifest["known_limitations"],
    }

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with (out_dir / "segments.jsonl").open("w", encoding="utf-8") as f:
        for row in segments:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out_dir / "frames.jsonl").open("w", encoding="utf-8") as f:
        for row in frames:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out_dir / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    # empty indexables until gated pass
    (out_dir / "segments_indexable.jsonl").write_text("", encoding="utf-8")
    (out_dir / "chunks_indexable.jsonl").write_text("", encoding="utf-8")

    return {"ok": True, "package_id": package_id, "manifest": manifest, "audit": audit}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stem", required=True, help="Content library stem, e.g. Breast_Lecture_Invasive")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--mp4-name", default=None, help="Override source_videos filename")
    p.add_argument("--package-id", default=None)
    p.add_argument("--root", default=None)
    args = p.parse_args()
    result = build_package(
        args.stem,
        out_dir=args.out_dir,
        mp4_override=args.mp4_name,
        package_id=args.package_id,
        root=args.root,
    )
    print(json.dumps({"ok": True, "package_id": result["package_id"], "counts": result["manifest"]["counts"]}, indent=2))


if __name__ == "__main__":
    main()
