#!/usr/bin/env python3
"""Build Browse nav from WHO + real ABPath AP Content Specifications only.

Replaces the bloated `abpath_source_tags.jsonl` ontology (~6k expanded tags)
with terminal entities parsed from the official ABPath Anatomic Pathology
Content Specifications PDF/DOCX, plus WHO leaves.

Inputs:
  - data/source_specs/ABPath_Anatomic_Pathology_Content_Specifications.pdf
    (or .docx)
  - Existing WHO leaves from the previous browse index snapshot
    (frontend/.../static/browse_tag_index_v0_1.json) when who_processed/ is
    unavailable in this environment; OR data/curriculum_map_v0_2/who_processed

Outputs:
  - outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.json
  - outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.audit.json
  - frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json
  - 06_audits/abpath_content_specs/v0_1_pdf/… parse sidecars
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
MVP_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_REPO = REPO_ROOT / "scripts"
if str(SCRIPTS_REPO) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_REPO))

from parse_abpath_ap_content_specs_v0_1 import (  # noqa: E402
    LEVEL_SUFFIX_RE,
    normalize_whitespace,
    parse_rows,
    slugify,
    validate_rows,
    write_csv,
    write_jsonl,
    ROW_FIELDS,
)

PDF_PATH = REPO_ROOT / "data/source_specs/ABPath_Anatomic_Pathology_Content_Specifications.pdf"
DOCX_PATH = REPO_ROOT / "data/source_specs/ABPath_Anatomic_Pathology_Content_Specifications.docx"
WHO_DIR = REPO_ROOT / "data/curriculum_map_v0_2/who_processed"
PRIOR_INDEX = MVP_DIR / "static" / "browse_tag_index_v0_1.json"
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
WHO_SNAPSHOT = OUTPUT_DIR / "who_nav_leaves_snapshot_v0_1.json"
AUDIT_DIR = REPO_ROOT / "06_audits/abpath_content_specs/v0_1_pdf"
INDEX_PATH = OUTPUT_DIR / "browse_tag_index_v0_1.json"
AUDIT_PATH = OUTPUT_DIR / "browse_tag_index_v0_1.audit.json"
STATIC_COPY = MVP_DIR / "static" / "browse_tag_index_v0_1.json"

SCHEMA_VERSION = "browse_tag_index_v0_3"

# Content-spec major section number → Browse root id / display label.
MAJOR_TO_ROOT: dict[int, tuple[str, str]] = {
    1: ("breast", "Breast"),
    2: ("gu", "Genitourinary"),
    3: ("gu", "Genitourinary"),
    4: ("cardio", "Cardiovascular"),
    5: ("hn", "Head and Neck"),
    6: ("gi", "Gastrointestinal"),
    7: ("endo", "Endocrine"),
    8: ("gyn", "Gynecologic"),
    9: ("gyn", "Gynecologic"),
    10: ("thorax_mediastinum", "Thorax / Mediastinum"),
    11: ("bst", "Bone / Soft Tissue"),
    12: ("cyto", "Cytopathology"),
    13: ("skin", "Dermatopathology"),
    14: ("forensic", "Forensic Pathology"),
    16: ("heme", "Hematopathology / Lymph Nodes"),
    17: ("neuro", "Neuropathology"),
    18: ("peds", "Pediatric Pathology"),
}

# Skip TOC / non-entity noise if any slip through.
SKIP_ITEM_RE = re.compile(
    r"^(contents|overview|guidance|preparing for|american board|page\s*\d+)\b",
    re.I,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_pdf_line(line: str) -> str:
    line = normalize_whitespace(line)
    if not line:
        return ""
    if line == "American Board of Pathology":
        return ""
    if re.fullmatch(r"\d{1,3}", line):
        return ""
    # TOC leaders / dotted fills
    if "...." in line or "…" in line:
        # Keep major TOC lines that still look like "16. Hematopathology ..."
        if not re.match(r"^\d{1,2}\.\s+\S", line):
            return ""
        line = re.split(r"\s+\.{2,}", line)[0].strip()
    # Strip trailing page numbers: "Fibroadenoma C 98" → "Fibroadenoma C"
    line = re.sub(r"\s+\d{1,4}$", "", line).strip()
    return line


def extract_paragraphs_from_pdf(pdf_path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    raw_lines: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for raw in text.splitlines():
            line = clean_pdf_line(raw)
            if line:
                raw_lines.append(line)

    # Rejoin OCR/PDF wraps like "p" + ". Syringomatous adenoma AR"
    merged: list[str] = []
    i = 0
    while i < len(raw_lines):
        cur = raw_lines[i]
        if re.fullmatch(r"[a-z]", cur) and i + 1 < len(raw_lines) and raw_lines[i + 1].startswith("."):
            merged.append(normalize_whitespace(cur + raw_lines[i + 1]))
            i += 2
            continue
        merged.append(cur)
        i += 1
    return merged


def major_number(major_section: str) -> Optional[int]:
    m = re.match(r"^(\d{1,2})\.", major_section or "")
    return int(m.group(1)) if m else None


def normalize_label_key(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def content_spec_to_leaf(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    item = (row.get("item_text") or "").strip()
    if not item or SKIP_ITEM_RE.match(item):
        return None
    if not row.get("abpath_level"):
        return None
    maj = major_number(row.get("major_section") or "")
    if maj not in MAJOR_TO_ROOT:
        return None
    root_id, _root_label = MAJOR_TO_ROOT[maj]
    organ = (row.get("organ_system") or "").strip()
    category = (row.get("category") or "").strip()
    subsection = (row.get("subsection") or "").strip()
    sub_label = organ or category or subsection or "General"
    # Strip leading "A. " / "1. " from subcategory display
    sub_label = re.sub(r"^[A-Za-z0-9]+\.\s+", "", sub_label).strip() or "General"
    label = item
    tag = "::".join(
        [
            "ABPathSpec",
            root_id,
            slugify(sub_label) or "general",
            slugify(label) or "item",
        ]
    )
    return {
        "tag": tag,
        "label": label,
        "query": label,
        "provenance": "abpath",
        "root_id": root_id,
        "sub_id": slugify(sub_label) or "general",
        "sub_label": sub_label,
        "abpath_level": row.get("abpath_level"),
        "abpath_spec_id": row.get("abpath_spec_id"),
        "raw_path": row.get("raw_path"),
    }


def _who_leaf_from_parts(
    *,
    tag: str,
    label: str,
    query: str,
    root_id: str,
    sub_id: str,
    sub_label: str,
) -> dict[str, Any]:
    return {
        "tag": tag,
        "label": label,
        "query": query,
        "provenance": "who",
        "root_id": root_id,
        "sub_id": sub_id,
        "sub_label": sub_label,
    }


def harvest_who_from_browse_index(index: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep WHO entity tags only — never ABPathSpec or bloated ontology abpath-only."""
    leaves: list[dict[str, Any]] = []
    for root in index.get("roots") or []:
        for sub in root.get("subcategories") or []:
            for leaf in sub.get("leaves") or []:
                tag = leaf.get("tag") or ""
                if not isinstance(tag, str) or "::" not in tag:
                    continue
                if tag.startswith("ABPathSpec::"):
                    continue
                # Accept prior who/both; also accept who-shaped tags if provenance missing.
                prov = str(leaf.get("provenance") or "").lower()
                if prov in {"abpath"}:
                    continue
                if prov not in {"who", "both", ""}:
                    continue
                leaves.append(
                    _who_leaf_from_parts(
                        tag=tag,
                        label=leaf.get("label") or tag.split("::")[-1],
                        query=leaf.get("query") or str(leaf.get("label") or "").replace("_", " "),
                        root_id=root["id"],
                        sub_id=sub["id"],
                        sub_label=sub["label"],
                    )
                )
    return leaves


def load_who_leaves() -> tuple[list[dict[str, Any]], str]:
    """Prefer who_processed; else WHO snapshot; else WHO leaves from prior browse index."""
    leaves: list[dict[str, Any]] = []
    if WHO_DIR.is_dir() and any(WHO_DIR.glob("*.json")):
        for who_path in sorted(WHO_DIR.glob("*.json")):
            entities = json.loads(who_path.read_text(encoding="utf-8"))
            if not isinstance(entities, list):
                continue
            for entity in entities:
                for raw_tag in entity.get("tags") or []:
                    if not isinstance(raw_tag, str) or "::" not in raw_tag:
                        continue
                    segments = raw_tag.split("::")
                    root_seg = segments[0]
                    if root_seg.startswith("Cyto_"):
                        root_id = "cyto"
                        sub_label = root_seg
                    else:
                        root_id = re.sub(r"[^a-z0-9]+", "", root_seg.lower()) or slugify(root_seg)
                        sub_label = segments[1] if len(segments) > 2 else "General"
                    label = segments[-1]
                    leaves.append(
                        _who_leaf_from_parts(
                            tag=raw_tag,
                            label=label,
                            query=label.replace("_", " "),
                            root_id=root_id,
                            sub_id=slugify(sub_label) or "general",
                            sub_label=sub_label,
                        )
                    )
        return leaves, str(WHO_DIR.relative_to(REPO_ROOT))

    if WHO_SNAPSHOT.exists():
        payload = json.loads(WHO_SNAPSHOT.read_text(encoding="utf-8"))
        raw_leaves = payload.get("leaves") if isinstance(payload, dict) else payload
        if isinstance(raw_leaves, list) and raw_leaves:
            for leaf in raw_leaves:
                if not isinstance(leaf, dict) or not leaf.get("tag"):
                    continue
                leaves.append(
                    _who_leaf_from_parts(
                        tag=leaf["tag"],
                        label=leaf.get("label") or leaf["tag"].split("::")[-1],
                        query=leaf.get("query") or str(leaf.get("label") or "").replace("_", " "),
                        root_id=leaf["root_id"],
                        sub_id=leaf.get("sub_id") or "general",
                        sub_label=leaf.get("sub_label") or "General",
                    )
                )
            return leaves, str(WHO_SNAPSHOT.relative_to(REPO_ROOT))

    if not PRIOR_INDEX.exists():
        raise SystemExit(
            "No who_processed/, who_nav_leaves_snapshot_v0_1.json, or prior browse index"
        )
    prior = json.loads(PRIOR_INDEX.read_text(encoding="utf-8"))
    leaves = harvest_who_from_browse_index(prior)
    return leaves, f"{PRIOR_INDEX.relative_to(REPO_ROOT)}#who_harvest"


def build_roots(leaves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    roots: dict[str, dict] = {}
    root_labels = {rid: label for rid, label in MAJOR_TO_ROOT.values()}
    root_labels["cyto"] = "Cytopathology"

    for leaf in leaves:
        root_id = leaf["root_id"]
        root = roots.setdefault(
            root_id,
            {
                "id": root_id,
                "label": root_labels.get(root_id, root_id.replace("_", " ").title()),
                "kind": "cyto_aggregate" if root_id == "cyto" else "root",
                "leaf_count": 0,
                "subcategories": {},
            },
        )
        sub_id = leaf["sub_id"]
        sub = root["subcategories"].setdefault(
            sub_id,
            {"id": sub_id, "label": leaf["sub_label"], "leaf_count": 0, "leaves": []},
        )
        # Dedupe within subcategory by normalized label; prefer abpath > both > who
        rank = {"abpath": 0, "both": 1, "who": 2}.get(leaf["provenance"], 9)
        label_key = normalize_label_key(leaf["label"])
        existing_i = next(
            (i for i, e in enumerate(sub["leaves"]) if normalize_label_key(e["label"]) == label_key),
            None,
        )
        entry = {
            "tag": leaf["tag"],
            "label": leaf["label"],
            "provenance": leaf["provenance"],
            "query": leaf["query"],
        }
        if leaf.get("abpath_level"):
            entry["abpath_level"] = leaf["abpath_level"]
        if existing_i is None:
            sub["leaves"].append(entry)
        else:
            prev = sub["leaves"][existing_i]
            prev_rank = {"abpath": 0, "both": 1, "who": 2}.get(prev.get("provenance"), 9)
            if rank < prev_rank:
                # Keep abpath tag/label; mark both if other was who
                if prev.get("provenance") == "who" and leaf["provenance"] == "abpath":
                    entry["provenance"] = "both"
                sub["leaves"][existing_i] = entry
            elif prev.get("provenance") == "abpath" and leaf["provenance"] == "who":
                prev["provenance"] = "both"

    final = []
    for root in sorted(roots.values(), key=lambda r: r["label"]):
        subs = []
        for sub in sorted(root["subcategories"].values(), key=lambda s: s["label"]):
            sub["leaves"] = sorted(sub["leaves"], key=lambda leaf: leaf["label"].casefold())
            sub["leaf_count"] = len(sub["leaves"])
            if sub["leaf_count"]:
                subs.append(sub)
        root["subcategories"] = subs
        root["leaf_count"] = sum(s["leaf_count"] for s in subs)
        if root["leaf_count"]:
            final.append(root)
    return final


def main() -> int:
    if PDF_PATH.exists():
        paragraphs = extract_paragraphs_from_pdf(PDF_PATH)
        source_doc = str(PDF_PATH.relative_to(REPO_ROOT))
    elif DOCX_PATH.exists():
        from parse_abpath_ap_content_specs_v0_1 import extract_paragraphs

        paragraphs = extract_paragraphs(DOCX_PATH)
        source_doc = str(DOCX_PATH.relative_to(REPO_ROOT))
    else:
        raise SystemExit(f"Missing content-spec PDF/DOCX under data/source_specs/")

    rows, warnings = parse_rows(paragraphs)
    validate_rows(rows)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(AUDIT_DIR / "abpath_ap_content_specs_v0_1.jsonl", rows)
    write_csv(AUDIT_DIR / "abpath_ap_content_specs_v0_1.csv", rows, ROW_FIELDS)
    write_csv(
        AUDIT_DIR / "abpath_ap_content_specs_v0_1_parse_warnings.csv",
        warnings,
        ["line_index", "raw_text", "warning_type", "detail"],
    )

    abpath_leaves: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        leaf = content_spec_to_leaf(row)
        if leaf is None:
            skipped += 1
            continue
        abpath_leaves.append(leaf)

    who_leaves, who_source = load_who_leaves()

    # Persist WHO snapshot so rebuilds do not depend on a bloated prior index.
    WHO_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    WHO_SNAPSHOT.write_text(
        json.dumps(
            {
                "schema_version": "who_nav_leaves_snapshot_v0_1",
                "generated_at": utc_now(),
                "source": who_source,
                "leaf_count": len(who_leaves),
                "leaves": who_leaves,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    # Merge: index by root+label for both-marking.
    # Only mark both when the existing leaf is an ABPath content-spec entity.
    # Duplicate WHO labels must NOT become provenance=both.
    by_root_label: dict[tuple[str, str], dict] = {}
    for leaf in abpath_leaves:
        key = (leaf["root_id"], normalize_label_key(leaf["label"]))
        by_root_label[key] = leaf
    for leaf in who_leaves:
        key = (leaf["root_id"], normalize_label_key(leaf["label"]))
        existing = by_root_label.get(key)
        if existing is None:
            by_root_label[key] = leaf
            continue
        existing_tag = str(existing.get("tag") or "")
        if existing_tag.startswith("ABPathSpec::") or existing.get("provenance") == "abpath":
            existing["provenance"] = "both"

    merged = list(by_root_label.values())
    # Sanitize: abpath/both provenance is reserved for content-spec tags.
    for leaf in merged:
        tag = str(leaf.get("tag") or "")
        if leaf.get("provenance") in {"abpath", "both"} and not tag.startswith("ABPathSpec::"):
            leaf["provenance"] = "who"
    roots = build_roots(merged)

    prov = Counter(leaf["provenance"] for leaf in merged)
    per_root = {r["id"]: r["leaf_count"] for r in roots}
    generated_at = utc_now()

    index = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "inputs": {
            "abpath_content_spec": source_doc,
            "abpath_content_spec_rows": len(rows),
            "who_source": who_source,
            "prior_bloated_abpath_ontology": "excluded (abpath_source_tags.jsonl not used)",
        },
        "counts": {
            "abpath_content_spec_terminal_rows": len(rows),
            "abpath_nav_leaves": prov.get("abpath", 0) + prov.get("both", 0),
            "who_nav_leaves_input": len(who_leaves),
            "leaves_total": sum(r["leaf_count"] for r in roots),
            "leaves_abpath_only": prov.get("abpath", 0),
            "leaves_who_only": prov.get("who", 0),
            "leaves_both": prov.get("both", 0),
            "roots_total": len(roots),
            "content_spec_rows_skipped": skipped,
            "parser_warnings": len(warnings),
            "per_root_leaf_counts": per_root,
        },
        "dedupe_rules": {
            "key": "root_id + normalize(label)",
            "canonical_preference": "abpath_content_spec_over_who",
            "nav_sources": ["abpath_content_spec", "who"],
            "provenance_values": ["abpath", "who", "both"],
            "pathout_nav": False,
            "bloated_abpath_ontology_excluded": True,
            "default_nav_mode": "full",
            "abpath_means": "official_AP_content_specifications_C_AR_F_terminals",
        },
        "roots": roots,
        "known_limitations": [
            "ABPath nav leaves come ONLY from the official AP Content Specifications (C/AR/F terminals).",
            "The expanded abpath_source_tags.jsonl curriculum ontology is intentionally excluded.",
            "WHO leaves are overlaid; PathOut remains citation-only (not nav).",
            "Content-spec tags use ABPathSpec::<root>::… identity — retrieval still uses the query/label text.",
            "Index is a local snapshot; not proof of API/vector coverage.",
        ],
    }

    audit = {
        "schema_version": "browse_tag_index_who_abpath_spec_audit_v0_1",
        "generated_at": generated_at,
        "input_paths": [source_doc, who_source],
        "output_paths": [
            str(INDEX_PATH.relative_to(REPO_ROOT)),
            str(STATIC_COPY.relative_to(REPO_ROOT)),
            str(AUDIT_PATH.relative_to(REPO_ROOT)),
        ],
        "counts": index["counts"],
        "known_limitations": index["known_limitations"],
    }

    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    STATIC_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INDEX_PATH, STATIC_COPY)
    (AUDIT_DIR / "browse_rebuild_audit_v0_1.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(json.dumps(index["counts"], indent=2))
    print(f"Wrote {STATIC_COPY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
