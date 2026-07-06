#!/usr/bin/env python3
"""Create QA samples from high-volume Curriculum Gap Fill v0.3 review rows."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_GAPFILL_DIR = Path("outputs/curriculum_gapfill_v0_3")
DEFAULT_LECTURES = Path("data/curriculum_map_v0_2/lecture_timecoded_tagged_chunks_ROUTED_ONLY_STRICT_CYTO_v9.jsonl")
DEFAULT_TEXTBOOKS = Path("data/curriculum_map_v0_2/textbook_primary_tagged_chunks_v1.jsonl")
DEFAULT_OUTPUT_DIR = Path("06_audits/curriculum_gapfill/v0_3/qa_samples")
PRIORITY_ROOTS = ("Skin", "HN", "BST", "Breast", "GYN", "GU")
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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def has_forbidden(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else str(value)
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


def root_of(tag: str) -> str:
    return tag.split("::", 1)[0] if "::" in tag else tag


def clean_text(value: str, limit: int = 1800) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:limit]


def parse_jsonish(value: str) -> Any:
    if value is None or value == "":
        return []
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def load_source_text(path: Path, source_family: str, chunk_ids: set[str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not chunk_ids:
        return out
    for row in read_jsonl(path):
        chunk_id = str(row.get("chunk_id") or "")
        if chunk_id not in chunk_ids:
            continue
        if source_family == "lectures":
            title = str(row.get("title") or "")
            source_id = str(row.get("video_id") or row.get("raw_source_gcs_uri") or "")
            prior = str(row.get("primary_tag_governed") or row.get("primary_tag") or row.get("primary_tag_original_pre_governance_v10_4") or "")
            text = " ".join(str(row.get(key) or "") for key in ("title", "summary", "transcript_text", "tag_basis"))
            page_or_time = f"{row.get('start_sec', '')}-{row.get('end_sec', '')}".strip("-")
        else:
            title = " | ".join(str(row.get(key) or "") for key in ("source_title", "chapter_title", "section_heading") if row.get(key))
            source_id = str(row.get("source_id") or row.get("source_title") or "")
            prior = str(row.get("primary_tag_governed") or row.get("primary_tag") or row.get("primary_tag_original_pre_governance_v10_4") or "")
            text = " ".join(str(row.get(key) or "") for key in ("source_title", "chapter_title", "section_heading", "text", "primary_tag_basis") if row.get(key))
            page_or_time = str(row.get("page") or "")
        out[chunk_id] = {
            "source_id": source_id,
            "source_title": title,
            "page_or_time": page_or_time,
            "source_primary_tag": prior,
            "source_text": clean_text(text),
            "raw_source_gcs_uri": str(row.get("raw_source_gcs_uri") or ""),
            "normalized_artifact_gcs_uri": str(row.get("normalized_artifact_gcs_uri") or ""),
        }
        if len(out) >= len(chunk_ids):
            break
    return out


def qa_recommendation(row: dict[str, str]) -> tuple[str, str]:
    tag = row.get("abpath_tag", "")
    prior = row.get("original_existing_tag", "")
    proposed_root = row.get("root") or root_of(tag)
    prior_root = root_of(prior) if prior and prior != "_UNMAPPED_" else ""
    score = float(row.get("hybrid_score") or 0)
    who_hits = parse_jsonish(row.get("who_phrase_hits", ""))
    pathout_hits = parse_jsonish(row.get("pathout_phrase_hits", ""))
    textbook_hits = parse_jsonish(row.get("textbook_phrase_hits", ""))
    lecture_hits = parse_jsonish(row.get("lecture_phrase_hits", ""))
    negative_hits = parse_jsonish(row.get("negative_phrase_hits", ""))
    cross_source_count = sum(1 for hits in (who_hits, pathout_hits, textbook_hits) if isinstance(hits, list) and hits)
    conflict = as_bool(row.get("sibling_or_cross_root_conflict", ""))
    generic = as_bool(row.get("generic_only_match", ""))
    entity = as_bool(row.get("entity_phrase_hit", ""))
    root_agree = as_bool(row.get("root_agreement", ""))

    if has_forbidden(tag) or has_forbidden(prior):
        return "reject", "forbidden/generated visible tag field"
    if generic:
        return "reject", "generic-only match"
    if conflict and not (entity and cross_source_count >= 2):
        return "reject", "sibling or cross-root conflict without enough cross-source support"
    if prior_root and proposed_root and prior_root != proposed_root and not root_agree:
        return "reject", "prior/source tag root conflicts with proposed root"
    if score >= 0.98 and entity and cross_source_count >= 2 and not conflict:
        return "auto-approve", "entity phrase plus two or more cross-source supports and no conflict"
    if score >= 0.95 and entity and (cross_source_count >= 1 or lecture_hits) and root_agree and not conflict:
        return "auto-approve", "strong entity/root support with no conflict"
    if negative_hits:
        return "human-review", "negative or ambiguous phrase present"
    return "human-review", "plausible review row needs human adjudication"


def select_rows(rows: list[dict[str, str]], per_root: int, per_tag: int) -> list[dict[str, str]]:
    root_tag_counts = Counter((row.get("root", ""), row.get("abpath_tag", "")) for row in rows)
    grouped: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row.get("root", "")][row.get("abpath_tag", "")].append(row)

    selected: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for root in PRIORITY_ROOTS:
        tag_counts = Counter({tag: len(tag_rows) for tag, tag_rows in grouped.get(root, {}).items()})
        root_selected = 0
        for tag, _ in tag_counts.most_common():
            ranked = sorted(
                grouped[root][tag],
                key=lambda row: (-float(row.get("hybrid_score") or 0), str(row.get("source_family")), str(row.get("chunk_id"))),
            )
            for row in ranked[:per_tag]:
                key = (row.get("source_family", ""), row.get("chunk_id", ""), row.get("abpath_tag", ""))
                if key in seen:
                    continue
                out = dict(row)
                out["_tag_review_row_count"] = str(root_tag_counts[(root, tag)])
                selected.append(out)
                seen.add(key)
                root_selected += 1
                if root_selected >= per_root:
                    break
            if root_selected >= per_root:
                break
    return selected


def build_sample_rows(rows: list[dict[str, str]], lecture_text: dict[str, dict[str, str]], textbook_text: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        lookup = lecture_text if row.get("source_family") == "lectures" else textbook_text
        source = lookup.get(row.get("chunk_id", ""), {})
        recommendation, recommendation_reason = qa_recommendation(row)
        out.append(
            {
                "qa_recommendation": recommendation,
                "qa_recommendation_reason": recommendation_reason,
                "source_family": row.get("source_family", ""),
                "root": row.get("root", ""),
                "proposed_primary_tag": row.get("abpath_tag", ""),
                "tag_review_row_count": row.get("_tag_review_row_count", ""),
                "chunk_id": row.get("chunk_id", ""),
                "source_id": source.get("source_id") or row.get("source_id", ""),
                "source_title": source.get("source_title", ""),
                "page_or_time": source.get("page_or_time", ""),
                "prior_or_source_tag": row.get("original_existing_tag", ""),
                "source_primary_tag": source.get("source_primary_tag", ""),
                "hybrid_decision": row.get("hybrid_decision", ""),
                "hybrid_score": row.get("hybrid_score", ""),
                "confidence": row.get("confidence", ""),
                "decision_reason": row.get("hybrid_reason", ""),
                "entity_phrase_hit": row.get("entity_phrase_hit", ""),
                "root_agreement": row.get("root_agreement", ""),
                "sibling_or_cross_root_conflict": row.get("sibling_or_cross_root_conflict", ""),
                "generic_only_match": row.get("generic_only_match", ""),
                "who_phrase_hits": row.get("who_phrase_hits", ""),
                "pathout_phrase_hits": row.get("pathout_phrase_hits", ""),
                "textbook_phrase_hits": row.get("textbook_phrase_hits", ""),
                "lecture_phrase_hits": row.get("lecture_phrase_hits", ""),
                "negative_phrase_hits": row.get("negative_phrase_hits", ""),
                "text_excerpt": row.get("text_excerpt", ""),
                "source_text": source.get("source_text", ""),
                "raw_source_gcs_uri": source.get("raw_source_gcs_uri", ""),
                "normalized_artifact_gcs_uri": source.get("normalized_artifact_gcs_uri", ""),
            }
        )
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "qa_recommendation",
        "qa_recommendation_reason",
        "source_family",
        "root",
        "proposed_primary_tag",
        "tag_review_row_count",
        "chunk_id",
        "source_id",
        "source_title",
        "page_or_time",
        "prior_or_source_tag",
        "source_primary_tag",
        "hybrid_decision",
        "hybrid_score",
        "confidence",
        "decision_reason",
        "entity_phrase_hit",
        "root_agreement",
        "sibling_or_cross_root_conflict",
        "generic_only_match",
        "who_phrase_hits",
        "pathout_phrase_hits",
        "textbook_phrase_hits",
        "lecture_phrase_hits",
        "negative_phrase_hits",
        "text_excerpt",
        "source_text",
        "raw_source_gcs_uri",
        "normalized_artifact_gcs_uri",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_readme(path: Path, audit: dict[str, Any]) -> None:
    text = f"""# Curriculum Gap Fill v0.3 QA Samples

These samples are generated from `review_hybrid` rows only. They are intended for human QA and do not alter approved, review, rejected, map, vector, API, or GCS artifacts.

Priority roots:
- {", ".join(PRIORITY_ROOTS)}

Outputs:
- `curriculum_gapfill_v0_3_review_qa_sample.csv`
- `curriculum_gapfill_v0_3_review_qa_audit.json`

Rows sampled: {audit["sample_rows"]}

Recommendation labels are QA triage suggestions only:
- `auto-approve`: strong candidate for manual promotion after spot review
- `human-review`: needs human adjudication
- `reject`: likely should remain rejected or be moved from review to rejected
"""
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gapfill-dir", type=Path, default=DEFAULT_GAPFILL_DIR)
    parser.add_argument("--lecture-chunks", type=Path, default=DEFAULT_LECTURES)
    parser.add_argument("--textbook-chunks", type=Path, default=DEFAULT_TEXTBOOKS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--per-root", type=int, default=30)
    parser.add_argument("--per-tag", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    lecture_review_path = args.gapfill_dir / "lecture_abpath_gapfill_review_FULL_v0_3.csv"
    textbook_review_path = args.gapfill_dir / "textbook_abpath_gapfill_review_FULL_v0_3.csv"
    rows = read_csv(lecture_review_path) + read_csv(textbook_review_path)
    target_rows = [row for row in rows if row.get("root") in PRIORITY_ROOTS]
    selected = select_rows(target_rows, args.per_root, args.per_tag)
    lecture_ids = {row.get("chunk_id", "") for row in selected if row.get("source_family") == "lectures"}
    textbook_ids = {row.get("chunk_id", "") for row in selected if row.get("source_family") == "textbooks"}
    lecture_text = load_source_text(args.lecture_chunks, "lectures", lecture_ids)
    textbook_text = load_source_text(args.textbook_chunks, "textbooks", textbook_ids)
    samples = build_sample_rows(selected, lecture_text, textbook_text)

    sample_path = args.output_dir / "curriculum_gapfill_v0_3_review_qa_sample.csv"
    audit_path = args.output_dir / "curriculum_gapfill_v0_3_review_qa_audit.json"
    write_csv(sample_path, samples)
    recommendation_counts = Counter(row["qa_recommendation"] for row in samples)
    root_counts = Counter(row["root"] for row in samples)
    source_counts = Counter(row["source_family"] for row in samples)
    tag_counts = Counter(row["proposed_primary_tag"] for row in samples)
    audit = {
        "schema_version": "curriculum_gapfill_v0_3_review_qa_sample",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "lecture_review": str(lecture_review_path),
            "textbook_review": str(textbook_review_path),
            "lecture_chunks": str(args.lecture_chunks),
            "textbook_chunks": str(args.textbook_chunks),
        },
        "outputs": {
            "sample_csv": str(sample_path),
            "audit_json": str(audit_path),
            "readme": str(args.output_dir / "README.md"),
        },
        "priority_roots": list(PRIORITY_ROOTS),
        "source_review_rows": len(rows),
        "priority_root_review_rows": len(target_rows),
        "sample_rows": len(samples),
        "sample_root_counts": dict(root_counts.most_common()),
        "sample_source_counts": dict(source_counts.most_common()),
        "qa_recommendation_counts": dict(recommendation_counts.most_common()),
        "sample_top_tag_counts": dict(tag_counts.most_common(30)),
        "limitations": [
            "Recommendations are triage labels for human QA, not approval decisions.",
            "Source text is truncated for review ergonomics.",
            "Sampling prioritizes high-volume tags in Skin, HN, BST, Breast, GYN, and GU.",
        ],
    }
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_readme(args.output_dir / "README.md", audit)
    print(json.dumps(audit, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
