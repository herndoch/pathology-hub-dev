#!/usr/bin/env python3
"""Rescore lecture ABPath gap-fill candidates with exemplar seed profiles."""

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
METHOD = "exemplar_rescore_abpath_gapfill_v0_3"
APPROVAL_STATUS = "approved_exemplar_high"
APPROVAL_SCOPE = "local_refinement_preview_only"

DEFAULT_CANDIDATES = Path("outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_candidates_v0_3.jsonl")
DEFAULT_PRIOR_APPROVED = Path("outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_approved_v0_3_HIGHCONF.jsonl")
DEFAULT_PROFILES = Path("outputs/curriculum_gapfill_v0_3/lecture_tag_seed_profiles_v0_3.jsonl")
DEFAULT_LECTURE_CHUNKS = Path(
    "data/curriculum_map_v0_2/lecture_timecoded_tagged_chunks_ROUTED_ONLY_STRICT_CYTO_v9.jsonl"
)
DEFAULT_ACCEPTANCE_SUMMARY = Path("outputs/curriculum_map_v0_2/acceptance_summary_v0_2.json")
DEFAULT_OUTPUT_DIR = Path("outputs/curriculum_gapfill_v0_3")

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

GENERIC_TERMS = {
    "tumor",
    "tumors",
    "neoplasm",
    "neoplasms",
    "malignant",
    "benign",
    "disease",
    "lesion",
    "lesions",
    "other",
    "miscellaneous",
    "pathology",
    "diagnosis",
    "clinical",
    "carcinoma",
    "adenocarcinoma",
    "lymphoma",
    "sarcoma",
    "cyst",
}

ROOT_ALIASES = {
    "GYN": {"gyn", "gynecologic", "gynecological", "cervix", "cervical", "endocervical", "uterus", "endometrial", "ovary", "ovarian", "vagina", "vaginal", "vulva", "fallopian"},
    "HN": {"head", "neck", "salivary", "parotid", "submandibular", "oral", "oropharynx", "sinonasal", "nasal", "larynx", "thyroid", "branchial"},
    "BST": {"bone", "soft", "tissue", "sarcoma"},
    "BR": {"breast", "mammary"},
    "GI": {"gastrointestinal", "colon", "colonic", "stomach", "gastric", "esophagus", "intestinal", "appendix"},
    "GU": {"genitourinary", "prostate", "prostatic", "kidney", "renal", "bladder", "testis", "testicular"},
    "HEM": {"heme", "hematopathology", "lymphoma", "leukemia", "marrow"},
    "LUNG": {"lung", "pulmonary", "thoracic"},
    "DERM": {"skin", "cutaneous", "derm"},
}

SITE_ALIASES = {
    "cervix": {"cervix", "cervical", "endocervical", "ectocervical"},
    "ovary": {"ovary", "ovarian"},
    "uterus": {"uterus", "uterine", "endometrial", "endometrium", "myometrial"},
    "vagina": {"vagina", "vaginal"},
    "vulva": {"vulva", "vulvar"},
    "salivary": {"salivary", "parotid", "submandibular"},
    "oral": {"oral", "tongue", "gingiva", "mouth"},
    "sinonasal": {"sinonasal", "nasal", "sinus"},
    "thyroid": {"thyroid"},
    "neck": {"neck", "branchial"},
}

CSV_FIELDS = [
    "schema_version",
    "source_family",
    "chunk_id",
    "source_id",
    "video_id",
    "abpath_tag",
    "root",
    "matched_query",
    "matched_terms",
    "score",
    "confidence",
    "method",
    "review_status",
    "text_excerpt",
    "original_existing_tag",
    "reason",
    "exemplar_score",
    "exemplar_confidence",
    "exemplar_status",
    "positive_phrase_hits",
    "negative_phrase_hits",
    "entity_phrase_hit",
    "title_heading_match",
    "root_context_hit",
    "site_context_hit",
    "generic_only_match",
    "sibling_conflict",
    "cross_root_ambiguity",
    "exemplar_reason",
]


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


def has_forbidden(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


def root_of(tag: str) -> str:
    return tag.split("::", 1)[0] if "::" in tag else tag


def tag_parts(tag: str) -> list[str]:
    return [part for part in tag.split("::") if part]


def phrase_from_tag_part(value: str) -> str:
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def tag_leaf_phrase(tag: str) -> str:
    parts = tag_parts(tag)
    return phrase_from_tag_part(parts[-1]) if parts else ""


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def contains_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    return re.search(r"\b" + re.escape(phrase.lower()) + r"\b", text.lower()) is not None


def token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def text_from_chunk(row: dict[str, Any]) -> str:
    fields = [row.get("title"), row.get("summary"), row.get("transcript_text"), row.get("tag_basis")]
    return clean_text(" ".join(str(field) for field in fields if field))


def load_candidates(path: Path) -> list[dict[str, Any]]:
    return list(read_jsonl(path))


def load_profiles(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("abpath_tag")): row for row in read_jsonl(path)}


def load_prior_approved_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in read_jsonl(path))


def load_candidate_chunk_texts(path: Path, chunk_ids: set[str]) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    if not path.exists():
        return rows
    for row in read_jsonl(path):
        chunk_id = str(row.get("chunk_id") or "")
        if chunk_id not in chunk_ids:
            continue
        rows[chunk_id] = {
            "title": str(row.get("title") or ""),
            "text": text_from_chunk(row),
            "primary_tag": str(row.get("primary_tag_governed") or row.get("primary_tag") or ""),
        }
        if len(rows) >= len(chunk_ids):
            break
    return rows


def site_terms_for_tag(tag: str) -> set[str]:
    terms: set[str] = set()
    for part in tag_parts(tag)[1:4]:
        phrase = phrase_from_tag_part(part)
        for token in re.findall(r"[a-z0-9]+", phrase):
            if token in SITE_ALIASES:
                terms.update(SITE_ALIASES[token])
            elif token not in GENERIC_TERMS and len(token) >= 4:
                terms.add(token)
    return terms


def root_context(root: str, text_tokens: set[str], original_tag: str) -> bool:
    if original_tag.startswith(root + "::"):
        return True
    aliases = ROOT_ALIASES.get(root, {root.lower()})
    return bool(text_tokens & aliases)


def site_context(tag: str, text_tokens: set[str], original_tag: str) -> bool:
    candidate_terms = site_terms_for_tag(tag)
    if not candidate_terms:
        return True
    if any(term in original_tag.lower() for term in candidate_terms):
        return True
    return bool(text_tokens & candidate_terms)


def cross_root_ambiguous(candidate_root: str, original_tag: str, root_hit: bool, site_hit: bool) -> bool:
    if not original_tag or original_tag == "_UNMAPPED_":
        return False
    original_root = root_of(original_tag)
    if original_root == candidate_root:
        return False
    if original_root.startswith("Cyto_"):
        return not site_hit
    return not (root_hit and site_hit)


def matched_positive_phrases(profile: dict[str, Any], text: str) -> list[str]:
    phrases = profile.get("positive_phrases") or []
    hits = [phrase for phrase in phrases if len(str(phrase)) >= 3 and contains_phrase(text, str(phrase))]
    hits.sort(key=lambda phrase: (-len(str(phrase).split()), str(phrase)))
    return hits[:20]


def matched_negative_phrases(profile: dict[str, Any], text: str) -> list[str]:
    phrases = profile.get("negative_or_ambiguous_phrases") or []
    hits = [phrase for phrase in phrases if len(str(phrase)) >= 3 and contains_phrase(text, str(phrase))]
    hits.sort(key=lambda phrase: (-len(str(phrase).split()), str(phrase)))
    return hits[:20]


def generic_only(candidate: dict[str, Any], positive_hits: list[str], entity_hit: bool) -> bool:
    terms = [str(term).lower() for term in candidate.get("matched_terms") or []]
    if entity_hit or positive_hits:
        return False
    return bool(terms) and all(term in GENERIC_TERMS for term in terms)


def rescore_candidate(candidate: dict[str, Any], profile: dict[str, Any], chunk: dict[str, str]) -> dict[str, Any]:
    tag = str(candidate.get("abpath_tag") or "")
    root = str(candidate.get("root") or root_of(tag))
    full_text = clean_text(" ".join([chunk.get("title", ""), chunk.get("text", ""), str(candidate.get("text_excerpt") or "")]))
    title = chunk.get("title", "")
    tokens = token_set(full_text)
    original_tag = str(candidate.get("original_existing_tag") or chunk.get("primary_tag") or "")

    entity_phrase = tag_leaf_phrase(tag)
    entity_hit = contains_phrase(full_text, entity_phrase)
    title_hit = contains_phrase(title, entity_phrase)
    pos_hits = matched_positive_phrases(profile, full_text)
    neg_hits = matched_negative_phrases(profile, full_text)
    root_hit = root_context(root, tokens, original_tag)
    site_hit = site_context(tag, tokens, original_tag)
    sibling_conflict = bool(neg_hits[:3]) and not title_hit
    cross_root = cross_root_ambiguous(root, original_tag, root_hit, site_hit)
    is_generic_only = generic_only(candidate, pos_hits, entity_hit)

    score = float(candidate.get("score") or 0.0)
    reasons: list[str] = []
    if entity_hit:
        score += 0.12
        reasons.append("exact entity phrase present")
    if pos_hits:
        score += min(0.18, 0.04 * len(pos_hits))
        reasons.append("positive seed phrase overlap")
    if title_hit:
        score += 0.08
        reasons.append("title or heading match")
    if root_hit:
        score += 0.05
        reasons.append("root context present")
    if site_hit:
        score += 0.07
        reasons.append("site context present")
    if sibling_conflict:
        score -= 0.25
        reasons.append("sibling negative phrase conflict")
    if cross_root:
        score -= 0.20
        reasons.append("cross-root or cross-site ambiguity")
    if is_generic_only:
        score -= 0.35
        reasons.append("generic-only lexical match")
    if has_forbidden(candidate):
        score = 0.0
        reasons.append("forbidden pattern")

    score = max(0.0, min(1.0, score))
    seed_count = int(profile.get("seed_record_count") or 0)
    original_conf = str(candidate.get("confidence") or "")

    if has_forbidden(candidate) or is_generic_only or (sibling_conflict and cross_root):
        status = "rejected_exemplar"
    elif original_conf == "high" and score >= 0.92 and not sibling_conflict and not cross_root and (
        (seed_count > 0 and (pos_hits or entity_hit)) or (entity_hit and site_hit)
    ):
        status = "approved_exemplar_high"
    else:
        status = "review_exemplar"

    out = dict(candidate)
    out.update(
        {
            "method": METHOD,
            "exemplar_score": round(score, 3),
            "exemplar_confidence": "high" if score >= 0.92 else "medium" if score >= 0.7 else "low",
            "exemplar_status": status,
            "positive_phrase_hits": pos_hits,
            "negative_phrase_hits": neg_hits,
            "entity_phrase_hit": entity_hit,
            "title_heading_match": title_hit,
            "root_context_hit": root_hit,
            "site_context_hit": site_hit,
            "generic_only_match": is_generic_only,
            "sibling_conflict": sibling_conflict,
            "cross_root_ambiguity": cross_root,
            "exemplar_reason": "; ".join(reasons) if reasons else "no exemplar adjustment",
        }
    )
    if status == "approved_exemplar_high":
        out["approval_status"] = APPROVAL_STATUS
        out["approved_by_method"] = METHOD
        out["approval_scope"] = APPROVAL_SCOPE
        out["review_status"] = "approved_local_preview"
    else:
        out["review_status"] = status
    return out


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] = CSV_FIELDS) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def make_review_sample(rows: list[dict[str, Any]], size: int, seed: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("root") or ""), str(row.get("exemplar_status") or ""))].append(row)
    sample: list[dict[str, Any]] = []
    used: set[tuple[str, str]] = set()
    for key in sorted(groups):
        ranked = sorted(groups[key], key=lambda row: (-float(row.get("exemplar_score") or 0), str(row.get("chunk_id"))))
        take = max(1, size // max(1, len(groups)))
        for row in ranked[:take]:
            row_key = (str(row.get("chunk_id")), str(row.get("abpath_tag")))
            if row_key not in used:
                sample.append(row)
                used.add(row_key)
            if len(sample) >= size:
                return sample
    remaining = [row for row in rows if (str(row.get("chunk_id")), str(row.get("abpath_tag"))) not in used]
    rng = random.Random(seed)
    rng.shuffle(remaining)
    sample.extend(remaining[: max(0, size - len(sample))])
    return sample[:size]


def write_readme(path: Path, audit: dict[str, Any]) -> None:
    counts = audit["counts"]
    text = f"""# Lecture Gap Fill Exemplar Refinement v0.3

This directory contains local-only exemplar-aware refinement outputs for Curriculum Gap Fill v0.3.

Scope:
- lecture candidate rescoring only
- seed profiles derived from already-tagged local v0.2 records and local lecture chunks
- ABPath is used as tag ontology, not content evidence
- no textbook gap-fill processing
- no live sidecar, GCS upload, deployment, GPT Builder update, vector rebuild, FAISS rebuild, or v0.2 output mutation

Generated files:
- `lecture_tag_seed_profiles_v0_3.jsonl`
- `lecture_abpath_gapfill_candidates_v0_3_EXEMPLAR_RESCORED.jsonl`
- `lecture_abpath_gapfill_approved_v0_3_EXEMPLAR_HIGHCONF.jsonl`
- `lecture_abpath_gapfill_exemplar_review_queue_v0_3.csv`
- `lecture_abpath_gapfill_exemplar_audit_v0_3.json`
- `lecture_gapfill_exemplar_review_sample_150.csv`
- `README_LECTURE_GAPFILL_EXEMPLAR_V0_3.md`

Counts:
- original candidates: {counts["original_candidate_count"]}
- seed profiles: {counts["seed_profile_count"]}
- tags with seed profiles: {counts["tags_with_seed_profiles"]}
- approved exemplar high: {counts["approved_exemplar_high_count"]}
- review exemplar: {counts["review_exemplar_count"]}
- rejected exemplar: {counts["rejected_exemplar_count"]}
- previous high-confidence approvals: {counts["prior_high_confidence_approval_count"]}

Use guidance:
These outputs are suitable for local preview review only. They should not be treated as final, live, indexed, API-exposed, or uploaded.
"""
    path.write_text(text, encoding="utf-8")


def build_audit(
    args: argparse.Namespace,
    acceptance_summary: dict[str, Any] | None,
    prior_count: int,
    profiles: dict[str, dict[str, Any]],
    rescored: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(str(row.get("exemplar_status") or "") for row in rescored)
    root_counts = Counter(str(row.get("root") or "") for row in rescored if row.get("exemplar_status") == "approved_exemplar_high")
    original_conf_counts = Counter(str(row.get("confidence") or "") for row in rescored)
    demoted = [
        row
        for row in rescored
        if row.get("confidence") == "high" and row.get("exemplar_status") != "approved_exemplar_high"
    ]
    retained = [
        row
        for row in rescored
        if row.get("confidence") == "high" and row.get("exemplar_status") == "approved_exemplar_high"
    ]
    promoted = [
        row
        for row in rescored
        if row.get("confidence") != "high" and row.get("exemplar_status") == "approved_exemplar_high"
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workstream": "Curriculum Gap Fill v0.3",
        "phase": "exemplar_aware_lecture_refinement",
        "method": METHOD,
        "inputs": {
            "candidates_jsonl": str(args.candidates),
            "prior_high_confidence_jsonl": str(args.prior_approved),
            "seed_profiles_jsonl": str(args.profiles),
            "lecture_chunks": str(args.lecture_chunks),
            "acceptance_summary": str(args.acceptance_summary),
        },
        "outputs": {
            "rescored_candidates_jsonl": str(args.output_dir / "lecture_abpath_gapfill_candidates_v0_3_EXEMPLAR_RESCORED.jsonl"),
            "approved_jsonl": str(args.output_dir / "lecture_abpath_gapfill_approved_v0_3_EXEMPLAR_HIGHCONF.jsonl"),
            "review_queue_csv": str(args.output_dir / "lecture_abpath_gapfill_exemplar_review_queue_v0_3.csv"),
            "audit_json": str(args.output_dir / "lecture_abpath_gapfill_exemplar_audit_v0_3.json"),
            "review_sample_csv": str(args.output_dir / "lecture_gapfill_exemplar_review_sample_150.csv"),
            "readme": str(args.output_dir / "README_LECTURE_GAPFILL_EXEMPLAR_V0_3.md"),
        },
        "counts": {
            "original_candidate_count": len(rescored),
            "original_confidence_counts": dict(sorted(original_conf_counts.items())),
            "seed_profile_count": len(profiles),
            "tags_with_seed_profiles": sum(1 for profile in profiles.values() if int(profile.get("seed_record_count") or 0) > 0),
            "approved_exemplar_high_count": status_counts.get("approved_exemplar_high", 0),
            "review_exemplar_count": status_counts.get("review_exemplar", 0),
            "rejected_exemplar_count": status_counts.get("rejected_exemplar", 0),
            "prior_high_confidence_approval_count": prior_count,
            "high_confidence_demoted_count": len(demoted),
            "high_confidence_retained_count": len(retained),
            "medium_promoted_count": len(promoted),
            "approved_top_roots": dict(root_counts.most_common(20)),
            "v0_2_visible_curriculum_records": (acceptance_summary or {}).get("records_visible_in_curriculum"),
        },
        "known_limitations": [
            "Seed profiles are phrase-based and bounded; they are not independent content evidence.",
            "Exact entity phrase matches can still be ambiguous across sites and are kept in review when site/root context conflicts.",
            "This is local refinement only and does not rebuild Curriculum Map v0.3.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--prior-approved", type=Path, default=DEFAULT_PRIOR_APPROVED)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--lecture-chunks", type=Path, default=DEFAULT_LECTURE_CHUNKS)
    parser.add_argument("--acceptance-summary", type=Path, default=DEFAULT_ACCEPTANCE_SUMMARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--review-sample-size", type=int, default=150)
    parser.add_argument("--review-sample-seed", type=int, default=330)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.candidates.exists():
        raise SystemExit(f"Missing candidates input: {args.candidates}")
    if not args.profiles.exists():
        raise SystemExit(f"Missing seed profile input: {args.profiles}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    candidates = load_candidates(args.candidates)
    profiles = load_profiles(args.profiles)
    prior_count = load_prior_approved_count(args.prior_approved)
    chunks = load_candidate_chunk_texts(args.lecture_chunks, {str(row.get("chunk_id") or "") for row in candidates})
    acceptance_summary = json.loads(args.acceptance_summary.read_text(encoding="utf-8")) if args.acceptance_summary.exists() else None

    rescored = [
        rescore_candidate(candidate, profiles.get(str(candidate.get("abpath_tag"))) or {}, chunks.get(str(candidate.get("chunk_id"))) or {})
        for candidate in candidates
    ]
    rescored.sort(key=lambda row: (str(row.get("root")), str(row.get("abpath_tag")), str(row.get("exemplar_status")), str(row.get("chunk_id"))))
    approved = [row for row in rescored if row.get("exemplar_status") == "approved_exemplar_high"]
    review = [row for row in rescored if row.get("exemplar_status") == "review_exemplar"]
    rejected = [row for row in rescored if row.get("exemplar_status") == "rejected_exemplar"]
    sample = make_review_sample(rescored, args.review_sample_size, args.review_sample_seed)
    audit = build_audit(args, acceptance_summary, prior_count, profiles, rescored)

    write_jsonl(args.output_dir / "lecture_abpath_gapfill_candidates_v0_3_EXEMPLAR_RESCORED.jsonl", rescored)
    write_jsonl(args.output_dir / "lecture_abpath_gapfill_approved_v0_3_EXEMPLAR_HIGHCONF.jsonl", approved)
    write_csv(args.output_dir / "lecture_abpath_gapfill_exemplar_review_queue_v0_3.csv", review + rejected)
    write_csv(args.output_dir / "lecture_gapfill_exemplar_review_sample_150.csv", sample)
    (args.output_dir / "lecture_abpath_gapfill_exemplar_audit_v0_3.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_readme(args.output_dir / "README_LECTURE_GAPFILL_EXEMPLAR_V0_3.md", audit)

    print(json.dumps(audit["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
