#!/usr/bin/env python3
"""Build a lecture-centric reverse map: lecture → topics → segments/transcripts.

Complements the topic→clips Lecture Video OncoTree. Intended for sharing with
education leadership in multiple formats (HTML UI, JSON, CSV).

IMPORTANT: The source docstore is semantic_gated_v0_2 — that gate still admits
off-target / ambiguous topic hits. This builder labels confidence tiers and
defaults leadership exports to high-confidence only.

Input:
  lecture_deck_packages_vector_docstore_v0_1.jsonl

Outputs (under frontend/lecture_to_topics_map_v0_1/):
  data/lecture_to_topics_index_v0_1.json
  data/exports/lectures_summary_high_confidence_v0_1.csv
  data/exports/lecture_topic_segments_high_confidence_v0_1.csv
  data/exports/lecture_topic_segments_all_gated_v0_1.csv  (includes uncertain)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "frontend" / "lecture_to_topics_map_v0_1"
DEFAULT_INDEX = OUT_DIR / "data" / "lecture_to_topics_index_v0_1.json"
DEFAULT_EXPORTS = OUT_DIR / "data" / "exports"
SCHEMA = "lecture_to_topics_index.v0_1"
EXCERPT_CHARS = 420

# Leadership-facing defaults (stricter than semantic_gated admission).
HIGH_MIN_SCORE = 0.65
HIGH_MIN_MARGIN = 0.05
MED_MIN_SCORE = 0.60
MED_MIN_MARGIN = 0.03


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


def confidence_tier(score: float | None, margin: float | None) -> str:
    s = float(score) if score is not None else 0.0
    m = float(margin) if margin is not None else 0.0
    if s >= HIGH_MIN_SCORE and m >= HIGH_MIN_MARGIN:
        return "high"
    if s >= MED_MIN_SCORE and m >= MED_MIN_MARGIN:
        return "medium"
    return "low"


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
        transcript = (row.get("text") or "").strip()
    score = row.get("tag_score")
    margin = row.get("tag_margin")
    tier = confidence_tier(score, margin)
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
        "tag_score": score,
        "tag_margin": margin,
        "tag_runner_up": row.get("tag_runner_up"),
        "confidence": tier,
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
                "high_confidence_segment_count": 0,
                "topics": {},
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
                "high_confidence_segment_count": 0,
                "segments": [],
            }
            lec["topics"][tag] = topic
        topic["segments"].append(segment_from_row(row))

    lectures: list[dict] = []
    roots: set[str] = set()
    total_segments = 0
    total_topic_links = 0
    tier_counts = {"high": 0, "medium": 0, "low": 0}
    for lec in by_video.values():
        topics = list(lec["topics"].values())
        for t in topics:
            t["segments"].sort(key=lambda s: (s["start_sec"], s["end_sec"]))
            t["segment_count"] = len(t["segments"])
            t["high_confidence_segment_count"] = sum(1 for s in t["segments"] if s["confidence"] == "high")
            total_segments += t["segment_count"]
            total_topic_links += 1
            for s in t["segments"]:
                tier_counts[s["confidence"]] = tier_counts.get(s["confidence"], 0) + 1
            if t.get("root"):
                roots.add(t["root"])
        topics.sort(key=lambda t: (t.get("root") or "", t["label"].lower()))
        lec["topics"] = topics
        lec["topic_count"] = len(topics)
        lec["segment_count"] = sum(t["segment_count"] for t in topics)
        lec["high_confidence_segment_count"] = sum(t["high_confidence_segment_count"] for t in topics)
        lectures.append(lec)

    lectures.sort(key=lambda L: (L.get("root") or "", L["title"].lower()))
    counts = {
        "lectures": len(lectures),
        "segments": total_segments,
        "topic_links": total_topic_links,
        "unique_roots": len(roots),
        "unique_topics": len({t["primary_tag"] for L in lectures for t in L["topics"]}),
        "segments_high_confidence": tier_counts["high"],
        "segments_medium_confidence": tier_counts["medium"],
        "segments_low_confidence": tier_counts["low"],
        "high_confidence_rule": {
            "min_tag_score": HIGH_MIN_SCORE,
            "min_tag_margin": HIGH_MIN_MARGIN,
        },
    }
    return lectures, counts


def _write_segments_csv(path: Path, lectures: list[dict], *, confidence_allow: set[str] | None) -> int:
    n = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "video_id",
                "lecture_title",
                "primary_tag",
                "topic_label",
                "entity_name",
                "confidence",
                "tag_score",
                "tag_margin",
                "tag_runner_up",
                "start_sec",
                "end_sec",
                "start_label",
                "end_label",
                "duration_sec",
                "video_time_url",
                "tag_status",
                "excerpt",
            ],
        )
        w.writeheader()
        for lec in lectures:
            for topic in lec["topics"]:
                for seg in topic["segments"]:
                    if confidence_allow is not None and seg["confidence"] not in confidence_allow:
                        continue
                    n += 1
                    w.writerow(
                        {
                            "video_id": lec["video_id"],
                            "lecture_title": lec["title"],
                            "primary_tag": topic["primary_tag"],
                            "topic_label": topic["label"],
                            "entity_name": seg.get("entity_name") or "",
                            "confidence": seg.get("confidence") or "",
                            "tag_score": seg.get("tag_score") if seg.get("tag_score") is not None else "",
                            "tag_margin": seg.get("tag_margin") if seg.get("tag_margin") is not None else "",
                            "tag_runner_up": seg.get("tag_runner_up") or "",
                            "start_sec": seg["start_sec"],
                            "end_sec": seg["end_sec"],
                            "start_label": seg["start_label"],
                            "end_label": seg["end_label"],
                            "duration_sec": seg["duration_sec"],
                            "video_time_url": seg.get("video_time_url") or "",
                            "tag_status": seg.get("tag_status") or "",
                            "excerpt": (seg.get("excerpt") or "").replace("\n", " "),
                        }
                    )
    return n


def write_csvs(lectures: list[dict], exports_dir: Path) -> dict[str, str]:
    exports_dir.mkdir(parents=True, exist_ok=True)
    summary_path = exports_dir / "lectures_summary_high_confidence_v0_1.csv"
    high_path = exports_dir / "lecture_topic_segments_high_confidence_v0_1.csv"
    all_path = exports_dir / "lecture_topic_segments_all_gated_v0_1.csv"

    with summary_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "video_id",
                "title",
                "root",
                "package_id",
                "high_confidence_segment_count",
                "all_gated_segment_count",
                "topic_count",
                "video_url",
                "high_confidence_topic_tags",
            ],
        )
        w.writeheader()
        for lec in lectures:
            high_tags = [
                t["primary_tag"]
                for t in lec["topics"]
                if any(s["confidence"] == "high" for s in t["segments"])
            ]
            w.writerow(
                {
                    "video_id": lec["video_id"],
                    "title": lec["title"],
                    "root": lec.get("root") or "",
                    "package_id": lec.get("package_id") or "",
                    "high_confidence_segment_count": lec["high_confidence_segment_count"],
                    "all_gated_segment_count": lec["segment_count"],
                    "topic_count": lec["topic_count"],
                    "video_url": lec.get("video_url") or "",
                    "high_confidence_topic_tags": " | ".join(high_tags),
                }
            )

    _write_segments_csv(high_path, lectures, confidence_allow={"high"})
    _write_segments_csv(all_path, lectures, confidence_allow=None)

    return {
        "lectures_summary_high_confidence_csv": str(summary_path.relative_to(OUT_DIR)),
        "lecture_topic_segments_high_confidence_csv": str(high_path.relative_to(OUT_DIR)),
        "lecture_topic_segments_all_gated_csv": str(all_path.relative_to(OUT_DIR)),
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
            "Reverse content map: pick a lecture to see tagged topics and "
            "timestamped transcript segments. Default view is high-confidence only — "
            "semantic_gated tags can still be off-target."
        ),
        "audience": "education_leadership",
        "default_confidence_filter": "high",
        "share_formats": [
            "Interactive HTML (high-confidence default; toggle for all gated)",
            "JSON index (includes confidence tiers on every segment)",
            "CSV high-confidence summary + segments (preferred for leadership)",
            "CSV all gated segments (includes uncertain / possible off-target hits)",
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
            "Source tags are automated semantic_gated_v0_2 — not human-reviewed.",
            "Off-target topic hits exist in the full gated set (low score/margin or wrong entity).",
            f"Leadership default keeps confidence=high only (score≥{HIGH_MIN_SCORE}, margin≥{HIGH_MIN_MARGIN}).",
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
