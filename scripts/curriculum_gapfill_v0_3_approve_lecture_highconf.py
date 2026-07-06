#!/usr/bin/env python3
"""Approve conservative high-confidence lecture gap-fill candidates for v0.3.

Local sidecar only. This script does not mutate source chunks, indexes,
Curriculum Map v0.2 outputs, GCS objects, deployments, or GPT Builder state.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "curriculum_gapfill_v0_3"
APPROVAL_STATUS = "approved_high_confidence_local"
APPROVED_BY_METHOD = "strict_fts_abpath_gapfill_v0_3"
APPROVAL_SCOPE = "local_preview_only"

DEFAULT_CANDIDATES = Path("outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_candidates_v0_3.jsonl")
DEFAULT_PHASE1_AUDIT = Path("outputs/curriculum_gapfill_v0_3/lecture_gapfill_audit_v0_3.json")
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

CSV_FIELDS = [
    "schema_version",
    "source_family",
    "chunk_id",
    "source_id",
    "video_id",
    "abpath_tag",
    "root",
    "matched_query",
    "matched_terms",
    "score",
    "confidence",
    "method",
    "review_status",
    "text_excerpt",
    "original_existing_tag",
    "reason",
    "approval_status",
    "approved_by_method",
    "approval_scope",
    "rejection_reason",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path} line {line_no}: {exc}") from exc
    return rows


def has_forbidden(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


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


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] = CSV_FIELDS) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def make_review_sample(approved: list[dict[str, Any]], sample_size: int, seed: int) -> list[dict[str, Any]]:
    by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in approved:
        by_root[str(row.get("root") or "")].append(row)

    sample: list[dict[str, Any]] = []
    rng = random.Random(seed)
    roots = sorted(by_root)
    if not roots:
        return sample

    base_take = max(1, sample_size // len(roots))
    selected_keys: set[tuple[str, str]] = set()
    for root in roots:
        rows = sorted(by_root[root], key=lambda r: (-float(r.get("score") or 0), str(r.get("chunk_id")), str(r.get("abpath_tag"))))
        for row in rows[:base_take]:
            key = (str(row.get("chunk_id")), str(row.get("abpath_tag")))
            if key not in selected_keys:
                sample.append(row)
                selected_keys.add(key)
            if len(sample) >= sample_size:
                return sample

    remaining = [row for row in approved if (str(row.get("chunk_id")), str(row.get("abpath_tag"))) not in selected_keys]
    rng.shuffle(remaining)
    for row in remaining:
        sample.append(row)
        if len(sample) >= sample_size:
            break
    return sample


def split_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    approved: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_approved: set[tuple[str, str]] = set()

    for row in candidates:
        tag = str(row.get("abpath_tag") or "")
        confidence = str(row.get("confidence") or "").lower()
        key = (str(row.get("chunk_id") or ""), tag)

        if has_forbidden(tag) or has_forbidden(row):
            rejected_row = dict(row)
            rejected_row["rejection_reason"] = "forbidden_pattern"
            rejected.append(rejected_row)
            continue

        if confidence == "high":
            if key in seen_approved:
                rejected_row = dict(row)
                rejected_row["rejection_reason"] = "duplicate_chunk_id_abpath_tag"
                rejected.append(rejected_row)
                continue
            approved_row = dict(row)
            approved_row["approval_status"] = APPROVAL_STATUS
            approved_row["approved_by_method"] = APPROVED_BY_METHOD
            approved_row["approval_scope"] = APPROVAL_SCOPE
            approved.append(approved_row)
            seen_approved.add(key)
        elif confidence == "medium":
            review_row = dict(row)
            review_row["review_status"] = "review_queue"
            review.append(review_row)
        else:
            rejected_row = dict(row)
            rejected_row["rejection_reason"] = f"not_approved_confidence_{confidence or 'missing'}"
            rejected.append(rejected_row)

    approved.sort(key=lambda r: (str(r.get("root")), str(r.get("abpath_tag")), str(r.get("chunk_id"))))
    review.sort(key=lambda r: (str(r.get("root")), str(r.get("abpath_tag")), str(r.get("chunk_id"))))
    rejected.sort(key=lambda r: (str(r.get("rejection_reason")), str(r.get("root")), str(r.get("abpath_tag")), str(r.get("chunk_id"))))
    return approved, review, rejected


def write_readme(path: Path, audit: dict[str, Any]) -> None:
    counts = audit["counts"]
    text = f"""# Lecture ABPath Gap Fill Approval v0.3

This directory contains a conservative local-only approval sidecar for Curriculum Gap Fill v0.3 Phase 2.

Scope:
- source family: lectures only
- approved input: high-confidence Phase 1 candidates only
- medium-confidence candidates are review queue only
- ABPath is used as tag ontology, not as content evidence
- no textbook processing
- no source mutation, vector rebuild, FAISS rebuild, GCS upload, deployment, or GPT Builder update

Generated files:
- `lecture_abpath_gapfill_approved_v0_3_HIGHCONF.jsonl`
- `lecture_abpath_gapfill_review_queue_v0_3.csv`
- `lecture_abpath_gapfill_rejected_v0_3.csv`
- `lecture_abpath_gapfill_approval_audit_v0_3.json`
- `lecture_gapfill_highconf_review_sample_100.csv`
- `README_LECTURE_GAPFILL_APPROVAL_V0_3.md`

Counts:
- approved high-confidence rows: {counts["approved_rows"]}
- review queue rows: {counts["review_queue_rows"]}
- rejected rows: {counts["rejected_rows"]}
- forbidden approved hits: {counts["approved_forbidden_pattern_hits"]}

Use guidance:
This sidecar is safe only for local Curriculum Map v0.3 preview experiments. It is not final, live, API-exposed, uploaded, or deployed.
"""
    path.write_text(text, encoding="utf-8")


def build_audit(
    args: argparse.Namespace,
    phase1_audit: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    approved: list[dict[str, Any]],
    review: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> dict[str, Any]:
    approved_roots = Counter(str(row.get("root") or "") for row in approved)
    approved_tags = Counter(str(row.get("abpath_tag") or "") for row in approved)
    confidence_counts = Counter(str(row.get("confidence") or "") for row in candidates)
    rejection_counts = Counter(str(row.get("rejection_reason") or "") for row in rejected)
    approved_forbidden_hits = sum(1 for row in approved if has_forbidden(row))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workstream": "Curriculum Gap Fill v0.3",
        "phase": "phase_2_conservative_lecture_high_confidence_approval",
        "approval_status": APPROVAL_STATUS,
        "approved_by_method": APPROVED_BY_METHOD,
        "approval_scope": APPROVAL_SCOPE,
        "inputs": {
            "candidates_jsonl": str(args.candidates),
            "phase1_audit_json": str(args.phase1_audit),
        },
        "outputs": {
            "approved_jsonl": str(args.output_dir / "lecture_abpath_gapfill_approved_v0_3_HIGHCONF.jsonl"),
            "review_queue_csv": str(args.output_dir / "lecture_abpath_gapfill_review_queue_v0_3.csv"),
            "rejected_csv": str(args.output_dir / "lecture_abpath_gapfill_rejected_v0_3.csv"),
            "approval_audit_json": str(args.output_dir / "lecture_abpath_gapfill_approval_audit_v0_3.json"),
            "review_sample_csv": str(args.output_dir / "lecture_gapfill_highconf_review_sample_100.csv"),
            "readme": str(args.output_dir / "README_LECTURE_GAPFILL_APPROVAL_V0_3.md"),
        },
        "rules": {
            "approved_confidence": "high only",
            "dedupe_key": "chunk_id + abpath_tag",
            "medium_confidence_destination": "review_queue",
            "low_or_rejected_destination": "rejected",
            "forbidden_patterns": list(FORBIDDEN_PATTERNS),
            "local_only": True,
        },
        "counts": {
            "candidate_rows": len(candidates),
            "candidate_confidence_counts": dict(sorted(confidence_counts.items())),
            "approved_rows": len(approved),
            "review_queue_rows": len(review),
            "rejected_rows": len(rejected),
            "rejection_reason_counts": dict(sorted(rejection_counts.items())),
            "approved_forbidden_pattern_hits": approved_forbidden_hits,
            "approved_root_counts": dict(sorted(approved_roots.items())),
            "approved_distinct_tags": len(approved_tags),
            "approved_distinct_chunks": len({str(row.get("chunk_id") or "") for row in approved}),
            "phase1_low_confidence_hidden_count": ((phase1_audit or {}).get("counts") or {}).get("low_confidence_hidden_count"),
        },
        "known_limitations": [
            "High-confidence status comes from lexical FTS candidate generation and is not final content validation.",
            "This is a local preview sidecar only and must not be treated as live or API-exposed.",
            "Medium-confidence candidates are deliberately excluded from approval.",
            "Low-confidence hidden Phase 1 hits are counted from the Phase 1 audit but are not present as row-level records in the candidate JSONL.",
            "ABPath supplies ontology tags only, not content evidence.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--phase1-audit", type=Path, default=DEFAULT_PHASE1_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--review-sample-size", type=int, default=100)
    parser.add_argument("--review-sample-seed", type=int, default=303)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.candidates.exists():
        raise SystemExit(f"Missing candidate input: {args.candidates}")
    if args.review_sample_size <= 0:
        raise SystemExit("--review-sample-size must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidates = read_jsonl(args.candidates)
    phase1_audit = json.loads(args.phase1_audit.read_text(encoding="utf-8")) if args.phase1_audit.exists() else None

    approved, review, rejected = split_candidates(candidates)
    sample = make_review_sample(approved, args.review_sample_size, args.review_sample_seed)
    audit = build_audit(args, phase1_audit, candidates, approved, review, rejected)

    approved_path = args.output_dir / "lecture_abpath_gapfill_approved_v0_3_HIGHCONF.jsonl"
    review_path = args.output_dir / "lecture_abpath_gapfill_review_queue_v0_3.csv"
    rejected_path = args.output_dir / "lecture_abpath_gapfill_rejected_v0_3.csv"
    audit_path = args.output_dir / "lecture_abpath_gapfill_approval_audit_v0_3.json"
    sample_path = args.output_dir / "lecture_gapfill_highconf_review_sample_100.csv"
    readme_path = args.output_dir / "README_LECTURE_GAPFILL_APPROVAL_V0_3.md"

    write_jsonl(approved_path, approved)
    write_csv(review_path, review)
    write_csv(rejected_path, rejected)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(sample_path, sample)
    write_readme(readme_path, audit)

    print(json.dumps(audit["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
