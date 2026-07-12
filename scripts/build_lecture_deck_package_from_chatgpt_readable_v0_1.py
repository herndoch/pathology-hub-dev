#!/usr/bin/env python3
"""Convert a ChatGPT-readable lecture package into a Pathology Hub deck sidecar.

PoC input shape (Heme SH Aggressive B-Cell package):
  READ_ME_FIRST.txt
  lecture_index.json      # video_file, duration_seconds, frames[]
  transcript.txt
  transcript_segments.json  # {language, segments:[{id,start,end,text}]}
  frames/*.jpg
  lecture_review.html

Output (sidecar only — does not overwrite normalized lecture JSONL):
  manifest.json
  segments.jsonl
  frames.jsonl
  audit.json

Does NOT rebuild FAISS / claim API exposure. Join to raw MP4 is recorded when
a matching gs://pathology-hub-0/source_videos URI is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote


SCHEMA_VERSION = "lecture_deck_package.v0_1"
PUBLIC_VIDEO_BASE = "https://storage.googleapis.com/pathology-hub-0/"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def gcs_to_https(gcs_uri: str) -> str:
    if not gcs_uri.startswith("gs://"):
        return gcs_uri
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


ASSET_LIBRARY_PREFIX = "_asset_library/lectures/"


def legacy_slide_asset_paths(lecture_stem: str, frame_index: Any) -> dict[str, str]:
    """Match pathology-hub-0 lecture slide layout (BST / canonical Heme_SH_* style)."""
    try:
        idx = int(frame_index)
    except (TypeError, ValueError):
        idx = 0
    rel = f"{lecture_stem}/{lecture_stem}_slide_{idx:04d}.jpg"
    gcs = f"gs://pathology-hub-0/{ASSET_LIBRARY_PREFIX}{rel}"
    return {
        "image_path": rel,
        "asset_gcs_uri": gcs,
        "image_url": gcs_to_https(gcs),
    }


def load_chatgpt_package(src: Path) -> dict[str, Any]:
    index_path = src / "lecture_index.json"
    segs_path = src / "transcript_segments.json"
    readme = src / "READ_ME_FIRST.txt"
    if not index_path.is_file() or not segs_path.is_file():
        raise FileNotFoundError(
            f"Expected lecture_index.json + transcript_segments.json under {src}"
        )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    segs_doc = json.loads(segs_path.read_text(encoding="utf-8"))
    if not isinstance(index, dict) or "frames" not in index:
        raise ValueError("lecture_index.json missing frames[]")
    if not isinstance(segs_doc, dict) or not isinstance(segs_doc.get("segments"), list):
        raise ValueError("transcript_segments.json missing segments[]")
    return {
        "index": index,
        "segments_doc": segs_doc,
        "readme_text": readme.read_text(encoding="utf-8") if readme.is_file() else "",
        "transcript_path": src / "transcript.txt",
        "index_path": index_path,
        "segs_path": segs_path,
    }


def build_package(
    src: Path,
    out_dir: Path,
    *,
    package_id: Optional[str] = None,
    root: str = "Heme",
    raw_source_gcs_uri: Optional[str] = None,
    title: Optional[str] = None,
) -> dict[str, Any]:
    loaded = load_chatgpt_package(src)
    index = loaded["index"]
    segs = loaded["segments_doc"]["segments"]
    frames = index.get("frames") or []

    video_file = index.get("video_file") or "unknown.mp4"
    stem = Path(str(video_file)).stem
    lecture_stem = stem
    pkg_id = package_id or f"{slugify(stem)}_v0_1"
    lecture_title = title or stem.replace("_", " ")

    video_url = gcs_to_https(raw_source_gcs_uri) if raw_source_gcs_uri else None
    join_basis = "filename_match_source_videos" if raw_source_gcs_uri else "no_match"

    out_dir.mkdir(parents=True, exist_ok=True)

    segment_rows: list[dict[str, Any]] = []
    for seg in segs:
        start = seg.get("start")
        end = seg.get("end")
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        row = {
            "schema_version": "lecture_deck_segment.v0_1",
            "package_id": pkg_id,
            "segment_id": f"{pkg_id}::seg_{int(seg.get('id', len(segment_rows))):05d}",
            "start_sec": start,
            "end_sec": end,
            "text": text,
            "language": loaded["segments_doc"].get("language") or "en",
            "video_id": pkg_id,
            "video_url": video_url,
            "video_time_url": make_video_time_url(video_url, start, end),
            "raw_source_gcs_uri": raw_source_gcs_uri,
            "raw_source_join_basis": join_basis,
            "primary_tag": None,
            "tag_status": "untagged_poc",
            "root": root,
        }
        segment_rows.append(row)

    frame_rows: list[dict[str, Any]] = []
    for fr in frames:
        if not isinstance(fr, dict):
            continue
        t = fr.get("time")
        frame_rows.append(
            {
                "schema_version": "lecture_deck_frame.v0_1",
                "package_id": pkg_id,
                "frame_index": fr.get("index"),
                "start_sec": t,
                "timestamp": fr.get("timestamp"),
                "change_score": fr.get("change_score"),
                "file": fr.get("file"),
                "transcript_context": fr.get("transcript_context"),
                **legacy_slide_asset_paths(lecture_stem, fr.get("index")),
                "video_id": pkg_id,
                "video_url": video_url,
                "video_time_url": make_video_time_url(video_url, t, None),
                "raw_source_gcs_uri": raw_source_gcs_uri,
                "raw_source_join_basis": join_basis,
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_id": pkg_id,
        "title": lecture_title,
        "root": root,
        "source_format": "chatgpt_readable_package_v0",
        "video_file_declared": video_file,
        "duration_seconds": index.get("duration_seconds"),
        "video_id": pkg_id,
        "raw_source_gcs_uri": raw_source_gcs_uri,
        "video_url": video_url,
        "raw_source_join_basis": join_basis,
        "counts": {
            "segments": len(segment_rows),
            "frames": len(frame_rows),
            "segments_with_video_time_url": sum(1 for r in segment_rows if r.get("video_time_url")),
            "frames_with_video_time_url": sum(1 for r in frame_rows if r.get("video_time_url")),
        },
        "input_files": {
            "lecture_index": "lecture_index.json",
            "transcript_segments": "transcript_segments.json",
            "transcript": "transcript.txt",
            "readme": "READ_ME_FIRST.txt",
        },
        "created_at_utc": _utc_now(),
        "known_limitations": [
            "PoC: primary_tag left null (untagged_poc) — tagging is a separate step.",
            "Does not rebuild lecture FAISS/docstore or claim API exposure.",
            "ChatGPT-readable package format differs from _content_library slide JSON.",
            "Frames are change-detected screenshots; durable bytes target pathology-hub-0 _asset_library/lectures/<canonical_stem>/ (legacy slide layout).",
        ],
    }

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with (out_dir / "segments.jsonl").open("w", encoding="utf-8") as f:
        for row in segment_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out_dir / "frames.jsonl").open("w", encoding="utf-8") as f:
        for row in frame_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Copy package inventory pointers (not all JPG bytes) into audit
    zip_candidates = list(src.glob("*.zip")) + list(src.parent.glob("*chatgpt_readable_package.zip"))
    source_zip_sha = None
    source_zip_name = None
    for z in zip_candidates:
        if z.is_file() and "Aggressive_B_Cell" in z.name:
            source_zip_name = z.name
            source_zip_sha = _sha256_file(z)
            break

    audit = {
        "schema_version": "lecture_deck_package_build_audit.v0_1",
        "created_at_utc": _utc_now(),
        "package_id": pkg_id,
        "input_paths": [
            str(loaded["index_path"]),
            str(loaded["segs_path"]),
            str(loaded["transcript_path"]),
            raw_source_gcs_uri,
            "gs://pathology_hub/Heme_SH_Aggressive_B_Cell_chatgpt_readable_package.zip",
        ],
        "output_paths": [
            str(out_dir / "manifest.json"),
            str(out_dir / "segments.jsonl"),
            str(out_dir / "frames.jsonl"),
            str(out_dir / "audit.json"),
        ],
        "counts": manifest["counts"],
        "source_zip": {"name": source_zip_name, "sha256": source_zip_sha},
        "join": {
            "raw_source_gcs_uri": raw_source_gcs_uri,
            "video_url": video_url,
            "raw_source_join_basis": join_basis,
        },
        "format_notes": {
            "chatgpt_readable": {
                "segments": "whisper-style {id,start,end,text} with real seconds",
                "frames": "change-detected screenshots + transcript_context",
            },
            "legacy_content_library": {
                "shape": "list of slide-aligned {segment_id,start_time,end_time,image_path,cleaned_transcript,title}",
                "example": "gs://pathology-hub-0/_content_library/lectures/Other_Heme_Lecture_aggressive b cell lymphomas/",
            },
        },
        "known_limitations": manifest["known_limitations"]
        + [
            "Not vectorized; not written into STRICT_CYTO_v9 docstore.",
            "Not claiming Chat MVP Videos strip will play until a vector/API rebuild consumes this sidecar.",
        ],
        "next_steps": [
            "Human/AI tag primary_tag on segments (Heme aggressive B-cell entities).",
            "Optional: upload frames/ to a deck_packages asset prefix (sidecars only).",
            "After more packages: rebuild lecture vector index from deck sidecars with non-null video_time_url.",
        ],
    }
    (out_dir / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return {"manifest": manifest, "audit": audit, "out_dir": str(out_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, required=True, help="Extracted chatgpt_readable package dir")
    parser.add_argument("--out", type=Path, required=True, help="Output deck package directory")
    parser.add_argument("--package-id", default=None)
    parser.add_argument("--root", default="Heme")
    parser.add_argument(
        "--raw-source-gcs-uri",
        default=None,
        help="gs://pathology-hub-0/source_videos/....mp4",
    )
    parser.add_argument("--title", default=None)
    args = parser.parse_args()
    result = build_package(
        args.src,
        args.out,
        package_id=args.package_id,
        root=args.root,
        raw_source_gcs_uri=args.raw_source_gcs_uri,
        title=args.title,
    )
    print(json.dumps({"ok": True, "package_id": result["manifest"]["package_id"], "counts": result["manifest"]["counts"]}, indent=2))


if __name__ == "__main__":
    main()
