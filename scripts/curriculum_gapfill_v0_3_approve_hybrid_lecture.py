#!/usr/bin/env python3
"""Create conservative local hybrid-approved lecture sidecars for v0.3."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "curriculum_gapfill_v0_3"
APPROVAL_STATUS = "approved_hybrid_high_confidence_local"
APPROVED_BY_METHOD = "cross_source_hybrid_fts_abpath_gapfill_v0_3"
APPROVAL_SCOPE = "local_preview_only"
DEFAULT_INPUT = Path("outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_candidates_v0_3_HYBRID_RESCORED.jsonl")
DEFAULT_HYBRID_AUDIT = Path("outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_hybrid_audit_v0_3.json")
DEFAULT_OUTPUT_DIR = Path("outputs/curriculum_gapfill_v0_3")
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


def has_forbidden(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else str(value)
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


def forbidden_visible_tag_fields(row: dict[str, Any]) -> bool:
    fields = [
        row.get("abpath_tag"),
        row.get("original_existing_tag"),
        row.get("review_status"),
        row.get("hybrid_decision"),
    ]
    return any(has_forbidden(field) for field in fields if field)


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    seen: set[str] = set()
    preferred = [
        "abpath_tag",
        "root",
        "chunk_id",
        "source_id",
        "hybrid_decision",
        "hybrid_score",
        "confidence",
        "score",
        "vector_status",
        "hybrid_reason",
        "original_existing_tag",
        "text_excerpt",
        "rejection_reason",
    ]
    for field in preferred:
        seen.add(field)
        fieldnames.append(field)
    for row in rows:
        for field in row:
            if field not in seen:
                fieldnames.append(field)
                seen.add(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def split_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    approved: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    approved_seen: set[tuple[str, str]] = set()
    for row in rows:
        decision = str(row.get("hybrid_decision") or row.get("review_status") or "")
        key = (str(row.get("chunk_id") or ""), str(row.get("abpath_tag") or ""))
        if forbidden_visible_tag_fields(row):
            rejected_row = dict(row)
            rejected_row["rejection_reason"] = "forbidden_visible_tag_field"
            rejected.append(rejected_row)
            continue
        if decision == "approved_hybrid_high":
            if key in approved_seen:
                rejected_row = dict(row)
                rejected_row["rejection_reason"] = "duplicate_chunk_id_abpath_tag"
                rejected.append(rejected_row)
                continue
            approved_row = dict(row)
            approved_row["approval_status"] = APPROVAL_STATUS
            approved_row["approved_by_method"] = APPROVED_BY_METHOD
            approved_row["approval_scope"] = APPROVAL_SCOPE
            approved_row["ontology_source"] = "abpath"
            approved_row["content_source"] = "lectures"
            approved.append(approved_row)
            approved_seen.add(key)
        elif decision == "review_hybrid":
            review.append(dict(row))
        else:
            rejected_row = dict(row)
            rejected_row.setdefault("rejection_reason", decision or "not_approved_hybrid_high")
            rejected.append(rejected_row)
    approved.sort(key=lambda row: (str(row.get("root")), str(row.get("abpath_tag")), str(row.get("chunk_id"))))
    review.sort(key=lambda row: (str(row.get("root")), str(row.get("abpath_tag")), str(row.get("chunk_id"))))
    rejected.sort(key=lambda row: (str(row.get("root")), str(row.get("abpath_tag")), str(row.get("chunk_id"))))
    return approved, review, rejected


def write_readme(path: Path, counts: dict[str, Any]) -> None:
    text = f"""# Lecture Hybrid Gap Fill Approval v0.3

This directory contains conservative local-only approval outputs from cross-source hybrid lecture rescoring.

Approved rows are `approved_hybrid_high` only, deduplicated by `chunk_id + abpath_tag`, and labeled:
- `approval_status = approved_hybrid_high_confidence_local`
- `approved_by_method = cross_source_hybrid_fts_abpath_gapfill_v0_3`
- `approval_scope = local_preview_only`
- `ontology_source = abpath`
- `content_source = lectures`

Counts:
- approved rows: {counts["approved_rows"]}
- review rows: {counts["review_rows"]}
- rejected rows: {counts["rejected_rows"]}
- forbidden approved hits: {counts["approved_forbidden_hits"]}

This sidecar is not final, live, API-exposed, deployed, uploaded, or vector-indexed.
"""
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--hybrid-audit", type=Path, default=DEFAULT_HYBRID_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Missing input: {args.input}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = list(read_jsonl(args.input))
    approved, review, rejected = split_rows(rows)
    hybrid_audit = json.loads(args.hybrid_audit.read_text(encoding="utf-8")) if args.hybrid_audit.exists() else {}
    counts = {
        "input_rows": len(rows),
        "approved_rows": len(approved),
        "review_rows": len(review),
        "rejected_rows": len(rejected),
        "decision_counts": dict(Counter(str(row.get("hybrid_decision") or "") for row in rows)),
        "approved_root_counts": dict(Counter(str(row.get("root") or "") for row in approved).most_common(20)),
        "approved_distinct_tags": len({str(row.get("abpath_tag") or "") for row in approved}),
        "approved_distinct_chunks": len({str(row.get("chunk_id") or "") for row in approved}),
        "approved_forbidden_hits": sum(1 for row in approved if has_forbidden(row.get("abpath_tag"))),
    }
    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "phase_4_conservative_hybrid_lecture_approval",
        "approval_status": APPROVAL_STATUS,
        "approved_by_method": APPROVED_BY_METHOD,
        "approval_scope": APPROVAL_SCOPE,
        "ontology_source": "abpath",
        "content_source": "lectures",
        "inputs": {"hybrid_rescored_candidates": str(args.input), "hybrid_audit": str(args.hybrid_audit)},
        "outputs": {
            "approved_jsonl": str(args.output_dir / "lecture_abpath_gapfill_approved_v0_3_HYBRID_HIGHCONF.jsonl"),
            "review_csv": str(args.output_dir / "lecture_abpath_gapfill_review_hybrid_v0_3.csv"),
            "rejected_csv": str(args.output_dir / "lecture_abpath_gapfill_rejected_hybrid_v0_3.csv"),
            "audit_json": str(args.output_dir / "lecture_abpath_gapfill_hybrid_approval_audit_v0_3.json"),
            "readme": str(args.output_dir / "README_LECTURE_GAPFILL_HYBRID_APPROVAL_V0_3.md"),
        },
        "counts": counts,
        "vector_status": hybrid_audit.get("vector_status"),
        "known_limitations": [
            "ABPath is ontology provenance only, not content evidence.",
            "Cross-source hybrid support is lexical/exemplar-based; vectors were not used.",
            "Output is local preview approval only and is not live/API-exposed.",
        ],
    }
    write_jsonl(args.output_dir / "lecture_abpath_gapfill_approved_v0_3_HYBRID_HIGHCONF.jsonl", approved)
    write_csv(args.output_dir / "lecture_abpath_gapfill_review_hybrid_v0_3.csv", review)
    write_csv(args.output_dir / "lecture_abpath_gapfill_rejected_hybrid_v0_3.csv", rejected)
    (args.output_dir / "lecture_abpath_gapfill_hybrid_approval_audit_v0_3.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_readme(args.output_dir / "README_LECTURE_GAPFILL_HYBRID_APPROVAL_V0_3.md", counts)
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
