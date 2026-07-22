#!/usr/bin/env python3
"""Build ABPath + WHO combo dedupe export for a separate Anki project.

Policy (matches Browse nav / curriculum spine):
  1. Ingest ABPath tags first (canonical spelling).
  2. Overlay WHO tags; same casefold(full_tag_path) → provenance ``both``.
  3. One export row per organ root + display label; prefer ABPath > both > WHO.

Inputs (first available wins):
  - data/curriculum_map_v0_2/abpath_source_tags.jsonl
  - data/curriculum_map_v0_2/who_processed/*.json
  - fallback: frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json

Outputs:
  - release_artifacts/anki_combo_dedupe_v0_1/abpath_who_combo_dedupe_v0_1.jsonl
  - release_artifacts/anki_combo_dedupe_v0_1/abpath_who_combo_dedupe_v0_1.csv
  - release_artifacts/anki_combo_dedupe_v0_1/abpath_who_combo_dedupe_v0_1.audit.json
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
ABPATH_PATH = REPO_ROOT / "data/curriculum_map_v0_2/abpath_source_tags.jsonl"
WHO_DIR = REPO_ROOT / "data/curriculum_map_v0_2/who_processed"
BROWSE_INDEX_PATH = (
    REPO_ROOT / "frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json"
)
OUTPUT_DIR = REPO_ROOT / "release_artifacts/anki_combo_dedupe_v0_1"
JSONL_PATH = OUTPUT_DIR / "abpath_who_combo_dedupe_v0_1.jsonl"
CSV_PATH = OUTPUT_DIR / "abpath_who_combo_dedupe_v0_1.csv"
AUDIT_PATH = OUTPUT_DIR / "abpath_who_combo_dedupe_v0_1.audit.json"

SCHEMA_VERSION = "anki_combo_dedupe_v0_1"
PROVENANCE_RANK = {"abpath": 0, "both": 1, "who": 2}


def _human_query(label: str, tag: str) -> str:
    query = label.replace("_", " ").strip()
    query = re.sub(r"\s+", " ", query)
    if tag.split("::", 1)[0].casefold().startswith("cyto") and "cytology" not in query.casefold():
        query = f"{query} cytology"
    return query


def _root_id_from_tag(tag: str) -> str:
    first = tag.split("::", 1)[0]
    return re.sub(r"[^a-zA-Z0-9]+", "_", first.strip()).strip("_").lower() or "root"


def _iter_browse_leaves(index: dict) -> list[dict]:
    rows: list[dict] = []
    for root in index.get("roots") or []:
        root_id = root.get("id") or _root_id_from_tag(root.get("label") or "")
        root_label = root.get("label") or root_id
        for sub in root.get("subcategories") or []:
            sub_id = sub.get("id") or ""
            sub_label = sub.get("label") or ""
            for leaf in sub.get("leaves") or []:
                tag = str(leaf.get("tag") or "").strip()
                if not tag:
                    continue
                rows.append(
                    {
                        "tag": tag,
                        "label": str(leaf.get("label") or tag.split("::")[-1]),
                        "provenance": str(leaf.get("provenance") or "abpath").lower(),
                        "query": leaf.get("query") or _human_query(
                            str(leaf.get("label") or ""), tag
                        ),
                        "root_id": root_id,
                        "root_label": root_label,
                        "subcategory_id": sub_id,
                        "subcategory_label": sub_label,
                    }
                )
    return rows


def _load_from_browse_index() -> tuple[list[dict], dict]:
    data = json.loads(BROWSE_INDEX_PATH.read_text(encoding="utf-8"))
    return _iter_browse_leaves(data), {
        "source": "browse_tag_index_v0_1.json",
        "path": str(BROWSE_INDEX_PATH.relative_to(REPO_ROOT)),
        "generated_at": data.get("generated_at"),
        "raw_leaf_count": sum(1 for _ in _iter_browse_leaves(data)),
    }


def _load_from_raw_sources() -> tuple[list[dict], dict]:
    rows_by_path: dict[str, dict] = {}
    abpath_root_casing: dict[str, str] = {}

    with ABPATH_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            tag = str(row.get("primary_tag") or "").strip()
            if not tag:
                continue
            root = tag.split("::", 1)[0]
            abpath_root_casing.setdefault(root.casefold(), root)
            key = tag.casefold()
            if key in rows_by_path:
                continue
            rows_by_path[key] = {
                "tag": tag,
                "label": tag.split("::")[-1],
                "provenance": "abpath",
                "query": _human_query(tag.split("::")[-1], tag),
                "root_id": _root_id_from_tag(tag),
                "root_label": root,
                "subcategory_id": "",
                "subcategory_label": tag.split("::")[1] if "::" in tag else "General",
            }

    who_files = 0
    who_entities = 0
    for who_path in sorted(WHO_DIR.glob("*.json")):
        who_files += 1
        entities = json.loads(who_path.read_text(encoding="utf-8"))
        if not isinstance(entities, list):
            continue
        for entity in entities:
            who_entities += 1
            for raw_tag in entity.get("tags") or []:
                if not isinstance(raw_tag, str) or not raw_tag.strip():
                    continue
                tag = raw_tag.strip()
                first = tag.split("::", 1)[0]
                canonical_first = abpath_root_casing.get(first.casefold(), first)
                if canonical_first != first:
                    tag = canonical_first + tag[len(first) :]
                key = tag.casefold()
                if key in rows_by_path:
                    if rows_by_path[key]["provenance"] == "abpath":
                        rows_by_path[key]["provenance"] = "both"
                    continue
                rows_by_path[key] = {
                    "tag": tag,
                    "label": tag.split("::")[-1],
                    "provenance": "who",
                    "query": _human_query(tag.split("::")[-1], tag),
                    "root_id": _root_id_from_tag(tag),
                    "root_label": canonical_first,
                    "subcategory_id": "",
                    "subcategory_label": tag.split("::")[1] if "::" in tag else "General",
                }

    return list(rows_by_path.values()), {
        "source": "raw_abpath_who",
        "abpath_path": str(ABPATH_PATH.relative_to(REPO_ROOT)),
        "who_dir": str(WHO_DIR.relative_to(REPO_ROOT)),
        "who_files_read": who_files,
        "who_entities_seen": who_entities,
        "raw_tag_count": len(rows_by_path),
    }


def _load_raw_rows() -> tuple[list[dict], dict]:
    if ABPATH_PATH.is_file() and WHO_DIR.is_dir() and any(WHO_DIR.glob("*.json")):
        return _load_from_raw_sources()
    if not BROWSE_INDEX_PATH.is_file():
        raise SystemExit(
            f"Missing inputs: need {ABPATH_PATH} + {WHO_DIR} or {BROWSE_INDEX_PATH}"
        )
    return _load_from_browse_index()


def _dedupe_abpath_over_who(rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """One export row per root_id + display label; ABPath wins on overlap."""
    winners: dict[str, dict] = {}
    merged_aliases: dict[str, list[str]] = {}
    stats = Counter()

    for row in rows:
        stats["input_rows"] += 1
        label_key = str(row.get("label") or "").strip().casefold()
        if not label_key:
            stats["skipped_empty_label"] += 1
            continue
        dedupe_key = f"{row['root_id']}::{label_key}"
        provenance = str(row.get("provenance") or "").lower()
        rank = PROVENANCE_RANK.get(provenance, 9)
        depth = len(str(row.get("tag") or "").split("::"))
        candidate = {**row, "_rank": rank, "_depth": depth}

        prev = winners.get(dedupe_key)
        if not prev:
            winners[dedupe_key] = candidate
            merged_aliases.setdefault(dedupe_key, [])
            continue

        merged_aliases.setdefault(dedupe_key, []).append(row["tag"])
        better = (
            rank < prev["_rank"]
            or (rank == prev["_rank"] and depth > prev["_depth"])
            or (
                rank == prev["_rank"]
                and depth == prev["_depth"]
                and str(row["tag"]) < str(prev["tag"])
            )
        )
        if better:
            merged_aliases[dedupe_key].append(prev["tag"])
            winners[dedupe_key] = candidate
        stats["label_collision"] += 1

    export_rows: list[dict] = []
    for dedupe_key, winner in sorted(winners.items(), key=lambda kv: kv[1]["tag"]):
        aliases = sorted(set(merged_aliases.get(dedupe_key) or []))
        aliases = [t for t in aliases if t != winner["tag"]]
        export_rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "canonical_tag": winner["tag"],
                "display_label": winner["label"],
                "root_id": winner["root_id"],
                "root_label": winner["root_label"],
                "subcategory_label": winner.get("subcategory_label") or "",
                "provenance": winner["provenance"],
                "study_query": winner.get("query") or _human_query(winner["label"], winner["tag"]),
                "dedupe_key": dedupe_key,
                "merged_alias_tags": aliases,
                "merged_alias_count": len(aliases),
            }
        )

    stats["export_rows"] = len(export_rows)
    stats["removed_by_label_dedupe"] = stats["input_rows"] - stats["export_rows"]
    return export_rows, dict(stats)


def _write_jsonl(rows: list[dict]) -> None:
    with JSONL_PATH.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(rows: list[dict]) -> None:
    fieldnames = [
        "canonical_tag",
        "display_label",
        "root_id",
        "root_label",
        "subcategory_label",
        "provenance",
        "study_query",
        "dedupe_key",
        "merged_alias_count",
        "merged_alias_tags",
    ]
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **{k: row.get(k, "") for k in fieldnames},
                    "merged_alias_tags": "|".join(row.get("merged_alias_tags") or []),
                }
            )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_rows, input_meta = _load_raw_rows()
    export_rows, dedupe_stats = _dedupe_abpath_over_who(raw_rows)

    provenance_counts = Counter(r["provenance"] for r in export_rows)
    root_counts = Counter(r["root_id"] for r in export_rows)

    _write_jsonl(export_rows)
    _write_csv(export_rows)

    audit = {
        "schema_version": f"{SCHEMA_VERSION}_audit",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_paths": [input_meta.get("path") or input_meta.get("abpath_path"), input_meta.get("who_dir")],
        "output_paths": [
            str(JSONL_PATH.relative_to(REPO_ROOT)),
            str(CSV_PATH.relative_to(REPO_ROOT)),
        ],
        "counts": {
            **dedupe_stats,
            "provenance_export": dict(provenance_counts),
            "roots_export": len(root_counts),
            "per_root_export_counts": dict(sorted(root_counts.items())),
        },
        "dedupe_rules": {
            "priority": "ABPath > both > WHO",
            "dedupe_key": "root_id + casefold(display_label)",
            "canonical_tag": "winner full tag path (ABPath spelling when overlapping)",
        },
        "known_limitations": [
            "Export is a local snapshot for Anki deck building; not proof of API exposure or vector coverage.",
            "Built from browse index fallback when raw ABPath/WHO inputs are absent in this workspace.",
            "Label-level dedupe per organ root may collapse distinct ABPath paths that share a display label.",
            "WHO-only rows are kept when no ABPath label collision exists in the same root.",
        ],
        "input_meta": input_meta,
    }
    AUDIT_PATH.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(export_rows)} rows")
    print(f"  JSONL: {JSONL_PATH}")
    print(f"  CSV:   {CSV_PATH}")
    print(f"  Audit: {AUDIT_PATH}")
    print("Provenance:", dict(provenance_counts))


if __name__ == "__main__":
    main()
