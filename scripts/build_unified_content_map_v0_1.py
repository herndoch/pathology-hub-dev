#!/usr/bin/env python3
"""Build a unified Textbooks + WHO + PathOut content map.

- One navigable OncoTree by specialty
- All Cyto_* textbook roots nested under Cytopathology
- Journals `cyto` root labeled Cytopathology
- Leaves carry provenance: textbooks / who / pathout

Outputs:
  frontend/pathology_hub_map_hub_v0_1/content/data/unified_content_map_v0_1.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO / "frontend" / "pathology_hub_map_hub_v0_1" / "content" / "data" / "unified_content_map_v0_1.json"
)
SCHEMA = "unified_content_map.v0_1"

ROOT_ALIASES = {
    "bst": "BST",
    "breast": "Breast",
    "cyto": "Cytopathology",
    "cytopathology": "Cytopathology",
    "endo": "Endo",
    "eye_orbit": "Eye_Orbit",
    "gi": "GI",
    "gu": "GU",
    "gyn": "GYN",
    "hn": "HN",
    "heme": "Heme",
    "molecular": "Molecular",
    "neuro": "Neuro",
    "peds": "Peds",
    "skin": "Skin",
    "thorax_mediastinum": "Thorax_Mediastinum",
    "forensic": "Forensic",
}


def pretty(text: str | None) -> str:
    t = (text or "").replace("_", " ").strip()
    return re.sub(r"\s+", " ", t) or "(untitled)"


def norm_root(raw: str | None) -> str:
    if not raw:
        return "Other"
    if raw.startswith("Cyto_"):
        return "Cytopathology"
    key = raw.strip()
    return ROOT_ALIASES.get(key.lower(), key)


def canon_part(part: str) -> str:
    """Stable id for tree segments; preserves known specialty casing."""
    raw = (part or "").strip()
    if not raw:
        return "Other"
    if raw.startswith("Cyto_"):
        return raw  # site id kept until nested under Cytopathology
    aliased = ROOT_ALIASES.get(raw.lower())
    if aliased:
        return aliased
    # Prefer Title_Snake when input is all-lowercase snake
    if raw == raw.lower() and "_" in raw:
        return "_".join(p.capitalize() if p else p for p in raw.split("_"))
    return raw


def ensure_child(node: dict, part: str) -> dict:
    part_id = canon_part(part)
    key = part_id.lower()
    for child in node["children"]:
        if str(child.get("id") or "").lower() == key:
            return child
    child = {
        "id": part_id,
        "label": pretty(part_id),
        "path": f"{node['path']}::{part_id}" if node.get("path") else part_id,
        "kind": "branch",
        "children": [],
        "leaf_count": 0,
        "sources": {"textbooks": 0, "who": 0, "pathout": 0},
    }
    node["children"].append(child)
    return child


def empty_leaf(path: str, label: str) -> dict:
    return {
        "id": path,
        "label": pretty(label),
        "path": path,
        "kind": "leaf",
        "children": [],
        "leaf_count": 1,
        "primary_tag": path,
        "sources": {"textbooks": 0, "who": 0, "pathout": 0},
        "textbook_items": [],
        "who": None,
        "pathout": None,
    }


def normalize_parts(parts: list[str]) -> list[str]:
    """Normalize a tag path; nest Cyto_* under Cytopathology::<Site>."""
    cleaned = [p for p in parts if p]
    if not cleaned:
        return ["Other"]
    if cleaned[0].startswith("Cyto_"):
        site = cleaned[0][len("Cyto_") :] or cleaned[0]
        cleaned = ["Cytopathology", site, *cleaned[1:]]
    else:
        cleaned[0] = norm_root(cleaned[0])
    return [canon_part(p) if i else cleaned[0] for i, p in enumerate(cleaned)]


def ensure_root(roots_out: dict[str, dict], root_id: str) -> dict:
    if root_id not in roots_out:
        roots_out[root_id] = {
            "id": root_id,
            "label": "Cytopathology" if root_id == "Cytopathology" else pretty(root_id),
            "path": root_id,
            "kind": "root",
            "children": [],
            "leaf_count": 0,
            "sources": {"textbooks": 0, "who": 0, "pathout": 0},
        }
    return roots_out[root_id]


def find_or_create_leaf(parent: dict, leaf_path: str, label: str) -> dict:
    key = leaf_path.lower()
    for child in parent["children"]:
        if child.get("kind") == "leaf" and str(child.get("path") or "").lower() == key:
            return child
        if child.get("kind") == "leaf" and pretty(child.get("label")).lower() == pretty(label).lower():
            # Same label under same parent — merge
            return child
    leaf = empty_leaf(leaf_path, label)
    parent["children"].append(leaf)
    return leaf


def place_by_parts(roots_out: dict[str, dict], parts: list[str], label: str) -> dict:
    parts = normalize_parts(parts)
    root = ensure_root(roots_out, parts[0])
    node = root
    if len(parts) == 1:
        # Rare: specialty-level leaf
        return find_or_create_leaf(root, parts[0], label or parts[0])
    for part in parts[1:-1]:
        node = ensure_child(node, part)
    leaf_path = "::".join(parts)
    return find_or_create_leaf(node, leaf_path, label or parts[-1])


def finalize(node: dict) -> tuple[int, dict]:
    if node.get("kind") == "leaf":
        src = {
            "textbooks": 1 if node.get("textbook_items") else 0,
            "who": 1 if node.get("who") else 0,
            "pathout": 1 if node.get("pathout") else 0,
        }
        node["sources"] = src
        node["leaf_count"] = 1
        return 1, src
    leaves = 0
    src = {"textbooks": 0, "who": 0, "pathout": 0}
    for child in node.get("children") or []:
        l, s = finalize(child)
        leaves += l
        for k in src:
            src[k] += s[k]
    node["leaf_count"] = leaves
    node["sources"] = src
    node["children"] = sorted(node.get("children") or [], key=lambda c: c["label"].lower())
    return leaves, src


def walk_textbook_leaves(node: dict, acc: list[dict]) -> None:
    kids = node.get("children") or []
    if node.get("kind") == "leaf" or (not kids and node.get("items") is not None):
        acc.append(node)
        return
    for child in kids:
        walk_textbook_leaves(child, acc)


def add_textbook_tree(roots_out: dict[str, dict], tb: dict) -> None:
    leaves: list[dict] = []
    for r in tb.get("roots") or []:
        walk_textbook_leaves(r, leaves)
    for leaf in leaves:
        path = leaf.get("path") or ""
        parts = [p for p in path.split("::") if p]
        if not parts:
            continue
        existing = place_by_parts(roots_out, parts, leaf.get("label") or parts[-1])
        items = []
        for it in leaf.get("items") or []:
            row = dict(it)
            row["source_family"] = "textbooks"
            items.append(row)
        existing["textbook_items"] = (existing.get("textbook_items") or []) + items
        existing["sources"]["textbooks"] = 1
        existing["primary_tag"] = existing.get("primary_tag") or "::".join(normalize_parts(parts))


def add_journals(roots_out: dict[str, dict], journals: dict) -> None:
    """Walk each WHO/PathOut leaf by its full tag path (not the browse subcategory)."""

    def walk_journal_leaves(node: dict, acc: list[dict]) -> None:
        kids = node.get("children") or []
        if node.get("kind") == "leaf" or (not kids and (node.get("tag") or node.get("provenance"))):
            acc.append(node)
            return
        for child in kids:
            walk_journal_leaves(child, acc)

    leaves: list[dict] = []
    for r in journals.get("roots") or []:
        walk_journal_leaves(r, leaves)

    for leaf in leaves:
        tag = leaf.get("tag") or leaf.get("path") or leaf.get("id") or ""
        parts = [p for p in str(tag).split("::") if p]
        if not parts:
            # Fall back to journal root id + label
            rid = norm_root(leaf.get("root_id"))
            parts = [rid, leaf.get("label") or "topic"]
        leaf_label = leaf.get("label") or parts[-1]
        existing = place_by_parts(roots_out, parts, leaf_label)
        existing["primary_tag"] = tag or existing.get("primary_tag")
        prov = (leaf.get("provenance") or "").lower()
        payload = {
            "tag": tag,
            "query": leaf.get("query") or leaf_label,
            "label": leaf_label,
            "provenance": prov,
        }
        if "pathout" in prov:
            existing["pathout"] = payload
            existing["sources"]["pathout"] = 1
        else:
            existing["who"] = payload
            existing["sources"]["who"] = 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--textbooks",
        type=Path,
        default=REPO / "frontend" / "pathology_hub_map_hub_v0_1" / "textbooks" / "data" / "textbook_oncotree_index_v0_1.json",
    )
    ap.add_argument(
        "--journals",
        type=Path,
        default=REPO
        / "frontend"
        / "pathology_hub_map_hub_v0_1"
        / "journals"
        / "data"
        / "journals_who_pathout_map_v0_1.json",
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    tb = json.loads(args.textbooks.read_text(encoding="utf-8"))
    journals = json.loads(args.journals.read_text(encoding="utf-8"))

    roots_out: dict[str, dict] = {}
    add_textbook_tree(roots_out, tb)
    add_journals(roots_out, journals)

    root_list = sorted(roots_out.values(), key=lambda r: r["label"].lower())
    for r in root_list:
        finalize(r)

    # counts
    def count_leaves(n):
        if n.get("kind") == "leaf":
            return [n]
        out = []
        for c in n.get("children") or []:
            out.extend(count_leaves(c))
        return out

    leaves = []
    for r in root_list:
        leaves.extend(count_leaves(r))

    counts = {
        "roots": len(root_list),
        "leaves": len(leaves),
        "leaves_with_textbooks": sum(1 for L in leaves if L.get("textbook_items")),
        "leaves_with_who": sum(1 for L in leaves if L.get("who")),
        "leaves_with_pathout": sum(1 for L in leaves if L.get("pathout")),
        "cytopathology_sites": len(next((r["children"] for r in root_list if r["id"] == "Cytopathology"), [])),
    }

    payload = {
        "schema_version": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": "Pathology Hub — Content map",
        "subtitle": "Textbooks, WHO Classification, and PathologyOutlines in one tree. One Cytopathology root.",
        "chat_url": "https://chat.pathologynotebook.com",
        "filters": ["all", "textbooks", "who", "pathout"],
        "counts": counts,
        "known_limitations": [
            "Unified browse map for education sharing; not a claim that every leaf is vectorized/API-exposed.",
            "Textbook samples are capped per leaf; WHO/PathOut entries open into Chat for retrieval.",
            "All Cyto_* textbook roots are nested under Cytopathology.",
            "Preferred host: map.pathologynotebook.com (requires DNS CNAME).",
        ],
        "roots": root_list,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
