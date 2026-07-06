#!/usr/bin/env python3
"""Hybrid-rescore existing lecture ABPath gap-fill candidates."""

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


SCHEMA_VERSION = "curriculum_gapfill_v0_3"
METHOD = "cross_source_hybrid_abpath_gapfill_v0_3"
DEFAULT_CANDIDATES = Path("outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_candidates_v0_3.jsonl")
DEFAULT_PROFILES = Path("outputs/curriculum_gapfill_v0_3/cross_source_tag_seed_profiles_v0_3.jsonl")
DEFAULT_SQL_APPROVED = Path("outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_approved_v0_3_HIGHCONF.jsonl")
DEFAULT_LECTURE_CHUNKS = Path("data/curriculum_map_v0_2/lecture_timecoded_tagged_chunks_ROUTED_ONLY_STRICT_CYTO_v9.jsonl")
DEFAULT_OUTPUT_DIR = Path("outputs/curriculum_gapfill_v0_3")
VECTOR_HINTS = (
    Path("data/curriculum_map_readiness_v0/lecture_timecoded_vector_docstore_STRICT_CYTO_v9.sample5000.jsonl"),
    Path("data/curriculum_map_readiness_v0/textbook_lean_vector_docstore.sample5000.jsonl"),
    Path("data/curriculum_map_readiness_v0/pathout_ap_diagnostic_vector_docstore.sample5000.jsonl"),
)
FORBIDDEN_PATTERNS = ("::Lectures::", "::Textbooks::", "::Error", "Slide_", "Page_", "Digital_Pathology_Slide", "Pathology_Slide", "rejected_generated")
GENERIC_TERMS = {"tumor", "tumors", "neoplasm", "neoplasms", "malignant", "benign", "lesion", "lesions", "disease", "pathology", "diagnosis", "other", "miscellaneous", "carcinoma", "adenocarcinoma", "lymphoma", "sarcoma", "cyst"}
ROOT_ALIASES = {
    "GYN": {"gyn", "gynecologic", "cervix", "cervical", "endocervical", "uterus", "uterine", "endometrial", "ovary", "ovarian", "vagina", "vaginal", "vulva", "vulvar"},
    "HN": {"head", "neck", "salivary", "parotid", "submandibular", "oral", "oropharynx", "sinonasal", "nasal", "larynx", "thyroid", "branchial"},
    "BST": {"bone", "soft", "tissue", "sarcoma"},
    "BR": {"breast", "mammary"},
    "GI": {"gastrointestinal", "colon", "colonic", "stomach", "gastric", "esophagus", "intestinal"},
    "GU": {"genitourinary", "prostate", "prostatic", "kidney", "renal", "bladder", "testis"},
    "HEM": {"heme", "hematopathology", "lymphoma", "leukemia", "marrow"},
    "LUNG": {"lung", "pulmonary", "thoracic"},
    "DERM": {"skin", "cutaneous", "derm"},
}
CSV_FIELDS = [
    "abpath_tag",
    "root",
    "chunk_id",
    "source_id",
    "confidence",
    "score",
    "hybrid_score",
    "hybrid_decision",
    "vector_status",
    "who_phrase_hits",
    "pathout_phrase_hits",
    "textbook_phrase_hits",
    "lecture_phrase_hits",
    "negative_phrase_hits",
    "entity_phrase_hit",
    "root_agreement",
    "generic_only_match",
    "sibling_or_cross_root_conflict",
    "hybrid_reason",
    "original_existing_tag",
    "text_excerpt",
]


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def has_forbidden(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


def norm_phrase(value: str) -> str:
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and re.search(r"\b" + re.escape(phrase.lower()) + r"\b", text.lower()) is not None


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def root_of(tag: str) -> str:
    return tag.split("::", 1)[0] if "::" in tag else tag


def load_profiles(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row["abpath_tag"]): row for row in read_jsonl(path)}


def load_chunks(path: Path, chunk_ids: set[str]) -> dict[str, dict[str, str]]:
    chunks: dict[str, dict[str, str]] = {}
    if not path.exists():
        return chunks
    for row in read_jsonl(path):
        chunk_id = str(row.get("chunk_id") or "")
        if chunk_id not in chunk_ids:
            continue
        text = " ".join(str(row.get(k) or "") for k in ("title", "summary", "transcript_text", "tag_basis"))
        chunks[chunk_id] = {
            "title": str(row.get("title") or ""),
            "text": re.sub(r"\s+", " ", text).strip(),
            "primary_tag": str(row.get("primary_tag_governed") or row.get("primary_tag") or ""),
        }
        if len(chunks) >= len(chunk_ids):
            break
    return chunks


def phrase_hits(phrases: list[str], text: str, limit: int = 20) -> list[str]:
    hits = [str(phrase) for phrase in phrases if len(str(phrase)) >= 3 and contains_phrase(text, str(phrase))]
    hits.sort(key=lambda phrase: (-len(phrase.split()), phrase))
    return hits[:limit]


def root_agreement(root: str, text_tokens: set[str], original_tag: str) -> bool:
    if original_tag.startswith(root + "::"):
        return True
    return bool(text_tokens & ROOT_ALIASES.get(root, {root.lower()}))


def generic_only(candidate: dict[str, Any], all_hits: list[str], entity_hit: bool) -> bool:
    terms = [str(term).lower() for term in candidate.get("matched_terms") or []]
    return bool(terms) and not all_hits and not entity_hit and all(term in GENERIC_TERMS for term in terms)


def vector_status() -> tuple[str, list[str]]:
    existing = [str(path) for path in VECTOR_HINTS if path.exists()]
    if existing:
        return "unavailable_sample_docstores_only_no_local_similarity_index", existing
    return "unavailable", []


def rescore(candidate: dict[str, Any], profile: dict[str, Any], chunk: dict[str, str], vec_status: str) -> dict[str, Any]:
    tag = str(candidate.get("abpath_tag") or "")
    root = str(candidate.get("root") or root_of(tag))
    text = " ".join([chunk.get("title", ""), chunk.get("text", ""), str(candidate.get("text_excerpt") or "")])
    text_tokens = tokens(text)
    original_tag = str(candidate.get("original_existing_tag") or chunk.get("primary_tag") or "")
    entity_phrase = str(profile.get("entity_phrase") or norm_phrase(tag.split("::")[-1]))
    entity_hit = contains_phrase(text, entity_phrase)
    who_hits = phrase_hits(profile.get("who_terms") or [], text)
    pathout_hits = phrase_hits(profile.get("pathout_terms") or [], text)
    textbook_hits = phrase_hits(profile.get("textbook_terms") or [], text)
    lecture_hits = phrase_hits(profile.get("lecture_terms") or [], text, limit=10)
    negative_hits = phrase_hits(profile.get("negative_or_ambiguous_phrases") or [], text, limit=10)
    cross_source_hits = who_hits + pathout_hits + textbook_hits
    root_hit = root_agreement(root, text_tokens, original_tag)
    original_root = root_of(original_tag)
    cross_root = bool(original_tag and original_tag != "_UNMAPPED_" and original_root != root and not root_hit)
    sibling_conflict = bool(negative_hits[:2]) and not (who_hits or pathout_hits)
    generic = generic_only(candidate, cross_source_hits + lecture_hits, entity_hit)

    score = float(candidate.get("score") or 0.0)
    reasons: list[str] = []
    if entity_hit:
        score += 0.12
        reasons.append("entity phrase match")
    if who_hits:
        score += min(0.20, 0.07 * len(who_hits))
        reasons.append("WHO phrase support")
    if pathout_hits:
        score += min(0.18, 0.06 * len(pathout_hits))
        reasons.append("PathOut phrase support")
    if textbook_hits:
        score += min(0.14, 0.035 * len(textbook_hits))
        reasons.append("textbook phrase support")
    if lecture_hits:
        score += min(0.05, 0.015 * len(lecture_hits))
        reasons.append("secondary lecture phrase support")
    if root_hit:
        score += 0.06
        reasons.append("lecture root agreement")
    if sibling_conflict:
        score -= 0.24
        reasons.append("sibling negative phrase conflict")
    if cross_root:
        score -= 0.24
        reasons.append("cross-root conflict")
    if generic:
        score -= 0.35
        reasons.append("generic-only match")
    if has_forbidden(candidate):
        score = 0.0
        reasons.append("forbidden pattern")
    score = max(0.0, min(1.0, score))

    strong_cross_source = bool(who_hits or pathout_hits or len(textbook_hits) >= 2)
    if has_forbidden(candidate) or generic or (cross_root and not strong_cross_source) or sibling_conflict:
        decision = "rejected_hybrid"
    elif str(candidate.get("confidence")) == "high" and score >= 0.92 and entity_hit and strong_cross_source and not cross_root:
        decision = "approved_hybrid_high"
    elif str(candidate.get("confidence")) == "high" and score >= 0.95 and strong_cross_source and root_hit and not cross_root:
        decision = "approved_hybrid_high"
    else:
        decision = "review_hybrid"

    out = dict(candidate)
    out.update(
        {
            "method": METHOD,
            "hybrid_score": round(score, 3),
            "hybrid_decision": decision,
            "vector_status": vec_status,
            "tag_name_similarity": None,
            "cross_source_seed_similarity": None,
            "sibling_negative_similarity": None,
            "final_hybrid_score": round(score, 3),
            "who_phrase_hits": who_hits,
            "pathout_phrase_hits": pathout_hits,
            "textbook_phrase_hits": textbook_hits,
            "lecture_phrase_hits": lecture_hits,
            "negative_phrase_hits": negative_hits,
            "entity_phrase_hit": entity_hit,
            "root_agreement": root_hit,
            "generic_only_match": generic,
            "sibling_or_cross_root_conflict": sibling_conflict or cross_root,
            "hybrid_reason": "; ".join(reasons) if reasons else "no hybrid support",
            "review_status": decision,
        }
    )
    return out


def csv_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in CSV_FIELDS})


def make_sample(rows: list[dict[str, Any]], size: int, seed: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("root") or ""), str(row.get("hybrid_decision") or ""))].append(row)
    sample: list[dict[str, Any]] = []
    used: set[tuple[str, str]] = set()
    take = max(1, size // max(1, len(groups)))
    for key in sorted(groups):
        ranked = sorted(groups[key], key=lambda row: (-float(row.get("hybrid_score") or 0), str(row.get("chunk_id"))))
        for row in ranked[:take]:
            rk = (str(row.get("chunk_id")), str(row.get("abpath_tag")))
            if rk not in used:
                sample.append(row)
                used.add(rk)
            if len(sample) >= size:
                return sample
    remaining = [row for row in rows if (str(row.get("chunk_id")), str(row.get("abpath_tag"))) not in used]
    random.Random(seed).shuffle(remaining)
    sample.extend(remaining[: max(0, size - len(sample))])
    return sample[:size]


def write_readme(path: Path, audit: dict[str, Any]) -> None:
    counts = audit["counts"]
    text = f"""# Hybrid Lecture Gap Fill v0.3

This directory contains local-only cross-source hybrid rescoring outputs.

ABPath is used as ontology only. WHO, PathOut, textbooks, existing curriculum records, and secondary lecture tags provide tag meaning context.

Generated files:
- `cross_source_tag_seed_profiles_v0_3.jsonl`
- `lecture_abpath_gapfill_candidates_v0_3_HYBRID_RESCORED.jsonl`
- `lecture_abpath_gapfill_hybrid_review_sample_150.csv`
- `lecture_abpath_gapfill_hybrid_audit_v0_3.json`
- `README_HYBRID_GAPFILL_V0_3.md`

Counts:
- total candidates: {counts["total_candidates"]}
- tags with cross-source profiles: {counts["tags_with_cross_source_profiles"]}
- approved_hybrid_high: {counts["approved_hybrid_high_count"]}
- review_hybrid: {counts["review_hybrid_count"]}
- rejected_hybrid: {counts["rejected_hybrid_count"]}
- vector_status: {audit["vector_status"]}

This is not a final approved sidecar and is not live, deployed, uploaded, indexed, or API-exposed.
"""
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--sql-approved", type=Path, default=DEFAULT_SQL_APPROVED)
    parser.add_argument("--lecture-chunks", type=Path, default=DEFAULT_LECTURE_CHUNKS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--review-sample-size", type=int, default=150)
    parser.add_argument("--review-sample-seed", type=int, default=407)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.candidates.exists():
        raise SystemExit(f"Missing candidates: {args.candidates}")
    if not args.profiles.exists():
        raise SystemExit(f"Missing profiles: {args.profiles}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidates = list(read_jsonl(args.candidates))
    profiles = load_profiles(args.profiles)
    chunks = load_chunks(args.lecture_chunks, {str(row.get("chunk_id") or "") for row in candidates})
    vec_status, vec_sources = vector_status()
    rescored = [rescore(row, profiles.get(str(row.get("abpath_tag"))) or {}, chunks.get(str(row.get("chunk_id"))) or {}, vec_status) for row in candidates]
    rescored.sort(key=lambda row: (str(row.get("root")), str(row.get("abpath_tag")), str(row.get("hybrid_decision")), str(row.get("chunk_id"))))
    sample = make_sample(rescored, args.review_sample_size, args.review_sample_seed)
    decisions = Counter(str(row.get("hybrid_decision") or "") for row in rescored)
    roots = Counter(str(row.get("root") or "") for row in rescored if row.get("hybrid_decision") == "approved_hybrid_high")
    sql_count = sum(1 for _ in read_jsonl(args.sql_approved)) if args.sql_approved.exists() else 0
    profile_tags_with_seed = {tag for tag, profile in profiles.items() if int(profile.get("seed_record_count") or 0) > 0}
    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workstream": "Curriculum Gap Fill v0.3 - cross-source hybrid ABPath tagging",
        "method": METHOD,
        "vector_status": vec_status,
        "vector_sources_detected": vec_sources,
        "inputs": {
            "candidates": str(args.candidates),
            "profiles": str(args.profiles),
            "sql_high_confidence_sidecar": str(args.sql_approved),
            "lecture_chunks": str(args.lecture_chunks),
        },
        "outputs": {
            "rescored_candidates": str(args.output_dir / "lecture_abpath_gapfill_candidates_v0_3_HYBRID_RESCORED.jsonl"),
            "review_sample": str(args.output_dir / "lecture_abpath_gapfill_hybrid_review_sample_150.csv"),
            "audit": str(args.output_dir / "lecture_abpath_gapfill_hybrid_audit_v0_3.json"),
            "readme": str(args.output_dir / "README_HYBRID_GAPFILL_V0_3.md"),
        },
        "counts": {
            "total_candidates": len(rescored),
            "candidate_tag_count": len({str(row.get("abpath_tag") or "") for row in rescored}),
            "cross_source_profile_count": len(profiles),
            "tags_with_cross_source_profiles": len(profile_tags_with_seed),
            "tags_lacking_profile": len(profiles) - len(profile_tags_with_seed),
            "approved_hybrid_high_count": decisions.get("approved_hybrid_high", 0),
            "review_hybrid_count": decisions.get("review_hybrid", 0),
            "rejected_hybrid_count": decisions.get("rejected_hybrid", 0),
            "sql_only_high_confidence_count": sql_count,
            "hybrid_vs_sql_high_delta": decisions.get("approved_hybrid_high", 0) - sql_count,
            "approved_top_roots": dict(roots.most_common(20)),
            "forbidden_pattern_hits_in_approved_decisions": sum(1 for row in rescored if row.get("hybrid_decision") == "approved_hybrid_high" and has_forbidden(row)),
        },
        "known_limitations": [
            "Hybrid scores are lexical and source-weighted; no new embeddings were generated.",
            "Local vector docstore samples were detected but no complete local similarity index was used.",
            "The output is review material only, not a final approved sidecar.",
        ],
    }
    write_jsonl(args.output_dir / "lecture_abpath_gapfill_candidates_v0_3_HYBRID_RESCORED.jsonl", rescored)
    write_csv(args.output_dir / "lecture_abpath_gapfill_hybrid_review_sample_150.csv", sample)
    (args.output_dir / "lecture_abpath_gapfill_hybrid_audit_v0_3.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_readme(args.output_dir / "README_HYBRID_GAPFILL_V0_3.md", audit)
    print(json.dumps(audit["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
