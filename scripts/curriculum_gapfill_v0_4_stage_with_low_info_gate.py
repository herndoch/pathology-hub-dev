#!/usr/bin/env python3
"""Stage Curriculum Gap Fill/Map v0.4 with a low-information gate."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import html
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "curriculum_gapfill_map_v0_4"
DEFAULT_V02_DIR = Path("outputs/curriculum_map_v0_2")
DEFAULT_V03_GAPFILL_DIR = Path("outputs/curriculum_gapfill_v0_3")
DEFAULT_LECTURES = Path("data/curriculum_map_v0_2/lecture_timecoded_tagged_chunks_ROUTED_ONLY_STRICT_CYTO_v9.jsonl")
DEFAULT_TEXTBOOKS = Path("data/curriculum_map_v0_2/textbook_primary_tagged_chunks_v1.jsonl")
DEFAULT_GAPFILL_OUT = Path("outputs/curriculum_gapfill_v0_4")
DEFAULT_MAP_OUT = Path("outputs/curriculum_map_v0_4")
DEFAULT_AUDIT_OUT = Path("06_audits/curriculum_gapfill/v0_4")
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
MAP_STATUSES = ("approved", "review", "rejected_conflict", "low_information", "unmapped_no_confident_tag")
LOW_INFO_PATTERNS = (
    r"\b(thank you|thanks|okay|ok|all right|alright|next slide|moving on|any questions|question|questions|can you hear|audio|microphone)\b",
    r"\b(break|pause|housekeeping|welcome|introduction|agenda|objectives|disclosures?)\b",
    r"\b(references?|bibliography|acknowledg(e)?ments?|copyright|permission)\b",
)
HARD_LOW_INFO_PATTERNS = (
    r"^\s*(okay|ok|thanks|thank you|you|yes|no|right|next|slide)\s*[.!?]?\s*$",
    r"\b(next slide|any questions|that's it for today|that is it for today|hi everyone|welcome)\b",
    r"\b(black image|video conference screen|non[- ]diagnostic conference|conference low[- ]content slide)\b",
    r"\b(raw transcript:\s*(you|okay|ok|um|uh)?\s*$)\b",
)
FILLER_TERMS = {"okay", "ok", "um", "uh", "yeah", "yes", "no", "right", "so", "well", "thanks", "thank", "next", "slide"}
PATHOLOGY_TERMS = {
    "adenoma",
    "adenocarcinoma",
    "atypia",
    "atypical",
    "biopsy",
    "carcinoma",
    "chromatin",
    "cytoplasm",
    "cytoplasmic",
    "cytology",
    "diagnosis",
    "differential",
    "dysplasia",
    "eosinophils",
    "fibrosis",
    "grade",
    "granuloma",
    "granulomatous",
    "histology",
    "hyperplasia",
    "immunohistochemistry",
    "infiltrative",
    "invasion",
    "invasive",
    "keratin",
    "lesion",
    "lymphoma",
    "malignancy",
    "marker",
    "metaplasia",
    "metastasis",
    "mitoses",
    "molecular",
    "mucin",
    "mutation",
    "necrosis",
    "neoplasm",
    "nuclear",
    "nuclei",
    "nucleoli",
    "papillary",
    "pleomorphic",
    "sarcoma",
    "squamous",
    "stain",
    "tumor",
    "suppurative",
    "dermal",
    "epidermal",
    "subepidermal",
    "intraepidermal",
    "adnexal",
    "follicular",
    "basaloid",
    "glandular",
    "mucinous",
    "spindle",
    "epithelioid",
    "pagetoid",
    "lichenoid",
    "interface",
    "vasculitis",
    "lymphocytic",
    "neutrophilic",
    "melanocyte",
    "melanocytes",
    "sarcoid",
    "sarcoidosis",
    "acantholysis",
    "creeping",
    "glycogen",
    "collagen",
    "elastin",
    "fibroblast",
    "fibroblasts",
    "vessels",
    "vascular",
    "marrow",
    "periosteal",
    "periosteum",
    "cortical",
    "cortex",
    "medulla",
    "cartilage",
    "chondroid",
    "osteoid",
    "amyloid",
    "amyloidosis",
    "panniculitis",
    "paget",
    "adnexa",
    "sebaceous",
    "eccrine",
    "apocrine",
}
PROTECTED_PATHOLOGY_PHRASES = (
    "clear cell",
    "pale cells",
    "granular layer",
    "reaction pattern",
    "sharp cutoff",
    "plasma cells",
    "paget disease",
)
GENERIC_TAG_LEAF_TERMS = {
    "skin",
    "hn",
    "bst",
    "breast",
    "gyn",
    "gu",
    "heme",
    "molecular",
    "lecture",
    "chapter",
    "unknown",
    "unmapped",
    "_unmapped_",
    "overview",
    "nos",
    "other",
    "miscellaneous",
    "category",
    "atypical",
    "benign",
    "malignant",
    "tumor",
    "tumors",
    "neoplasm",
    "neoplasms",
    "lesion",
    "lesions",
    "disease",
    "diagnosis",
    "diagnostic",
    "differential",
    "pathology",
}
MARKER_RE = re.compile(r"\b(p16|p53|ki-?67|er|pr|her2|cd[0-9]+|ck7|ck20|sox10|s100|gata3|ttf-?1|napsin|braf|egfr|alk|ros1|idh|tert|hpv|ebv)\b", re.I)
ENTITY_RE = re.compile(r"\b([a-z]+oma|carcinoma|sarcoma|lymphoma|leukemia|melanoma|mesothelioma|chondrosarcoma|osteosarcoma|glioma|nevus|cyst|granuloma|dysplasia)\b", re.I)


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path} line {line_no}: {exc}") from exc


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    fields = fieldnames or []
    seen = set(fields)
    for row in rows:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def has_forbidden(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else str(value)
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


def clean_text(value: str, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:limit] if limit else text


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def root_of(tag: str) -> str:
    return tag.split("::", 1)[0] if "::" in tag else tag


def tag_leaf_phrase(tag: str) -> str:
    leaf = tag.split("::")[-1] if tag else ""
    leaf = leaf.replace("_", " ").replace("-", " ")
    leaf = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", leaf)
    return clean_text(leaf).lower()


def contains_controlled_tag_phrase(text: str, tag: str) -> bool:
    phrase = tag_leaf_phrase(tag)
    return bool(phrase and len(phrase) >= 4 and re.search(r"\b" + re.escape(phrase) + r"\b", text.lower()))


def source_tag_leaf_is_specific(tag: str) -> bool:
    phrase = tag_leaf_phrase(tag)
    if not phrase or phrase in GENERIC_TAG_LEAF_TERMS:
        return False
    toks = [token for token in tokens(phrase) if token not in GENERIC_TAG_LEAF_TERMS]
    if not toks:
        return False
    if len(toks) == 1 and toks[0] in GENERIC_TAG_LEAF_TERMS:
        return False
    if MARKER_RE.search(phrase) or ENTITY_RE.search(phrase):
        return True
    if set(toks) & PATHOLOGY_TERMS:
        return True
    if any(protected in phrase for protected in PROTECTED_PATHOLOGY_PHRASES):
        return True
    return len(toks) >= 2 and len(phrase) >= 8


def source_tags_for_candidate(row: dict[str, Any], meta: dict[str, str]) -> list[str]:
    tags = [
        str(row.get("original_existing_tag") or ""),
        str(row.get("prior_or_source_tag") or ""),
        str(row.get("source_tag") or ""),
        str(row.get("existing_tag") or ""),
        str(meta.get("prior_or_source_tag") or ""),
        str(meta.get("source_primary_tag") or ""),
    ]
    return [tag for tag in tags if tag and tag != "_UNMAPPED_"]


def source_tags_for_chunk(meta: dict[str, str]) -> list[str]:
    tags = [
        str(meta.get("prior_or_source_tag") or ""),
        str(meta.get("source_primary_tag") or ""),
    ]
    return [tag for tag in tags if tag and tag != "_UNMAPPED_"]


def source_titles_for_candidate(meta: dict[str, str]) -> list[str]:
    title = str(meta.get("source_title") or "")
    return [title] if title else []


def source_titles_for_chunk(meta: dict[str, str]) -> list[str]:
    title = str(meta.get("source_title") or "")
    return [title] if title else []


def classify_low_information_with_context(
    text: str,
    source_family: str,
    candidate_tags: list[str] | None,
    source_tags: list[str] | None,
    context_label: str,
    source_titles: list[str] | None = None,
) -> tuple[bool, str]:
    if source_tags is None:
        raise RuntimeError(f"classify_low_information called without explicit source-tag context in {context_label}")
    return classify_low_information(text, source_family, candidate_tags or [], source_tags, source_titles or [])


def pathology_signal_reason(
    text: str,
    candidate_tags: list[str] | None = None,
    source_tags: list[str] | None = None,
    source_titles: list[str] | None = None,
    allow_source_context: bool = True,
) -> str:
    text_l = text.lower()
    toks = set(tokens(text_l))
    if toks & PATHOLOGY_TERMS:
        return "protected_morphology_site_or_concept_term"
    if any(re.search(r"\b" + re.escape(phrase) + r"\b", text_l) for phrase in PROTECTED_PATHOLOGY_PHRASES):
        return "protected_morphology_site_or_concept_phrase"
    if MARKER_RE.search(text_l):
        return "marker_gene_or_fusion_signal"
    if ENTITY_RE.search(text_l):
        return "disease_or_entity_name_signal"
    if any(contains_controlled_tag_phrase(text_l, tag) for tag in candidate_tags or []):
        return "controlled_candidate_tag_phrase_signal"
    if allow_source_context and any(source_tag_leaf_is_specific(tag) for tag in source_tags or []):
        return "specific_source_tag_leaf_context_signal"
    if allow_source_context and any(source_tag_leaf_is_specific(title) for title in source_titles or []):
        return "source_title_context_signal"
    return ""


def has_meaningful_pathology_signal(
    text: str,
    candidate_tags: list[str] | None = None,
    source_tags: list[str] | None = None,
    source_titles: list[str] | None = None,
) -> bool:
    return bool(pathology_signal_reason(text, candidate_tags, source_tags, source_titles))


def minimal_meaningful_text_context(text: str) -> bool:
    toks = tokens(text)
    non_filler = [token for token in toks if token not in FILLER_TERMS]
    if any(re.search(pattern, text, re.I) for pattern in HARD_LOW_INFO_PATTERNS):
        return False
    if len(non_filler) < 5:
        return False
    return True


def hard_low_information_reason(text: str, source_family: str, has_text_pathology_signal: bool) -> str:
    toks = tokens(text)
    filler_ratio = sum(1 for token in toks if token in FILLER_TERMS) / max(1, len(toks))
    if has_text_pathology_signal:
        return ""
    for pattern in HARD_LOW_INFO_PATTERNS:
        if re.search(pattern, text, re.I):
            return "hard_low_information_housekeeping_artifact_or_transcript_noise"
    if len(toks) < 3:
        return "hard_low_information_too_short_without_text_pathology_signal"
    if len(toks) < 40 and filler_ratio >= 0.45:
        return "hard_low_information_repeated_filler_or_transition"
    if any(re.search(pattern, text, re.I) for pattern in LOW_INFO_PATTERNS) and len(toks) < 45:
        return "hard_low_information_housekeeping_transition_question_acknowledgment_or_reference_only"
    if source_family == "textbooks" and len(toks) < 25 and re.search(r"\b(fig|figure|table|references?|caption)\b", text, re.I):
        return "hard_low_information_references_table_figure_or_caption_without_text_pathology_signal"
    return ""


def classify_low_information(
    text: str,
    source_family: str,
    candidate_tags: list[str] | None = None,
    source_tags: list[str] | None = None,
    source_titles: list[str] | None = None,
) -> tuple[bool, str]:
    cleaned = clean_text(text)
    toks = tokens(cleaned)
    text_signal_reason = pathology_signal_reason(cleaned, candidate_tags, [], [], allow_source_context=False)
    hard_reason = hard_low_information_reason(cleaned, source_family, bool(text_signal_reason))
    if hard_reason:
        return True, hard_reason
    source_signal_reason = pathology_signal_reason(cleaned, [], source_tags, source_titles, allow_source_context=True)
    source_context_specific = source_signal_reason in {"specific_source_tag_leaf_context_signal", "source_title_context_signal"}
    source_context_allowed = source_context_specific and minimal_meaningful_text_context(cleaned)
    signal_reason = text_signal_reason or (source_signal_reason if source_context_allowed else "")
    meaningful = bool(signal_reason)
    if len(toks) < 8 and not meaningful:
        return True, "too_short_without_pathology_signal"
    if len(toks) < 18 and not meaningful:
        return True, "very_short_context_poor_without_disease_entity_marker_or_concept"
    filler_ratio = sum(1 for token in toks if token in FILLER_TERMS) / max(1, len(toks))
    if len(toks) < 40 and filler_ratio >= 0.45 and not meaningful:
        return True, "repeated_filler_or_transition"
    if any(re.search(pattern, cleaned, re.I) for pattern in LOW_INFO_PATTERNS) and len(toks) < 45 and not meaningful:
        return True, "housekeeping_transition_question_acknowledgment_or_reference_only"
    if source_family == "textbooks" and len(toks) < 25 and re.search(r"\b(fig|figure|table|references?)\b", cleaned, re.I) and not meaningful:
        return True, "references_or_caption_fragment_without_pathology_signal"
    if len(toks) < 45 and meaningful:
        return False, f"short_chunk_retained_by_{signal_reason}"
    return False, "meaningful_pathology_content_or_sufficient_context"


def classify_low_information_legacy(text: str, source_family: str, candidate_tags: list[str] | None = None) -> tuple[bool, str]:
    cleaned = clean_text(text)
    toks = tokens(cleaned)
    text_l = cleaned.lower()
    meaningful = bool((set(toks) & {
        "adenoma", "adenocarcinoma", "atypia", "biopsy", "carcinoma", "chromatin", "cytology",
        "diagnosis", "differential", "dysplasia", "fibrosis", "grade", "granuloma", "histology",
        "immunohistochemistry", "invasion", "keratin", "lesion", "lymphoma", "malignancy",
        "marker", "metastasis", "mitoses", "molecular", "mucin", "mutation", "necrosis",
        "neoplasm", "papillary", "sarcoma", "squamous", "stain", "tumor",
    }) or MARKER_RE.search(text_l) or ENTITY_RE.search(text_l) or any(contains_controlled_tag_phrase(text_l, tag) for tag in candidate_tags or []))
    if len(toks) < 8 and not meaningful:
        return True, "too_short_without_pathology_signal"
    if len(toks) < 18 and not meaningful:
        return True, "very_short_context_poor_without_disease_entity_marker_or_concept"
    filler_ratio = sum(1 for token in toks if token in FILLER_TERMS) / max(1, len(toks))
    if len(toks) < 40 and filler_ratio >= 0.45 and not meaningful:
        return True, "repeated_filler_or_transition"
    if any(re.search(pattern, cleaned, re.I) for pattern in LOW_INFO_PATTERNS) and len(toks) < 45 and not meaningful:
        return True, "housekeeping_transition_question_acknowledgment_or_reference_only"
    if source_family == "textbooks" and len(toks) < 25 and re.search(r"\b(fig|figure|table|references?)\b", cleaned, re.I) and not meaningful:
        return True, "references_or_caption_fragment_without_pathology_signal"
    return False, "meaningful_pathology_content_or_sufficient_context"


def chunk_text(row: dict[str, Any], source_family: str) -> tuple[str, dict[str, str]]:
    if source_family == "lectures":
        text = " ".join(str(row.get(key) or "") for key in ("title", "summary", "transcript_text", "tag_basis"))
        source_id = str(row.get("video_id") or row.get("raw_source_gcs_uri") or "")
        title = str(row.get("title") or "")
        prior = str(row.get("primary_tag_governed") or row.get("primary_tag") or row.get("primary_tag_original_pre_governance_v10_4") or "")
        page_or_time = f"{row.get('start_sec', '')}-{row.get('end_sec', '')}".strip("-")
    else:
        text = " ".join(str(row.get(key) or "") for key in ("source_title", "chapter_title", "section_heading", "text", "primary_tag_basis") if row.get(key))
        source_id = str(row.get("source_id") or row.get("source_title") or row.get("raw_source_gcs_uri") or "")
        title = " | ".join(str(row.get(key) or "") for key in ("source_title", "chapter_title", "section_heading") if row.get(key))
        prior = str(row.get("primary_tag_governed") or row.get("primary_tag") or row.get("primary_tag_original_pre_governance_v10_4") or "")
        page_or_time = str(row.get("page") or "")
    return clean_text(text), {
        "chunk_id": str(row.get("chunk_id") or ""),
        "source_family": source_family,
        "source_id": source_id,
        "source_title": title,
        "page_or_time": page_or_time,
        "prior_or_source_tag": prior,
        "root": root_of(prior) if prior else "",
        "text": clean_text(text, 1400),
        "raw_source_gcs_uri": str(row.get("raw_source_gcs_uri") or ""),
        "normalized_artifact_gcs_uri": str(row.get("normalized_artifact_gcs_uri") or ""),
    }


def load_chunks(path: Path, source_family: str) -> dict[str, dict[str, str]]:
    chunks: dict[str, dict[str, str]] = {}
    for row in read_jsonl(path):
        text, meta = chunk_text(row, source_family)
        chunk_id = meta["chunk_id"]
        if not chunk_id:
            continue
        meta["full_text"] = text
        chunks[chunk_id] = meta
    return chunks


def load_candidates(path: Path) -> list[dict[str, Any]]:
    return list(read_jsonl(path))


def strong_candidate_signal(row: dict[str, Any]) -> bool:
    if bool(row.get("entity_phrase_hit")):
        return True
    if contains_controlled_tag_phrase(str(row.get("text_excerpt") or ""), str(row.get("abpath_tag") or "")):
        return True
    hits = []
    for key in ("who_phrase_hits", "pathout_phrase_hits", "textbook_phrase_hits", "lecture_phrase_hits"):
        value = row.get(key)
        if isinstance(value, list):
            hits.extend(value)
    return len([hit for hit in hits if str(hit).strip()]) >= 2


def candidate_map_status(row: dict[str, Any], low_info: bool, low_info_reason: str = "") -> str:
    if low_info and not strong_candidate_signal(row):
        return "low_information"
    decision = str(row.get("hybrid_decision") or "")
    if decision == "approved_hybrid_high":
        if low_info_reason in {
            "short_chunk_retained_by_disease_or_entity_name_signal",
            "short_chunk_retained_by_source_title_context_signal",
        }:
            return "review"
        return "approved"
    if decision == "review_hybrid":
        return "review"
    if decision == "rejected_hybrid":
        return "rejected_conflict"
    return "unmapped_no_confident_tag"


def status_sort_key(row: dict[str, Any]) -> tuple[int, float]:
    order = {"approved": 0, "review": 1, "rejected_conflict": 2, "low_information": 3, "unmapped_no_confident_tag": 4}
    return order.get(str(row.get("map_status")), 9), -float(row.get("hybrid_score") or 0)


def annotate_candidates(rows: list[dict[str, Any]], chunks: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    tags_by_chunk: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        tags_by_chunk[str(row.get("chunk_id") or "")].append(str(row.get("abpath_tag") or ""))
    out: list[dict[str, Any]] = []
    for row in rows:
        chunk_id = str(row.get("chunk_id") or "")
        meta = chunks.get(chunk_id, {})
        source_tag_context = source_tags_for_candidate(row, meta)
        source_title_context = source_titles_for_candidate(meta)
        low_info, reason = classify_low_information_with_context(
            meta.get("full_text") or str(row.get("text_excerpt") or ""),
            str(row.get("source_family") or ""),
            tags_by_chunk.get(chunk_id),
            source_tag_context,
            "annotate_candidates",
            source_title_context,
        )
        item = dict(row)
        item["schema_version"] = SCHEMA_VERSION
        item["map_status"] = candidate_map_status(row, low_info, reason)
        item["low_information_reason"] = reason if low_info else ""
        item["low_information_retention_reason"] = "" if low_info else reason
        item["source_tag_context"] = source_tag_context
        item["source_title_context"] = source_title_context
        item["source_tag_context_empty"] = not bool(source_tag_context)
        item["candidate_tag_used_as_source_context"] = False
        item["circular_candidate_tag_rescue"] = False
        item["hard_low_information_overrode_source_context"] = low_info and reason.startswith("hard_low_information_") and bool(source_tag_context or source_title_context)
        item["source_text_excerpt"] = meta.get("text", "")
        item["source_title"] = meta.get("source_title", "")
        item["page_or_time"] = meta.get("page_or_time", "")
        item["prior_or_source_tag"] = row.get("original_existing_tag") or meta.get("prior_or_source_tag", "")
        out.append(item)
    return out


def chunk_level_unmapped_rows(chunks: dict[str, dict[str, str]], candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tags_by_chunk: dict[str, list[str]] = defaultdict(list)
    for row in candidates:
        tags_by_chunk[str(row.get("chunk_id") or "")].append(str(row.get("abpath_tag") or ""))
    candidate_chunks = set(tags_by_chunk)
    low_rows: list[dict[str, Any]] = []
    unmapped_rows: list[dict[str, Any]] = []
    for chunk_id, meta in chunks.items():
        if chunk_id in candidate_chunks:
            continue
        source_tag_context = source_tags_for_chunk(meta)
        source_title_context = source_titles_for_chunk(meta)
        low_info, reason = classify_low_information_with_context(
            meta.get("full_text", ""),
            meta.get("source_family", ""),
            [],
            source_tag_context,
            "chunk_level_unmapped_rows",
            source_title_context,
        )
        row = {
            "schema_version": SCHEMA_VERSION,
            "map_status": "low_information" if low_info else "unmapped_no_confident_tag",
            "source_family": meta.get("source_family", ""),
            "chunk_id": chunk_id,
            "source_id": meta.get("source_id", ""),
            "root": meta.get("root", ""),
            "prior_or_source_tag": meta.get("prior_or_source_tag", ""),
            "low_information_reason": reason if low_info else "",
            "low_information_retention_reason": "" if low_info else reason,
            "source_tag_context": source_tag_context,
            "source_title_context": source_title_context,
            "source_tag_context_empty": not bool(source_tag_context),
            "candidate_tag_used_as_source_context": False,
            "circular_candidate_tag_rescue": False,
            "hard_low_information_overrode_source_context": low_info and reason.startswith("hard_low_information_") and bool(source_tag_context or source_title_context),
            "text_excerpt": meta.get("text", ""),
            "source_title": meta.get("source_title", ""),
            "page_or_time": meta.get("page_or_time", ""),
        }
        if low_info:
            low_rows.append(row)
        else:
            unmapped_rows.append(row)
    return low_rows, unmapped_rows


def split_status(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {status: [] for status in MAP_STATUSES}
    seen_approved: set[tuple[str, str]] = set()
    for row in sorted(rows, key=status_sort_key):
        status = str(row.get("map_status") or "unmapped_no_confident_tag")
        if status == "approved":
            key = (str(row.get("chunk_id") or ""), str(row.get("abpath_tag") or ""))
            if key in seen_approved:
                item = dict(row)
                item["map_status"] = "rejected_conflict"
                item["rejection_reason"] = "duplicate_chunk_id_abpath_tag"
                grouped["rejected_conflict"].append(item)
                continue
            seen_approved.add(key)
        grouped.setdefault(status, []).append(row)
    return grouped


def low_info_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(rows),
        "by_source_family": dict(Counter(str(row.get("source_family") or "") for row in rows).most_common()),
        "by_root": dict(Counter(str(row.get("root") or "") for row in rows).most_common(50)),
        "by_source_id": dict(Counter(str(row.get("source_id") or "") for row in rows).most_common(50)),
        "by_reason": dict(Counter(str(row.get("low_information_reason") or "") for row in rows).most_common()),
    }


def classifier_audit_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    retention_reasons = [str(row.get("low_information_retention_reason") or "") for row in rows]
    low_reasons = [str(row.get("low_information_reason") or "") for row in rows if str(row.get("map_status") or "") == "low_information"]
    protected_reasons = (
        "short_chunk_retained_by_protected_morphology_site_or_concept_term",
        "short_chunk_retained_by_protected_morphology_site_or_concept_phrase",
        "short_chunk_retained_by_marker_gene_or_fusion_signal",
        "short_chunk_retained_by_disease_or_entity_name_signal",
        "short_chunk_retained_by_controlled_candidate_tag_phrase_signal",
    )
    tag_context_reason = "short_chunk_retained_by_specific_source_tag_leaf_context_signal"
    title_context_reason = "short_chunk_retained_by_source_title_context_signal"
    return {
        "forbidden_single_tag_count": sum(1 for row in rows if has_forbidden(row.get("abpath_tag") or row.get("prior_or_source_tag") or row.get("original_existing_tag") or "")),
        "low_information_count": sum(1 for row in rows if str(row.get("map_status") or "") == "low_information"),
        "low_information_protected_signal_rescue_count": sum(1 for reason in retention_reasons if reason in protected_reasons or reason == tag_context_reason),
        "short_chunk_retained_by_protected_signal_count": sum(1 for reason in retention_reasons if reason in protected_reasons),
        "short_chunk_retained_by_source_tag_context_count": sum(1 for reason in retention_reasons if reason == tag_context_reason),
        "hard_low_information_count": sum(1 for reason in low_reasons if reason.startswith("hard_low_information_")),
        "hard_low_information_overrode_source_context_count": sum(1 for row in rows if row.get("hard_low_information_overrode_source_context") is True),
        "source_tag_context_rescue_count": sum(1 for reason in retention_reasons if reason == tag_context_reason),
        "source_title_context_rescue_count": sum(1 for reason in retention_reasons if reason == title_context_reason),
        "circular_candidate_tag_rescue_count": sum(1 for row in rows if row.get("circular_candidate_tag_rescue") is True),
        "candidate_tag_used_as_source_context_count": sum(1 for row in rows if row.get("candidate_tag_used_as_source_context") is True),
        "empty_source_tag_context_count": sum(1 for row in rows if row.get("source_tag_context_empty") is True),
    }


def validate_required_audit_counters(audit: dict[str, Any]) -> None:
    required = (
        "forbidden_single_tag_count",
        "low_information_protected_signal_rescue_count",
        "short_chunk_retained_by_protected_signal_count",
        "short_chunk_retained_by_source_tag_context_count",
        "low_information_count",
        "hard_low_information_count",
        "hard_low_information_overrode_source_context_count",
        "source_tag_context_rescue_count",
        "source_title_context_rescue_count",
        "circular_candidate_tag_rescue_count",
        "candidate_tag_used_as_source_context_count",
    )
    for field in required:
        if field not in audit:
            raise RuntimeError(f"Missing required v0.4 audit counter: {field}")
        value = audit[field]
        if not isinstance(value, int) or value < 0:
            raise RuntimeError(f"Invalid v0.4 audit counter {field}: {value!r}")
    if audit["circular_candidate_tag_rescue_count"] != 0:
        raise RuntimeError("candidate/circular tag rescue detected in v0.4 low-information audit")
    if audit["candidate_tag_used_as_source_context_count"] != 0:
        raise RuntimeError("candidate tag was used as source context in v0.4 low-information audit")


def gapfill_record(row: dict[str, Any], source_family: str) -> dict[str, Any]:
    tag = str(row.get("abpath_tag") or "")
    chunk_id = str(row.get("chunk_id") or "")
    return {
        "schema_version": "curriculum_map_v0_4",
        "record_id": f"gapfill_v0_4:{source_family}:{chunk_id}:{tag}",
        "source": source_family,
        "content_source": source_family,
        "ontology_source": "abpath",
        "status": "approved_gapfill_v0_4",
        "visible": True,
        "approved_tag": tag,
        "root": str(row.get("root") or root_of(tag)),
        "title": str(row.get("source_id") or chunk_id),
        "original_tag": str(row.get("original_existing_tag") or row.get("prior_or_source_tag") or ""),
        "original_tag_field": "hybrid_gapfill_abpath_tag",
        "mapped_from": "gapfill_v0_4",
        "fuzzy_score": row.get("hybrid_score"),
        "review_reason": "",
        "rejection_reason": "",
        "input_path": f"outputs/curriculum_gapfill_v0_4/{source_family[:-1] if source_family.endswith('s') else source_family}_abpath_gapfill_approved_v0_4.jsonl",
        "raw_source_gcs_uri": "",
        "normalized_artifact_gcs_uri": "",
        "original_record": row,
    }


def row_key(row: dict[str, Any], occurrence: int) -> str:
    original = row.get("original_record") if isinstance(row.get("original_record"), dict) else {}
    identity = [
        row.get("content_source") or row.get("source") or "",
        original.get("source_id") or original.get("video_id") or row.get("title") or "",
        original.get("chunk_id") or "",
        row.get("record_id") or "",
        row.get("approved_tag") or "",
        row.get("status") or "",
        row.get("input_path") or "",
        row.get("original_tag") or "",
        row.get("title") or "",
        occurrence,
    ]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def write_sqlite(path: Path, records: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    conn = sqlite3.connect(tmp_path)
    conn.execute(
        "CREATE TABLE curriculum_records (curriculum_row_key TEXT PRIMARY KEY, record_id TEXT, approved_tag TEXT, root TEXT, source TEXT, title TEXT, input_path TEXT, content_source TEXT, ontology_source TEXT, map_status TEXT)"
    )
    conn.execute("CREATE TABLE curriculum_nodes (tag TEXT PRIMARY KEY, root TEXT, record_count INTEGER)")
    counts: Counter[tuple[str, ...]] = Counter()
    for row in records:
        identity = (
            str(row.get("content_source") or row.get("source") or ""),
            str(row.get("record_id") or ""),
            str(row.get("approved_tag") or ""),
            str(row.get("status") or ""),
            str(row.get("input_path") or ""),
            str(row.get("title") or ""),
        )
        counts[identity] += 1
        conn.execute(
            "INSERT INTO curriculum_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row_key(row, counts[identity]),
                row.get("record_id"),
                row.get("approved_tag"),
                row.get("root"),
                row.get("source"),
                row.get("title"),
                row.get("input_path"),
                row.get("content_source") or ("" if row.get("source") == "abpath" else row.get("source")),
                row.get("ontology_source") or ("abpath" if row.get("source") == "abpath" else ""),
                row.get("status"),
            ),
        )
    for node in nodes:
        conn.execute("INSERT INTO curriculum_nodes VALUES (?, ?, ?)", (node["tag"], node["root"], int(node["record_count"])))
    conn.execute("CREATE INDEX idx_records_tag_v0_4 ON curriculum_records(approved_tag)")
    conn.execute("CREATE INDEX idx_records_source_v0_4 ON curriculum_records(source)")
    sqlite_rows = conn.execute("SELECT COUNT(*) FROM curriculum_records").fetchone()[0]
    by_status = dict(conn.execute("SELECT map_status, COUNT(*) FROM curriculum_records GROUP BY map_status ORDER BY COUNT(*) DESC").fetchall())
    by_root = dict(conn.execute("SELECT root, COUNT(*) FROM curriculum_records GROUP BY root ORDER BY COUNT(*) DESC").fetchall())
    by_source = dict(conn.execute("SELECT content_source, COUNT(*) FROM curriculum_records GROUP BY content_source ORDER BY COUNT(*) DESC").fetchall())
    conn.commit()
    conn.close()
    tmp_path.replace(path)
    if sqlite_rows != len(records):
        raise RuntimeError(f"SQLite row drop detected for v0.4: input={len(records)} sqlite={sqlite_rows}")
    return {"sqlite_rows": sqlite_rows, "by_status": by_status, "by_root": by_root, "by_source_family": by_source}


def make_map(v02_dir: Path, approved_rows: list[dict[str, Any]], map_out: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    map_out.mkdir(parents=True, exist_ok=True)
    v02_summary = json.loads((v02_dir / "acceptance_summary_v0_2.json").read_text(encoding="utf-8"))
    _, v02_nodes = read_csv(v02_dir / "curriculum_nodes_v0_2.csv")
    records = [row for row in read_jsonl(v02_dir / "curriculum_records_v0_2.jsonl") if row.get("visible") and not has_forbidden(row.get("approved_tag"))]
    for row in approved_rows:
        records.append(gapfill_record(row, str(row.get("source_family") or "")))
    node_counts = {row["tag"]: int(row.get("record_count") or 0) for row in v02_nodes}
    node_roots = {row["tag"]: row.get("root", "") for row in v02_nodes}
    added_counts = Counter(str(row.get("abpath_tag") or "") for row in approved_rows)
    for tag, count in added_counts.items():
        node_counts[tag] = node_counts.get(tag, 0) + count
        node_roots.setdefault(tag, root_of(tag))
    nodes = [{"tag": tag, "root": node_roots.get(tag, ""), "record_count": node_counts[tag]} for tag in sorted(node_counts)]
    records_path = map_out / "curriculum_records_v0_4.jsonl"
    write_jsonl(records_path, records)
    with records_path.open("rb") as src, gzip.open(map_out / "curriculum_records_v0_4.jsonl.gz", "wb") as dst:
        dst.writelines(src)
    write_csv(map_out / "curriculum_nodes_v0_4.csv", nodes, ["tag", "root", "record_count"])
    sqlite_audit = write_sqlite(map_out / "curriculum_tag_index_v0_4.sqlite", records, nodes)
    summary = {
        "schema_version": "curriculum_map_v0_4",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "build_status": "passed_low_information_gate",
        "v0_2_visible_records": int(v02_summary.get("records_visible_in_curriculum") or 0),
        "v0_4_visible_records": int(v02_summary.get("records_visible_in_curriculum") or 0) + len(approved_rows),
        "net_added_records": len(approved_rows),
        "approved_gapfill_rows_added": len(approved_rows),
        "forbidden_visible_tag_count": sum(1 for row in records if has_forbidden(row.get("approved_tag"))),
        "content_source_counts_excluding_abpath": {
            **{k: v for k, v in (v02_summary.get("source_counts") or {}).items() if k != "abpath"},
            "lecture_gapfill_v0_4": sum(1 for row in approved_rows if row.get("source_family") == "lectures"),
            "textbook_gapfill_v0_4": sum(1 for row in approved_rows if row.get("source_family") == "textbooks"),
        },
        "ontology_provenance": {"abpath": "tag ontology only; not counted as content source"},
        "sqlite": sqlite_audit,
    }
    if summary["forbidden_visible_tag_count"] != 0:
        raise RuntimeError("Forbidden visible tags detected in v0.4 map")
    (map_out / "acceptance_summary_v0_4.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_browser(map_out / "curriculum_browser_v0_4.html", summary)
    return summary, sqlite_audit


def write_browser(path: Path, summary: dict[str, Any]) -> None:
    text = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Curriculum Map v0.4</title>
<style>body{{font-family:Georgia,'Times New Roman',serif;margin:0;background:#f7f8f4;color:#202520}}header{{background:#203d37;color:white;padding:24px 32px}}main{{max-width:1080px;margin:0 auto;padding:24px}}.banner{{background:#fff5df;border:1px solid #d8b36b;padding:12px;margin-bottom:16px;font-weight:700}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}.metric{{background:white;border:1px solid #d9dfd2;padding:12px}}strong{{display:block;font-size:1.35rem}}</style></head>
<body><header><h1>Curriculum Map v0.4</h1><div>STAGED LOW-INFORMATION GATED BUILD, NOT LIVE API</div></header>
<main><div class="banner">Low-information and unmapped rows are excluded from approved/API-facing curriculum outputs. No deploy or GPT Builder update was performed.</div>
<section class="metrics"><div class="metric"><strong>{summary['v0_2_visible_records']}</strong>v0.2 visible</div><div class="metric"><strong>{summary['v0_4_visible_records']}</strong>v0.4 visible</div><div class="metric"><strong>{summary['net_added_records']}</strong>net added</div><div class="metric"><strong>{summary['forbidden_visible_tag_count']}</strong>forbidden visible tags</div></section>
</main></body></html>
"""
    path.write_text(text, encoding="utf-8")


def validation_row(label: str, text: str, source_family: str, source_tags: list[str] | None = None, source_titles: list[str] | None = None, candidate_tags: list[str] | None = None) -> dict[str, Any]:
    low_info, reason = classify_low_information_with_context(
        text,
        source_family,
        candidate_tags or [],
        source_tags or [],
        f"targeted_validation:{label}",
        source_titles or [],
    )
    return {
        "label": label,
        "source_family": source_family,
        "map_status": "low_information" if low_info else "retained_or_review",
        "reason": reason,
        "source_tags": source_tags or [],
        "source_titles": source_titles or [],
        "candidate_tags": candidate_tags or [],
        "text_excerpt": clean_text(text, 240),
    }


def targeted_validation_report() -> dict[str, Any]:
    hard_inputs = [
        "Okay.",
        "Next slide. Any questions?",
        "Okay, thank you. I have still one question. Sorry.",
        "Hi everyone, welcome.",
        "Okay, that's it for today.",
        "Black image. Raw transcript: you",
        "Video Conference Screen. Raw transcript: all who you.",
        "Non-diagnostic conference low-content slide.",
        "Raw transcript: you",
        "References.",
        "Table.",
        "Figure.",
        "Acknowledgments and copyright permissions.",
        "Can you hear me?",
        "Moving on.",
        "Break.",
        "Objectives.",
        "Agenda.",
        "Thank you.",
        "Question?",
    ]
    meaningful_short = [
        "Pale cells filled with glycogen, loss of granular layer.",
        "Pleomorphic and ugly nuclei.",
        "Invisible creeping, bad sign.",
        "Melanocytes up close.",
        "Sharp cutoff.",
        "Chondroid / osteoid matrix.",
        "Amyloid deposition.",
        "Panniculitis with lobular inflammation.",
        "Basaloid nests with peripheral palisading.",
        "Dermal granulomatous inflammation.",
        "Necrosis and mitotic activity.",
        "Pagetoid melanocytes in epidermis.",
        "Lichenoid interface dermatitis.",
        "Suppurative granuloma.",
        "Spindle cells in collagenous stroma.",
        "Eosinophils and plasma cells.",
        "Adnexal tumor with eccrine differentiation.",
        "Sebaceous lobules with atypia.",
        "Cortical bone with osteoid matrix.",
        "Marrow fibrosis.",
    ]
    source_rescues = [
        "Cellular aspirate with cohesive fragments and mild changes.",
        "Lesional tissue shows mixed background and texture.",
        "The specimen shows nests and cords in a stromal background.",
        "Submitted material demonstrates an organized pattern.",
        "Microscopy shows sheets of abnormal cells.",
        "The process is circumscribed with focal degeneration.",
        "Tissue fragments show organized architecture.",
        "Smear shows abnormal cells with granular appearance.",
        "Sections show proliferation in small groups.",
        "The process involves superficial soft tissue.",
        "The sample shows lobular inflammation.",
        "Fragments show matrix-like material.",
        "The slide shows hard tissue involvement.",
        "Cells show clearing and pale appearance.",
        "There is boundary change with mixed cells.",
        "The aspirate contains mixed cellular material.",
        "Abnormal cells are present in nests.",
        "The specimen shows sticky background material.",
        "There is cellular proliferation in fascicles.",
        "The submitted sample shows organized reaction.",
    ]
    over_rescued = [
        "Black image. Raw transcript: you",
        "Video Conference Screen. Raw transcript: all who you.",
        "Non-diagnostic conference low-content slide.",
        "Okay.",
        "Next slide. Any questions?",
        "Hi everyone, welcome.",
        "Okay, that's it for today.",
        "Thank you.",
        "Question?",
        "Raw transcript: okay",
        "Copyright.",
        "References.",
        "Agenda.",
        "Objectives.",
        "Break.",
        "Moving on.",
        "Can you hear me?",
        "Slide.",
        "Table.",
        "Figure.",
    ]
    report = {
        "hard_low_information_despite_context": [
            validation_row("hard_low_information_despite_context", text, "lectures", ["HN::Neck_Lymph_Node::Cyst::Branchial_Cleft_Cyst"], ["Benign Cystic Neck Mass"])
            for text in hard_inputs
        ],
        "meaningful_short_retained_or_reviewed": [
            validation_row("meaningful_short_retained_or_reviewed", text, "lectures")
            for text in meaningful_short
        ],
        "source_tag_context_rescues_with_minimal_content": [
            validation_row("source_tag_context_rescue", text, "lectures", ["Skin::Inflammatory::Panniculitis"])
            for text in source_rescues
        ],
        "previously_over_rescued_now_low_information": [
            validation_row("previously_over_rescued_now_low_information", text, "lectures", ["HN::Neck_Lymph_Node::Cyst::Branchial_Cleft_Cyst"], ["Benign Cystic Neck Mass"])
            for text in over_rescued
        ],
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02-dir", type=Path, default=DEFAULT_V02_DIR)
    parser.add_argument("--v03-gapfill-dir", type=Path, default=DEFAULT_V03_GAPFILL_DIR)
    parser.add_argument("--lecture-chunks", type=Path, default=DEFAULT_LECTURES)
    parser.add_argument("--textbook-chunks", type=Path, default=DEFAULT_TEXTBOOKS)
    parser.add_argument("--gapfill-output-dir", type=Path, default=DEFAULT_GAPFILL_OUT)
    parser.add_argument("--map-output-dir", type=Path, default=DEFAULT_MAP_OUT)
    parser.add_argument("--audit-output-dir", type=Path, default=DEFAULT_AUDIT_OUT)
    parser.add_argument("--targeted-validation", action="store_true", help="Run bounded low-information classifier validation without rebuilding outputs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.targeted_validation:
        print(json.dumps(targeted_validation_report(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    args.gapfill_output_dir.mkdir(parents=True, exist_ok=True)
    args.map_output_dir.mkdir(parents=True, exist_ok=True)
    args.audit_output_dir.mkdir(parents=True, exist_ok=True)

    lecture_chunks = load_chunks(args.lecture_chunks, "lectures")
    textbook_chunks = load_chunks(args.textbook_chunks, "textbooks")
    lecture_candidates = load_candidates(args.v03_gapfill_dir / "lecture_abpath_gapfill_candidates_FULL_v0_3.jsonl")
    textbook_candidates = load_candidates(args.v03_gapfill_dir / "textbook_abpath_gapfill_candidates_FULL_v0_3.jsonl")
    annotated = annotate_candidates(lecture_candidates, lecture_chunks) + annotate_candidates(textbook_candidates, textbook_chunks)
    low_no_candidate_l, unmapped_l = chunk_level_unmapped_rows(lecture_chunks, lecture_candidates)
    low_no_candidate_t, unmapped_t = chunk_level_unmapped_rows(textbook_chunks, textbook_candidates)
    grouped = split_status(annotated)
    low_info_rows = grouped["low_information"] + low_no_candidate_l + low_no_candidate_t
    unmapped_rows = grouped["unmapped_no_confident_tag"] + unmapped_l + unmapped_t
    approved = grouped["approved"]
    review = grouped["review"]
    rejected = grouped["rejected_conflict"]

    write_jsonl(args.gapfill_output_dir / "lecture_abpath_gapfill_approved_v0_4.jsonl", [row for row in approved if row.get("source_family") == "lectures"])
    write_jsonl(args.gapfill_output_dir / "textbook_abpath_gapfill_approved_v0_4.jsonl", [row for row in approved if row.get("source_family") == "textbooks"])
    write_csv(args.gapfill_output_dir / "lecture_abpath_gapfill_review_v0_4.csv", [row for row in review if row.get("source_family") == "lectures"])
    write_csv(args.gapfill_output_dir / "textbook_abpath_gapfill_review_v0_4.csv", [row for row in review if row.get("source_family") == "textbooks"])
    write_csv(args.gapfill_output_dir / "lecture_abpath_gapfill_rejected_conflict_v0_4.csv", [row for row in rejected if row.get("source_family") == "lectures"])
    write_csv(args.gapfill_output_dir / "textbook_abpath_gapfill_rejected_conflict_v0_4.csv", [row for row in rejected if row.get("source_family") == "textbooks"])
    write_csv(args.audit_output_dir / "low_information_rows_v0_4.csv", low_info_rows)
    write_csv(args.audit_output_dir / "unmapped_no_confident_tag_rows_v0_4.csv", unmapped_rows)
    map_summary, sqlite_audit = make_map(args.v02_dir, approved, args.map_output_dir)

    raw_target_rows = len(lecture_chunks) + len(textbook_chunks)
    status_counts = {
        "approved": len(approved),
        "review": len(review),
        "rejected_conflict": len(rejected),
        "low_information": len(low_info_rows),
        "unmapped_no_confident_tag": len(unmapped_rows),
    }
    accounted_candidate_or_chunk_rows = len(annotated) + len(low_no_candidate_l) + len(low_no_candidate_t) + len(unmapped_l) + len(unmapped_t)
    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "map_status_values": list(MAP_STATUSES),
        "raw_input_row_count": {
            "lectures": len(lecture_chunks),
            "textbooks": len(textbook_chunks),
            "total_target_chunks": raw_target_rows,
            "candidate_decision_rows": len(annotated),
            "candidate_or_chunk_rows_accounted": accounted_candidate_or_chunk_rows,
        },
        "status_counts": status_counts,
        "status_counts_by_source_family": {
            status: dict(Counter(str(row.get("source_family") or "") for row in rows).most_common())
            for status, rows in {
                "approved": approved,
                "review": review,
                "rejected_conflict": rejected,
                "low_information": low_info_rows,
                "unmapped_no_confident_tag": unmapped_rows,
            }.items()
        },
        "low_information_counts": low_info_counts(low_info_rows),
        "low_information_counts_by_reason": dict(Counter(str(row.get("low_information_reason") or "") for row in low_info_rows).most_common()),
        "sqlite_row_count": sqlite_audit["sqlite_rows"],
        "map_visible_records": map_summary["v0_4_visible_records"],
        "unexpected_row_drops": 0 if sqlite_audit["sqlite_rows"] == map_summary["v0_4_visible_records"] else map_summary["v0_4_visible_records"] - sqlite_audit["sqlite_rows"],
        "outputs": {
            "gapfill_output_dir": str(args.gapfill_output_dir),
            "map_output_dir": str(args.map_output_dir),
            "low_information_rows": str(args.audit_output_dir / "low_information_rows_v0_4.csv"),
            "unmapped_rows": str(args.audit_output_dir / "unmapped_no_confident_tag_rows_v0_4.csv"),
            "audit": str(args.audit_output_dir / "curriculum_gapfill_map_v0_4_audit.json"),
        },
        "limitations": [
            "v0.4 reuses existing v0.3 full hybrid candidate evidence and adds a pre-approval low-information gate.",
            "Low-information and unmapped rows are audited but excluded from approved/API-facing curriculum outputs.",
            "No GCS upload, API deployment, GPT Builder update, raw source mutation, or vector/FAISS rebuild was performed.",
        ],
    }
    if audit["unexpected_row_drops"] != 0:
        raise RuntimeError(f"Unexpected v0.4 SQLite row drop: {audit['unexpected_row_drops']}")
    real_build_rows = annotated + low_info_rows + unmapped_rows
    audit.update(classifier_audit_counts(real_build_rows))
    validate_required_audit_counters(audit)
    (args.audit_output_dir / "curriculum_gapfill_map_v0_4_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.gapfill_output_dir / "README_CURRICULUM_GAPFILL_V0_4.md").write_text("# Curriculum Gap Fill v0.4\n\nLow-information gated staged outputs. Not uploaded, not live, not API-exposed.\n", encoding="utf-8")
    (args.map_output_dir / "README_CURRICULUM_MAP_V0_4.md").write_text("# Curriculum Map v0.4\n\nStaged map built from v0.2 plus approved v0.4 gap-fill rows. Low-information and unmapped rows are excluded.\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
