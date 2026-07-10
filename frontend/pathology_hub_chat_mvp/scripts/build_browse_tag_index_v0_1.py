#!/usr/bin/env python3
"""Build the combined, deduped ABPath+PathOut Browse tag index (pilot v0_1).

Read-only inputs:
    data/curriculum_map_v0_2/abpath_source_tags.jsonl
    data/curriculum_map_v0_2/pathout_tagged_pages_AP_DIAGNOSTIC_v1.jsonl

Outputs:
    outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.json
    outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.audit.json
    frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json  (static UI copy)

Rules implemented per docs/PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md section 4:
    - Dedupe key = casefold(full "Root::...::Leaf" tag path).
    - Canonical spelling prefers ABPath; PathOut-only tags keep the PathOut
      path but normalize root casing to the matching ABPath root spelling
      when the roots casefold-match (e.g. "HEME" -> "Heme").
    - PathOut rows are skipped before dedupe if their governed/primary tag is
      blank, "_UNMAPPED_"/"__UNMAPPED__" (case-insensitive), or starts with
      "UNRESOLVED_ROOT".
    - All "Cyto_*" first-segment tags (ABPath + PathOut) are aggregated under
      one synthetic root ("Cytopathology", id "cyto"); every other distinct
      first segment is its own top-level root/tile.
    - 3-level UI tree: root -> subcategory (2nd segment, else "General";
      for cyto, subcategory = the original "Cyto_*" first segment) -> leaf
      (last segment as display label; full tag kept as the identity key).

This script is read-only against its inputs and only ever writes into
outputs/chat_mvp_topic_prepop_v0_1/ and the Chat MVP static/ directory.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
ABPATH_PATH = REPO_ROOT / "data/curriculum_map_v0_2/abpath_source_tags.jsonl"
PATHOUT_PATH = REPO_ROOT / "data/curriculum_map_v0_2/pathout_tagged_pages_AP_DIAGNOSTIC_v1.jsonl"
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
INDEX_PATH = OUTPUT_DIR / "browse_tag_index_v0_1.json"
AUDIT_PATH = OUTPUT_DIR / "browse_tag_index_v0_1.audit.json"
STATIC_COPY_PATH = STATIC_DIR / "browse_tag_index_v0_1.json"

SCHEMA_VERSION = "browse_tag_index_v0_1"

_UNMAPPED_TOKENS = {"_unmapped_", "__unmapped__"}


def _is_skippable_pathout_tag(tag: Optional[str]) -> bool:
    if not tag or not tag.strip():
        return True
    stripped = tag.strip()
    if stripped.casefold() in _UNMAPPED_TOKENS:
        return True
    if stripped.upper().startswith("UNRESOLVED_ROOT"):
        return True
    return False


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_").lower()
    return slug or "root"


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _humanized_query(last_segment: str, is_cyto: bool) -> str:
    query = last_segment.replace("_", " ").strip()
    query = re.sub(r"\s+", " ", query)
    if is_cyto and "cytology" not in query.casefold():
        query = f"{query} cytology"
    return query


def build_index() -> tuple[dict, dict]:
    abpath_rows = _read_jsonl(ABPATH_PATH)
    pathout_rows = _read_jsonl(PATHOUT_PATH)

    leaves: dict[str, dict] = {}
    abpath_root_casing: dict[str, str] = {}

    for row in abpath_rows:
        tag = (row.get("primary_tag") or "").strip()
        if not tag:
            continue
        root = tag.split("::", 1)[0]
        abpath_root_casing.setdefault(root.casefold(), root)
        leaves[tag.casefold()] = {"tag": tag, "provenance": "abpath"}

    pathout_pages_seen = 0
    pathout_tags_skipped = 0
    pathout_tags_resolved = 0

    for row in pathout_rows:
        pathout_pages_seen += 1
        raw_tag = row.get("primary_tag_governed") or row.get("primary_tag")
        if _is_skippable_pathout_tag(raw_tag):
            pathout_tags_skipped += 1
            continue

        tag = raw_tag.strip()
        pathout_tags_resolved += 1
        key = tag.casefold()

        if key in leaves:
            leaves[key]["provenance"] = "both"
            continue

        segments = tag.split("::")
        canonical_root = abpath_root_casing.get(segments[0].casefold())
        if canonical_root and canonical_root != segments[0]:
            segments[0] = canonical_root
            tag = "::".join(segments)
            key = tag.casefold()
            if key in leaves:
                leaves[key]["provenance"] = "both"
                continue

        leaves[key] = {"tag": tag, "provenance": "pathout"}

    roots: dict[str, dict] = {}
    cyto_root = {
        "id": "cyto",
        "label": "Cytopathology",
        "kind": "cyto_aggregate",
        "leaf_count": 0,
        "subcategories": {},
    }

    leaves_abpath_only = 0
    leaves_pathout_only = 0
    leaves_both = 0
    cyto_leaves = 0

    for leaf in leaves.values():
        tag = leaf["tag"]
        provenance = leaf["provenance"]
        if provenance == "abpath":
            leaves_abpath_only += 1
        elif provenance == "pathout":
            leaves_pathout_only += 1
        else:
            leaves_both += 1

        segments = tag.split("::")
        first_segment = segments[0]
        last_segment = segments[-1]
        is_cyto = first_segment.startswith("Cyto_")
        leaf_entry = {
            "tag": tag,
            "label": last_segment,
            "provenance": provenance,
            "query": _humanized_query(last_segment, is_cyto),
        }

        if is_cyto:
            cyto_leaves += 1
            sub_id = _slug(first_segment)
            sub = cyto_root["subcategories"].setdefault(
                sub_id,
                {"id": sub_id, "label": first_segment, "leaf_count": 0, "leaves": []},
            )
            sub["leaves"].append(leaf_entry)
            sub["leaf_count"] += 1
            cyto_root["leaf_count"] += 1
        else:
            root_id = _slug(first_segment)
            root_entry = roots.setdefault(
                root_id,
                {
                    "id": root_id,
                    "label": first_segment,
                    "kind": "root",
                    "leaf_count": 0,
                    "subcategories": {},
                },
            )
            sub_label = segments[1] if len(segments) > 2 else "General"
            sub_id = _slug(sub_label)
            sub = root_entry["subcategories"].setdefault(
                sub_id,
                {"id": sub_id, "label": sub_label, "leaf_count": 0, "leaves": []},
            )
            sub["leaves"].append(leaf_entry)
            sub["leaf_count"] += 1
            root_entry["leaf_count"] += 1

    def finalize_root(root_entry: dict) -> dict:
        finalized = dict(root_entry)
        subs = sorted(root_entry["subcategories"].values(), key=lambda s: s["label"])
        for sub in subs:
            sub["leaves"] = sorted(sub["leaves"], key=lambda leaf: leaf["label"])
        finalized["subcategories"] = subs
        return finalized

    final_roots = [finalize_root(cyto_root)]
    for root_entry in sorted(roots.values(), key=lambda r: r["label"]):
        final_roots.append(finalize_root(root_entry))

    generated_at = datetime.now(timezone.utc).isoformat()
    counts = {
        "abpath_tags": len(abpath_rows),
        "pathout_pages_seen": pathout_pages_seen,
        "pathout_tags_skipped": pathout_tags_skipped,
        "pathout_tags_resolved": pathout_tags_resolved,
        "leaves_total": len(leaves),
        "leaves_abpath_only": leaves_abpath_only,
        "leaves_pathout_only": leaves_pathout_only,
        "leaves_both": leaves_both,
        "roots_total": len(final_roots),
        "cyto_leaves": cyto_leaves,
    }

    known_limitations = [
        "Index is a local v0_2 snapshot; not proof of API exposure or vector coverage.",
        "UI collapses deep paths to 3 levels; full tag remains the leaf identity.",
        "PathOut-only leaves may retrieve thinly if evidence search lacks matching text.",
    ]

    index = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "inputs": {
            "abpath": str(ABPATH_PATH.relative_to(REPO_ROOT)),
            "pathout": str(PATHOUT_PATH.relative_to(REPO_ROOT)),
        },
        "counts": counts,
        "dedupe_rules": {
            "key": "casefold(full_tag_path)",
            "canonical_preference": "abpath_spelling_then_pathout_with_abpath_root_casing",
            "provenance_values": ["abpath", "pathout", "both"],
            "skips": ["blank", "_UNMAPPED_", "UNRESOLVED_ROOT*"],
        },
        "roots": final_roots,
        "known_limitations": known_limitations,
    }

    audit = {
        "schema_version": "browse_tag_index_v0_1_audit",
        "created_at_utc": generated_at,
        "input_paths": [
            str(ABPATH_PATH.relative_to(REPO_ROOT)),
            str(PATHOUT_PATH.relative_to(REPO_ROOT)),
        ],
        "output_paths": [
            str(INDEX_PATH.relative_to(REPO_ROOT)),
            str(STATIC_COPY_PATH.relative_to(REPO_ROOT)),
        ],
        "counts": counts,
        "known_limitations": known_limitations,
    }

    return index, audit


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index, audit = build_index()

    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INDEX_PATH, STATIC_COPY_PATH)

    print(f"Wrote {INDEX_PATH}")
    print(f"Wrote {AUDIT_PATH}")
    print(f"Copied to {STATIC_COPY_PATH}")
    print(json.dumps(index["counts"], indent=2))


if __name__ == "__main__":
    main()
