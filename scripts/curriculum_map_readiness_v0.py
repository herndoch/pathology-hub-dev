#!/usr/bin/env python3
"""Local Curriculum Map Readiness Audit v0.

This script is local-only. It does not call gcloud, upload to GCS, deploy
services, run v11 promotion, or update any API/GPT schema.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import json
import os
import re
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


SCHEMA_VERSION = "curriculum_map_readiness_audit.v0"
DEFAULT_INPUT_DIR = "data/curriculum_map_readiness_v0"
DEFAULT_OUTPUT_DIR = "audits/curriculum_map_readiness_v0"

TAG_FIELDS = [
    "primary_tag",
    "primary_tags",
    "curriculum_tags",
    "curriculum_unit",
    "candidate_tags",
    "ai_tags",
    "tags",
]

STATUS_FIELDS = [
    "tag_status",
    "primary_tag_status",
    "tag_basis",
    "primary_tag_basis",
]

HIDDEN_MARKERS = {
    "__unmapped__",
    "unmapped",
    "none",
    "null",
    "",
    "rejected",
    "rejected_generated",
    "excluded_junk",
    "hidden",
    "unmapped_no_context",
}

FORBIDDEN_PATTERNS = [
    "::Lectures::",
    "::Textbooks::",
    "Slide_",
    "Page_",
    "Digital_Pathology_Slide",
    "Pathology_Slide",
    "::Error",
]

HIGH_YIELD_ROOTS = [
    "GYN::Ovary",
    "GU::Prostate",
    "Breast",
    "GI",
    "Lung",
    "Derm",
    "Bone",
    "Soft_Tissue",
    "Cyto",
]

SOURCE_HINTS = {
    "textbook": "textbooks",
    "textbooks": "textbooks",
    "pathout": "pathout",
    "pathology_outlines": "pathout",
    "lecture": "lectures",
    "lectures": "lectures",
    "strict_cyto": "lectures",
    "who": "who",
    "abpath": "abpath",
    "api_proof": "proof",
    "proof": "proof",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def hidden_marker(value: Any) -> bool:
    return normalize_text(value).lower() in HIDDEN_MARKERS


def flatten_values(value: Any) -> List[str]:
    out: List[str] = []
    if value is None:
        return out
    if isinstance(value, str):
        parts = [p.strip() for p in re.split(r"[|;,]", value) if p.strip()]
        return parts or ([value.strip()] if value.strip() else [])
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        for item in value:
            out.extend(flatten_values(item))
        return out
    if isinstance(value, dict):
        for key in ("tag", "name", "label", "path", "value", "primary_tag"):
            if key in value:
                out.extend(flatten_values(value.get(key)))
        if not out:
            for item in value.values():
                if isinstance(item, (str, list, dict)):
                    out.extend(flatten_values(item))
        return out
    return [str(value)]


def find_json_files(input_dir: Path) -> List[Path]:
    if not input_dir.exists():
        return []
    return sorted(
        p
        for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".json", ".jsonl"}
    )


def detect_source(path: Path, record: Optional[Dict[str, Any]] = None) -> str:
    haystack = str(path).lower()
    if record:
        for key in ("source", "source_name", "dataset", "collection", "corpus"):
            value = normalize_text(record.get(key)).lower()
            if value:
                haystack += " " + value
    for hint, source in SOURCE_HINTS.items():
        if hint in haystack:
            return source
    return "unknown"


def records_from_json_object(obj: Any) -> Iterator[Dict[str, Any]]:
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(obj, dict):
        for key in ("records", "items", "data", "results", "documents", "chunks", "rows"):
            value = obj.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
                return
        yield obj


def read_records(path: Path) -> Iterator[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    yield {
                        "_parse_error": str(exc),
                        "_path": str(path),
                        "_line_no": line_no,
                    }
                    continue
                if isinstance(obj, dict):
                    obj.setdefault("_path", str(path))
                    obj.setdefault("_line_no", line_no)
                    yield obj
        return

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        try:
            obj = json.load(handle)
        except json.JSONDecodeError as exc:
            yield {"_parse_error": str(exc), "_path": str(path)}
            return
    for index, record in enumerate(records_from_json_object(obj), 1):
        record.setdefault("_path", str(path))
        record.setdefault("_record_index", index)
        yield record


def record_id(record: Dict[str, Any], fallback: int) -> str:
    for key in ("id", "record_id", "chunk_id", "doc_id", "page_id", "url", "title"):
        value = normalize_text(record.get(key))
        if value:
            return value[:240]
    path = normalize_text(record.get("_path"))
    line = normalize_text(record.get("_line_no") or record.get("_record_index"))
    return f"{path}:{line or fallback}"


def extract_tags(record: Dict[str, Any]) -> Tuple[List[str], Dict[str, List[str]]]:
    by_field: Dict[str, List[str]] = {}
    tags: List[str] = []
    for field in TAG_FIELDS:
        values = flatten_values(record.get(field))
        values = [v for v in values if normalize_text(v)]
        if values:
            by_field[field] = values
            tags.extend(values)
    deduped = list(dict.fromkeys(tags))
    return deduped, by_field


def extract_statuses(record: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for field in STATUS_FIELDS:
        values.extend(flatten_values(record.get(field)))
    return [v for v in values if normalize_text(v)]


def visible_tags(tags: Sequence[str]) -> List[str]:
    return [tag for tag in tags if not hidden_marker(tag)]


def record_is_hidden(tags: Sequence[str], statuses: Sequence[str]) -> bool:
    if not tags:
        return True
    if all(hidden_marker(tag) for tag in tags):
        return True
    return any(hidden_marker(status) for status in statuses)


def forbidden_hits(tags: Sequence[str]) -> List[Tuple[str, str]]:
    hits: List[Tuple[str, str]] = []
    for tag in tags:
        if hidden_marker(tag):
            continue
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in tag:
                hits.append((tag, pattern))
    return hits


def title_for_record(record: Dict[str, Any]) -> str:
    for key in ("title", "name", "heading", "diagnosis", "entity", "label", "text"):
        value = normalize_text(record.get(key))
        if value:
            return value[:500]
    return ""


def collect_abpath_terms(records: Sequence[Dict[str, Any]]) -> List[str]:
    terms: List[str] = []
    for rec in records:
        if rec["source"] == "abpath":
            terms.extend(rec["visible_tags"])
            title = normalize_text(rec["title"])
            if title:
                terms.append(title)
    return sorted(set(t for t in terms if t and not hidden_marker(t)))


def best_abpath_match(term: str, abpath_terms: Sequence[str]) -> Tuple[str, int, str]:
    if not term or not abpath_terms:
        return "", 0, "no_abpath_terms"
    best_term = ""
    best_score = 0
    for candidate in abpath_terms:
        score = int(round(difflib.SequenceMatcher(None, term.lower(), candidate.lower()).ratio() * 100))
        if score > best_score:
            best_score = score
            best_term = candidate
    if best_score >= 90:
        bucket = "accepted"
    elif best_score >= 80:
        bucket = "review"
    else:
        bucket = "rejected"
    return best_term, best_score, bucket


def get_numeric(record: Dict[str, Any], keys: Sequence[str]) -> Optional[float]:
    for key in keys:
        value = record.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    return None


def inheritance_info(record: Dict[str, Any]) -> Tuple[bool, Optional[float], str]:
    lower_keys = {k.lower(): k for k in record.keys()}
    inherited = any("inherit" in k for k in lower_keys)
    basis = " ".join(extract_statuses(record)).lower()
    if "inherit" in basis:
        inherited = True
    distance = get_numeric(
        record,
        [
            "inheritance_distance",
            "inherited_distance",
            "inheritance_row_gap",
            "inheritance_page_gap",
            "inheritance_time_gap_sec",
            "inheritance_seconds",
            "row_gap",
            "page_gap",
            "time_gap_sec",
        ],
    )
    field_names = ",".join(k for k in record.keys() if "inherit" in k.lower() or k.lower() in {"row_gap", "page_gap", "time_gap_sec"})
    return inherited, distance, field_names


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def inventory_input_files(input_dir: Path) -> List[Dict[str, Any]]:
    rows = []
    for path in find_json_files(input_dir):
        rows.append(
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "suffix": path.suffix.lower(),
                "source_hint": detect_source(path),
            }
        )
    return rows


def write_sqlite(path: Path, records: Sequence[Dict[str, Any]], tag_counts: Counter, high_yield_rows: Sequence[Dict[str, Any]]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE records (record_id TEXT, source TEXT, title TEXT, hidden INTEGER, path TEXT)"
        )
        conn.execute(
            "CREATE TABLE tags (record_id TEXT, source TEXT, tag TEXT, visible INTEGER)"
        )
        conn.execute(
            "CREATE TABLE tag_counts (source TEXT, tag TEXT, count INTEGER)"
        )
        conn.execute(
            "CREATE TABLE high_yield_examples (root TEXT, source TEXT, tag TEXT, record_id TEXT, title TEXT)"
        )
        for rec in records:
            conn.execute(
                "INSERT INTO records VALUES (?, ?, ?, ?, ?)",
                (rec["record_id"], rec["source"], rec["title"], int(rec["hidden"]), rec["path"]),
            )
            for tag in rec["all_tags"]:
                conn.execute(
                    "INSERT INTO tags VALUES (?, ?, ?, ?)",
                    (rec["record_id"], rec["source"], tag, int(not hidden_marker(tag))),
                )
        for (source, tag), count in sorted(tag_counts.items()):
            conn.execute("INSERT INTO tag_counts VALUES (?, ?, ?)", (source, tag, count))
        for row in high_yield_rows:
            conn.execute(
                "INSERT INTO high_yield_examples VALUES (?, ?, ?, ?, ?)",
                (row["root"], row["source"], row["tag"], row["record_id"], row["title"]),
            )
        conn.commit()
    finally:
        conn.close()


def parse_all_records(input_dir: Path, sample_size: Optional[int]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    parsed: List[Dict[str, Any]] = []
    parse_errors: List[Dict[str, Any]] = []
    count = 0
    for path in find_json_files(input_dir):
        for raw in read_records(path):
            if "_parse_error" in raw:
                parse_errors.append(raw)
                continue
            count += 1
            if sample_size is not None and len(parsed) >= sample_size:
                return parsed, parse_errors
            source = detect_source(path, raw)
            tags, tags_by_field = extract_tags(raw)
            statuses = extract_statuses(raw)
            vis_tags = visible_tags(tags)
            hidden = record_is_hidden(tags, statuses)
            inherited, distance, inheritance_fields = inheritance_info(raw)
            parsed.append(
                {
                    "record_id": record_id(raw, count),
                    "source": source,
                    "title": title_for_record(raw),
                    "path": str(path),
                    "all_tags": tags,
                    "visible_tags": vis_tags,
                    "tags_by_field": tags_by_field,
                    "statuses": statuses,
                    "hidden": hidden,
                    "forbidden_hits": forbidden_hits(vis_tags),
                    "inherited": inherited,
                    "inheritance_distance": distance,
                    "inheritance_fields": inheritance_fields,
                    "raw": raw,
                }
            )
    return parsed, parse_errors


def build_outputs(input_dir: Path, output_dir: Path, sample_size: Optional[int], probe_only: bool) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    file_inventory = inventory_input_files(input_dir)

    audit: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now_utc(),
        "mode": "probe_only" if probe_only else "audit",
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "sample_size": sample_size,
        "gcs_touched": False,
        "gcs_commands_run": [],
        "files_seen": file_inventory,
        "known_limitations": [
            "Local-only audit script; no gcloud calls, GCS downloads, GCS uploads, deployments, v11 promotion, or GPT Builder schema updates.",
            "Source and tag extraction are defensive heuristics based on local JSON/JSONL fields and filenames.",
            "Missing fields are treated as absent rather than fatal.",
            "WHO to ABPath fuzzy matching requires local ABPath terms; if absent, results are limitation rows.",
        ],
    }

    if probe_only:
        audit["record_count"] = 0
        audit["probe_only_note"] = "Input files were inventoried only; records were not parsed."
        (output_dir / "audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
        write_readme(output_dir, audit, [], [], probe_only=True)
        return audit

    records, parse_errors = parse_all_records(input_dir, sample_size)
    source_counts = Counter(rec["source"] for rec in records)
    visible_tag_counts = Counter((rec["source"], tag) for rec in records for tag in rec["visible_tags"])
    hidden_counts = Counter(rec["source"] for rec in records if rec["hidden"])

    forbidden_rows = []
    for rec in records:
        for tag, pattern in rec["forbidden_hits"]:
            forbidden_rows.append(
                {
                    "source": rec["source"],
                    "record_id": rec["record_id"],
                    "tag": tag,
                    "pattern": pattern,
                    "title": rec["title"],
                    "path": rec["path"],
                }
            )

    inheritance_records = [rec for rec in records if rec["inherited"] or rec["inheritance_distance"] is not None]
    distances = [rec["inheritance_distance"] for rec in inheritance_records if rec["inheritance_distance"] is not None]
    inheritance_summary_rows: List[Dict[str, Any]] = []
    if inheritance_records:
        by_source: Dict[str, List[float]] = defaultdict(list)
        source_inherited_counts = Counter(rec["source"] for rec in inheritance_records)
        for rec in inheritance_records:
            if rec["inheritance_distance"] is not None:
                by_source[rec["source"]].append(float(rec["inheritance_distance"]))
        for source in sorted(set(source_inherited_counts) | set(by_source)):
            values = sorted(by_source.get(source, []))
            inheritance_summary_rows.append(
                {
                    "source": source,
                    "inherited_record_count": source_inherited_counts[source],
                    "distance_count": len(values),
                    "min_distance": values[0] if values else "",
                    "max_distance": values[-1] if values else "",
                    "avg_distance": round(sum(values) / len(values), 3) if values else "",
                }
            )

    inheritance_example_rows = [
        {
            "source": rec["source"],
            "record_id": rec["record_id"],
            "distance": rec["inheritance_distance"] if rec["inheritance_distance"] is not None else "",
            "fields": rec["inheritance_fields"],
            "visible_tags": "|".join(rec["visible_tags"]),
            "title": rec["title"],
            "path": rec["path"],
        }
        for rec in inheritance_records[:200]
    ]

    abpath_terms = collect_abpath_terms(records)
    who_rows = []
    if not abpath_terms:
        who_rows.append(
            {
                "who_term": "",
                "best_abpath_match": "",
                "score": "",
                "bucket": "limitation",
                "source": "who",
                "note": "No local ABPath source tags found; fuzzy audit could not compare WHO terms to ABPath.",
            }
        )
    else:
        seen_who_terms = sorted(
            set(tag for rec in records if rec["source"] == "who" for tag in rec["visible_tags"])
        )
        for term in seen_who_terms:
            match, score, bucket = best_abpath_match(term, abpath_terms)
            who_rows.append(
                {
                    "who_term": term,
                    "best_abpath_match": match,
                    "score": score,
                    "bucket": bucket,
                    "source": "who",
                    "note": "",
                }
            )

    pathout_tag_counts = Counter(tag for rec in records if rec["source"] == "pathout" for tag in rec["visible_tags"])
    pathout_rows = [
        {
            "tag": tag,
            "count": count,
            "review_reason": "singleton_or_local_review" if count == 1 else "local_tag_review",
        }
        for tag, count in sorted(pathout_tag_counts.items(), key=lambda item: (item[1], item[0]))
    ]

    high_yield_rows = []
    for root in HIGH_YIELD_ROOTS:
        root_l = root.lower()
        matches = []
        for rec in records:
            for tag in rec["visible_tags"]:
                if tag.lower().startswith(root_l) or root_l in tag.lower():
                    matches.append(
                        {
                            "root": root,
                            "source": rec["source"],
                            "tag": tag,
                            "record_id": rec["record_id"],
                            "title": rec["title"],
                            "path": rec["path"],
                        }
                    )
                    break
            if len(matches) >= 25:
                break
        if not matches:
            high_yield_rows.append(
                {
                    "root": root,
                    "source": "",
                    "tag": "",
                    "record_id": "",
                    "title": "",
                    "path": "",
                }
            )
        else:
            high_yield_rows.extend(matches)

    write_csv(output_dir / "source_counts.csv", ["source", "record_count"], [{"source": k, "record_count": v} for k, v in sorted(source_counts.items())])
    write_csv(
        output_dir / "visible_tag_counts_by_source.csv",
        ["source", "tag", "count"],
        [{"source": s, "tag": t, "count": c} for (s, t), c in sorted(visible_tag_counts.items())],
    )
    write_csv(
        output_dir / "hidden_record_counts.csv",
        ["source", "hidden_record_count"],
        [{"source": k, "hidden_record_count": v} for k, v in sorted(hidden_counts.items())],
    )
    write_csv(
        output_dir / "forbidden_visible_tag_examples.csv",
        ["source", "record_id", "tag", "pattern", "title", "path"],
        forbidden_rows,
    )
    if inheritance_summary_rows:
        write_csv(
            output_dir / "inheritance_distance_summary.csv",
            ["source", "inherited_record_count", "distance_count", "min_distance", "max_distance", "avg_distance"],
            inheritance_summary_rows,
        )
    if inheritance_example_rows:
        write_csv(
            output_dir / "inheritance_examples.csv",
            ["source", "record_id", "distance", "fields", "visible_tags", "title", "path"],
            inheritance_example_rows,
        )
    write_csv(
        output_dir / "who_abpath_fuzzy_audit.csv",
        ["who_term", "best_abpath_match", "score", "bucket", "source", "note"],
        who_rows,
    )
    write_csv(output_dir / "pathout_local_tag_review.csv", ["tag", "count", "review_reason"], pathout_rows)
    write_csv(
        output_dir / "high_yield_root_examples.csv",
        ["root", "source", "tag", "record_id", "title", "path"],
        high_yield_rows,
    )
    write_sqlite(output_dir / "curriculum_tag_index_v0.sqlite", records, visible_tag_counts, high_yield_rows)

    audit.update(
        {
            "record_count": len(records),
            "parse_error_count": len(parse_errors),
            "source_counts": dict(sorted(source_counts.items())),
            "hidden_record_counts": dict(sorted(hidden_counts.items())),
            "visible_tag_count_rows": len(visible_tag_counts),
            "forbidden_visible_tag_example_count": len(forbidden_rows),
            "inheritance_fields_seen": bool(inheritance_records),
            "who_abpath_fuzzy_rows": len(who_rows),
            "pathout_local_tag_rows": len(pathout_rows),
            "high_yield_root_example_rows": len(high_yield_rows),
            "abpath_terms_found": len(abpath_terms),
            "parse_errors": parse_errors[:50],
        }
    )
    (output_dir / "audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
    write_readme(output_dir, audit, forbidden_rows, who_rows, probe_only=False)
    return audit


def write_readme(output_dir: Path, audit: Dict[str, Any], forbidden_rows: Sequence[Dict[str, Any]], who_rows: Sequence[Dict[str, Any]], probe_only: bool) -> None:
    lines = [
        "# Curriculum Map Readiness Audit v0 Review",
        "",
        f"Generated: {audit.get('generated_at_utc', '')}",
        f"Mode: {audit.get('mode', '')}",
        "",
        "## Safety",
        "",
        "- Local script only.",
        "- No gcloud commands are executed by this script.",
        "- No GCS upload, GCS mutation, v11 promotion, deployment, or GPT Builder schema update is performed.",
        "",
        "## Inputs",
        "",
        f"- Input directory: `{audit.get('input_dir', '')}`",
        f"- Files seen: {len(audit.get('files_seen', []))}",
        "",
    ]
    if probe_only:
        lines.extend(
            [
                "## Probe-only result",
                "",
                "Input files were inventoried only. Record-level audit outputs were intentionally not generated.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Summary",
                "",
                f"- Records parsed: {audit.get('record_count', 0)}",
                f"- Parse errors: {audit.get('parse_error_count', 0)}",
                f"- Forbidden visible tag examples: {len(forbidden_rows)}",
                f"- ABPath terms found for WHO fuzzy audit: {audit.get('abpath_terms_found', 0)}",
                "",
                "## Review notes",
                "",
                "- `who_abpath_fuzzy_audit.csv` contains a limitation row if no local ABPath source was present.",
                "- `pathout_local_tag_review.csv` is a local review aid; it does not approve or promote tags.",
                "- `high_yield_root_examples.csv` is a browsing sanity check, not proof of live API behavior.",
                "",
            ]
        )
    (output_dir / "README_REVIEW.md").write_text("\n".join(lines), encoding="utf-8")


def run_self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_dir = root / "input"
        output_dir = root / "output"
        input_dir.mkdir()
        sample = [
            {"source": "abpath", "primary_tag": "GYN::Ovary::Serous_Tumor", "title": "Ovary serous tumor"},
            {"source": "who", "tags": ["Ovary serous tumour"], "title": "WHO ovary entity"},
            {"source": "textbooks", "primary_tag": "Page_12::Textbooks::Bad", "title": "Bad generated tag"},
            {"source": "pathout", "primary_tag": "Soft_Tissue::Lipoma", "title": "Lipoma"},
            {"source": "lectures", "primary_tag": "__UNMAPPED__", "tag_status": "unmapped_no_context"},
            {"source": "lectures", "primary_tag": "Cyto::Lung", "tag_basis": "inherited_context", "inheritance_distance": 3},
        ]
        with (input_dir / "synthetic_records.jsonl").open("w", encoding="utf-8") as handle:
            for rec in sample:
                handle.write(json.dumps(rec) + "\n")
        audit = build_outputs(input_dir, output_dir, sample_size=None, probe_only=False)
        required = [
            "audit.json",
            "source_counts.csv",
            "visible_tag_counts_by_source.csv",
            "hidden_record_counts.csv",
            "forbidden_visible_tag_examples.csv",
            "inheritance_distance_summary.csv",
            "inheritance_examples.csv",
            "who_abpath_fuzzy_audit.csv",
            "pathout_local_tag_review.csv",
            "high_yield_root_examples.csv",
            "curriculum_tag_index_v0.sqlite",
            "README_REVIEW.md",
        ]
        missing = [name for name in required if not (output_dir / name).exists()]
        if missing:
            print(f"Self-test failed; missing outputs: {missing}", file=sys.stderr)
            return 1
        if audit.get("forbidden_visible_tag_example_count", 0) < 1:
            print("Self-test failed; expected forbidden tag example.", file=sys.stderr)
            return 1
    print("Self-test passed.")
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Curriculum Map Readiness Audit v0")
    parser.add_argument("--probe-only", action="store_true", help="Inventory local input files only; do not parse records.")
    parser.add_argument("--sample-size", type=int, default=None, help="Maximum number of records to parse in local audit mode.")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help=f"Input directory; default {DEFAULT_INPUT_DIR}")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Output directory; default {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--self-test", action="store_true", help="Run synthetic local self-test only; no gcloud.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return run_self_test()
    if args.sample_size is not None and args.sample_size < 0:
        print("--sample-size must be non-negative", file=sys.stderr)
        return 2
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    audit = build_outputs(input_dir, output_dir, args.sample_size, args.probe_only)
    print(f"Wrote audit outputs to {output_dir}")
    print(f"Mode: {audit['mode']}")
    print(f"Files seen: {len(audit.get('files_seen', []))}")
    if not args.probe_only:
        print(f"Records parsed: {audit.get('record_count', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
