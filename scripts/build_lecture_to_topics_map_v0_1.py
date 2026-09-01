#!/usr/bin/env python3
"""Build a lecture-centric reverse map: lecture → topics → segments/transcripts.

Complements the topic→clips Lecture Video OncoTree. Intended for sharing with
education leadership in multiple formats (HTML UI, JSON, CSV).

Input:
  lecture_deck_packages_vector_docstore_v0_1.jsonl

Outputs (under frontend/lecture_to_topics_map_v0_1/):
  data/lecture_to_topics_index_v0_1.json
  data/exports/lectures_summary_v0_1.csv
  data/exports/lecture_topic_segments_v0_1.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "frontend" / "lecture_to_topics_map_v0_1"
DEFAULT_INDEX = OUT_DIR / "data" / "lecture_to_topics_index_v0_1.json"
DEFAULT_EXPORTS = OUT_DIR / "data" / "exports"
SCHEMA = "lecture_to_topics_index.v0_1"
EXCERPT_CHARS = 420


def _pretty(text: str | None) -> str:
    t = (text or "").replace("_", " ").strip()
    return re.sub(r"\s+", " ", t) or "(untitled)"


def _fmt_time(sec: float) -> str:
    s = max(0, int(round(sec)))
    h, rem = divmod(s, 3600)
    m, sec_i = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec_i:02d}"
    return f"{m}:{sec_i:02d}"


def _gs_to_https(uri: str | None) -> str | None:
    if not uri:
        return None
    if uri.startswith("gs://"):
        return "https://storage.googleapis.com/" + uri[len("gs://") :]
    return uri


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("video_id"):
                continue
            if not (row.get("primary_tag") or "").strip():
                continue
            if not (row.get("video_time_url") or row.get("video_url")):
                continue
            rows.append(row)
    return rows


def segment_from_row(row: dict) -> dict:
    start = float(row.get("start_sec") or 0)
    end = float(row.get("end_sec") or start)
    transcript = (row.get("transcript_text") or "").strip()
    if not transcript:
        # Prefer pure transcript; fall back to truncated embed text without meta prefix
        raw = (row.get("text") or "").strip()
        transcript = raw
    return {
        "chunk_id": row.get("chunk_id") or row.get("deck_chunk_id"),
        "start_sec": round(start, 2),
        "end_sec": round(end, 2),
        "duration_sec": round(float(row.get("duration_sec") or max(0.0, end - start)), 2),
        "start_label": _fmt_time(start),
        "end_label": _fmt_time(end),
        "entity_name": row.get("entity_name"),
        "primary_tag": row.get("primary_tag"),
        "tag_status": row.get("tag_status"),
        "tag_score": row.get("tag_score"),
        "video_time_url": row.get("video_time_url"),
        "transcript": transcript,
        "excerpt": transcript[:EXCERPT_CHARS],
    }


def build_lectures(rows: list[dict]) -> tuple[list[dict], dict]:
    by_video: dict[str, dict] = {}
    for row in rows:
        vid = row["video_id"]
        lec = by_video.get(vid)
        if lec is None:
            lec = {
                "video_id": vid,
                "title": row.get("title") or _pretty(vid),
                "package_id": row.get("package_id"),
                "root": row.get("root"),
                "video_url": row.get("video_url") or _gs_to_https(row.get("raw_source_gcs_uri")),
                "raw_source_gcs_uri": row.get("raw_source_gcs_uri"),
                "segment_count": 0,
                "topic_count": 0,
                "topics": {},  # tag -> topic node
            }
            by_video[vid] = lec
        tag = (row.get("primary_tag") or "").strip()
        topic = lec["topics"].get(tag)
        if topic is None:
            parts = [p for p in tag.split("::") if p]
            topic = {
                "primary_tag": tag,
                "label": _pretty(parts[-1]) if parts else tag,
                "root": parts[0] if parts else row.get("root"),
                "path_labels": [_pretty(p) for p in parts],
                "segment_count": 0,
                "segments": [],
            }
            lec["topics"][tag] = topic
        topic["segments"].append(segment_from_row(row))

    lectures: list[dict] = []
    roots: set[str] = set()
    total_segments = 0
    total_topic_links = 0
    for lec in by_video.values():
        topics = list(lec["topics"].values())
        for t in topics:
            t["segments"].sort(key=lambda s: (s["start_sec"], s["end_sec"]))
            t["segment_count"] = len(t["segments"])
            total_segments += t["segment_count"]
            total_topic_links += 1
            if t.get("root"):
                roots.add(t["root"])
        topics.sort(key=lambda t: (t.get("root") or "", t["label"].lower()))
        lec["topics"] = topics
        lec["topic_count"] = len(topics)
        lec["segment_count"] = sum(t["segment_count"] for t in topics)
        lectures.append(lec)

    lectures.sort(key=lambda L: (L.get("root") or "", L["title"].lower()))
    counts = {
        "lectures": len(lectures),
        "segments": total_segments,
        "topic_links": total_topic_links,
        "unique_roots": len(roots),
        "unique_topics": len({t["primary_tag"] for L in lectures for t in L["topics"]}),
    }
    return lectures, counts


def write_csvs(lectures: list[dict], exports_dir: Path) -> dict[str, str]:
    exports_dir.mkdir(parents=True, exist_ok=True)
    summary_path = exports_dir / "lectures_summary_v0_1.csv"
    segments_path = exports_dir / "lecture_topic_segments_v0_1.csv"

    with summary_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "video_id",
                "title",
                "root",
                "package_id",
                "topic_count",
                "segment_count",
                "video_url",
                "topic_tags",
            ],
        )
        w.writeheader()
        for lec in lectures:
            w.writerow(
                {
                    "video_id": lec["video_id"],
                    "title": lec["title"],
                    "root": lec.get("root") or "",
                    "package_id": lec.get("package_id") or "",
                    "topic_count": lec["topic_count"],
                    "segment_count": lec["segment_count"],
                    "video_url": lec.get("video_url") or "",
                    "topic_tags": " | ".join(t["primary_tag"] for t in lec["topics"]),
                }
            )

    with segments_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "video_id",
                "lecture_title",
                "primary_tag",
                "topic_label",
                "entity_name",
                "start_sec",
                "end_sec",
                "start_label",
                "end_label",
                "duration_sec",
                "video_time_url",
                "tag_status",
                "tag_score",
                "excerpt",
            ],
        )
        w.writeheader()
        for lec in lectures:
            for topic in lec["topics"]:
                for seg in topic["segments"]:
                    w.writerow(
                        {
                            "video_id": lec["video_id"],
                            "lecture_title": lec["title"],
                            "primary_tag": topic["primary_tag"],
                            "topic_label": topic["label"],
                            "entity_name": seg.get("entity_name") or "",
                            "start_sec": seg["start_sec"],
                            "end_sec": seg["end_sec"],
                            "start_label": seg["start_label"],
                            "end_label": seg["end_label"],
                            "duration_sec": seg["duration_sec"],
                            "video_time_url": seg.get("video_time_url") or "",
                            "tag_status": seg.get("tag_status") or "",
                            "tag_score": seg.get("tag_score") if seg.get("tag_score") is not None else "",
                            "excerpt": (seg.get("excerpt") or "").replace("\n", " "),
                        }
                    )

    return {
        "lectures_summary_csv": str(summary_path.relative_to(OUT_DIR)),
        "lecture_topic_segments_csv": str(segments_path.relative_to(OUT_DIR)),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docstore", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=DEFAULT_INDEX)
    ap.add_argument("--exports-dir", type=Path, default=DEFAULT_EXPORTS)
    args = ap.parse_args()

    rows = load_rows(args.docstore)
    lectures, counts = build_lectures(rows)
    export_paths = write_csvs(lectures, args.exports_dir)

    payload = {
        "schema_version": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": "Pathology Hub — Lecture → topics map",
        "subtitle": (
            "Reverse content map: pick a lecture to see its tagged topics and "
            "timestamped transcript segments. Companion to the topic→clips OncoTree."
        ),
        "audience": "education_leadership",
        "share_formats": [
            "Interactive HTML (this package)",
            "JSON index (data/lecture_to_topics_index_v0_1.json)",
            "CSV lecture summary (data/exports/lectures_summary_v0_1.csv)",
            "CSV segment inventory (data/exports/lecture_topic_segments_v0_1.csv)",
        ],
        "source": {
            "docstore": str(args.docstore),
            "canonical_docstore_gcs": (
                "gs://pathology_hub/03_indexes/lectures/vector_deck_packages_v0_1/"
                "lecture_deck_packages_vector_docstore_v0_1.jsonl"
            ),
            "companion_topic_oncotree": "frontend/lecture_video_oncotree_v0_1/",
        },
        "exports": export_paths,
        "counts": counts,
        "known_limitations": [
            "Only segments with a primary_tag and video URL are included.",
            "Tags come from semantic-gated deck packaging — not every spoken mention is tagged.",
            "Transcript excerpts are segment-level, not full lecture transcripts.",
            "Companion topic-first browse: frontend/lecture_video_oncotree_v0_1/.",
            "Not claimed as deployed to a public custom domain by this package.",
        ],
        "lectures": lectures,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), "counts": counts, "exports": export_paths}, indent=2))


if __name__ == "__main__":
    main()
