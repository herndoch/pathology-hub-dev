#!/usr/bin/env python3
"""Build the WHO + ABPath Browse tag index (v0_2 schema in v0_1 artifact paths).

Read-only inputs:
    data/curriculum_map_v0_2/abpath_source_tags.jsonl
    data/curriculum_map_v0_2/who_processed/*.json
    outputs/chat_mvp_topic_prepop_v0_1/who_root_map_v0_1.json
    outputs/chat_mvp_topic_prepop_v0_1/cyto_lumping_map_v0_1.json

Outputs:
    outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.json
    outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.audit.json
    frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json  (static UI copy)

Phase 2 rules (docs/PLAN_CHAT_MVP_BROWSE_UX_OVERHAUL_v0_1.md):
    A1 — Browse nav = WHO + ABPath only (no PathOut leaves).
    A2 — Ingest WHO tags via approved who_root_map tag_root_remap.
    A3 — Cyto lump/dedupe/drop via approved cyto_lumping_map.
    A4 — EYE / Eye → Eye_Orbit root merge.
    A5 — Drop leaves whose 2nd segment casefolds to "concept".
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
ABPATH_PATH = REPO_ROOT / "data/curriculum_map_v0_2/abpath_source_tags.jsonl"
WHO_DIR = REPO_ROOT / "data/curriculum_map_v0_2/who_processed"
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
CYTO_MAP_PATH = OUTPUT_DIR / "cyto_lumping_map_v0_1.json"
WHO_MAP_PATH = OUTPUT_DIR / "who_root_map_v0_1.json"
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
INDEX_PATH = OUTPUT_DIR / "browse_tag_index_v0_1.json"
AUDIT_PATH = OUTPUT_DIR / "browse_tag_index_v0_1.audit.json"
STATIC_COPY_PATH = STATIC_DIR / "browse_tag_index_v0_1.json"

SCHEMA_VERSION = "browse_tag_index_v0_2"


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


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _humanized_query(last_segment: str, is_cyto: bool, override: Optional[str] = None) -> str:
    if override:
        return override
    query = last_segment.replace("_", " ").strip()
    query = re.sub(r"\s+", " ", query)
    if is_cyto and "cytology" not in query.casefold():
        query = f"{query} cytology"
    return query


def _remap_tag_root(tag: str, tag_root_remap: dict[str, str], abpath_root_casing: dict[str, str]) -> str:
    segments = tag.split("::")
    if not segments:
        return tag
    first = segments[0]
    remapped = tag_root_remap.get(first, tag_root_remap.get(first.casefold(), first))
    if remapped != first:
        segments[0] = remapped
    canonical = abpath_root_casing.get(segments[0].casefold())
    if canonical and canonical != segments[0]:
        segments[0] = canonical
    return "::".join(segments)


class MapContext:
    def __init__(self, cyto_map: dict, who_map: dict) -> None:
        self.cyto_map = cyto_map
        self.who_map = who_map
        self.tag_root_remap: dict[str, str] = who_map.get("tag_root_remap", {})
        self.root_display_overrides: dict[str, str] = who_map.get("browse_root_display_overrides", {})
        self.drop_tags: set[str] = {
            entry["source_tag"].casefold()
            for entry in cyto_map.get("drop_list", [])
            if entry.get("source_tag")
        }
        self.lump_by_source: dict[str, dict] = {}
        for group in cyto_map.get("lump_groups", []):
            for src in group.get("source_tags", []):
                self.lump_by_source[src.casefold()] = group
        for group in cyto_map.get("dedupe_groups", []):
            for src in group.get("source_tags", []):
                self.lump_by_source[src.casefold()] = group
        drop_predicates = cyto_map.get("drop_predicates", [])
        self.category_last_segments: set[str] = set()
        self.path_suffix_drops: list[str] = []
        self.drop_concept = False
        for pred in drop_predicates:
            if pred.get("id") == "bare_category_last_segment":
                self.category_last_segments = set(pred.get("last_segment_in", []))
            elif pred.get("id") == "degenerate_malignant_leaf":
                self.path_suffix_drops = list(pred.get("path_suffixes", []))
            elif pred.get("id") == "concept_subcategory":
                self.drop_concept = True
            elif pred.get("id") == "pattern_adequacy_descriptors":
                self.pattern_prefix = pred.get("path_prefix", "")

        self.pattern_prefix = getattr(self, "pattern_prefix", "Cyto_Breast::Pattern::")
        self.stats = {
            "dropped_explicit": 0,
            "dropped_predicate": 0,
            "dropped_concept": 0,
            "dropped_pathout_residual": 0,
            "lumped": 0,
            "who_tags_ingested": 0,
            "who_tags_skipped_duplicate": 0,
        }
        self.collapsed_lumps: list[dict] = []

    def should_drop(self, tag: str) -> tuple[bool, str]:
        if "PathOut_Residual_Generated" in tag:
            self.stats["dropped_pathout_residual"] += 1
            return True, "pathout_residual"
        if tag.casefold() in self.drop_tags:
            self.stats["dropped_explicit"] += 1
            return True, "explicit_drop_list"
        segments = tag.split("::")
        if self.drop_concept and len(segments) > 1 and segments[1].casefold() == "concept":
            self.stats["dropped_concept"] += 1
            return True, "concept_subcategory"
        last = segments[-1] if segments else ""
        if last in self.category_last_segments:
            self.stats["dropped_predicate"] += 1
            return True, "bare_category_last_segment"
        for suffix in self.path_suffix_drops:
            if tag.endswith(suffix):
                self.stats["dropped_predicate"] += 1
                return True, "degenerate_suffix"
        if tag.startswith(self.pattern_prefix):
            self.stats["dropped_predicate"] += 1
            return True, "pattern_adequacy"
        return False, ""

    def canonicalize(self, tag: str) -> tuple[str, str, Optional[str], Optional[str]]:
        """Return (canonical_tag, label, query_override, lump_family)."""
        group = self.lump_by_source.get(tag.casefold())
        if not group:
            segments = tag.split("::")
            return tag, segments[-1], None, None
        canonical = group["canonical_tag"]
        self.stats["lumped"] += 1
        self.collapsed_lumps.append(
            {
                "family": group.get("family", ""),
                "source_tag": tag,
                "canonical_tag": canonical,
            }
        )
        return (
            canonical,
            group.get("canonical_label") or canonical.split("::")[-1],
            group.get("canonical_query"),
            group.get("family"),
        )


def build_index() -> tuple[dict, dict]:
    cyto_map = _load_json(CYTO_MAP_PATH)
    who_map = _load_json(WHO_MAP_PATH)
    ctx = MapContext(cyto_map, who_map)

    abpath_rows = _read_jsonl(ABPATH_PATH)
    leaves: dict[str, dict] = {}
    abpath_root_casing: dict[str, str] = {}

    for row in abpath_rows:
        tag = (row.get("primary_tag") or "").strip()
        if not tag:
            continue
        root = tag.split("::", 1)[0]
        abpath_root_casing.setdefault(root.casefold(), root)
        tag = _remap_tag_root(tag, ctx.tag_root_remap, abpath_root_casing)
        drop, _reason = ctx.should_drop(tag)
        if drop:
            continue
        canonical_tag, label, query_override, _family = ctx.canonicalize(tag)
        key = canonical_tag.casefold()
        if key in leaves:
            continue
        leaves[key] = {
            "tag": canonical_tag,
            "label": label,
            "query_override": query_override,
            "provenance": "abpath",
        }

    who_files_read = 0
    who_entities_seen = 0
    for who_path in sorted(WHO_DIR.glob("*.json")):
        who_files_read += 1
        entities = json.loads(who_path.read_text(encoding="utf-8"))
        if not isinstance(entities, list):
            continue
        for entity in entities:
            who_entities_seen += 1
            for raw_tag in entity.get("tags") or []:
                if not isinstance(raw_tag, str) or not raw_tag.strip():
                    continue
                tag = _remap_tag_root(raw_tag.strip(), ctx.tag_root_remap, abpath_root_casing)
                drop, _reason = ctx.should_drop(tag)
                if drop:
                    continue
                canonical_tag, label, query_override, _family = ctx.canonicalize(tag)
                key = canonical_tag.casefold()
                ctx.stats["who_tags_ingested"] += 1
                if key in leaves:
                    if leaves[key]["provenance"] == "abpath":
                        leaves[key]["provenance"] = "both"
                    ctx.stats["who_tags_skipped_duplicate"] += 1
                    continue
                leaves[key] = {
                    "tag": canonical_tag,
                    "label": label,
                    "query_override": query_override,
                    "provenance": "who",
                }

    roots: dict[str, dict] = {}
    cyto_root = {
        "id": "cyto",
        "label": "Cytopathology",
        "kind": "cyto_aggregate",
        "leaf_count": 0,
        "subcategories": {},
    }

    provenance_counts = {"abpath": 0, "who": 0, "both": 0}
    cyto_leaves = 0
    per_root_before: dict[str, int] = {}

    for leaf in leaves.values():
        tag = leaf["tag"]
        provenance = leaf["provenance"]
        provenance_counts[provenance] = provenance_counts.get(provenance, 0) + 1

        segments = tag.split("::")
        first_segment = segments[0]
        last_segment = leaf["label"]
        is_cyto = first_segment.startswith("Cyto_")
        leaf_entry = {
            "tag": tag,
            "label": last_segment,
            "provenance": provenance,
            "query": _humanized_query(last_segment, is_cyto, leaf.get("query_override")),
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
            per_root_before["cyto"] = per_root_before.get("cyto", 0) + 1
        else:
            root_id = _slug(first_segment)
            display_label = ctx.root_display_overrides.get(root_id, first_segment)
            root_entry = roots.setdefault(
                root_id,
                {
                    "id": root_id,
                    "label": display_label,
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
            per_root_before[root_id] = per_root_before.get(root_id, 0) + 1

    def finalize_root(root_entry: dict) -> dict:
        finalized = dict(root_entry)
        subs = sorted(root_entry["subcategories"].values(), key=lambda s: s["label"])
        for sub in subs:
            sub["leaves"] = sorted(sub["leaves"], key=lambda leaf: leaf["label"])
        finalized["subcategories"] = subs
        return finalized

    final_roots = []
    if cyto_root["leaf_count"] > 0:
        final_roots.append(finalize_root(cyto_root))
    for root_entry in sorted(roots.values(), key=lambda r: r["label"]):
        final_roots.append(finalize_root(root_entry))

    generated_at = datetime.now(timezone.utc).isoformat()
    counts: dict[str, Any] = {
        "abpath_tags": len(abpath_rows),
        "who_files_read": who_files_read,
        "who_entities_seen": who_entities_seen,
        "leaves_total": len(leaves),
        "leaves_abpath_only": provenance_counts.get("abpath", 0),
        "leaves_who_only": provenance_counts.get("who", 0),
        "leaves_both": provenance_counts.get("both", 0),
        "roots_total": len(final_roots),
        "cyto_leaves": cyto_leaves,
        **ctx.stats,
        "per_root_leaf_counts": {k: v for k, v in sorted(per_root_before.items())},
    }

    known_limitations = [
        "Index is a local v0_2 snapshot; not proof of API exposure or vector coverage.",
        "Browse nav = WHO + ABPath only; PathOut remains a retrieval/citation source only.",
        "UI collapses deep paths to 3 levels; full tag remains the leaf identity.",
        "Cyto lumping applied per approved cyto_lumping_map_v0_1.json (breast families in v0.1).",
        "WHO CYTO category-definition entities may still appear until a secondary drop pass.",
    ]

    index = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "inputs": {
            "abpath": str(ABPATH_PATH.relative_to(REPO_ROOT)),
            "who_processed": str(WHO_DIR.relative_to(REPO_ROOT)),
            "who_root_map": str(WHO_MAP_PATH.relative_to(REPO_ROOT)),
            "cyto_lumping_map": str(CYTO_MAP_PATH.relative_to(REPO_ROOT)),
        },
        "counts": counts,
        "dedupe_rules": {
            "key": "casefold(full_tag_path)",
            "canonical_preference": "abpath_spelling_with_who_overlay",
            "provenance_values": ["abpath", "who", "both"],
            "nav_sources": ["abpath", "who"],
            "pathout_nav": False,
        },
        "roots": final_roots,
        "known_limitations": known_limitations,
    }

    audit = {
        "schema_version": "browse_tag_index_v0_2_audit",
        "created_at_utc": generated_at,
        "input_paths": [
            str(ABPATH_PATH.relative_to(REPO_ROOT)),
            str(WHO_DIR.relative_to(REPO_ROOT)),
            str(WHO_MAP_PATH.relative_to(REPO_ROOT)),
            str(CYTO_MAP_PATH.relative_to(REPO_ROOT)),
        ],
        "output_paths": [
            str(INDEX_PATH.relative_to(REPO_ROOT)),
            str(STATIC_COPY_PATH.relative_to(REPO_ROOT)),
        ],
        "counts": counts,
        "collapsed_lumps_sample": ctx.collapsed_lumps[:50],
        "collapsed_lumps_total": len(ctx.collapsed_lumps),
        "known_limitations": known_limitations,
    }

    return index, audit


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not CYTO_MAP_PATH.is_file():
        raise SystemExit(f"Missing approved cyto map: {CYTO_MAP_PATH}")
    if not WHO_MAP_PATH.is_file():
        raise SystemExit(f"Missing approved who map: {WHO_MAP_PATH}")

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
