#!/usr/bin/env python3
"""Create source-balanced QA samples for Curriculum Gap Fill v0.3 review rows."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_GAPFILL_DIR = Path("outputs/curriculum_gapfill_v0_3")
DEFAULT_LECTURES = Path("data/curriculum_map_v0_2/lecture_timecoded_tagged_chunks_ROUTED_ONLY_STRICT_CYTO_v9.jsonl")
DEFAULT_TEXTBOOKS = Path("data/curriculum_map_v0_2/textbook_primary_tagged_chunks_v1.jsonl")
DEFAULT_OUTPUT_DIR = Path("06_audits/curriculum_gapfill/v0_3/qa_samples/source_balanced")
PRIORITY_ROOTS = ("Skin", "HN", "BST", "Breast", "GYN", "GU")
SOURCE_FAMILIES = ("lectures", "textbooks")
FORBIDDEN_PATTERNS = (
    "::Lectures::",
    "::Textbooks::",
    "::Error",
    "Slide_",
    "Page_",
    "Digital_Pathology_Slide",
    "Pathology_Slide",
    "rejected_generated",
)


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path} line {line_no}: {exc}") from exc


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def has_forbidden(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else str(value)
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


def clean_text(value: str, limit: int = 1800) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def load_source_text(path: Path, source_family: str, chunk_ids: set[str]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    if not chunk_ids:
        return lookup
    for row in read_jsonl(path):
        chunk_id = str(row.get("chunk_id") or "")
        if chunk_id not in chunk_ids:
            continue
        if source_family == "lectures":
            source_id = str(row.get("video_id") or row.get("raw_source_gcs_uri") or "")
            title = str(row.get("title") or "")
            prior_tag = str(row.get("primary_tag_governed") or row.get("primary_tag") or row.get("primary_tag_original_pre_governance_v10_4") or "")
            page_or_time = f"{row.get('start_sec', '')}-{row.get('end_sec', '')}".strip("-")
            text = " ".join(str(row.get(key) or "") for key in ("title", "summary", "transcript_text", "tag_basis"))
        else:
            source_id = str(row.get("source_id") or row.get("source_title") or row.get("raw_source_gcs_uri") or "")
            title = " | ".join(str(row.get(key) or "") for key in ("source_title", "chapter_title", "section_heading") if row.get(key))
            prior_tag = str(row.get("primary_tag_governed") or row.get("primary_tag") or row.get("primary_tag_original_pre_governance_v10_4") or "")
            page_or_time = str(row.get("page") or "")
            text = " ".join(str(row.get(key) or "") for key in ("source_title", "chapter_title", "section_heading", "text", "primary_tag_basis") if row.get(key))
        lookup[chunk_id] = {
            "source_id": source_id,
            "source_title": title,
            "page_or_time": page_or_time,
            "source_primary_tag": prior_tag,
            "source_text": clean_text(text),
            "raw_source_gcs_uri": str(row.get("raw_source_gcs_uri") or ""),
            "normalized_artifact_gcs_uri": str(row.get("normalized_artifact_gcs_uri") or ""),
        }
        if len(lookup) >= len(chunk_ids):
            break
    return lookup


def qa_label(row: dict[str, str]) -> tuple[str, str]:
    if has_forbidden(row.get("abpath_tag")) or has_forbidden(row.get("original_existing_tag")):
        return "reject", "forbidden/generated visible tag field"
    if row.get("generic_only_match", "").lower() == "true":
        return "reject", "generic-only match"
    if row.get("sibling_or_cross_root_conflict", "").lower() == "true":
        return "human-review", "sibling or cross-root conflict flag is present"
    if row.get("entity_phrase_hit", "").lower() == "true" and float(row.get("hybrid_score") or 0) >= 0.98:
        return "human-review", "high-evidence review row; candidate for manual promotion only"
    return "human-review", "review_hybrid row requires human adjudication"


def select_source_balanced(rows: list[dict[str, str]], per_root_source: int, per_tag: int) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    tag_counts = Counter((row.get("root", ""), row.get("source_family", ""), row.get("abpath_tag", "")) for row in rows)
    for row in rows:
        root = row.get("root", "")
        source_family = row.get("source_family", "")
        if root in PRIORITY_ROOTS and source_family in SOURCE_FAMILIES:
            grouped[(root, source_family)][row.get("abpath_tag", "")].append(row)

    selected: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for root in PRIORITY_ROOTS:
        for source_family in SOURCE_FAMILIES:
            root_source_selected = 0
            ranked_tags = Counter({tag: len(tag_rows) for tag, tag_rows in grouped.get((root, source_family), {}).items()})
            for tag, _ in ranked_tags.most_common():
                ranked_rows = sorted(
                    grouped[(root, source_family)][tag],
                    key=lambda row: (-float(row.get("hybrid_score") or 0), str(row.get("chunk_id"))),
                )
                for row in ranked_rows[:per_tag]:
                    key = (source_family, row.get("chunk_id", ""), row.get("abpath_tag", ""))
                    if key in seen:
                        continue
                    out = dict(row)
                    out["_root_source_tag_review_row_count"] = str(tag_counts[(root, source_family, tag)])
                    selected.append(out)
                    seen.add(key)
                    root_source_selected += 1
                    if root_source_selected >= per_root_source:
                        break
                if root_source_selected >= per_root_source:
                    break
    return selected


def build_output_rows(rows: list[dict[str, str]], lecture_text: dict[str, dict[str, str]], textbook_text: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        source_family = row.get("source_family", "")
        source = lecture_text.get(row.get("chunk_id", ""), {}) if source_family == "lectures" else textbook_text.get(row.get("chunk_id", ""), {})
        label, label_reason = qa_label(row)
        output.append(
            {
                "qa_recommendation": label,
                "qa_recommendation_reason": label_reason,
                "source_family": source_family,
                "source_id": source.get("source_id") or row.get("source_id", ""),
                "chunk_id": row.get("chunk_id", ""),
                "root": row.get("root", ""),
                "prior_or_source_tag": row.get("original_existing_tag", ""),
                "source_primary_tag": source.get("source_primary_tag", ""),
                "proposed_primary_tag": row.get("abpath_tag", ""),
                "hybrid_score": row.get("hybrid_score", ""),
                "hybrid_reason": row.get("hybrid_reason", ""),
                "decision_reason": row.get("hybrid_reason", ""),
                "hybrid_decision": row.get("hybrid_decision", ""),
                "confidence": row.get("confidence", ""),
                "score": row.get("score", ""),
                "entity_phrase_hit": row.get("entity_phrase_hit", ""),
                "root_agreement": row.get("root_agreement", ""),
                "generic_only_match": row.get("generic_only_match", ""),
                "sibling_or_cross_root_conflict": row.get("sibling_or_cross_root_conflict", ""),
                "who_phrase_hits": row.get("who_phrase_hits", ""),
                "pathout_phrase_hits": row.get("pathout_phrase_hits", ""),
                "textbook_phrase_hits": row.get("textbook_phrase_hits", ""),
                "lecture_phrase_hits": row.get("lecture_phrase_hits", ""),
                "negative_phrase_hits": row.get("negative_phrase_hits", ""),
                "matched_terms": row.get("matched_terms", ""),
                "matched_query": row.get("matched_query", ""),
                "text_excerpt": row.get("text_excerpt", ""),
                "source_text": source.get("source_text", ""),
                "source_title": source.get("source_title", ""),
                "page_or_time": source.get("page_or_time", ""),
                "root_source_tag_review_row_count": row.get("_root_source_tag_review_row_count", ""),
                "raw_source_gcs_uri": source.get("raw_source_gcs_uri", ""),
                "normalized_artifact_gcs_uri": source.get("normalized_artifact_gcs_uri", ""),
            }
        )
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "qa_recommendation",
        "qa_recommendation_reason",
        "source_family",
        "source_id",
        "chunk_id",
        "root",
        "prior_or_source_tag",
        "source_primary_tag",
        "proposed_primary_tag",
        "hybrid_score",
        "hybrid_reason",
        "decision_reason",
        "hybrid_decision",
        "confidence",
        "score",
        "entity_phrase_hit",
        "root_agreement",
        "generic_only_match",
        "sibling_or_cross_root_conflict",
        "who_phrase_hits",
        "pathout_phrase_hits",
        "textbook_phrase_hits",
        "lecture_phrase_hits",
        "negative_phrase_hits",
        "matched_terms",
        "matched_query",
        "text_excerpt",
        "source_text",
        "source_title",
        "page_or_time",
        "root_source_tag_review_row_count",
        "raw_source_gcs_uri",
        "normalized_artifact_gcs_uri",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_readme(path: Path, audit: dict[str, Any]) -> None:
    text = f"""# Source-Balanced Curriculum Gap Fill v0.3 QA Samples

This directory contains source-balanced QA samples from `review_hybrid` rows only.

Priority roots:
- {", ".join(PRIORITY_ROOTS)}

Sources:
- lectures
- textbooks

Rows sampled: {audit["sample_rows"]}

These files do not modify staged review rows, SQLite, API/live artifacts, or GCS objects.
"""
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gapfill-dir", type=Path, default=DEFAULT_GAPFILL_DIR)
    parser.add_argument("--lecture-chunks", type=Path, default=DEFAULT_LECTURES)
    parser.add_argument("--textbook-chunks", type=Path, default=DEFAULT_TEXTBOOKS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--per-root-source", type=int, default=20)
    parser.add_argument("--per-tag", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    lecture_review_path = args.gapfill_dir / "lecture_abpath_gapfill_review_FULL_v0_3.csv"
    textbook_review_path = args.gapfill_dir / "textbook_abpath_gapfill_review_FULL_v0_3.csv"
    review_rows = read_csv(lecture_review_path) + read_csv(textbook_review_path)
    selected = select_source_balanced(review_rows, args.per_root_source, args.per_tag)

    lecture_ids = {row.get("chunk_id", "") for row in selected if row.get("source_family") == "lectures"}
    textbook_ids = {row.get("chunk_id", "") for row in selected if row.get("source_family") == "textbooks"}
    lecture_text = load_source_text(args.lecture_chunks, "lectures", lecture_ids)
    textbook_text = load_source_text(args.textbook_chunks, "textbooks", textbook_ids)
    output_rows = build_output_rows(selected, lecture_text, textbook_text)

    sample_path = args.output_dir / "curriculum_gapfill_v0_3_review_qa_source_balanced_sample.csv"
    audit_path = args.output_dir / "curriculum_gapfill_v0_3_review_qa_source_balanced_audit.json"
    readme_path = args.output_dir / "README.md"
    write_csv(sample_path, output_rows)

    audit = {
        "schema_version": "curriculum_gapfill_v0_3_source_balanced_review_qa_sample",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "lecture_review": str(lecture_review_path),
            "textbook_review": str(textbook_review_path),
            "lecture_chunks": str(args.lecture_chunks),
            "textbook_chunks": str(args.textbook_chunks),
        },
        "outputs": {
            "sample_csv": str(sample_path),
            "audit_json": str(audit_path),
            "readme": str(readme_path),
        },
        "priority_roots": list(PRIORITY_ROOTS),
        "source_families": list(SOURCE_FAMILIES),
        "per_root_source_target": args.per_root_source,
        "per_tag_cap": args.per_tag,
        "review_rows_read": len(review_rows),
        "sample_rows": len(output_rows),
        "sample_root_counts": dict(Counter(row["root"] for row in output_rows).most_common()),
        "sample_source_counts": dict(Counter(row["source_family"] for row in output_rows).most_common()),
        "sample_root_source_counts": dict(Counter(f"{row['root']}::{row['source_family']}" for row in output_rows).most_common()),
        "qa_recommendation_counts": dict(Counter(row["qa_recommendation"] for row in output_rows).most_common()),
        "limitations": [
            "Samples are review_hybrid rows only and do not change approval status.",
            "Source text is truncated for reviewer ergonomics.",
            "A root/source pair may contain fewer rows than requested if insufficient review rows exist.",
        ],
    }
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_readme(readme_path, audit)
    print(json.dumps(audit, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
