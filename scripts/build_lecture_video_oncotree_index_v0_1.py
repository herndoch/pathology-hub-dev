#!/usr/bin/env python3
"""Build a video-only OncoTree index from the lecture deck vector docstore.

Input (default):
  gs://pathology_hub/03_indexes/lectures/vector_deck_packages_v0_1/
    lecture_deck_packages_vector_docstore_v0_1.jsonl
  (or a local copy via --docstore)

Output:
  frontend/lecture_video_oncotree_v0_1/data/video_oncotree_index_v0_1.json

Only tags that have at least one timestamped lecture clip are included — this is
intentionally a video index, not the full Browse taxonomy.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO_ROOT
    / "frontend"
    / "lecture_video_oncotree_v0_1"
    / "data"
    / "video_oncotree_index_v0_1.json"
)
SCHEMA = "lecture_video_oncotree_index.v0_1"


def _pretty_label(part: str) -> str:
    text = (part or "").replace("_", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text or "(untitled)"


def _clip_from_row(row: dict) -> dict:
    start = float(row.get("start_sec") or 0)
    end = float(row.get("end_sec") or start)
    return {
        "chunk_id": row.get("chunk_id") or row.get("deck_chunk_id"),
        "package_id": row.get("package_id"),
        "title": row.get("title") or row.get("video_id") or "Lecture",
        "video_id": row.get("video_id"),
        "video_url": row.get("video_url"),
        "video_time_url": row.get("video_time_url"),
        "start_sec": round(start, 2),
        "end_sec": round(end, 2),
        "duration_sec": round(float(row.get("duration_sec") or max(0.0, end - start)), 2),
        "entity_name": row.get("entity_name"),
        "primary_tag": row.get("primary_tag"),
        "root": row.get("root"),
        "tag_status": row.get("tag_status"),
        "excerpt": (row.get("transcript_text") or row.get("text") or "")[:280],
    }


def _ensure_child(node: dict, part: str) -> dict:
    label = _pretty_label(part)
    for child in node["children"]:
        if child["id"] == part:
            return child
    child = {
        "id": part,
        "label": label,
        "path": f"{node['path']}::{part}" if node.get("path") else part,
        "clip_count": 0,
        "children": [],
        "clips": [],
        "kind": "branch",
    }
    node["children"].append(child)
    return child


def build_tree(rows: list[dict]) -> tuple[list[dict], dict]:
    root_nodes: dict[str, dict] = {}
    clips_by_tag: dict[str, list] = defaultdict(list)
    videos: set[str] = set()

    for row in rows:
        tag = (row.get("primary_tag") or "").strip()
        if not tag or not row.get("video_time_url"):
            continue
        clip = _clip_from_row(row)
        clips_by_tag[tag].append(clip)
        if clip.get("video_id"):
            videos.add(clip["video_id"])
        elif clip.get("video_url"):
            videos.add(clip["video_url"])

        parts = [p for p in tag.split("::") if p]
        if not parts:
            continue
        root_id = parts[0]
        if root_id not in root_nodes:
            root_nodes[root_id] = {
                "id": root_id,
                "label": _pretty_label(root_id),
                "path": root_id,
                "clip_count": 0,
                "children": [],
                "clips": [],
                "kind": "root",
            }
        node = root_nodes[root_id]
        for part in parts[1:]:
            node = _ensure_child(node, part)
        # Leaf = full tag node
        node["kind"] = "leaf"
        node["clips"].append(clip)

    def finalize(node: dict) -> int:
        total = len(node.get("clips") or [])
        for child in node["children"]:
            total += finalize(child)
        node["clip_count"] = total
        node["children"].sort(key=lambda c: c["label"].lower())
        # Keep leaf clips sorted by lecture then time
        node["clips"].sort(key=lambda c: (c.get("title") or "", c.get("start_sec") or 0))
        return total

    roots = sorted(root_nodes.values(), key=lambda r: r["label"].lower())
    for r in roots:
        finalize(r)

    counts = {
        "clips": sum(len(v) for v in clips_by_tag.values()),
        "videos": len(videos),
        "tagged_leaves": len(clips_by_tag),
        "roots": len(roots),
    }
    return roots, {
        "counts": counts,
        "clips_by_tag": {k: clips_by_tag[k] for k in sorted(clips_by_tag)},
    }


def load_docstore(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docstore",
        type=Path,
        required=True,
        help="Local path to lecture_deck_packages_vector_docstore_v0_1.jsonl",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    rows = load_docstore(args.docstore)
    roots, extra = build_tree(rows)
    payload = {
        "schema_version": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": "Pathology Hub — Lecture Video OncoTree",
        "subtitle": "Timestamped lecture clips indexed by taxonomy tag (video-only).",
        "source": {
            "docstore": str(args.docstore),
            "canonical_gcs": (
                "gs://pathology_hub/03_indexes/lectures/vector_deck_packages_v0_1/"
                "lecture_deck_packages_vector_docstore_v0_1.jsonl"
            ),
            "row_count_read": len(rows),
        },
        "counts": extra["counts"],
        "known_limitations": [
            "Only tags present on gated lecture chunks are shown (not the full Browse leaf set).",
            "Playback requires public HTTPS MP4 URLs (pathology-hub-0 source_videos).",
            "Tagging is automated (semantic_gated); not all clips are human-reviewed.",
            "Share as a local folder or static host; not deployed to chat.pathologynotebook.com by this script.",
        ],
        "roots": roots,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), "counts": extra["counts"]}, indent=2))


if __name__ == "__main__":
    main()
