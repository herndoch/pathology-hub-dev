#!/usr/bin/env python3
"""Build a human-review QA calibration package for ABPath-to-v0_4 enrichment."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "abpath_enrichment_qa_calibration_v0_1"
DEFAULT_ENRICHMENT_DIR = Path("06_audits/abpath_content_specs/v0_1/enrichment_to_curriculum_v0_4")
DEFAULT_OUT_DIR = DEFAULT_ENRICHMENT_DIR / "qa_calibration"
SAMPLE_SIZE = 50
RANDOM_SEED = 42

PROTECTED_V04_FILES = (
    Path("outputs/curriculum_map_v0_4/curriculum_records_v0_4.jsonl"),
    Path("outputs/curriculum_map_v0_4/curriculum_tag_index_v0_4.sqlite"),
    Path("outputs/curriculum_map_v0_4/acceptance_summary_v0_4.json"),
    Path("06_audits/curriculum_gapfill/v0_4/curriculum_gapfill_map_v0_4_audit.json"),
)

SOURCE_FIELDS = [
    "curriculum_tag",
    "curriculum_root",
    "map_status",
    "source_family",
    "source_id",
    "chunk_id",
    "text_excerpt",
    "abpath_spec_id",
    "abpath_item_text",
    "abpath_raw_path",
    "abpath_level",
    "abpath_level_label",
    "expected_resident_depth",
    "specialty_board_scope",
    "match_type",
    "match_score",
    "match_confidence",
    "match_reason",
    "warning",
]

REVIEW_FIELDS = [
    "manual_match_decision",
    "corrected_abpath_spec_id",
    "corrected_abpath_level",
    "reviewer_note",
    "severity",
]

UNMATCHED_FIELDS = [
    "abpath_spec_id",
    "abpath_item_text",
    "abpath_raw_path",
    "abpath_level",
    "abpath_level_label",
    "expected_resident_depth",
    "major_section",
    "specialty_board_scope",
    "priority_bucket",
    "manual_match_decision",
    "corrected_curriculum_tag",
    "reviewer_note",
    "severity",
]

PRIORITY_BUCKETS = [
    ("breast", re.compile(r"\b1\.\s*Breast\b|breast", re.I)),
    ("gi", re.compile(r"digestive|gastrointestinal|\b6\.\s*The Digestive", re.I)),
    ("gu_kidney", re.compile(r"genitourinary|kidney|\b2\.\s*The Genitourinary", re.I)),
    ("skin", re.compile(r"dermatopathology|\b13\.|skin", re.I)),
    ("head_and_neck", re.compile(r"head and neck|\b5\.\s*Head", re.I)),
    ("bst", re.compile(r"soft tissue|bones|joints|\b11\.\s*Soft", re.I)),
]

MANUAL_DECISION_VALUES = [
    "accept",
    "reject",
    "wrong_root",
    "too_generic",
    "better_match_exists",
    "uncertain",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint_paths(paths: tuple[Path, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in paths:
        if not path.exists():
            out[str(path)] = {"missing": True}
            continue
        stat = path.stat()
        out[str(path)] = {"size": stat.st_size, "mtime": stat.st_mtime}
    return out


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def is_cross_root_warning(warning: str) -> bool:
    return "cross-root" in (warning or "").lower()


def is_compatible_root_row(row: dict[str, str]) -> bool:
    return row.get("match_confidence") == "high" and not is_cross_root_warning(row.get("warning", ""))


def dedupe_key(row: dict[str, str]) -> str:
    return f"{row.get('curriculum_tag', '')}::{row.get('abpath_spec_id', '')}"


def sample_rows(
    pool: list[dict[str, str]],
    size: int,
    *,
    dedupe: bool = True,
) -> list[dict[str, str]]:
    if dedupe:
        seen: set[str] = set()
        unique_pool: list[dict[str, str]] = []
        for row in pool:
            key = dedupe_key(row)
            if key in seen:
                continue
            seen.add(key)
            unique_pool.append(row)
        pool = unique_pool
    if len(pool) <= size:
        return list(pool)
    rng = random.Random(RANDOM_SEED)
    return rng.sample(pool, size)


def enrich_row(row: dict[str, str]) -> dict[str, str]:
    out = {field: row.get(field, "") for field in SOURCE_FIELDS}
    for field in REVIEW_FIELDS:
        out[field] = ""
    return out


def priority_bucket_for_unmatched(row: dict[str, str]) -> str:
    blob = " ".join(
        [
            row.get("major_section", ""),
            row.get("abpath_item_text", ""),
            row.get("abpath_raw_path", ""),
        ]
    )
    for name, pattern in PRIORITY_BUCKETS:
        if pattern.search(blob):
            return name
    return "other"


def sample_unmatched_core(rows: list[dict[str, str]], size: int) -> list[dict[str, str]]:
    core_rows = [row for row in rows if row.get("abpath_level") == "C"]
    by_bucket: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in core_rows:
        bucket = priority_bucket_for_unmatched(row)
        by_bucket[bucket].append(row)

    priority_order = [name for name, _ in PRIORITY_BUCKETS] + ["other"]
    per_bucket = max(1, size // len(priority_order))
    rng = random.Random(RANDOM_SEED)
    selected: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for bucket in priority_order:
        pool = by_bucket.get(bucket, [])
        rng.shuffle(pool)
        for row in pool:
            spec_id = row.get("abpath_spec_id", "")
            if spec_id in seen_ids:
                continue
            seen_ids.add(spec_id)
            selected.append(row)
            if sum(1 for r in selected if priority_bucket_for_unmatched(r) == bucket) >= per_bucket:
                break

    if len(selected) < size:
        remaining = [row for row in core_rows if row.get("abpath_spec_id") not in seen_ids]
        rng.shuffle(remaining)
        selected.extend(remaining[: size - len(selected)])
    return selected[:size]


def enrich_unmatched_row(row: dict[str, str], abpath_lookup: dict[str, dict[str, str]]) -> dict[str, str]:
    spec = abpath_lookup.get(row.get("abpath_spec_id", ""), {})
    return {
        "abpath_spec_id": row.get("abpath_spec_id", ""),
        "abpath_item_text": row.get("abpath_item_text", ""),
        "abpath_raw_path": row.get("abpath_raw_path", ""),
        "abpath_level": row.get("abpath_level", ""),
        "abpath_level_label": spec.get("abpath_level_label", ""),
        "expected_resident_depth": spec.get("expected_resident_depth", ""),
        "major_section": row.get("major_section", ""),
        "specialty_board_scope": row.get("specialty_board_scope", ""),
        "priority_bucket": priority_bucket_for_unmatched(row),
        "manual_match_decision": "",
        "corrected_curriculum_tag": "",
        "reviewer_note": "",
        "severity": "",
    }


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_qa_instructions(path: Path) -> None:
    path.write_text(
        """# ABPath Enrichment QA Instructions

## What you are reviewing

A staged **read-only sidecar** that proposes ABPath training-level metadata (`C`, `AR`, `F`) for v0_4 curriculum gapfill rows. This is **not** a curriculum map approval pass and **not** API/live deployment.

## Critical rules

1. **C / AR / F are training-level metadata only.**
   - `C` = Core / Foundational → expected resident depth: mastery
   - `AR` = Advanced Resident → competence
   - `F` = Fellow / Advanced Practitioner → superficial familiarity for residents

2. **Do not change `map_status`.**
   - `approved`, `review`, `rejected_conflict`, etc. remain governed by v0_4 gapfill/map logic.
   - A good ABPath enrichment match does **not** mean the chunk should be promoted.

3. **Do not treat this package as auto-promotion.**
   - No GCS upload, API/live changes, vector rebuilds, or v0_4 output edits.

## How to review each sample file

### `abpath_enrichment_high_confidence_sample.csv`

- Spot-check even "high" rows.
- Confirm tag leaf ↔ ABPath `item_text` alignment and compatible root.
- Use `manual_match_decision = accept` only when you would trust this as metadata enrichment.

### `abpath_enrichment_medium_confidence_sample.csv`

- Treat as provisional.
- Expect more synonym / partial-name issues.
- Prefer `uncertain` or `better_match_exists` when uneasy.

### `abpath_enrichment_low_confidence_sample.csv`

- Assume reject unless clearly justified.
- Common failure mode: generic substring matches (`fibroma`, `chondroma`, `lipoma`).

### `abpath_enrichment_cross_root_warning_sample.csv`

- Usually `wrong_root` or `reject`.
- Accept only when the curriculum root and ABPath section are intentionally cross-listed and clinically correct.

### `abpath_enrichment_unmatched_core_abpath_sample.csv`

- These are **Core (`C`) ABPath rows with no enrichment match**.
- They identify ontology/tag coverage gaps, not map failures.
- Note whether a curriculum tag should exist or matching rules need refinement.

## `manual_match_decision` values

| Value | When to use |
|-------|-------------|
| `accept` | Enrichment link is clinically and hierarchically correct |
| `reject` | Link should not be used |
| `wrong_root` | Name may match but organ/system root is wrong |
| `too_generic` | Partial/generic name collision |
| `better_match_exists` | A different ABPath row is the right target |
| `uncertain` | Needs second reviewer or more context |

## `severity` guidance

Use optional severity labels such as `low`, `medium`, `high`, or `blocker`:

- `blocker` — would cause unsafe training-metadata assignment if auto-applied
- `high` — clear mismatch or generic collision
- `medium` — plausible but needs refinement
- `low` — minor wording/synonym issue

## After QA

Summarize findings in the sample CSVs, then read `ABPATH_ENRICHMENT_NEXT_FIXES.md` for proposed v0_5 refinement themes. Do not modify v0_4 outputs based on this review alone.
""",
        encoding="utf-8",
    )


def write_next_fixes(path: Path, audit: dict[str, Any]) -> None:
    path.write_text(
        f"""# ABPath Enrichment — Proposed Next Fixes (post-QA calibration)

Generated from calibration audit `{audit.get("schema_version")}` on {audit.get("generated_at_utc", "")}.

## 1. Tag synonym additions

- Add curated synonym map for common ontology leaves ↔ ABPath item text (e.g., `DCIS` ↔ `Ductal carcinoma in situ`, `NOS` variants, hyphen/underscore forms).
- Maintain synonyms as a sidecar CSV keyed by `normalized_item_key`, not by mutating v0_4 tags.

## 2. Normalized leaf-name improvements

- Normalize leaves before matching: strip grade qualifiers, collapse `Not Otherwise Specified (NOS)`, unify British/American spelling.
- Prefer longest-token wins over substring wins when multiple ABPath rows share a token.

## 3. Root mapping improvements

- Current calibration flagged **{audit.get("cross_root_warning_pool_size", 0)}** cross-root warning candidates in the enrichment pool.
- Tighten organ/root gates for high-confidence promotion:
  - Breast ↔ Breast
  - GU/GU::* ↔ Genitourinary/Kidney/Prostate/Testis
  - GI ↔ Digestive/Liver/Pancreas
  - HN ↔ Head and Neck
  - Skin ↔ Dermatopathology
  - BST ↔ Soft Tissue/Bones/Joints
- Allow explicit crosswalk exceptions only via a reviewed allowlist.

## 4. Generic-name safeguards

Observed high-risk generic collisions in enrichment:

{audit.get("generic_collision_examples_markdown", "- lipoma, chondroma, fibroma")}

Proposed safeguards for v0_5:

- Block auto-accept when ABPath `item_text` is a single generic token unless tag leaf is exact full phrase.
- Require token-count parity or Jaccard threshold ≥ 0.8 for high confidence.
- Downgrade any generic match with incompatible root to `reject`, not `low`.

## 5. Unmatched Core ABPath coverage gaps

- Unmatched Core (`C`) ABPath rows in registry: **{audit.get("unmatched_core_abpath_total", 0)}**
- Calibration sample size: **{audit.get("sample_counts", {}).get("unmatched_core_abpath", 0)}**
- Priority buckets sampled: breast, gi, gu_kidney, skin, head_and_neck, bst

Handle gaps by:

1. Recording whether missing curriculum tags exist under different names.
2. Adding targeted synonym/root rules for high-yield Core topics (DCIS, invasive ductal carcinoma, axillary nodes, biomarkers, normal anatomy/histology).
3. Keeping unmatched Core rows as a backlog — not as map_status failures.

## 6. Future v0_5 enrichment pass?

**Recommendation:** Yes, but only after this QA calibration is reviewed.

A v0_5 pass should:

- Read v0_4 gapfill/map outputs unchanged (new sidecar only)
- Apply synonym table + generic safeguards + stricter root gates
- Emit separate `enrichment_v0_5` audit with before/after accept-rate on the same 250-row calibration set
- Still avoid API/GCS/live promotion until a second human sign-off

**Do not** auto-promote based on v0_4 enrichment counts:

- matched rows: {audit.get("source_enrichment_matched_rows", 0)}
- low confidence: {audit.get("source_enrichment_low_confidence_rows", 0)}
- cross-root warnings: {audit.get("source_enrichment_cross_root_rows", 0)}
""",
        encoding="utf-8",
    )


def build_calibration(enrichment_dir: Path, out_dir: Path) -> dict[str, Any]:
    before_fp = fingerprint_paths(PROTECTED_V04_FILES)

    candidates_path = enrichment_dir / "abpath_to_curriculum_v0_4_enrichment_candidates.csv"
    unmatched_path = enrichment_dir / "abpath_to_curriculum_v0_4_unmatched_abpath_rows.csv"
    abpath_jsonl = Path("06_audits/abpath_content_specs/v0_1/abpath_ap_content_specs_v0_1.jsonl")

    candidates = read_csv(candidates_path)
    unmatched = read_csv(unmatched_path)
    abpath_lookup: dict[str, dict[str, str]] = {}
    if abpath_jsonl.exists():
        for line in abpath_jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            abpath_lookup[row["abpath_spec_id"]] = row

    high_pool = [row for row in candidates if is_compatible_root_row(row)]
    medium_pool = [row for row in candidates if row.get("match_confidence") == "medium"]
    low_pool = [row for row in candidates if row.get("match_confidence") == "low"]
    cross_root_pool = [row for row in candidates if is_cross_root_warning(row.get("warning", ""))]

    high_sample = [enrich_row(row) for row in sample_rows(high_pool, SAMPLE_SIZE)]
    medium_sample = [enrich_row(row) for row in sample_rows(medium_pool, SAMPLE_SIZE)]
    low_sample = [enrich_row(row) for row in sample_rows(low_pool, SAMPLE_SIZE)]
    cross_root_sample = [enrich_row(row) for row in sample_rows(cross_root_pool, SAMPLE_SIZE, dedupe=False)]
    unmatched_core_sample = [
        enrich_unmatched_row(row, abpath_lookup)
        for row in sample_unmatched_core(unmatched, SAMPLE_SIZE)
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    sample_files = {
        "high_confidence": out_dir / "abpath_enrichment_high_confidence_sample.csv",
        "medium_confidence": out_dir / "abpath_enrichment_medium_confidence_sample.csv",
        "low_confidence": out_dir / "abpath_enrichment_low_confidence_sample.csv",
        "cross_root_warning": out_dir / "abpath_enrichment_cross_root_warning_sample.csv",
        "unmatched_core_abpath": out_dir / "abpath_enrichment_unmatched_core_abpath_sample.csv",
    }

    write_csv(sample_files["high_confidence"], high_sample, SOURCE_FIELDS + REVIEW_FIELDS)
    write_csv(sample_files["medium_confidence"], medium_sample, SOURCE_FIELDS + REVIEW_FIELDS)
    write_csv(sample_files["low_confidence"], low_sample, SOURCE_FIELDS + REVIEW_FIELDS)
    write_csv(sample_files["cross_root_warning"], cross_root_sample, SOURCE_FIELDS + REVIEW_FIELDS)
    write_csv(sample_files["unmatched_core_abpath"], unmatched_core_sample, UNMATCHED_FIELDS)

    generic_terms = ("lipoma", "chondroma", "fibroma", "carcinoma", "adenoma")
    generic_examples = []
    for row in candidates:
        item = (row.get("abpath_item_text") or "").lower()
        tag = (row.get("curriculum_tag") or "").lower()
        if any(term == item for term in generic_terms) or (
            any(term in tag for term in generic_terms) and row.get("match_confidence") == "low"
        ):
            generic_examples.append(
                f"- `{row.get('curriculum_tag', '')}` → `{row.get('abpath_item_text', '')}` ({row.get('match_confidence', '')})"
            )
        if len(generic_examples) >= 8:
            break

    after_fp = fingerprint_paths(PROTECTED_V04_FILES)
    if before_fp != after_fp:
        raise RuntimeError("Protected v0_4 artifacts changed during QA calibration build")

    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "random_seed": RANDOM_SEED,
        "input_paths": {
            "enrichment_candidates_csv": str(candidates_path),
            "unmatched_abpath_csv": str(unmatched_path),
        },
        "output_paths": {key: str(path) for key, path in sample_files.items()},
        "output_paths_extra": {
            "qa_instructions": str(out_dir / "ABPATH_ENRICHMENT_QA_INSTRUCTIONS.md"),
            "next_fixes": str(out_dir / "ABPATH_ENRICHMENT_NEXT_FIXES.md"),
            "audit_json": str(out_dir / "abpath_enrichment_qa_calibration_audit.json"),
        },
        "sample_counts": {
            "high_confidence": len(high_sample),
            "medium_confidence": len(medium_sample),
            "low_confidence": len(low_sample),
            "cross_root_warning": len(cross_root_sample),
            "unmatched_core_abpath": len(unmatched_core_sample),
        },
        "pool_sizes": {
            "high_confidence_compatible_root": len(high_pool),
            "medium_confidence": len(medium_pool),
            "low_confidence": len(low_pool),
            "cross_root_warning": len(cross_root_pool),
            "unmatched_core_abpath_total": sum(1 for row in unmatched if row.get("abpath_level") == "C"),
        },
        "source_enrichment_matched_rows": len(candidates),
        "source_enrichment_low_confidence_rows": len(low_pool),
        "source_enrichment_cross_root_rows": len(cross_root_pool),
        "cross_root_warning_pool_size": len(cross_root_pool),
        "unmatched_core_abpath_total": sum(1 for row in unmatched if row.get("abpath_level") == "C"),
        "unmatched_core_bucket_counts": dict(
            Counter(row["priority_bucket"] for row in unmatched_core_sample)
        ),
        "manual_match_decision_allowed_values": MANUAL_DECISION_VALUES,
        "validation": {
            "v0_4_files_modified": False,
            "map_status_changed": False,
            "api_gcs_live_action": False,
            "enrichment_candidates_overwritten": False,
            "qa_files_created": True,
        },
        "limitations": [
            "Samples are stratified random subsets for human calibration only.",
            "High-confidence sample excludes cross-root warnings.",
            "Unmatched Core sample prioritizes breast, GI, GU/kidney, skin, HN, and BST buckets.",
            "This package does not modify v0_4 outputs or enrichment candidate files.",
        ],
    }

    instructions_path = out_dir / "ABPATH_ENRICHMENT_QA_INSTRUCTIONS.md"
    next_fixes_path = out_dir / "ABPATH_ENRICHMENT_NEXT_FIXES.md"
    audit_path = out_dir / "abpath_enrichment_qa_calibration_audit.json"

    audit["generic_collision_examples_markdown"] = "\n".join(generic_examples) or "- lipoma, chondroma, fibroma"
    write_qa_instructions(instructions_path)
    write_next_fixes(next_fixes_path, audit)
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enrichment-dir", type=Path, default=DEFAULT_ENRICHMENT_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = build_calibration(args.enrichment_dir, args.out_dir)
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
