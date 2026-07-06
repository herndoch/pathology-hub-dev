#!/usr/bin/env python3
"""Generate lecture-first ABPath gap-fill candidates for Curriculum Gap Fill v0.3.

This script creates local sidecar files only. It treats ABPath/source tags as the
gold ontology and uses lecture STRICT_CYTO_v9 chunks as searchable content.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "curriculum_gapfill_v0_3"
METHOD = "sqlite_fts_abpath_gapfill_v0_3"
SOURCE_FAMILY = "lectures"

DEFAULT_ABPATH = Path("data/curriculum_map_v0_2/abpath_source_tags.jsonl")
DEFAULT_LECTURES = Path(
    "data/curriculum_map_v0_2/lecture_timecoded_tagged_chunks_ROUTED_ONLY_STRICT_CYTO_v9.jsonl"
)
DEFAULT_OUTPUT_DIR = Path("outputs/curriculum_gapfill_v0_3")
DEFAULT_PRIORITY_ROOTS = (
    "CYP",
    "HN",
    "BR",
    "GYN",
    "GU",
    "GI",
    "LUNG",
    "HEM",
    "DERM",
    "NEURO",
    "RENAL",
    "LIVER",
    "BST",
)

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

STOPWORDS = {
    "and",
    "or",
    "of",
    "the",
    "a",
    "an",
    "in",
    "with",
    "without",
    "for",
    "to",
    "by",
    "on",
    "from",
    "type",
    "types",
    "tumor",
    "tumour",
    "neoplasm",
    "neoplasms",
    "disease",
    "disorder",
    "lesion",
    "lesions",
}

ROOT_LABELS = {
    "BST": ("bone", "soft tissue", "sarcoma"),
    "BR": ("breast",),
    "CG": ("cytogenetics", "molecular"),
    "CP": ("clinical pathology",),
    "CYP": ("cytopathology", "cytology", "fna", "fine needle"),
    "DERM": ("skin", "dermatology", "cutaneous"),
    "GI": ("gastrointestinal", "colon", "stomach", "esophagus", "intestine"),
    "GU": ("genitourinary", "kidney", "bladder", "prostate", "testis"),
    "GYN": ("gynecologic", "gynecology", "ovary", "uterus", "cervix"),
    "HEM": ("hematopathology", "lymphoma", "leukemia", "marrow"),
    "HN": ("head and neck", "thyroid", "salivary", "neck"),
    "LIVER": ("liver", "hepatic", "biliary"),
    "LUNG": ("lung", "pulmonary", "thoracic"),
    "NEURO": ("brain", "central nervous", "neuropathology"),
    "PEDS": ("pediatric", "paediatric", "childhood"),
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


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def tag_leaf(tag: str) -> str:
    return tag.split("::")[-1] if tag else ""


def root_of(tag: str) -> str:
    return tag.split("::", 1)[0] if "::" in tag else tag


def phrase_from_tag_part(value: str) -> str:
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    return clean_space(value).lower()


def terms_for_phrase(phrase: str) -> list[str]:
    terms = re.findall(r"[a-z0-9]+", phrase.lower())
    return [t for t in terms if len(t) >= 3 and t not in STOPWORDS]


def has_forbidden(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


def fts_quote(phrase: str) -> str:
    return '"' + phrase.replace('"', '""') + '"'


def fts_token(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "", token)


def make_queries(tag: str, title: str) -> list[tuple[str, str, list[str]]]:
    leaf_phrase = phrase_from_tag_part(title or tag_leaf(tag))
    path_phrase = phrase_from_tag_part(" ".join(tag.split("::")[1:]))
    leaf_terms = terms_for_phrase(leaf_phrase)
    path_terms = terms_for_phrase(path_phrase)

    queries: list[tuple[str, str, list[str]]] = []
    if leaf_phrase and len(leaf_phrase) >= 4:
        queries.append(("leaf_exact", fts_quote(leaf_phrase), leaf_terms))
    if len(leaf_terms) >= 2:
        queries.append(("leaf_terms", " AND ".join(fts_token(t) for t in leaf_terms), leaf_terms))
    strong_path_terms = [t for t in path_terms if t not in leaf_terms][:4]
    if leaf_terms and strong_path_terms:
        cluster = list(dict.fromkeys(leaf_terms[:3] + strong_path_terms[:2]))
        queries.append(("path_cluster", " AND ".join(fts_token(t) for t in cluster), cluster))
    return [(name, query, terms) for name, query, terms in queries if query and terms]


def root_context_present(root: str, original_tag: str, searchable_text: str) -> bool:
    if original_tag and original_tag.startswith(root + "::"):
        return True
    text = searchable_text.lower()
    return any(label in text for label in ROOT_LABELS.get(root, (root.lower(),)))


def exact_phrase_present(phrase: str, text: str) -> bool:
    if not phrase:
        return False
    return re.search(r"\b" + re.escape(phrase.lower()) + r"\b", text.lower()) is not None


def matched_terms(terms: list[str], text: str) -> list[str]:
    lower = text.lower()
    return [term for term in terms if re.search(r"\b" + re.escape(term) + r"\b", lower)]


def term_window_bonus(terms: list[str], text: str, window: int = 80) -> bool:
    positions: list[tuple[int, str]] = []
    lower = text.lower()
    for term in terms:
        match = re.search(r"\b" + re.escape(term) + r"\b", lower)
        if match:
            positions.append((match.start(), term))
    if len(positions) < 2:
        return False
    positions.sort()
    for idx, (start, _) in enumerate(positions):
        seen = {positions[idx][1]}
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


def build_excerpt(text: str, terms: list[str], phrase: str, size: int = 420) -> str:
    lower = text.lower()
    starts = []
    if phrase:
        found = lower.find(phrase.lower())
        if found >= 0:
            starts.append(found)
    for term in terms:
        found = lower.find(term.lower())
        if found >= 0:
            starts.append(found)
    center = min(starts) if starts else 0
    start = max(0, center - size // 3)
    end = min(len(text), start + size)
    return clean_space(text[start:end])


def load_abpath_tags(path: Path, limit: int, priority_roots: tuple[str, ...]) -> list[dict[str, str]]:
    rows_by_root: dict[str, list[dict[str, str]]] = defaultdict(list)
    fallback: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in read_jsonl(path):
        tag = str(row.get("primary_tag") or "").strip()
        if not tag or tag in seen or has_forbidden(tag):
            continue
        seen.add(tag)
        item = {
            "primary_tag": tag,
            "title": str(row.get("title") or tag_leaf(tag)),
            "root": root_of(tag),
        }
        rows_by_root[item["root"]].append(item)
        fallback.append(item)
    tags: list[dict[str, str]] = []
    selected: set[str] = set()
    for root in priority_roots:
        for item in rows_by_root.get(root, []):
            if item["primary_tag"] in selected:
                continue
            tags.append(item)
            selected.add(item["primary_tag"])
            if len(tags) >= limit:
                return tags
    for item in fallback:
        if item["primary_tag"] in selected:
            continue
        tags.append(item)
        selected.add(item["primary_tag"])
        if len(tags) >= limit:
            break
    return tags


def create_fts(lecture_path: Path) -> tuple[sqlite3.Connection, dict[str, Any]]:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, video_id TEXT, source_id TEXT, "
        "title TEXT, text TEXT, original_tag TEXT)"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE chunk_fts USING fts5(chunk_id UNINDEXED, title, text)"
    )

    input_rows = 0
    indexed_rows = 0
    skipped_forbidden = 0
    existing_tag_counts: Counter[str] = Counter()

    for row in read_jsonl(lecture_path):
        input_rows += 1
        chunk_id = str(row.get("chunk_id") or "").strip()
        if not chunk_id:
            continue
        original_tag = str(
            row.get("primary_tag_governed")
            or row.get("primary_tag")
            or row.get("primary_tag_original_pre_governance_v10_4")
            or ""
        ).strip()
        if has_forbidden(original_tag):
            skipped_forbidden += 1
            continue
        title = str(row.get("title") or "")
        transcript = str(row.get("transcript_text") or "")
        summary = str(row.get("summary") or "")
        video_id = str(row.get("video_id") or "")
        source_id = video_id or str(row.get("raw_source_gcs_uri") or "")
        text = clean_space(" ".join(part for part in (title, summary, transcript) if part))
        if not text:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
            (chunk_id, video_id, source_id, title, text, original_tag),
        )
        conn.execute("INSERT INTO chunk_fts(chunk_id, title, text) VALUES (?, ?, ?)", (chunk_id, title, text))
        indexed_rows += 1
        if original_tag:
            existing_tag_counts[original_tag] += 1

    conn.commit()
    return conn, {
        "input_rows": input_rows,
        "indexed_rows": indexed_rows,
        "skipped_forbidden_original_tag_rows": skipped_forbidden,
        "distinct_existing_tags": len(existing_tag_counts),
    }


def score_match(
    tag: str,
    root: str,
    query_name: str,
    query_terms: list[str],
    title: str,
    text: str,
    original_tag: str,
) -> tuple[float, str, list[str], str]:
    leaf_phrase = phrase_from_tag_part(tag_leaf(tag))
    all_text = clean_space(f"{title} {text}")
    found_terms = matched_terms(query_terms, all_text)
    exact = exact_phrase_present(leaf_phrase, all_text)
    window = term_window_bonus(found_terms, all_text)
    root_context = root_context_present(root, original_tag, all_text)

    score = 0.0
    reasons: list[str] = []
    if exact:
        score += 0.56
        reasons.append("exact ABPath leaf phrase present")
    if len(found_terms) >= 2 and window:
        score += 0.28
        reasons.append("strong matched-term cluster")
    elif len(found_terms) >= 2:
        score += 0.18
        reasons.append("matched-term cluster")
    elif len(found_terms) == 1 and query_name == "leaf_exact":
        score += 0.12
        reasons.append("single term in exact phrase query")
    if root_context:
        score += 0.16
        reasons.append("root context supported")
    if title and exact_phrase_present(leaf_phrase, title):
        score += 0.12
        reasons.append("title match")
    if original_tag == "_UNMAPPED_" or not original_tag:
        score += 0.04
        reasons.append("fills unmapped lecture chunk")
    if original_tag == tag:
        score = 0.0
        reasons.append("already has exact ABPath tag")

    score = min(score, 1.0)
    confidence = confidence_for(score)
    reason = "; ".join(reasons) if reasons else "weak lexical match"
    return score, confidence, found_terms, reason


def generate_candidates(
    conn: sqlite3.Connection,
    abpath_tags: list[dict[str, str]],
    max_candidates_per_tag: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    low_rejects = 0
    raw_hits = 0
    per_tag_counts: Counter[str] = Counter()

    for tag_row in abpath_tags:
        tag = tag_row["primary_tag"]
        root = tag_row["root"]
        if has_forbidden(tag):
            continue
        best_by_chunk: dict[str, dict[str, Any]] = {}
        queries = make_queries(tag, tag_row["title"])
        for query_name, fts_query, query_terms in queries:
            try:
                rows = conn.execute(
                    "SELECT c.chunk_id, c.video_id, c.source_id, c.title, c.text, c.original_tag "
                    "FROM chunk_fts f JOIN chunks c ON c.chunk_id = f.chunk_id "
                    "WHERE chunk_fts MATCH ? LIMIT ?",
                    (fts_query, max_candidates_per_tag * 6),
                ).fetchall()
            except sqlite3.OperationalError:
                continue
            for chunk_id, video_id, source_id, title, text, original_tag in rows:
                raw_hits += 1
                if original_tag == tag or has_forbidden(original_tag):
                    continue
                score, confidence, found_terms, reason = score_match(
                    tag, root, query_name, query_terms, title or "", text or "", original_tag or ""
                )
                if confidence == "low":
                    low_rejects += 1
                    continue
                candidate = {
                    "schema_version": SCHEMA_VERSION,
                    "source_family": SOURCE_FAMILY,
                    "chunk_id": chunk_id,
                    "source_id": source_id or video_id,
                    "video_id": video_id,
                    "abpath_tag": tag,
                    "root": root,
                    "matched_query": query_name,
                    "matched_terms": found_terms,
                    "score": round(score, 3),
                    "confidence": confidence,
                    "method": METHOD,
                    "review_status": "candidate",
                    "text_excerpt": build_excerpt(text or title or "", found_terms, phrase_from_tag_part(tag_leaf(tag))),
                    "original_existing_tag": original_tag or None,
                    "reason": reason,
                }
                if has_forbidden(candidate):
                    continue
                prev = best_by_chunk.get(chunk_id)
                if prev is None or candidate["score"] > prev["score"]:
                    best_by_chunk[chunk_id] = candidate

        ranked = sorted(best_by_chunk.values(), key=lambda x: (-x["score"], x["chunk_id"]))
        for candidate in ranked[:max_candidates_per_tag]:
            candidates.append(candidate)
            per_tag_counts[tag] += 1

    candidates.sort(key=lambda x: (x["root"], x["abpath_tag"], -x["score"], x["chunk_id"]))
    stats = {
        "raw_fts_hits": raw_hits,
        "low_confidence_hidden_count": low_rejects,
        "tags_with_candidates": len(per_tag_counts),
    }
    return candidates, stats


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_summary_csv(path: Path, candidates: list[dict[str, Any]]) -> None:
    fields = [
        "root",
        "abpath_tag",
        "candidate_count",
        "high_count",
        "medium_count",
        "max_score",
        "example_chunk_id",
        "example_source_id",
        "example_terms",
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["abpath_tag"]].append(candidate)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for tag, rows in sorted(grouped.items()):
            rows = sorted(rows, key=lambda x: -x["score"])
            conf = Counter(row["confidence"] for row in rows)
            writer.writerow(
                {
                    "root": rows[0]["root"],
                    "abpath_tag": tag,
                    "candidate_count": len(rows),
                    "high_count": conf.get("high", 0),
                    "medium_count": conf.get("medium", 0),
                    "max_score": rows[0]["score"],
                    "example_chunk_id": rows[0]["chunk_id"],
                    "example_source_id": rows[0]["source_id"],
                    "example_terms": "|".join(rows[0]["matched_terms"]),
                }
            )


def write_readme(path: Path, args: argparse.Namespace, audit: dict[str, Any]) -> None:
    text = f"""# Lecture ABPath Gap Fill Candidates v0.3

This directory contains local sidecar outputs for Curriculum Gap Fill v0.3 Phase 1.

Scope:
- source family: lectures only
- ontology source: ABPath/source tags only
- output status: reviewable candidates only
- no approved sidecar is produced
- no source records, lecture chunks, vector docstores, indexes, Curriculum Map v0.2 outputs, GCS objects, deployments, or GPT Builder settings are modified

Generated files:
- `lecture_abpath_gapfill_candidates_v0_3.jsonl`
- `lecture_abpath_gapfill_candidate_summary.csv`
- `lecture_gapfill_audit_v0_3.json`
- `README_LECTURE_GAPFILL_V0_3.md`

Run bounds:
- max ABPath tags: {args.max_abpath_tags}
- max candidates per tag: {args.max_candidates_per_tag}

Counts:
- candidates written: {audit["counts"]["candidates_written"]}
- high confidence: {audit["counts"]["confidence_counts"].get("high", 0)}
- medium confidence: {audit["counts"]["confidence_counts"].get("medium", 0)}
- low confidence hidden: {audit["counts"]["low_confidence_hidden_count"]}

Review note:
ABPath tags are used as ontology labels, not as content evidence. Candidate rows must be reviewed before any approved sidecar or live map integration is created.
"""
    path.write_text(text, encoding="utf-8")


def build_audit(
    args: argparse.Namespace,
    input_stats: dict[str, Any],
    candidate_stats: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    conf_counts = Counter(candidate["confidence"] for candidate in candidates)
    root_counts = Counter(candidate["root"] for candidate in candidates)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workstream": "Curriculum Gap Fill v0.3",
        "phase": "phase_1_lecture_candidate_generation",
        "method": METHOD,
        "inputs": {
            "abpath_source_tags": str(args.abpath_tags),
            "lecture_chunks": str(args.lecture_chunks),
        },
        "outputs": {
            "candidates_jsonl": str(args.output_dir / "lecture_abpath_gapfill_candidates_v0_3.jsonl"),
            "summary_csv": str(args.output_dir / "lecture_abpath_gapfill_candidate_summary.csv"),
            "audit_json": str(args.output_dir / "lecture_gapfill_audit_v0_3.json"),
            "readme": str(args.output_dir / "README_LECTURE_GAPFILL_V0_3.md"),
        },
        "bounds": {
            "max_abpath_tags": args.max_abpath_tags,
            "max_candidates_per_tag": args.max_candidates_per_tag,
            "priority_roots": [root.strip() for root in args.priority_roots.split(",") if root.strip()],
            "source_family": SOURCE_FAMILY,
        },
        "counts": {
            **input_stats,
            "abpath_tags_loaded": args._abpath_tags_loaded,
            "raw_fts_hits": candidate_stats["raw_fts_hits"],
            "low_confidence_hidden_count": candidate_stats["low_confidence_hidden_count"],
            "tags_with_candidates": candidate_stats["tags_with_candidates"],
            "candidates_written": len(candidates),
            "confidence_counts": dict(sorted(conf_counts.items())),
            "root_counts": dict(sorted(root_counts.items())),
        },
        "known_limitations": [
            "Lexical FTS candidates are not content proof and require manual review.",
            "The bounded run only searches the configured maximum ABPath tags.",
            "Low-confidence hits are counted but not written to the candidate sidecar.",
            "Root context uses existing lecture tag lineage and simple text cues.",
            "No approved sidecar, textbook gap-fill, GCS upload, deployment, or GPT Builder update is performed.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abpath-tags", type=Path, default=DEFAULT_ABPATH)
    parser.add_argument("--lecture-chunks", type=Path, default=DEFAULT_LECTURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-abpath-tags", type=int, default=500)
    parser.add_argument("--max-candidates-per-tag", type=int, default=20)
    parser.add_argument(
        "--priority-roots",
        default=",".join(DEFAULT_PRIORITY_ROOTS),
        help="Comma-separated ABPath roots to prioritize inside the bounded tag cap.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_abpath_tags <= 0:
        raise SystemExit("--max-abpath-tags must be positive")
    if args.max_candidates_per_tag <= 0:
        raise SystemExit("--max-candidates-per-tag must be positive")
    if not args.abpath_tags.exists():
        raise SystemExit(f"Missing ABPath input: {args.abpath_tags}")
    if not args.lecture_chunks.exists():
        raise SystemExit(f"Missing lecture input: {args.lecture_chunks}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    priority_roots = tuple(root.strip() for root in args.priority_roots.split(",") if root.strip())
    abpath_tags = load_abpath_tags(args.abpath_tags, args.max_abpath_tags, priority_roots)
    args._abpath_tags_loaded = len(abpath_tags)
    conn, input_stats = create_fts(args.lecture_chunks)
    candidates, candidate_stats = generate_candidates(conn, abpath_tags, args.max_candidates_per_tag)

    candidates_path = args.output_dir / "lecture_abpath_gapfill_candidates_v0_3.jsonl"
    summary_path = args.output_dir / "lecture_abpath_gapfill_candidate_summary.csv"
    audit_path = args.output_dir / "lecture_gapfill_audit_v0_3.json"
    readme_path = args.output_dir / "README_LECTURE_GAPFILL_V0_3.md"

    audit = build_audit(args, input_stats, candidate_stats, candidates)
    write_jsonl(candidates_path, candidates)
    write_summary_csv(summary_path, candidates)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_readme(readme_path, args, audit)

    print(json.dumps(audit["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
