#!/usr/bin/env python3
"""Build the textbook figure image quality-flag sidecar.

Reads the already-produced full-population flagged-image CSV from
`scripts/audit_textbook_figure_image_dimensions_v0_1.py` and tags each
flagged row with a final tier (`suppress_render` for Tier A
`(source_id, fig_slot)` pairs, `warn_render` for every other flagged row),
per the approved tier table in
`docs/RUNBOOK_TEXTBOOK_FIGURE_IMAGE_QUALITY_REPAIR_v0_1.md`.

This script is sidecar-only and read-only against existing local outputs. It
does not open `curriculum_source_locator_index_v0_1.sqlite` or
`curriculum_record_provenance_sidecar_repaired_v0_1.jsonl` in write mode, does
not touch any GCS object, and does not reassign, delete, or regenerate any
`image_path`/`image_url` value. It writes two new local files only:

- `outputs/curriculum_map_v0_4/curriculum_figure_image_quality_flags_v0_1.jsonl`
- `06_audits/curriculum_provenance_links/v0_1/figure_image_quality_flags_audit_v0_1.json`
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "textbook_figure_image_quality_flags.v0_1"

DEFAULT_FLAGGED_CSV = (
    "06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/"
    "flagged_figure_images_full_v0_1.csv"
)
DEFAULT_SOURCE_AUDIT_JSON = (
    "06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/"
    "figure_image_dimension_audit_full_v0_1.json"
)
DEFAULT_OUTPUT_JSONL = "outputs/curriculum_map_v0_4/curriculum_figure_image_quality_flags_v0_1.jsonl"
DEFAULT_OUTPUT_AUDIT = "06_audits/curriculum_provenance_links/v0_1/figure_image_quality_flags_audit_v0_1.json"

# Final, approved (2026-07-08) Tier A (source_id, fig_slot) pairs. Do not
# re-derive — see docs/RUNBOOK_TEXTBOOK_FIGURE_IMAGE_QUALITY_REPAIR_v0_1.md.
TIER_A_PAIRS = {
    ("cyto_comprehensive_part_one", "fig01"),
    ("cyto_comprehensive_part_two", "fig01"),
    ("gu_practical", "fig01"),
    ("gu_practical", "fig02"),
    ("gu_practical", "fig03"),
    ("hn_gnepp", "fig02"),
    ("hn_gnepp", "fig03"),
    ("hn_gnepp", "fig04"),
    ("gi_atlas", "fig02"),
    ("gi_atlas", "fig03"),
    ("gi_atlas", "fig04"),
}

TIER_SUPPRESS = "suppress_render"
TIER_WARN = "warn_render"


def _to_int(value: str) -> Optional[int]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        try:
            return int(float(value))
        except ValueError:
            return None


def _to_float(value: str) -> Optional[float]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def classify_tier(source_id: str, fig_slot: str) -> str:
    return TIER_SUPPRESS if (source_id, fig_slot) in TIER_A_PAIRS else TIER_WARN


def load_flagged_rows(csv_path: Path) -> List[Dict[str, Any]]:
    with csv_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def build_sidecar_rows(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sidecar_rows: List[Dict[str, Any]] = []
    for row in raw_rows:
        source_id = row.get("source_id") or ""
        fig_slot = row.get("fig_slot") or ""
        flags_raw = row.get("flags") or ""
        flags = [f for f in flags_raw.split(";") if f]
        sidecar_rows.append(
            {
                "record_id": row.get("record_id"),
                "chunk_id": row.get("chunk_id"),
                "source_id": source_id,
                "fig_slot": fig_slot,
                "width": _to_int(row.get("width", "")),
                "height": _to_int(row.get("height", "")),
                "aspect_ratio": _to_float(row.get("aspect_ratio", "")),
                "flags": flags,
                "tier": classify_tier(source_id, fig_slot),
            }
        )
    return sidecar_rows


def build_counts(sidecar_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(sidecar_rows)
    tier_counts = Counter(row["tier"] for row in sidecar_rows)
    per_source: Dict[str, Counter] = defaultdict(Counter)
    for row in sidecar_rows:
        per_source[row["source_id"]]["_total"] += 1
        per_source[row["source_id"]][row["tier"]] += 1

    per_source_breakdown = {
        source_id: dict(counter) for source_id, counter in sorted(per_source.items())
    }

    flag_reason_counts: Counter = Counter()
    for row in sidecar_rows:
        for flag in row["flags"]:
            flag_reason_counts[flag] += 1

    return {
        "total_rows": total,
        "tier_a_count": tier_counts.get(TIER_SUPPRESS, 0),
        "tier_b_count": tier_counts.get(TIER_WARN, 0),
        "per_source_id_breakdown": per_source_breakdown,
        "flag_reason_counts": dict(flag_reason_counts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flagged-csv", type=Path, default=Path(DEFAULT_FLAGGED_CSV))
    parser.add_argument("--source-audit-json", type=Path, default=Path(DEFAULT_SOURCE_AUDIT_JSON))
    parser.add_argument("--output-jsonl", type=Path, default=Path(DEFAULT_OUTPUT_JSONL))
    parser.add_argument("--output-audit-json", type=Path, default=Path(DEFAULT_OUTPUT_AUDIT))
    args = parser.parse_args()

    if not args.flagged_csv.exists():
        raise FileNotFoundError(f"missing input CSV: {args.flagged_csv}")

    raw_rows = load_flagged_rows(args.flagged_csv)
    sidecar_rows = build_sidecar_rows(raw_rows)
    counts = build_counts(sidecar_rows)

    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("w", encoding="utf-8") as fh:
        for row in sidecar_rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    args.output_audit_json.parent.mkdir(parents=True, exist_ok=True)
    audit = {
        "schema_version": SCHEMA_VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_paths": {
            "flagged_csv": str(args.flagged_csv),
            "source_audit_json": str(args.source_audit_json),
        },
        "output_paths": {
            "quality_flags_jsonl": str(args.output_jsonl),
            "audit_json": str(args.output_audit_json),
        },
        "tier_a_pairs": sorted(f"{source_id}:{fig_slot}" for source_id, fig_slot in TIER_A_PAIRS),
        "counts": counts,
        "known_limitations": [
            "Tier assignment is at (source_id, fig_slot) granularity, not per-image visual "
            "inspection; only rows already present in the flagged CSV are covered here.",
            "Rows with fetch_error in the source audit have null width/height/aspect_ratio in "
            "this sidecar (25 rows in the full-population run) but are still tiered and carried "
            "through so they are not silently dropped.",
            "This script does not re-run or re-derive the underlying dimension audit; it only "
            "re-tags rows already flagged by "
            "scripts/audit_textbook_figure_image_dimensions_v0_1.py.",
            "Sidecar-only: does not modify curriculum_source_locator_index_v0_1.sqlite, "
            "curriculum_record_provenance_sidecar_repaired_v0_1.jsonl, vector docstores, "
            "normalized records, or any image_path/image_url value anywhere.",
        ],
    }
    args.output_audit_json.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps({"output_paths": audit["output_paths"], "counts": counts}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
