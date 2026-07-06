#!/usr/bin/env python3
"""Run full hybrid ABPath gap-fill for lectures and textbooks."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import curriculum_gapfill_v0_3_build_cross_source_seed_profiles as seeds
import curriculum_gapfill_v0_3_hybrid_rescore_lecture_candidates as hybrid


SCHEMA_VERSION = "curriculum_gapfill_v0_3"
METHOD = "cross_source_hybrid_fts_abpath_gapfill_v0_3"
DEFAULT_ABPATH = Path("data/curriculum_map_v0_2/abpath_source_tags.jsonl")
DEFAULT_CURRICULUM_RECORDS = Path("outputs/curriculum_map_v0_2/curriculum_records_v0_2.jsonl")
DEFAULT_LECTURES = Path("data/curriculum_map_v0_2/lecture_timecoded_tagged_chunks_ROUTED_ONLY_STRICT_CYTO_v9.jsonl")
DEFAULT_TEXTBOOKS = Path("data/curriculum_map_v0_2/textbook_primary_tagged_chunks_v1.jsonl")
DEFAULT_OUTPUT_DIR = Path("outputs/curriculum_gapfill_v0_3")
FORBIDDEN_PATTERNS = hybrid.FORBIDDEN_PATTERNS
GENERIC_TERMS = {
    "and",
    "or",
    "of",
    "the",
    "with",
    "without",
    "tumor",
    "tumors",
    "tumour",
    "tumours",
    "neoplasm",
    "neoplasms",
    "malignant",
    "benign",
    "lesion",
    "lesions",
    "disease",
    "pathology",
    "diagnosis",
    "other",
    "miscellaneous",
}
ROOT_LABELS = {
    "BST": ("bone", "soft tissue", "sarcoma"),
    "Breast": ("breast", "mammary"),
    "BR": ("breast", "mammary"),
    "DERM": ("skin", "cutaneous", "dermatology"),
    "GI": ("gastrointestinal", "colon", "gastric", "stomach", "intestinal", "esophagus"),
    "GU": ("genitourinary", "kidney", "renal", "bladder", "prostate", "testis"),
    "GYN": ("gynecologic", "gynecology", "cervix", "uterus", "ovary", "vulva", "vagina"),
    "Heme": ("hematopathology", "lymphoma", "leukemia", "marrow"),
    "HEM": ("hematopathology", "lymphoma", "leukemia", "marrow"),
    "HN": ("head and neck", "salivary", "thyroid", "oral", "sinonasal", "larynx"),
    "Liver": ("liver", "hepatic", "biliary"),
    "LUNG": ("lung", "pulmonary", "thoracic"),
    "Neuro": ("brain", "central nervous", "neuropathology"),
    "RENAL": ("renal", "kidney"),
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
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else str(value)
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def norm_phrase(value: str) -> str:
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    return clean_space(value).lower()


def root_of(tag: str) -> str:
    return tag.split("::", 1)[0] if "::" in tag else tag


def tag_leaf(tag: str) -> str:
    return tag.split("::")[-1] if tag else ""


def load_abpath(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in read_jsonl(path):
        tag = str(row.get("primary_tag") or "").strip()
        if not tag or tag in seen or has_forbidden(tag):
            continue
        seen.add(tag)
        rows.append({"primary_tag": tag, "title": str(row.get("title") or tag_leaf(tag)), "root": root_of(tag)})
    return rows


def fts_quote(phrase: str) -> str:
    return '"' + phrase.replace('"', '""') + '"'


def fts_token(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "", token)


def terms_for_phrase(phrase: str) -> list[str]:
    terms = re.findall(r"[a-z0-9]+", phrase.lower())
    return [term for term in terms if len(term) >= 3 and term not in GENERIC_TERMS]


def make_queries(tag: str, title: str) -> list[tuple[str, str, list[str]]]:
    leaf_phrase = norm_phrase(title or tag_leaf(tag))
    path_phrase = norm_phrase(" ".join(tag.split("::")[1:]))
    leaf_terms = terms_for_phrase(leaf_phrase)
    path_terms = terms_for_phrase(path_phrase)
    queries: list[tuple[str, str, list[str]]] = []
    if leaf_phrase and len(leaf_phrase) >= 4 and leaf_terms:
        queries.append(("leaf_exact", fts_quote(leaf_phrase), leaf_terms))
    if len(leaf_terms) >= 2:
        queries.append(("leaf_terms", " AND ".join(fts_token(term) for term in leaf_terms), leaf_terms))
    cluster = list(dict.fromkeys(leaf_terms[:3] + [term for term in path_terms if term not in leaf_terms][:2]))
    if len(cluster) >= 2:
        queries.append(("path_cluster", " AND ".join(fts_token(term) for term in cluster), cluster))
    return [(name, query, terms) for name, query, terms in queries if query and all(fts_token(term) for term in terms)]


def exact_phrase_present(phrase: str, text: str) -> bool:
    return bool(phrase) and re.search(r"\b" + re.escape(phrase.lower()) + r"\b", text.lower()) is not None


def matched_terms(terms: list[str], text: str) -> list[str]:
    lower = text.lower()
    return [term for term in terms if re.search(r"\b" + re.escape(term) + r"\b", lower)]


def root_context_present(root: str, original_tag: str, text: str) -> bool:
    if original_tag.startswith(root + "::"):
        return True
    lower = text.lower()
    return any(label in lower for label in ROOT_LABELS.get(root, (root.lower(),)))


def term_window_bonus(terms: list[str], text: str, window: int = 90) -> bool:
    positions: list[tuple[int, str]] = []
    lower = text.lower()
    for term in terms:
        match = re.search(r"\b" + re.escape(term) + r"\b", lower)
        if match:
            positions.append((match.start(), term))
    positions.sort()
    for idx, (start, term) in enumerate(positions):
        seen = {term}
        for next_start, next_term in positions[idx + 1 :]:
            if next_start - start > window:
                break
            seen.add(next_term)
            if len(seen) >= 2:
                return True
    return False


def confidence_for(score: float) -> str:
    if score >= 0.9:
        return "high"
    if score >= 0.7:
        return "medium"
    return "low"


def excerpt(text: str, terms: list[str], phrase: str, size: int = 420) -> str:
    lower = text.lower()
    starts = []
    if phrase and (found := lower.find(phrase.lower())) >= 0:
        starts.append(found)
    for term in terms:
        found = lower.find(term.lower())
        if found >= 0:
            starts.append(found)
    start = max(0, (min(starts) if starts else 0) - size // 3)
    return clean_space(text[start : start + size])


def target_fields(row: dict[str, Any], source_family: str) -> tuple[str, str, str, str, str]:
    if source_family == "lectures":
        title = str(row.get("title") or "")
        text = clean_space(" ".join(str(row.get(key) or "") for key in ("title", "summary", "transcript_text", "tag_basis")))
        source_id = str(row.get("video_id") or row.get("raw_source_gcs_uri") or "")
        video_id = str(row.get("video_id") or "")
    else:
        title = clean_space(" ".join(str(row.get(key) or "") for key in ("source_title", "chapter_title", "section_heading") if row.get(key)))
        text = clean_space(" ".join(str(row.get(key) or "") for key in ("source_title", "chapter_title", "section_heading", "text", "primary_tag_basis") if row.get(key)))
        source_id = str(row.get("source_id") or row.get("source_title") or row.get("raw_source_gcs_uri") or "")
        video_id = ""
    original_tag = str(row.get("primary_tag_governed") or row.get("primary_tag") or row.get("primary_tag_original_pre_governance_v10_4") or "")
    return title, text, source_id, video_id, original_tag


def create_fts(path: Path, source_family: str) -> tuple[sqlite3.Connection, dict[str, Any]]:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, source_id TEXT, video_id TEXT, title TEXT, text TEXT, original_tag TEXT)")
    conn.execute("CREATE VIRTUAL TABLE chunk_fts USING fts5(chunk_id UNINDEXED, title, text)")
    stats = Counter()
    for row in read_jsonl(path):
        stats["input_rows"] += 1
        chunk_id = str(row.get("chunk_id") or "").strip()
        if not chunk_id:
            continue
        title, text, source_id, video_id, original_tag = target_fields(row, source_family)
        if has_forbidden(original_tag):
            stats["skipped_forbidden_original_tag_rows"] += 1
            continue
        if not text:
            continue
        conn.execute("INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?, ?, ?)", (chunk_id, source_id, video_id, title, text, original_tag))
        conn.execute("INSERT INTO chunk_fts(chunk_id, title, text) VALUES (?, ?, ?)", (chunk_id, title, text))
        stats["indexed_rows"] += 1
    conn.commit()
    return conn, dict(stats)


def score_match(tag: str, root: str, query_name: str, query_terms: list[str], title: str, text: str, original_tag: str) -> tuple[float, str, list[str], str]:
    leaf_phrase = norm_phrase(tag_leaf(tag))
    all_text = clean_space(f"{title} {text}")
    found_terms = matched_terms(query_terms, all_text)
    exact = exact_phrase_present(leaf_phrase, all_text)
    root_context = root_context_present(root, original_tag, all_text)
    score = 0.0
    reasons: list[str] = []
    if exact:
        score += 0.56
        reasons.append("exact ABPath entity phrase present")
    if len(found_terms) >= 2 and term_window_bonus(found_terms, all_text):
        score += 0.28
        reasons.append("strong matched-term cluster")
    elif len(found_terms) >= 2:
        score += 0.18
        reasons.append("matched-term cluster")
    if root_context:
        score += 0.16
        reasons.append("root context supported")
    if title and exact_phrase_present(leaf_phrase, title):
        score += 0.12
        reasons.append("title or heading match")
    if not original_tag or original_tag == "_UNMAPPED_":
        score += 0.04
        reasons.append("fills unmapped target chunk")
    if original_tag == tag:
        score = 0.0
        reasons.append("already has exact ABPath tag")
    score = min(score, 1.0)
    return score, confidence_for(score), found_terms, "; ".join(reasons) if reasons else "weak lexical match"


def generate_candidates(conn: sqlite3.Connection, tags: list[dict[str, str]], source_family: str, max_candidates_per_tag: int, max_fts_hits_per_query: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    stats = Counter()
    per_tag = Counter()
    for tag_row in tags:
        tag = tag_row["primary_tag"]
        root = tag_row["root"]
        best_by_chunk: dict[str, dict[str, Any]] = {}
        for query_name, fts_query, query_terms in make_queries(tag, tag_row["title"]):
            try:
                rows = conn.execute(
                    "SELECT c.chunk_id, c.source_id, c.video_id, c.title, c.text, c.original_tag "
                    "FROM chunk_fts f JOIN chunks c ON c.chunk_id = f.chunk_id WHERE chunk_fts MATCH ? LIMIT ?",
                    (fts_query, max_fts_hits_per_query),
                ).fetchall()
            except sqlite3.OperationalError:
                stats["query_errors"] += 1
                continue
            for chunk_id, source_id, video_id, title, text, original_tag in rows:
                stats["raw_fts_hits"] += 1
                if original_tag == tag or has_forbidden(original_tag):
                    continue
                score, confidence, found, reason = score_match(tag, root, query_name, query_terms, title or "", text or "", original_tag or "")
                if confidence == "low":
                    stats["low_confidence_hidden_count"] += 1
                    continue
                row = {
                    "schema_version": SCHEMA_VERSION,
                    "source_family": source_family,
                    "chunk_id": chunk_id,
                    "source_id": source_id,
                    "video_id": video_id or None,
                    "abpath_tag": tag,
                    "root": root,
                    "matched_query": query_name,
                    "matched_terms": found,
                    "score": round(score, 3),
                    "confidence": confidence,
                    "method": METHOD,
                    "review_status": "candidate",
                    "text_excerpt": excerpt(text or title or "", found, norm_phrase(tag_leaf(tag))),
                    "original_existing_tag": original_tag or None,
                    "reason": reason,
                }
                if has_forbidden(row):
                    continue
                previous = best_by_chunk.get(chunk_id)
                if previous is None or float(row["score"]) > float(previous["score"]):
                    best_by_chunk[chunk_id] = row
        ranked = sorted(best_by_chunk.values(), key=lambda row: (-float(row["score"]), str(row["chunk_id"])))
        for row in ranked[:max_candidates_per_tag]:
            candidates.append(row)
            per_tag[tag] += 1
    candidates.sort(key=lambda row: (str(row["source_family"]), str(row["root"]), str(row["abpath_tag"]), -float(row["score"]), str(row["chunk_id"])))
    stats["tags_with_candidates"] = len(per_tag)
    stats["candidate_rows"] = len(candidates)
    return candidates, dict(stats)


def load_chunk_lookup(path: Path, source_family: str, chunk_ids: set[str]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for row in read_jsonl(path):
        chunk_id = str(row.get("chunk_id") or "")
        if chunk_id not in chunk_ids:
            continue
        title, text, _, _, original_tag = target_fields(row, source_family)
        lookup[chunk_id] = {"title": title, "text": text, "primary_tag": original_tag}
        if len(lookup) >= len(chunk_ids):
            break
    return lookup


def split_approved(rows: list[dict[str, Any]], source_family: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    approved: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        decision = str(row.get("hybrid_decision") or "")
        key = (str(row.get("chunk_id") or ""), str(row.get("abpath_tag") or ""))
        if has_forbidden(row.get("abpath_tag")) or has_forbidden(row.get("original_existing_tag")):
            bad = dict(row)
            bad["rejection_reason"] = "forbidden_visible_tag_field"
            rejected.append(bad)
        elif decision == "approved_hybrid_high" and key not in seen:
            item = dict(row)
            item.update(
                {
                    "approval_status": "approved_hybrid_high_confidence_staged",
                    "approved_by_method": METHOD,
                    "approval_scope": "curriculum_map_v0_3_staging",
                    "ontology_source": "abpath",
                    "content_source": source_family,
                }
            )
            approved.append(item)
            seen.add(key)
        elif decision == "approved_hybrid_high":
            dup = dict(row)
            dup["rejection_reason"] = "duplicate_chunk_id_abpath_tag"
            rejected.append(dup)
        elif decision == "review_hybrid":
            review.append(dict(row))
        else:
            bad = dict(row)
            bad.setdefault("rejection_reason", decision or "not_approved")
            rejected.append(bad)
    return approved, review, rejected


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    preferred = ["source_family", "abpath_tag", "root", "chunk_id", "source_id", "hybrid_decision", "hybrid_score", "confidence", "score", "vector_status", "hybrid_reason", "original_existing_tag", "text_excerpt", "rejection_reason"]
    fields: list[str] = []
    seen: set[str] = set()
    for field in preferred:
        fields.append(field)
        seen.add(field)
    for row in rows:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json.dumps(row.get(field), ensure_ascii=False, sort_keys=True) if isinstance(row.get(field), (list, dict)) else ("" if row.get(field) is None else row.get(field)) for field in fields})


def sample_rows(rows: list[dict[str, Any]], size: int, seed: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("source_family") or ""), str(row.get("root") or ""), str(row.get("hybrid_decision") or ""))].append(row)
    out: list[dict[str, Any]] = []
    used: set[tuple[str, str]] = set()
    take = max(1, size // max(1, len(groups)))
    for key in sorted(groups):
        ranked = sorted(groups[key], key=lambda row: (-float(row.get("hybrid_score") or 0), str(row.get("chunk_id"))))
        for row in ranked[:take]:
            row_key = (str(row.get("chunk_id")), str(row.get("abpath_tag")))
            if row_key not in used:
                out.append(row)
                used.add(row_key)
            if len(out) >= size:
                return out
    rest = [row for row in rows if (str(row.get("chunk_id")), str(row.get("abpath_tag"))) not in used]
    random.Random(seed).shuffle(rest)
    out.extend(rest[: max(0, size - len(out))])
    return out[:size]


def write_readme(path: Path, audit: dict[str, Any]) -> None:
    counts = audit["counts"]
    text = f"""# Curriculum Gap Fill v0.3

Full staged hybrid ABPath gap-fill outputs for lectures and textbooks.

ABPath is ontology/tag provenance only. WHO, PathOut, textbooks, existing approved curriculum records, and secondary lecture tags provide semantic seed context. Lectures and textbooks are target corpora for new sidecars.

Counts:
- ABPath tags processed: {counts["abpath_tags"]}
- seed profiles: {counts["seed_profiles"]}
- lecture approved/review/rejected: {counts["lectures"]["approved"]}/{counts["lectures"]["review"]}/{counts["lectures"]["rejected"]}
- textbook approved/review/rejected: {counts["textbooks"]["approved"]}/{counts["textbooks"]["review"]}/{counts["textbooks"]["rejected"]}
- forbidden approved hits: {counts["forbidden_approved_hits"]}
- vector status: {audit["vector_status"]}

These artifacts are staged data product inputs. They do not overwrite raw normalized records, vector docstores, FAISS indexes, or Curriculum Map v0.2 outputs.
"""
    path.write_text(text, encoding="utf-8")


def run_target(path: Path, source_family: str, tags: list[dict[str, str]], profiles: dict[str, dict[str, Any]], args: argparse.Namespace, vec_status: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    conn, input_stats = create_fts(path, source_family)
    candidates, candidate_stats = generate_candidates(conn, tags, source_family, args.max_candidates_per_tag, args.max_fts_hits_per_query)
    chunk_lookup = load_chunk_lookup(path, source_family, {str(row.get("chunk_id") or "") for row in candidates})
    rescored = [
        hybrid.rescore(row, profiles.get(str(row.get("abpath_tag"))) or {}, chunk_lookup.get(str(row.get("chunk_id"))) or {}, vec_status)
        for row in candidates
    ]
    for row in rescored:
        row["source_family"] = source_family
    approved, review, rejected = split_approved(rescored, source_family)
    stats = {
        "input": input_stats,
        "candidate": candidate_stats,
        "rescored": len(rescored),
        "approved": len(approved),
        "review": len(review),
        "rejected": len(rejected),
        "decision_counts": dict(Counter(str(row.get("hybrid_decision") or "") for row in rescored)),
        "approved_root_counts": dict(Counter(str(row.get("root") or "") for row in approved).most_common(30)),
        "approved_tag_counts": dict(Counter(str(row.get("abpath_tag") or "") for row in approved).most_common(30)),
    }
    return rescored, approved, review, rejected, stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abpath-tags", type=Path, default=DEFAULT_ABPATH)
    parser.add_argument("--curriculum-records", type=Path, default=DEFAULT_CURRICULUM_RECORDS)
    parser.add_argument("--lecture-chunks", type=Path, default=DEFAULT_LECTURES)
    parser.add_argument("--textbook-chunks", type=Path, default=DEFAULT_TEXTBOOKS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-examples-per-source", type=int, default=80)
    parser.add_argument("--max-terms-per-source", type=int, default=40)
    parser.add_argument("--max-candidates-per-tag", type=int, default=40)
    parser.add_argument("--max-fts-hits-per-query", type=int, default=400)
    parser.add_argument("--review-sample-size", type=int, default=200)
    parser.add_argument("--review-sample-seed", type=int, default=403)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in (args.abpath_tags, args.curriculum_records, args.lecture_chunks, args.textbook_chunks):
        if not path.exists():
            raise SystemExit(f"Missing required input: {path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    tags = load_abpath(args.abpath_tags)
    tag_set = {row["primary_tag"] for row in tags}
    examples, source_counts = seeds.collect_examples(args.curriculum_records, tag_set, args.max_examples_per_source)
    profile_rows = seeds.build_profiles(tag_set, examples, source_counts, args.max_terms_per_source)
    profile_map = {row["abpath_tag"]: row for row in profile_rows}
    profiles_path = args.output_dir / "cross_source_tag_seed_profiles_FULL_v0_3.jsonl"
    write_jsonl(profiles_path, profile_rows)
    vec_status, vec_sources = hybrid.vector_status()

    lecture_rescored, lecture_approved, lecture_review, lecture_rejected, lecture_stats = run_target(args.lecture_chunks, "lectures", tags, profile_map, args, vec_status)
    textbook_rescored, textbook_approved, textbook_review, textbook_rejected, textbook_stats = run_target(args.textbook_chunks, "textbooks", tags, profile_map, args, vec_status)

    outputs = {
        "lecture_candidates": args.output_dir / "lecture_abpath_gapfill_candidates_FULL_v0_3.jsonl",
        "lecture_approved": args.output_dir / "lecture_abpath_gapfill_approved_FULL_v0_3.jsonl",
        "lecture_review": args.output_dir / "lecture_abpath_gapfill_review_FULL_v0_3.csv",
        "lecture_rejected": args.output_dir / "lecture_abpath_gapfill_rejected_FULL_v0_3.csv",
        "textbook_candidates": args.output_dir / "textbook_abpath_gapfill_candidates_FULL_v0_3.jsonl",
        "textbook_approved": args.output_dir / "textbook_abpath_gapfill_approved_FULL_v0_3.jsonl",
        "textbook_review": args.output_dir / "textbook_abpath_gapfill_review_FULL_v0_3.csv",
        "textbook_rejected": args.output_dir / "textbook_abpath_gapfill_rejected_FULL_v0_3.csv",
        "audit": args.output_dir / "curriculum_gapfill_v0_3_audit.json",
        "review_sample": args.output_dir / "curriculum_gapfill_v0_3_review_sample.csv",
        "readme": args.output_dir / "README_CURRICULUM_GAPFILL_V0_3.md",
    }
    write_jsonl(outputs["lecture_candidates"], lecture_rescored)
    write_jsonl(outputs["lecture_approved"], lecture_approved)
    write_csv(outputs["lecture_review"], lecture_review)
    write_csv(outputs["lecture_rejected"], lecture_rejected)
    write_jsonl(outputs["textbook_candidates"], textbook_rescored)
    write_jsonl(outputs["textbook_approved"], textbook_approved)
    write_csv(outputs["textbook_review"], textbook_review)
    write_csv(outputs["textbook_rejected"], textbook_rejected)
    write_csv(outputs["review_sample"], sample_rows(lecture_rescored + textbook_rescored, args.review_sample_size, args.review_sample_seed))

    source_coverage = Counter()
    for profile in profile_rows:
        for source, count in profile.get("source_counts", {}).items():
            if count:
                source_coverage[source] += 1
    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workstream": "Curriculum Gap Fill v0.3 - full hybrid ABPath tagging",
        "method": METHOD,
        "vector_status": vec_status,
        "vector_sources_detected": vec_sources,
        "inputs": {
            "abpath_tags": str(args.abpath_tags),
            "curriculum_records_v0_2": str(args.curriculum_records),
            "lecture_chunks": str(args.lecture_chunks),
            "textbook_chunks": str(args.textbook_chunks),
        },
        "outputs": {key: str(value) for key, value in outputs.items()} | {"seed_profiles": str(profiles_path)},
        "candidate_generation_limits": {
            "max_candidates_per_tag_per_source": args.max_candidates_per_tag,
            "max_fts_hits_per_query": args.max_fts_hits_per_query,
        },
        "counts": {
            "abpath_tags": len(tags),
            "seed_profiles": len(profile_rows),
            "tags_with_seed_profiles": sum(1 for row in profile_rows if int(row.get("seed_record_count") or 0) > 0),
            "tags_lacking_seed_profiles": sum(1 for row in profile_rows if int(row.get("seed_record_count") or 0) == 0),
            "source_tag_coverage": dict(sorted(source_coverage.items())),
            "lectures": lecture_stats,
            "textbooks": textbook_stats,
            "forbidden_approved_hits": sum(1 for row in lecture_approved + textbook_approved if has_forbidden(row)),
        },
        "known_limitations": [
            "Hybrid scoring is lexical and source-weighted; no new embeddings were generated.",
            "Local vector docstore samples were detected only as hints; no complete local similarity index was used.",
            "FTS candidate retrieval is capped per tag and query to keep the staged sidecars reviewable.",
            "PathOut and WHO are seed/context sources, not new target sidecar rows.",
        ],
    }
    outputs["audit"].write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_readme(outputs["readme"], audit)
    print(json.dumps(audit["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
