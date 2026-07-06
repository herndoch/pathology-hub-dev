#!/usr/bin/env python3
"""Build cross-source tag seed profiles for Curriculum Gap Fill v0.3."""

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
DEFAULT_OUTPUT_DIR = Path("outputs/curriculum_gapfill_v0_3")

SOURCE_ORDER = ("who", "pathout", "textbooks", "lectures")
SOURCE_WEIGHTS = {"who": 5, "pathout": 4, "textbooks": 3, "lectures": 1}
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
    "lesion",
    "lesions",
    "disease",
    "pathology",
    "diagnosis",
    "diagnostic",
    "other",
    "miscellaneous",
    "case",
    "cases",
    "clinical",
    "slide",
    "section",
    "chapter",
    "features",
    "feature",
    "histology",
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
    "may",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
    "without",
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
    "cribriform",
    "mucinous",
    "squamous",
    "spindle",
    "clear",
    "basaloid",
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


def norm_phrase(value: str) -> str:
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def tag_parts(tag: str) -> list[str]:
    return [part for part in tag.split("::") if part]


def tag_metadata(tag: str) -> dict[str, str]:
    parts = tag_parts(tag)
    return {
        "root": parts[0] if parts else "",
        "organ_site": norm_phrase(parts[1]) if len(parts) > 1 else "",
        "category": norm_phrase(parts[2]) if len(parts) > 2 else "",
        "entity_phrase": norm_phrase(parts[-1]) if parts else "",
        "tag_path_phrase": norm_phrase(" ".join(parts[1:])),
    }


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 2 and token not in STOPWORDS and token not in GENERIC_TERMS
    ]


def phrase_ok(phrase: str) -> bool:
    tokens = tokenize(phrase)
    return bool(tokens) and any(len(token) >= 3 or token in SIGNAL_TERMS for token in tokens)


def conflicts_other_root(phrase: str, root: str) -> bool:
    phrase_tokens = set(tokenize(phrase))
    own = ROOT_ALIASES.get(root, set())
    for other_root, aliases in ROOT_ALIASES.items():
        if other_root == root:
            continue
        if phrase_tokens & aliases and not phrase_tokens & own:
            return True
    return False


def ngrams(tokens: list[str], n: int) -> list[str]:
    return [" ".join(tokens[i : i + n]) for i in range(0, max(0, len(tokens) - n + 1))]


def record_text(record: dict[str, Any]) -> str:
    original = record.get("original_record") or {}
    fields = [
        record.get("title"),
        original.get("entity_name"),
        original.get("title"),
        original.get("page_title"),
        original.get("primary_header"),
        original.get("chapter_title"),
        original.get("section_heading"),
        original.get("definition"),
        original.get("related_terminology"),
        original.get("essential_and_desirable_diagnostic_criteria"),
        original.get("differential_diagnosis"),
        original.get("microscopic"),
        original.get("ancillary_studies"),
        original.get("diagnostic_molecular_pathology"),
        original.get("pathogenesis"),
        original.get("clean_text"),
        original.get("text"),
        original.get("tag_basis"),
    ]
    return " ".join(str(field) for field in fields if field)


def extract_terms(texts: list[str], base_phrases: list[str], max_terms: int) -> list[str]:
    counts: Counter[str] = Counter()
    for phrase in base_phrases:
        if phrase_ok(phrase):
            counts[phrase] += 1000
    for text in texts:
        tokens = tokenize(text)
        for token in tokens:
            if token in SIGNAL_TERMS:
                counts[token] += 5
        for phrase in ngrams(tokens, 2):
            if phrase_ok(phrase):
                counts[phrase] += 2
        for phrase in ngrams(tokens, 3):
            if phrase_ok(phrase):
                counts[phrase] += 3
    terms: list[str] = []
    for phrase, _ in counts.most_common(max_terms * 3):
        if phrase in terms or not phrase_ok(phrase):
            continue
        if len(phrase.split()) == 1 and any(phrase in prior.split() for prior in terms):
            continue
        terms.append(phrase)
        if len(terms) >= max_terms:
            break
    return terms


def load_candidate_tags(path: Path) -> set[str]:
    tags: set[str] = set()
    for row in read_jsonl(path):
        tag = str(row.get("abpath_tag") or "")
        if tag and not has_forbidden(tag):
            tags.add(tag)
    return tags


def collect_examples(path: Path, candidate_tags: set[str], max_examples_per_source: int) -> tuple[dict[str, dict[str, list[str]]], dict[str, Counter[str]]]:
    examples: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in read_jsonl(path):
        tag = str(record.get("approved_tag") or "")
        source = str(record.get("source") or "")
        if tag not in candidate_tags or source not in SOURCE_ORDER:
            continue
        if not record.get("visible") or has_forbidden(record):
            continue
        counts[tag][source] += 1
        if len(examples[tag][source]) < max_examples_per_source:
            text = record_text(record)
            if text:
                examples[tag][source].append(text)
    return examples, counts


def source_terms_for_tag(tag: str, examples: dict[str, list[str]], max_terms: int) -> dict[str, list[str]]:
    meta = tag_metadata(tag)
    base = [meta["entity_phrase"], meta["organ_site"], meta["category"]]
    terms: dict[str, list[str]] = {}
    for source in SOURCE_ORDER:
        source_examples = examples.get(source, [])
        if not source_examples:
            terms[source] = []
            continue
        terms[source] = extract_terms(
            source_examples,
            base if source != "lectures" else [meta["entity_phrase"]],
            max_terms,
        )
    return terms


def build_profiles(candidate_tags: set[str], examples: dict[str, dict[str, list[str]]], counts: dict[str, Counter[str]], max_terms: int) -> list[dict[str, Any]]:
    raw_terms: dict[str, dict[str, list[str]]] = {}
    for tag in candidate_tags:
        raw_terms[tag] = source_terms_for_tag(tag, examples.get(tag, {}), max_terms)

    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for tag in candidate_tags:
        meta = tag_metadata(tag)
        grouped[(meta["root"], meta["category"])].append(tag)

    profiles: list[dict[str, Any]] = []
    for tag in sorted(candidate_tags):
        meta = tag_metadata(tag)
        weighted: Counter[str] = Counter()
        for source, terms in raw_terms[tag].items():
            for term in terms:
                weighted[term] += SOURCE_WEIGHTS[source]
        positive = [
            term
            for term, _ in weighted.most_common(max_terms * 2)
            if phrase_ok(term) and not conflicts_other_root(term, meta["root"])
        ][:max_terms]
        sibling_tags = [
            other
            for (root, category), tags in grouped.items()
            for other in tags
            if other != tag and root == meta["root"] and (category != meta["category"] or tag_metadata(other)["organ_site"] != meta["organ_site"])
        ][:50]
        negative_counts: Counter[str] = Counter()
        own = set(positive)
        for sibling in sibling_tags:
            for source_terms in raw_terms.get(sibling, {}).values():
                for term in source_terms:
                    if term not in own and phrase_ok(term) and not conflicts_other_root(term, meta["root"]):
                        negative_counts[term] += 1
        source_counts = counts.get(tag) or Counter()
        seed_count = sum(source_counts.values())
        limitations: list[str] = []
        if seed_count == 0:
            limitations.append("No visible cross-source curriculum records found; profile relies on normalized tag phrases only.")
        if not source_counts.get("who"):
            limitations.append("No WHO seed record found for this tag in local v0.2 records.")
        if not source_counts.get("pathout"):
            limitations.append("No PathOut seed record found for this tag in local v0.2 records.")
        profiles.append(
            {
                "schema_version": SCHEMA_VERSION,
                "abpath_tag": tag,
                **meta,
                "who_terms": raw_terms[tag]["who"],
                "pathout_terms": raw_terms[tag]["pathout"],
                "textbook_terms": raw_terms[tag]["textbooks"],
                "lecture_terms": raw_terms[tag]["lectures"],
                "positive_phrases": positive,
                "negative_or_ambiguous_phrases": [term for term, _ in negative_counts.most_common(40)],
                "sibling_tags": sibling_tags,
                "source_counts": dict(sorted(source_counts.items())),
                "seed_record_count": seed_count,
                "limitations": limitations,
            }
        )
    return profiles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--curriculum-records", type=Path, default=DEFAULT_CURRICULUM_RECORDS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-examples-per-source", type=int, default=60)
    parser.add_argument("--max-terms-per-source", type=int, default=35)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.candidates.exists():
        raise SystemExit(f"Missing candidates: {args.candidates}")
    if not args.curriculum_records.exists():
        raise SystemExit(f"Missing curriculum records: {args.curriculum_records}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_tags = load_candidate_tags(args.candidates)
    examples, counts = collect_examples(args.curriculum_records, candidate_tags, args.max_examples_per_source)
    profiles = build_profiles(candidate_tags, examples, counts, args.max_terms_per_source)
    out = args.output_dir / "cross_source_tag_seed_profiles_v0_3.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for profile in profiles:
            handle.write(json.dumps(profile, ensure_ascii=False, sort_keys=True) + "\n")
    source_coverage = Counter()
    for profile in profiles:
        for source, count in profile["source_counts"].items():
            if count:
                source_coverage[source] += 1
    summary = {
        "candidate_tags": len(candidate_tags),
        "profiles_written": len(profiles),
        "tags_with_cross_source_profiles": sum(1 for p in profiles if p["seed_record_count"] > 0),
        "tags_lacking_profile": sum(1 for p in profiles if p["seed_record_count"] == 0),
        "source_tag_coverage": dict(sorted(source_coverage.items())),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output": str(out),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
