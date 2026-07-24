#!/usr/bin/env python3
"""Build a compact PathOutlines deep-content index for topic_page enrichment (v0_1).

Root-cause context (see audit): the live /evidence/search backend caps PathOutlines
excerpts at ~4000 chars from the start of each page and serves an older, shallow
ingestion. A far richer normalized crawl (~30 chunks + ~11 figures per topic,
section-typed: epidemiology, microscopic, ihc_special_stains, molecular,
differential_diagnosis, ...) was staged to GCS in June 2026 but has
indexed_searchable=false / vectorized=false / api_exposed=false for 100% of its
4,489 topics — i.e. it was never wired into the live backend.

This script reads that staged/normalized data (read-only) and writes a compact
JSON keyed by page_url with full section-level text + real figure URLs, so the
Chat MVP topic_page pipeline can enrich (not replace) live evidence for
PathOutlines pages specifically, without touching backend/vector infrastructure.

Source (staged, unindexed):
  gs://pathology-hub-0/_pathout_raw/allsite_console_crawl_v0_1/zips/
    pathout_allsite_complete_normalized_v0_1 (1).zip
    -> normalized/pathout_topics.jsonl
    -> normalized/pathout_chunks.jsonl
    -> normalized/pathout_figures.jsonl

Output (sidecar, enriched — does not overwrite any original normalized record):
  outputs/chat_mvp_topic_prepop_v0_1/pathout_deep_index_v0_1.json
  outputs/chat_mvp_topic_prepop_v0_1/pathout_deep_index_audit_v0_1.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
DEFAULT_INDEX_PATH = OUTPUT_DIR / "pathout_deep_index_v0_1.json"
DEFAULT_AUDIT_PATH = OUTPUT_DIR / "pathout_deep_index_audit_v0_1.json"


def build_index(extract_dir: Path) -> tuple[dict, dict]:
    normalized = extract_dir / "normalized"
    topics_path = normalized / "pathout_topics.jsonl"
    chunks_path = normalized / "pathout_chunks.jsonl"
    figures_path = normalized / "pathout_figures.jsonl"

    topics: dict[str, dict] = {}
    with topics_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            topics[rec["topic_id"]] = rec

    chunks_by_topic: dict[str, list[dict]] = defaultdict(list)
    with chunks_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            text = (rec.get("chunk_text") or rec.get("raw_text") or "").strip()
            if not text:
                continue
            chunks_by_topic[rec["topic_id"]].append(
                {
                    "heading": rec.get("heading") or "",
                    "section_type": rec.get("section_type") or "topic_text",
                    "text": text,
                    "block_index": rec.get("block_index"),
                }
            )

    figures_by_topic: dict[str, list[dict]] = defaultdict(list)
    with figures_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            url = rec.get("image_url") or rec.get("available_via_url") or ""
            if not url:
                continue
            figures_by_topic[rec["topic_id"]].append(
                {
                    "image_url": url,
                    "caption": rec.get("caption_or_nearby_text") or rec.get("alt_text") or "",
                    "alt_text": rec.get("alt_text") or "",
                    "image_kind": rec.get("image_kind") or "",
                }
            )

    index: dict[str, dict] = {}
    n_with_chunks = 0
    n_with_figures = 0
    total_chunks = 0
    total_figures = 0
    for topic_id, topic in topics.items():
        page_url = topic.get("page_url") or ""
        if not page_url:
            continue
        topic_chunks = chunks_by_topic.get(topic_id, [])
        for c in topic_chunks:
            c["block_index"] = c["block_index"] if c["block_index"] is not None else 0
        topic_chunks.sort(key=lambda c: c["block_index"])
        topic_figures = figures_by_topic.get(topic_id, [])
        if not topic_chunks and not topic_figures:
            continue
        if topic_chunks:
            n_with_chunks += 1
        if topic_figures:
            n_with_figures += 1
        total_chunks += len(topic_chunks)
        total_figures += len(topic_figures)
        index[page_url] = {
            "topic_id": topic_id,
            "entity_name": topic.get("entity_name") or topic.get("title") or "",
            "page_url": page_url,
            "chunks": [{"heading": c["heading"], "section_type": c["section_type"], "text": c["text"]} for c in topic_chunks],
            "figures": topic_figures,
        }

    audit = {
        "schema_version": "pathout_deep_index_audit_v0_1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_paths": [
            "gs://pathology-hub-0/_pathout_raw/allsite_console_crawl_v0_1/zips/"
            "pathout_allsite_complete_normalized_v0_1 (1).zip",
        ],
        "output_paths": [str(DEFAULT_INDEX_PATH.relative_to(REPO_ROOT))],
        "counts": {
            "n_topics_total": len(topics),
            "n_topics_in_index": len(index),
            "n_topics_with_chunks": n_with_chunks,
            "n_topics_with_figures": n_with_figures,
            "total_chunks": total_chunks,
            "total_figures": total_figures,
        },
        "known_limitations": [
            "Source data has indexed_searchable=false, vectorized=false, api_exposed=false "
            "for 100% of topics as of this build — this index is a frontend-only, read-time "
            "enrichment for topic_page synthesis. It is NOT proof of live backend indexing, "
            "vectorization, or API exposure, and must not be represented as such.",
            "Enrichment matches by exact page_url returned from the live /evidence/search "
            "call; PathOutlines pages not surfaced by live search (e.g. root-narrowed out) "
            "are never looked up.",
            "Figures are PathOutlines-hosted thumbnail URLs (pathologyoutlines.com/thumb/*), "
            "not re-hosted; captions/alt_text quality varies by source page.",
        ],
    }
    return index, audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extract-dir",
        type=Path,
        required=True,
        help="Directory where the pathout_allsite_complete_normalized_v0_1 zip was extracted "
        "(must contain normalized/pathout_topics.jsonl etc.)",
    )
    parser.add_argument("--index-out", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT_PATH)
    args = parser.parse_args()

    index, audit = build_index(args.extract_dir)
    args.index_out.parent.mkdir(parents=True, exist_ok=True)
    args.index_out.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    args.audit_out.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.index_out} ({args.index_out.stat().st_size / 1e6:.1f} MB)")
    print(json.dumps(audit["counts"], indent=2))


if __name__ == "__main__":
    main()
