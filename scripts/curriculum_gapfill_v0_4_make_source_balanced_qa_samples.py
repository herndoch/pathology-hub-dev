#!/usr/bin/env python3
"""Create source-balanced QA samples for v0.4 meaningful review rows."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_GAPFILL_DIR = Path("outputs/curriculum_gapfill_v0_4")
DEFAULT_OUTPUT_DIR = Path("06_audits/curriculum_gapfill/v0_4/qa_samples/source_balanced")
PRIORITY_ROOTS = ("Skin", "HN", "BST", "Breast", "GYN", "GU")
SOURCE_FAMILIES = ("lectures", "textbooks")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def select_rows(rows: list[dict[str, str]], per_root_source: int, per_tag: int) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    tag_counts = Counter((row.get("root", ""), row.get("source_family", ""), row.get("abpath_tag", "")) for row in rows)
    for row in rows:
        if row.get("root") in PRIORITY_ROOTS and row.get("source_family") in SOURCE_FAMILIES and row.get("map_status") == "review":
            grouped[(row["root"], row["source_family"])][row.get("abpath_tag", "")].append(row)
    selected: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for root in PRIORITY_ROOTS:
        for source_family in SOURCE_FAMILIES:
            taken = 0
            tag_rank = Counter({tag: len(tag_rows) for tag, tag_rows in grouped.get((root, source_family), {}).items()})
            for tag, _ in tag_rank.most_common():
                rows_for_tag = sorted(grouped[(root, source_family)][tag], key=lambda row: (-float(row.get("hybrid_score") or 0), row.get("chunk_id", "")))
                for row in rows_for_tag[:per_tag]:
                    key = (source_family, row.get("chunk_id", ""), row.get("abpath_tag", ""))
                    if key in seen:
                        continue
                    out = dict(row)
                    out["root_source_tag_review_row_count"] = str(tag_counts[(root, source_family, tag)])
                    selected.append(out)
                    seen.add(key)
                    taken += 1
                    if taken >= per_root_source:
                        break
                if taken >= per_root_source:
                    break
    return selected


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    preferred = [
        "source_family",
        "source_id",
        "chunk_id",
        "root",
        "prior_or_source_tag",
        "original_existing_tag",
        "abpath_tag",
        "map_status",
        "hybrid_score",
        "hybrid_reason",
        "entity_phrase_hit",
        "root_agreement",
        "generic_only_match",
        "sibling_or_cross_root_conflict",
        "who_phrase_hits",
        "pathout_phrase_hits",
        "textbook_phrase_hits",
        "lecture_phrase_hits",
        "negative_phrase_hits",
        "text_excerpt",
        "source_text_excerpt",
        "source_title",
        "page_or_time",
        "root_source_tag_review_row_count",
    ]
    fields = list(preferred)
    seen = set(fields)
    for row in rows:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gapfill-dir", type=Path, default=DEFAULT_GAPFILL_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--per-root-source", type=int, default=20)
    parser.add_argument("--per-tag", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = read_csv(args.gapfill_dir / "lecture_abpath_gapfill_review_v0_4.csv") + read_csv(args.gapfill_dir / "textbook_abpath_gapfill_review_v0_4.csv")
    selected = select_rows(rows, args.per_root_source, args.per_tag)
    sample_path = args.output_dir / "curriculum_gapfill_v0_4_review_qa_source_balanced_sample.csv"
    audit_path = args.output_dir / "curriculum_gapfill_v0_4_review_qa_source_balanced_audit.json"
    write_csv(sample_path, selected)
    audit = {
        "schema_version": "curriculum_gapfill_v0_4_source_balanced_review_qa_sample",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sample_rows": len(selected),
        "sample_root_counts": dict(Counter(row.get("root", "") for row in selected).most_common()),
        "sample_source_counts": dict(Counter(row.get("source_family", "") for row in selected).most_common()),
        "sample_root_source_counts": dict(Counter(f"{row.get('root', '')}::{row.get('source_family', '')}" for row in selected).most_common()),
        "inputs": {
            "lecture_review": str(args.gapfill_dir / "lecture_abpath_gapfill_review_v0_4.csv"),
            "textbook_review": str(args.gapfill_dir / "textbook_abpath_gapfill_review_v0_4.csv"),
        },
        "outputs": {"sample_csv": str(sample_path), "audit_json": str(audit_path)},
        "limitations": ["Samples include meaningful review rows only; low_information and unmapped_no_confident_tag rows are excluded."],
    }
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "README.md").write_text("# v0.4 Source-Balanced QA Samples\n\nMeaningful review rows only. Not uploaded and not API-exposed.\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
