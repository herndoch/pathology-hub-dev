#!/usr/bin/env python3
"""Build a read-only ABPath-to-v0_4 curriculum enrichment sidecar experiment."""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "abpath_to_curriculum_v0_4_enrichment_v0_1"
DEFAULT_ABPATH_JSONL = Path("06_audits/abpath_content_specs/v0_1/abpath_ap_content_specs_v0_1.jsonl")
DEFAULT_GAPFILL_DIR = Path("outputs/curriculum_gapfill_v0_4")
DEFAULT_MAP_JSONL = Path("outputs/curriculum_map_v0_4/curriculum_records_v0_4.jsonl")
DEFAULT_OUT_DIR = Path("06_audits/abpath_content_specs/v0_1/enrichment_to_curriculum_v0_4")

GAPFILL_FILES = (
    "lecture_abpath_gapfill_approved_v0_4.jsonl",
    "textbook_abpath_gapfill_approved_v0_4.jsonl",
    "lecture_abpath_gapfill_review_v0_4.csv",
    "textbook_abpath_gapfill_review_v0_4.csv",
    "lecture_abpath_gapfill_rejected_conflict_v0_4.csv",
    "textbook_abpath_gapfill_rejected_conflict_v0_4.csv",
)

PROTECTED_V04_FILES = (
    Path("outputs/curriculum_map_v0_4/curriculum_records_v0_4.jsonl"),
    Path("outputs/curriculum_map_v0_4/curriculum_tag_index_v0_4.sqlite"),
    Path("outputs/curriculum_map_v0_4/acceptance_summary_v0_4.json"),
    Path("06_audits/curriculum_gapfill/v0_4/curriculum_gapfill_map_v0_4_audit.json"),
)

CANDIDATE_FIELDS = [
    "curriculum_row_id",
    "record_id",
    "source_family",
    "source_id",
    "chunk_id",
    "curriculum_tag",
    "curriculum_root",
    "map_status",
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

ROOT_ALIASES: dict[str, set[str]] = {
    "Breast": {"breast"},
    "GU": {"gu", "kidney", "genitourinary", "prostate", "testis", "bladder", "urothelial", "penis"},
    "GI": {"gi", "gastrointestinal", "digestive", "colon", "liver", "pancreas", "biliary", "esophagus", "stomach"},
    "HN": {"hn", "head", "neck", "oral", "salivary", "larynx", "pharynx", "nasal", "temporal"},
    "Endo": {"endo", "thyroid", "pituitary", "parathyroid", "adrenal", "endocrine"},
    "Skin": {"skin", "derm", "dermatopathology"},
    "BST": {"bst", "bone", "soft tissue", "joint", "joints", "skeletal"},
    "GYN": {"gyn", "gynecologic", "uterus", "ovary", "cervix", "vulva", "vagina", "placenta", "fallopian"},
    "Thorax_Mediastinum": {"thorax", "respiratory", "pleura", "mediastinum", "lung"},
    "Neuro": {"neuro", "neuropathology", "brain", "spinal", "meninges"},
    "Heme": {"heme", "hematopathology", "hematology", "lymphoma", "leukemia", "marrow"},
    "Peds": {"peds", "pediatric", "paediatric", "perinatal"},
    "Eye_Orbit": {"eye", "ocular", "orbit"},
    "Cyto": {"cyto", "cytopathology"},
    "Molecular": {"molecular"},
    "Forensic": {"forensic"},
}

MAJOR_SECTION_ROOT_HINTS: dict[int, set[str]] = {
    1: {"breast"},
    2: {"gu", "kidney", "genitourinary", "bladder", "urothelial"},
    3: {"gu", "prostate", "testis", "penis"},
    4: {"cardiovascular"},
    5: {"hn", "head", "neck", "oral", "salivary", "larynx"},
    6: {"gi", "gastrointestinal", "liver", "pancreas", "biliary"},
    7: {"endo", "thyroid", "pituitary", "parathyroid", "adrenal"},
    8: {"gyn", "uterus", "ovary", "cervix", "vulva", "vagina"},
    9: {"gyn", "placenta"},
    10: {"thorax", "respiratory", "pleura", "mediastinum"},
    11: {"bst", "bone", "soft tissue", "joint"},
    12: {"cyto", "cytopathology"},
    13: {"skin", "derm", "dermatopathology"},
    14: {"forensic"},
    16: {"heme", "hematopathology"},
    17: {"neuro", "neuropathology"},
    18: {"peds", "pediatric"},
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip()


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def tag_leaf(tag: str) -> str:
    leaf = tag.split("::")[-1] if tag else ""
    leaf = leaf.replace("_", " ").replace("-", " ")
    leaf = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", leaf)
    return normalize_whitespace(leaf)


def curriculum_root_family(root: str) -> str:
    root = root or ""
    if "::" in root:
        return root.split("::", 1)[0]
    if root.startswith("Cyto_"):
        return "Cyto"
    return root


def root_tokens_for_curriculum(root: str) -> set[str]:
    family = curriculum_root_family(root)
    values = {slugify(family), slugify(root)}
    values.update(ROOT_ALIASES.get(family, set()))
    if "::" in root:
        values.add(slugify(root.split("::", 1)[1]))
    return {value for value in values if value}


def root_tokens_for_abpath(row: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    major = row.get("major_section", "")
    match = re.match(r"^(\d+)\.", major)
    if match:
        values.update(MAJOR_SECTION_ROOT_HINTS.get(int(match.group(1)), set()))
    blob = " ".join(
        [
            str(row.get("major_section") or ""),
            str(row.get("organ_system") or ""),
            str(row.get("subsection") or ""),
            str(row.get("category") or ""),
            str(row.get("raw_path") or ""),
        ]
    ).lower()
    for family, aliases in ROOT_ALIASES.items():
        if any(alias in blob for alias in aliases):
            values.add(slugify(family))
            values.update(aliases)
    return {slugify(value) for value in values if value}


def roots_compatible(curriculum_root: str, abpath_row: dict[str, Any]) -> bool:
    left = root_tokens_for_curriculum(curriculum_root)
    right = root_tokens_for_abpath(abpath_row)
    if not left or not right:
        return True
    if left & right:
        return True
    # Cytopathology curriculum tags may align loosely with organ-specific AP rows.
    if "cyto" in left and right & {"gi", "gyn", "gu", "hn", "breast", "lung", "thyroid", "heme", "neuro"}:
        return True
    return False


def token_overlap_score(left: str, right: str) -> float:
    left_tokens = tokens(left)
    right_tokens = tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    inter = left_tokens & right_tokens
    if not inter:
        return 0.0
    union = left_tokens | right_tokens
    return 100.0 * len(inter) / len(union)


def lexical_score(left: str, right: str) -> float:
    left_n = slugify(left)
    right_n = slugify(right)
    if not left_n or not right_n:
        return 0.0
    if left_n == right_n:
        return 100.0
    if left_n in right_n or right_n in left_n:
        return 95.0
    seq = difflib.SequenceMatcher(None, left_n, right_n).ratio() * 100.0
    overlap = token_overlap_score(left, right)
    return max(seq, overlap)


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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_abpath_rows(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def iter_gapfill_rows(gapfill_dir: Path):
    for name in GAPFILL_FILES:
        path = gapfill_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Missing gapfill artifact: {path}")
        if path.suffix == ".jsonl":
            for row in read_jsonl(path):
                yield normalize_curriculum_row(row)
        else:
            for row in read_csv_rows(path):
                yield normalize_curriculum_row(row)


def load_gapfill_rows(gapfill_dir: Path) -> list[dict[str, Any]]:
    return list(iter_gapfill_rows(gapfill_dir))


def load_unique_curriculum_tags(map_jsonl: Path) -> list[dict[str, Any]]:
    seen: set[str] = set()
    tags: list[dict[str, Any]] = []
    for row in read_jsonl(map_jsonl):
        tag = str(row.get("approved_tag") or row.get("original_tag") or "")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(
            {
                "curriculum_row_id": f"tag::{tag}",
                "record_id": str(row.get("record_id") or f"tag::{tag}"),
                "source_family": str(row.get("source") or ""),
                "source_id": "",
                "chunk_id": "",
                "curriculum_tag": tag,
                "curriculum_root": str(row.get("root") or curriculum_root_family(tag)),
                "map_status": str(row.get("status") or ""),
                "text_excerpt": str(row.get("title") or tag_leaf(tag))[:500],
            }
        )
    return tags


def normalize_curriculum_row(raw: dict[str, Any]) -> dict[str, Any]:
    chunk_id = str(raw.get("chunk_id") or "")
    tag = str(raw.get("abpath_tag") or raw.get("curriculum_tag") or raw.get("approved_tag") or "")
    return {
        "curriculum_row_id": chunk_id or str(raw.get("record_id") or raw.get("curriculum_row_id") or ""),
        "record_id": chunk_id or str(raw.get("record_id") or ""),
        "source_family": str(raw.get("source_family") or raw.get("source") or ""),
        "source_id": str(raw.get("source_id") or ""),
        "chunk_id": chunk_id,
        "curriculum_tag": tag,
        "curriculum_root": str(raw.get("root") or curriculum_root_family(tag)),
        "map_status": str(raw.get("map_status") or raw.get("status") or ""),
        "text_excerpt": normalize_whitespace(str(raw.get("text_excerpt") or raw.get("title") or ""))[:500],
    }


def build_abpath_indexes(abpath_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_item_slug: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_token: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_key_suffix: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_id: dict[str, dict[str, Any]] = {}

    for row in abpath_rows:
        by_id[row["abpath_spec_id"]] = row
        by_key[row["normalized_item_key"]].append(row)
        item_slug = slugify(row["item_text"])
        by_item_slug[item_slug].append(row)
        suffix = item_slug.rsplit("_", 1)[-1]
        if suffix:
            by_key_suffix[suffix].append(row)
        for hint in root_tokens_for_abpath(row):
            by_bucket[hint].append(row)
        for token in tokens(row["item_text"]):
            if len(token) >= 4:
                by_token[token].append(row)
    return {
        "by_key": by_key,
        "by_item_slug": by_item_slug,
        "by_bucket": by_bucket,
        "by_token": by_token,
        "by_key_suffix": by_key_suffix,
        "by_id": by_id,
        "all": abpath_rows,
    }


def candidate_abpath_pool(
    indexes: dict[str, Any],
    curriculum_root: str,
    tag: str,
    leaf_slug: str,
) -> list[dict[str, Any]]:
    pool: dict[str, dict[str, Any]] = {}

    if leaf_slug in indexes["by_item_slug"]:
        for row in indexes["by_item_slug"][leaf_slug]:
            pool[row["abpath_spec_id"]] = row

    for token in tokens(tag_leaf(tag)):
        if len(token) < 4:
            continue
        for row in indexes["by_token"].get(token, []):
            pool[row["abpath_spec_id"]] = row

    for hint in root_tokens_for_curriculum(curriculum_root):
        for row in indexes["by_bucket"].get(hint, [])[:250]:
            pool[row["abpath_spec_id"]] = row

    if pool:
        return list(pool.values())

    return indexes["all"][:300]


def score_match(
    curriculum_row: dict[str, Any],
    abpath_row: dict[str, Any],
    indexes: dict[str, Any],
) -> tuple[str, float, str, bool]:
    tag = curriculum_row["curriculum_tag"]
    leaf = tag_leaf(tag)
    leaf_slug = slugify(leaf)
    abpath_key = abpath_row["normalized_item_key"]
    abpath_text = abpath_row["item_text"]
    compatible = roots_compatible(curriculum_row["curriculum_root"], abpath_row)

    if leaf_slug and leaf_slug == slugify(abpath_text):
        return "exact_item_text_leaf", 100.0, "Exact normalized tag-leaf match to ABPath item_text", compatible
    if leaf_slug and abpath_key.endswith(leaf_slug):
        return "exact_normalized_item_key", 100.0, "Tag leaf matches ABPath normalized_item_key suffix", compatible
    if leaf_slug in indexes["by_key"] and abpath_row in indexes["by_key"][leaf_slug]:
        return "exact_normalized_item_key", 100.0, "Exact normalized_item_key index hit", compatible

    derived_key = slugify(f"{curriculum_row['curriculum_root']} {leaf}")
    if derived_key and (derived_key in indexes["by_key"]) and abpath_row in indexes["by_key"][derived_key]:
        return "exact_normalized_item_key", 98.0, "Derived normalized key match", compatible

    title_score = lexical_score(leaf, abpath_text)
    path_score = lexical_score(leaf, abpath_row.get("raw_path", ""))
    excerpt_score = lexical_score(curriculum_row.get("text_excerpt", ""), abpath_text) * 0.85
    score = max(title_score, path_score, excerpt_score)
    if score >= 70:
        return "fuzzy_lexical", round(score, 2), "Lexical similarity between curriculum tag/text and ABPath item/path", compatible
    return "no_match", round(score, 2), "Insufficient lexical similarity", compatible


def classify_confidence(match_type: str, score: float, compatible: bool) -> str:
    if match_type == "no_match":
        return "reject"
    if not compatible:
        if score >= 95 and match_type.startswith("exact"):
            return "low"
        if score >= 85:
            return "low"
        return "reject"
    if match_type in {"exact_normalized_item_key", "exact_item_text_leaf"} and score >= 98:
        return "high"
    if match_type.startswith("exact") and score >= 95:
        return "high"
    if score >= 85:
        return "medium"
    if score >= 70:
        return "low"
    return "reject"


def best_match_for_row(
    curriculum_row: dict[str, Any],
    indexes: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    tag = curriculum_row["curriculum_tag"]
    leaf = tag_leaf(tag)
    leaf_slug = slugify(leaf)

    if leaf_slug in indexes["by_item_slug"]:
        for abpath_row in indexes["by_item_slug"][leaf_slug]:
            compatible = roots_compatible(curriculum_row["curriculum_root"], abpath_row)
            confidence = "high" if compatible else "low"
            warning = ""
            if not compatible:
                warning = "Cross-root candidate; requires human review and is not specialty-board promotion."
            if abpath_row.get("specialty_board_scope") == "AP_resident_topic_only_not_subspecialty_board_spec":
                warning = normalize_whitespace(
                    f"{warning} AP-resident-topic only; not separate specialty-board specification.".strip()
                )
            return abpath_row, {
                "match_type": "exact_item_text_leaf",
                "match_score": 100.0,
                "match_confidence": confidence,
                "match_reason": "Exact normalized tag-leaf match to ABPath item_text",
                "warning": warning,
                "cross_root": not compatible,
            }

    if leaf_slug in indexes["by_key_suffix"]:
        for abpath_row in indexes["by_key_suffix"][leaf_slug]:
            compatible = roots_compatible(curriculum_row["curriculum_root"], abpath_row)
            confidence = "high" if compatible else "low"
            return abpath_row, {
                "match_type": "exact_normalized_item_key",
                "match_score": 100.0,
                "match_confidence": confidence,
                "match_reason": "Tag leaf matches ABPath normalized_item_key suffix",
                "warning": "" if compatible else "Cross-root candidate; requires human review and is not specialty-board promotion.",
                "cross_root": not compatible,
            }

    search_pool = candidate_abpath_pool(indexes, curriculum_row["curriculum_root"], tag, leaf_slug)
    best_abpath: dict[str, Any] | None = None
    best_result = {
        "match_type": "no_match",
        "match_score": 0.0,
        "match_confidence": "reject",
        "match_reason": "No ABPath candidate exceeded threshold",
        "warning": "",
        "cross_root": False,
    }

    for abpath_row in search_pool:
        match_type, score, reason, compatible = score_match(curriculum_row, abpath_row, indexes)
        confidence = classify_confidence(match_type, score, compatible)
        if confidence == "reject":
            continue
        warning = ""
        cross_root = not compatible
        if cross_root:
            warning = "Cross-root candidate; requires human review and is not specialty-board promotion."
        if abpath_row.get("specialty_board_scope") == "AP_resident_topic_only_not_subspecialty_board_spec":
            warning = normalize_whitespace(
                f"{warning} AP-resident-topic only; not separate specialty-board specification.".strip()
            )
        rank = ({"high": 3, "medium": 2, "low": 1}[confidence], score)
        best_rank = (
            {"high": 3, "medium": 2, "low": 1}.get(best_result["match_confidence"], 0),
            best_result["match_score"],
        )
        if rank > best_rank:
            best_abpath = abpath_row
            best_result = {
                "match_type": match_type,
                "match_score": score,
                "match_confidence": confidence,
                "match_reason": reason,
                "warning": warning,
                "cross_root": cross_root,
            }
    return best_abpath, best_result


def build_candidate_row(curriculum_row: dict[str, Any], abpath_row: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "curriculum_row_id": curriculum_row["curriculum_row_id"],
        "record_id": curriculum_row["record_id"],
        "source_family": curriculum_row["source_family"],
        "source_id": curriculum_row["source_id"],
        "chunk_id": curriculum_row["chunk_id"],
        "curriculum_tag": curriculum_row["curriculum_tag"],
        "curriculum_root": curriculum_row["curriculum_root"],
        "map_status": curriculum_row["map_status"],
        "text_excerpt": curriculum_row["text_excerpt"],
        "abpath_spec_id": abpath_row["abpath_spec_id"],
        "abpath_item_text": abpath_row["item_text"],
        "abpath_raw_path": abpath_row["raw_path"],
        "abpath_level": abpath_row["abpath_level"],
        "abpath_level_label": abpath_row["abpath_level_label"],
        "expected_resident_depth": abpath_row["expected_resident_depth"],
        "specialty_board_scope": abpath_row["specialty_board_scope"],
        "match_type": result["match_type"],
        "match_score": result["match_score"],
        "match_confidence": result["match_confidence"],
        "match_reason": result["match_reason"],
        "warning": result.get("warning", ""),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def fingerprint_paths(paths: tuple[Path, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in paths:
        if not path.exists():
            out[str(path)] = {"missing": True}
            continue
        stat = path.stat()
        out[str(path)] = {"size": stat.st_size, "mtime": stat.st_mtime}
    return out


def write_readme(path: Path) -> None:
    path.write_text(
        """# ABPath → v0_4 Curriculum Enrichment Experiment

## Purpose

Read-only sidecar that proposes ABPath **training-level** metadata (`C` / `AR` / `F`) for v0_4 curriculum gapfill/map rows. This does **not** modify v0_4 outputs or `map_status`.

## Inputs

- `06_audits/abpath_content_specs/v0_1/abpath_ap_content_specs_v0_1.jsonl`
- `outputs/curriculum_gapfill_v0_4/*_v0_4.{jsonl,csv}`

## Matching order

1. Exact `normalized_item_key` / tag-leaf suffix
2. Exact normalized `item_text` ↔ curriculum tag leaf
3. Fuzzy lexical match on tag leaf, ABPath `item_text`, and `raw_path`
4. Root-aware candidate pooling (Breast, GU, GI, HN, Skin, BST, etc.)
5. No forced match below threshold

## Confidence

| Level | Meaning |
|-------|---------|
| high | Exact normalized or tag-leaf match with compatible root |
| medium | Strong lexical match with compatible root |
| low | Fuzzy or cross-root candidate — human review only |
| reject | Not emitted as a candidate row |

## Safety

- `map_status` is copied verbatim for traceability only.
- `abpath_level` is training metadata only.
- Neuro/peds/heme ABPath rows retain `AP_resident_topic_only_not_subspecialty_board_spec`.
- Not API/live and not uploaded to GCS.
""",
        encoding="utf-8",
    )


def run_enrichment(
    *,
    abpath_jsonl: Path,
    gapfill_dir: Path,
    map_jsonl: Path,
    out_dir: Path,
) -> dict[str, Any]:
    before_fp = fingerprint_paths(PROTECTED_V04_FILES)

    abpath_rows = load_abpath_rows(abpath_jsonl)
    indexes = build_abpath_indexes(abpath_rows)

    gapfill_unique_tags: dict[str, dict[str, Any]] = {}
    curriculum_row_count = 0
    for row in iter_gapfill_rows(gapfill_dir):
        curriculum_row_count += 1
        tag = row["curriculum_tag"]
        if tag and tag not in gapfill_unique_tags:
            gapfill_unique_tags[tag] = row

    tag_enrichment: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    warnings: list[dict[str, Any]] = []
    matched_abpath_ids: set[str] = set()

    for tag, template_row in gapfill_unique_tags.items():
        abpath_row, result = best_match_for_row(template_row, indexes)
        if not abpath_row:
            continue
        tag_enrichment[tag] = (abpath_row, result)
        matched_abpath_ids.add(abpath_row["abpath_spec_id"])
        if result.get("cross_root"):
            warnings.append(
                {
                    "curriculum_row_id": template_row["curriculum_row_id"],
                    "curriculum_tag": tag,
                    "abpath_spec_id": abpath_row["abpath_spec_id"],
                    "warning_type": "cross_root_candidate",
                    "detail": result.get("warning", ""),
                }
            )
        if result["match_confidence"] == "low":
            warnings.append(
                {
                    "curriculum_row_id": template_row["curriculum_row_id"],
                    "curriculum_tag": tag,
                    "abpath_spec_id": abpath_row["abpath_spec_id"],
                    "warning_type": "low_confidence_match",
                    "detail": result.get("match_reason", ""),
                }
            )

    candidates: list[dict[str, Any]] = []
    for curriculum_row in iter_gapfill_rows(gapfill_dir):
        tag = curriculum_row["curriculum_tag"]
        hit = tag_enrichment.get(tag)
        if not hit:
            continue
        abpath_row, result = hit
        candidates.append(build_candidate_row(curriculum_row, abpath_row, result))

    matched_tags = set(tag_enrichment.keys())
    unmatched_curriculum_tags = [
        row for tag, row in gapfill_unique_tags.items() if tag not in matched_tags
    ]

    unmatched_abpath_rows = [
        {
            "abpath_spec_id": row["abpath_spec_id"],
            "abpath_item_text": row["item_text"],
            "abpath_raw_path": row["raw_path"],
            "abpath_level": row["abpath_level"],
            "major_section": row["major_section"],
            "specialty_board_scope": row["specialty_board_scope"],
        }
        for row in abpath_rows
        if row["abpath_spec_id"] not in matched_abpath_ids
    ]

    after_fp = fingerprint_paths(PROTECTED_V04_FILES)
    if before_fp != after_fp:
        raise RuntimeError("Protected v0_4 artifacts changed during enrichment run")

    out_dir.mkdir(parents=True, exist_ok=True)
    candidates_csv = out_dir / "abpath_to_curriculum_v0_4_enrichment_candidates.csv"
    candidates_jsonl = out_dir / "abpath_to_curriculum_v0_4_enrichment_candidates.jsonl"
    audit_json = out_dir / "abpath_to_curriculum_v0_4_enrichment_audit.json"
    unmatched_abpath_csv = out_dir / "abpath_to_curriculum_v0_4_unmatched_abpath_rows.csv"
    unmatched_curriculum_csv = out_dir / "abpath_to_curriculum_v0_4_unmatched_curriculum_tags.csv"
    warnings_csv = out_dir / "abpath_to_curriculum_v0_4_match_warnings.csv"
    readme = out_dir / "README.md"

    write_csv(candidates_csv, candidates, CANDIDATE_FIELDS)
    write_jsonl(candidates_jsonl, candidates)
    write_csv(
        unmatched_abpath_csv,
        unmatched_abpath_rows,
        [
            "abpath_spec_id",
            "abpath_item_text",
            "abpath_raw_path",
            "abpath_level",
            "major_section",
            "specialty_board_scope",
        ],
    )
    write_csv(
        unmatched_curriculum_csv,
        unmatched_curriculum_tags,
        [
            "curriculum_row_id",
            "record_id",
            "curriculum_tag",
            "curriculum_root",
            "map_status",
            "text_excerpt",
        ],
    )
    write_csv(
        warnings_csv,
        warnings,
        ["curriculum_row_id", "curriculum_tag", "abpath_spec_id", "warning_type", "detail"],
    )
    write_readme(readme)

    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "input_paths": {
            "abpath_jsonl": str(abpath_jsonl),
            "gapfill_dir": str(gapfill_dir),
            "map_jsonl": str(map_jsonl),
        },
        "output_paths": {
            "candidates_csv": str(candidates_csv),
            "candidates_jsonl": str(candidates_jsonl),
            "audit_json": str(audit_json),
            "unmatched_abpath_csv": str(unmatched_abpath_csv),
            "unmatched_curriculum_csv": str(unmatched_curriculum_csv),
            "warnings_csv": str(warnings_csv),
            "readme": str(readme),
        },
        "total_v0_4_rows_considered": curriculum_row_count,
        "unique_gapfill_tags_considered": len(gapfill_unique_tags),
        "unique_gapfill_tags_matched": len(tag_enrichment),
        "total_abpath_rows": len(abpath_rows),
        "matched_rows_total": len(candidates),
        "matched_rows_by_confidence": dict(Counter(row["match_confidence"] for row in candidates)),
        "matched_rows_by_abpath_level": dict(Counter(row["abpath_level"] for row in candidates)),
        "matched_rows_by_curriculum_root": dict(Counter(row["curriculum_root"] for row in candidates).most_common(25)),
        "unmatched_abpath_rows": len(unmatched_abpath_rows),
        "unmatched_curriculum_tags": len(unmatched_curriculum_tags),
        "cross_root_candidate_count": sum(1 for warning in warnings if warning["warning_type"] == "cross_root_candidate"),
        "ambiguous_match_count": sum(1 for row in candidates if row["match_confidence"] == "low"),
        "neuro_peds_heme_ap_only_match_count": sum(
            1
            for row in candidates
            if row.get("specialty_board_scope") == "AP_resident_topic_only_not_subspecialty_board_spec"
        ),
        "warnings_count": len(warnings),
        "limitations": [
            "Read-only sidecar experiment; v0_4 outputs were fingerprint-checked and not modified.",
            "Matching uses lexical heuristics only; no vector/FAISS similarity.",
            "C/AR/F are attached as training-level metadata only, never as map_status.",
            "Low-confidence and cross-root matches are emitted for review but are not final assignments.",
            "Tag-level matching is computed once per unique gapfill tag and projected to all chunk rows sharing that tag.",
        ],
        "protected_v0_4_fingerprint_unchanged": True,
    }
    audit_json.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abpath-jsonl", type=Path, default=DEFAULT_ABPATH_JSONL)
    parser.add_argument("--gapfill-dir", type=Path, default=DEFAULT_GAPFILL_DIR)
    parser.add_argument("--map-jsonl", type=Path, default=DEFAULT_MAP_JSONL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = run_enrichment(
        abpath_jsonl=args.abpath_jsonl,
        gapfill_dir=args.gapfill_dir,
        map_jsonl=args.map_jsonl,
        out_dir=args.out_dir,
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
