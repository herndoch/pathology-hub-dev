#!/usr/bin/env python3
"""Build exemplar seed profiles for lecture ABPath gap-fill refinement v0.3.

The output is a local sidecar only. It uses existing visible v0.2 curriculum
records as positive examples for tags already present in the lecture candidate
set, then extracts compact discriminative phrase profiles.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "curriculum_gapfill_v0_3"
DEFAULT_CANDIDATES = Path("outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_candidates_v0_3.jsonl")
DEFAULT_CURRICULUM_RECORDS = Path("outputs/curriculum_map_v0_2/curriculum_records_v0_2.jsonl")
DEFAULT_LECTURE_CHUNKS = Path(
    "data/curriculum_map_v0_2/lecture_timecoded_tagged_chunks_ROUTED_ONLY_STRICT_CYTO_v9.jsonl"
)
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
    "tumour",
    "tumours",
    "neoplasm",
    "neoplasms",
    "malignant",
    "benign",
    "neoplastic",
    "disease",
    "lesion",
    "lesions",
    "other",
    "miscellaneous",
    "pathology",
    "diagnosis",
    "clinical",
    "case",
    "cases",
    "slide",
    "segment",
    "lecture",
    "summary",
    "cleaned",
    "transcript",
    "image",
    "description",
    "time",
}

ROOT_ALIASES = {
    "GYN": {"gyn", "gynecologic", "gynecological", "cervix", "cervical", "endocervical", "uterus", "uterine", "endometrial", "endometrium", "ovary", "ovarian", "vagina", "vaginal", "vulva", "vulvar", "fallopian"},
    "HN": {"head", "neck", "salivary", "parotid", "submandibular", "oral", "oropharynx", "sinonasal", "nasal", "larynx", "thyroid", "branchial"},
    "BST": {"bone", "soft", "tissue", "sarcoma"},
    "BR": {"breast", "mammary"},
    "GI": {"gastrointestinal", "colon", "colonic", "stomach", "gastric", "esophagus", "intestinal", "appendix"},
    "GU": {"genitourinary", "prostate", "prostatic", "kidney", "renal", "bladder", "testis", "testicular"},
    "HEM": {"heme", "hematopathology", "lymphoma", "leukemia", "marrow"},
    "LUNG": {"lung", "pulmonary", "thoracic"},
    "DERM": {"skin", "cutaneous", "derm"},
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
    "without",
    "vs",
    "versus",
}

SIGNAL_TERMS = {
    "p16",
    "p53",
    "ki67",
    "er",
    "pr",
    "her2",
    "cd3",
    "cd5",
    "cd10",
    "cd20",
    "cd30",
    "cd34",
    "cd45",
    "cd56",
    "cd117",
    "ck7",
    "ck20",
    "ae1",
    "ae3",
    "sox10",
    "s100",
    "gata3",
    "ttf1",
    "napsin",
    "desmin",
    "myogenin",
    "myod1",
    "alk",
    "ros1",
    "egfr",
    "braf",
    "idh",
    "tert",
    "msh2",
    "msh6",
    "mlh1",
    "pms2",
    "hpv",
    "ebv",
    "fish",
    "fusion",
    "mutation",
    "amplification",
    "deletion",
    "necrosis",
    "mitotic",
    "keratinization",
    "glandular",
    "papillary",
    "solid",
    "cribriform",
    "mucinous",
    "squamous",
    "spindle",
    "clear",
    "basaloid",
}


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


def category_key(tag: str) -> str:
    parts = tag_parts(tag)
    return "::".join(parts[:3]) if len(parts) >= 3 else tag


def text_from_original_record(record: dict[str, Any]) -> str:
    original = record.get("original_record") or {}
    fields = [
        record.get("title"),
        original.get("title"),
        original.get("heading"),
        original.get("section_title"),
        original.get("summary"),
        original.get("text"),
        original.get("transcript_text"),
        original.get("caption"),
        original.get("diagnosis"),
        original.get("description"),
    ]
    return " ".join(str(field) for field in fields if field)


def text_from_lecture_chunk(row: dict[str, Any]) -> str:
    fields = [row.get("title"), row.get("summary"), row.get("transcript_text"), row.get("tag_basis")]
    return " ".join(str(field) for field in fields if field)


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 2 and token not in STOPWORDS and token not in GENERIC_TERMS
    ]


def phrase_ok(phrase: str) -> bool:
    tokens = tokenize(phrase)
    if not tokens:
        return False
    if all(token in GENERIC_TERMS for token in tokens):
        return False
    return any(len(token) >= 3 or token in SIGNAL_TERMS for token in tokens)


def ngrams(tokens: list[str], n: int) -> list[str]:
    out: list[str] = []
    for idx in range(0, max(0, len(tokens) - n + 1)):
        gram = tokens[idx : idx + n]
        if any(token in SIGNAL_TERMS for token in gram) or len(set(gram)) > 1:
            out.append(" ".join(gram))
    return out


def conflicts_other_root(phrase: str, root: str) -> bool:
    tokens = set(tokenize(phrase))
    if not tokens:
        return False
    own = ROOT_ALIASES.get(root, set())
    for other_root, aliases in ROOT_ALIASES.items():
        if other_root == root:
            continue
        if tokens & aliases and not tokens & own:
            return True
    return False


def extract_phrases(tag: str, texts: list[str], max_phrases: int) -> list[str]:
    counts: Counter[str] = Counter()
    root = root_of(tag)
    leaf = tag_leaf_phrase(tag)
    if phrase_ok(leaf) and not conflicts_other_root(leaf, root):
        counts[leaf] += 1000
    parts = [phrase_from_tag_part(part) for part in tag_parts(tag)[1:]]
    for part in parts:
        if phrase_ok(part) and part != root.lower() and not conflicts_other_root(part, root):
            counts[part] += 200

    for text in texts:
        tokens = tokenize(text)
        for token in tokens:
            if token in SIGNAL_TERMS:
                counts[token] += 3
        for phrase in ngrams(tokens, 2):
            if phrase_ok(phrase) and not conflicts_other_root(phrase, root):
                counts[phrase] += 2
        for phrase in ngrams(tokens, 3):
            if phrase_ok(phrase) and not conflicts_other_root(phrase, root):
                counts[phrase] += 3

    phrases = [
        phrase
        for phrase, _ in counts.most_common(max_phrases * 3)
        if phrase_ok(phrase) and not conflicts_other_root(phrase, root)
    ]
    deduped: list[str] = []
    for phrase in phrases:
        if phrase in deduped:
            continue
        if any(phrase != prior and phrase in prior and len(phrase.split()) == 1 for prior in deduped):
            continue
        deduped.append(phrase)
        if len(deduped) >= max_phrases:
            break
    return deduped


def load_candidate_tags(path: Path) -> set[str]:
    tags: set[str] = set()
    for row in read_jsonl(path):
        tag = str(row.get("abpath_tag") or "")
        if tag and not has_forbidden(tag):
            tags.add(tag)
    return tags


def collect_curriculum_examples(path: Path, candidate_tags: set[str], max_examples: int) -> tuple[dict[str, list[str]], dict[str, Counter[str]], Counter[str]]:
    examples: dict[str, list[str]] = defaultdict(list)
    source_counts: dict[str, Counter[str]] = defaultdict(Counter)
    status_counts: Counter[str] = Counter()
    if not path.exists():
        return examples, source_counts, status_counts

    for record in read_jsonl(path):
        tag = str(record.get("approved_tag") or "")
        if tag not in candidate_tags or has_forbidden(record):
            continue
        if not record.get("visible"):
            continue
        source = str(record.get("source") or "unknown")
        if source == "abpath":
            continue
        text = text_from_original_record(record)
        if text and len(examples[tag]) < max_examples:
            examples[tag].append(text)
        source_counts[tag][source] += 1
        status_counts[str(record.get("status") or "")] += 1
    return examples, source_counts, status_counts


def collect_lecture_examples(path: Path, candidate_tags: set[str], max_examples: int) -> tuple[dict[str, list[str]], dict[str, Counter[str]]]:
    examples: dict[str, list[str]] = defaultdict(list)
    source_counts: dict[str, Counter[str]] = defaultdict(Counter)
    if not path.exists():
        return examples, source_counts

    for row in read_jsonl(path):
        tags = [
            str(row.get("primary_tag_governed") or ""),
            str(row.get("primary_tag") or ""),
            str(row.get("primary_tag_original_pre_governance_v10_4") or ""),
        ]
        for tag in dict.fromkeys(tags):
            if tag not in candidate_tags or has_forbidden(tag):
                continue
            text = text_from_lecture_chunk(row)
            if text and len(examples[tag]) < max_examples:
                examples[tag].append(text)
            source_counts[tag]["lecture_chunks"] += 1
    return examples, source_counts


def build_profiles(
    candidate_tags: set[str],
    curriculum_examples: dict[str, list[str]],
    curriculum_source_counts: dict[str, Counter[str]],
    lecture_examples: dict[str, list[str]],
    lecture_source_counts: dict[str, Counter[str]],
    max_phrases: int,
) -> list[dict[str, Any]]:
    all_positive: dict[str, list[str]] = {}
    base_phrases_by_tag: dict[str, set[str]] = {}
    for tag in sorted(candidate_tags):
        texts = (curriculum_examples.get(tag) or []) + (lecture_examples.get(tag) or [])
        all_positive[tag] = texts
        base_phrases_by_tag[tag] = set(extract_phrases(tag, texts, max_phrases))

    sibling_terms: dict[str, Counter[str]] = defaultdict(Counter)
    for tag, phrases in base_phrases_by_tag.items():
        root = root_of(tag)
        own_category = category_key(tag)
        for other, other_phrases in base_phrases_by_tag.items():
            if other == tag or root_of(other) != root:
                continue
            if category_key(other) == own_category:
                continue
            for phrase in other_phrases:
                if phrase not in phrases:
                    sibling_terms[tag][phrase] += 1

    profiles: list[dict[str, Any]] = []
    for tag in sorted(candidate_tags):
        curriculum_counts = curriculum_source_counts.get(tag) or Counter()
        lecture_counts = lecture_source_counts.get(tag) or Counter()
        source_counts = Counter()
        source_counts.update(curriculum_counts)
        source_counts.update(lecture_counts)
        seed_count = sum(source_counts.values())
        limitations: list[str] = []
        if seed_count == 0:
            limitations.append("No already-tagged positive records found locally; profile uses tag-derived phrase anchors only.")
        if len(all_positive.get(tag) or []) < seed_count:
            limitations.append("Phrase extraction used a bounded text sample per tag.")
        negatives = [phrase for phrase, _ in sibling_terms[tag].most_common(30) if phrase_ok(phrase)]
        profiles.append(
            {
                "schema_version": SCHEMA_VERSION,
                "abpath_tag": tag,
                "root": root_of(tag),
                "seed_record_count": seed_count,
                "positive_phrases": sorted(base_phrases_by_tag[tag]),
                "negative_or_ambiguous_phrases": negatives,
                "source_counts": dict(sorted(source_counts.items())),
                "limitations": limitations,
            }
        )
    return profiles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--curriculum-records", type=Path, default=DEFAULT_CURRICULUM_RECORDS)
    parser.add_argument("--lecture-chunks", type=Path, default=DEFAULT_LECTURE_CHUNKS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-examples-per-tag", type=int, default=80)
    parser.add_argument("--max-positive-phrases", type=int, default=35)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.candidates.exists():
        raise SystemExit(f"Missing candidates input: {args.candidates}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    candidate_tags = load_candidate_tags(args.candidates)
    curriculum_examples, curriculum_source_counts, curriculum_status_counts = collect_curriculum_examples(
        args.curriculum_records, candidate_tags, args.max_examples_per_tag
    )
    lecture_examples, lecture_source_counts = collect_lecture_examples(
        args.lecture_chunks, candidate_tags, args.max_examples_per_tag
    )
    profiles = build_profiles(
        candidate_tags,
        curriculum_examples,
        curriculum_source_counts,
        lecture_examples,
        lecture_source_counts,
        args.max_positive_phrases,
    )

    profiles_path = args.output_dir / "lecture_tag_seed_profiles_v0_3.jsonl"
    with profiles_path.open("w", encoding="utf-8") as handle:
        for profile in profiles:
            handle.write(json.dumps(profile, ensure_ascii=False, sort_keys=True) + "\n")

    counts = {
        "candidate_tags": len(candidate_tags),
        "seed_profiles_written": len(profiles),
        "tags_with_seed_profiles": sum(1 for profile in profiles if profile["seed_record_count"] > 0),
        "curriculum_status_counts": dict(sorted(curriculum_status_counts.items())),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output": str(profiles_path),
    }
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
