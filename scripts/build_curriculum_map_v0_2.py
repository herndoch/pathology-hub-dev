#!/usr/bin/env python3
"""Build local Curriculum Map v0.2.

Local-only builder. It reads downloaded GCS artifacts from a local input
directory, writes governed sidecar outputs, and never uploads or mutates GCS.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import html
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


SCHEMA_VERSION = "curriculum_map_v0_2"
DEFAULT_INPUT_DIR = "data/curriculum_map_v0_2"
DEFAULT_OUTPUT_DIR = "outputs/curriculum_map_v0_2"

FORBIDDEN_PATTERNS = [
    "::Lectures::",
    "::Textbooks::",
    "::Error",
    "Slide_",
    "Page_",
    "Digital_Pathology_Slide",
    "Pathology_Slide",
]

HIDDEN_VALUES = {
    "",
    "none",
    "null",
    "__unmapped__",
    "unmapped",
    "rejected",
    "rejected_generated",
    "excluded_junk",
    "hidden",
    "unmapped_no_context",
}

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

TAG_FIELDS = [
    "primary_tag_governed",
    "approved_tag",
    "primary_tag",
    "primary_tags",
    "curriculum_tags",
    "curriculum_unit",
    "candidate_tags",
    "ai_tags",
    "tags",
]

TEXT_FIELDS = [
    "title",
    "source_title",
    "chapter_title",
    "section_heading",
    "page_title",
    "primary_header",
    "entity_name",
    "text",
    "transcript_text",
    "clean_text",
    "definition",
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def is_hidden_value(value: Any) -> bool:
    return clean_str(value).lower() in HIDDEN_VALUES


def has_forbidden(value: str) -> Tuple[bool, str]:
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in value:
            return True, pattern
    return False, ""


def flatten(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in re.split(r"[|;,]", value) if p.strip()]
        return parts or ([value.strip()] if value.strip() else [])
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            out.extend(flatten(item))
        return out
    if isinstance(value, dict):
        out = []
        for key in ("tag", "name", "label", "path", "value", "primary_tag"):
            if key in value:
                out.extend(flatten(value.get(key)))
        return out
    return [str(value)]


def read_jsonl(path: Path, limit: int = 0) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for idx, line in enumerate(handle, 1):
            if limit and idx > limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                rec["_input_path"] = str(path)
                rec["_line_no"] = idx
                yield rec


def read_json_records(path: Path, limit: int = 0) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        try:
            obj = json.load(handle)
        except json.JSONDecodeError:
            return
    rows: List[Any]
    if isinstance(obj, list):
        rows = obj
    elif isinstance(obj, dict):
        rows = []
        for key in ("records", "items", "data", "results", "rows", "documents"):
            if isinstance(obj.get(key), list):
                rows = obj[key]
                break
        if not rows:
            rows = [obj]
    else:
        rows = []
    for idx, item in enumerate(rows, 1):
        if limit and idx > limit:
            break
        if isinstance(item, dict):
            item["_input_path"] = str(path)
            item["_record_index"] = idx
            yield item


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def root_for_tag(tag: str) -> str:
    parts = tag.split("::")
    if len(parts) >= 2 and parts[0] in {"GYN", "GU"}:
        return "::".join(parts[:2])
    return parts[0] if parts else ""


def title_for_record(rec: Dict[str, Any]) -> str:
    for field in TEXT_FIELDS:
        value = clean_str(rec.get(field))
        if value:
            return value.replace("\n", " ")[:240]
    return ""


def record_id(source: str, rec: Dict[str, Any], fallback: int) -> str:
    for field in (
        "record_id",
        "chunk_id",
        "pathout_id",
        "primary_tag_sidecar_record_id",
        "doc_id",
        "source_id",
        "url",
        "entity_name",
        "primary_tag",
    ):
        value = clean_str(rec.get(field))
        if value:
            return f"{source}:{value[:220]}"
    return f"{source}:{rec.get('_input_path', '')}:{rec.get('_line_no') or rec.get('_record_index') or fallback}"


def load_abpath_tags(input_dir: Path) -> Tuple[set, Dict[str, str]]:
    path = input_dir / "abpath_source_tags.jsonl"
    tags = set()
    lower_to_exact: Dict[str, str] = {}
    if not path.exists():
        return tags, lower_to_exact
    for rec in read_jsonl(path):
        tag = clean_str(rec.get("primary_tag") or rec.get("tag"))
        if tag and not is_hidden_value(tag):
            tags.add(tag)
            lower_to_exact.setdefault(tag.lower(), tag)
    return tags, lower_to_exact


def tag_candidates(rec: Dict[str, Any]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for field in TAG_FIELDS:
        for value in flatten(rec.get(field)):
            value = clean_str(value)
            if value:
                out.append((field, value))
    seen = set()
    deduped = []
    for field, value in out:
        key = (field, value)
        if key not in seen:
            seen.add(key)
            deduped.append((field, value))
    return deduped


def preferred_tag(rec: Dict[str, Any]) -> Tuple[str, str]:
    for field in ("primary_tag_governed", "approved_tag", "primary_tag"):
        value = clean_str(rec.get(field))
        if value:
            return field, value
    for field, value in tag_candidates(rec):
        return field, value
    return "", ""


def first_token(value: str) -> str:
    match = re.search(r"[A-Za-z0-9]+", value)
    return match.group(0).lower() if match else ""


def fuzzy_abpath(term: str, abpath_by_lower: Dict[str, str], abpath_tags: set) -> Tuple[str, int]:
    if not term:
        return "", 0
    exact = abpath_by_lower.get(term.lower())
    if exact:
        return exact, 100
    token = first_token(term)
    if token:
        candidates = [tag for tag in abpath_tags if first_token(tag) == token]
    else:
        candidates = []
    if not candidates:
        candidates = list(abpath_tags)
    best_tag = ""
    best_score = 0
    term_l = term.lower()
    for candidate in candidates:
        score = int(round(difflib.SequenceMatcher(None, term_l, candidate.lower()).ratio() * 100))
        if score > best_score:
            best_tag = candidate
            best_score = score
    return best_tag, best_score


def govern_record(source: str, rec: Dict[str, Any], rid: str, abpath_tags: set, abpath_by_lower: Dict[str, str]) -> Dict[str, Any]:
    field, original_tag = preferred_tag(rec)
    forbidden, forbidden_pattern = has_forbidden(original_tag)
    status = "rejected_or_hidden"
    approved_tag = ""
    visible = False
    rejection_reason = ""
    review_reason = ""
    fuzzy_score: Optional[int] = None
    mapped_from = ""

    if not original_tag or is_hidden_value(original_tag):
        rejection_reason = "blank_or_unmapped"
    elif forbidden:
        rejection_reason = f"forbidden_pattern:{forbidden_pattern}"
    elif source == "abpath":
        if original_tag in abpath_tags:
            status = "approved_abpath"
            approved_tag = original_tag
            visible = True
        else:
            rejection_reason = "abpath_source_tag_not_in_loaded_gold_set"
    elif original_tag in abpath_tags:
        status = "approved_abpath"
        approved_tag = original_tag
        visible = True
    elif source == "who":
        match, score = fuzzy_abpath(original_tag, abpath_by_lower, abpath_tags)
        fuzzy_score = score
        if score >= 90 and match:
            status = "mapped_who_abpath"
            approved_tag = match
            visible = True
            mapped_from = original_tag
        else:
            status = "who_review"
            review_reason = f"who_abpath_fuzzy_score:{score}"
    elif source == "pathout":
        status = "pathout_local_review"
        review_reason = "pathout_non_abpath_local_tag"
    elif source in {"textbooks", "lectures"}:
        rejection_reason = "textbook_lecture_non_abpath_or_generated_tag"
    else:
        rejection_reason = "unknown_source_or_unapproved_tag"

    if approved_tag:
        approved_forbidden, approved_forbidden_pattern = has_forbidden(approved_tag)
        if approved_forbidden:
            visible = False
            status = "rejected_or_hidden"
            rejection_reason = f"approved_tag_forbidden_pattern:{approved_forbidden_pattern}"
            approved_tag = ""

    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": rid,
        "source": source,
        "title": title_for_record(rec),
        "original_tag": original_tag,
        "original_tag_field": field,
        "approved_tag": approved_tag,
        "status": status,
        "visible": visible,
        "root": root_for_tag(approved_tag) if visible else "",
        "mapped_from": mapped_from,
        "fuzzy_score": fuzzy_score,
        "rejection_reason": rejection_reason,
        "review_reason": review_reason,
        "raw_source_gcs_uri": clean_str(rec.get("raw_source_gcs_uri")),
        "normalized_artifact_gcs_uri": clean_str(rec.get("normalized_artifact_gcs_uri")),
        "input_path": clean_str(rec.get("_input_path")),
        "original_record": rec,
    }


def source_files(input_dir: Path) -> Dict[str, List[Path]]:
    return {
        "abpath": [input_dir / "abpath_source_tags.jsonl"],
        "proof": [input_dir / "PATHOLOGY_HUB_GOVERNED_CLEANUP_API_PROOF_v10_5_2.json"],
        "textbooks": [input_dir / "textbook_primary_tagged_chunks_v1.jsonl"],
        "lectures": [
            input_dir / "lecture_primary_tag_map_STRICT_CYTO_v9.jsonl",
            input_dir / "lecture_timecoded_tagged_chunks_ROUTED_ONLY_STRICT_CYTO_v9.jsonl",
        ],
        "pathout": [input_dir / "pathout_tagged_pages_AP_DIAGNOSTIC_v1.jsonl"],
        "who": sorted((input_dir / "who_processed").glob("*.json")),
    }


def iter_source_records(input_dir: Path, sample_size: int) -> Iterator[Tuple[str, Dict[str, Any]]]:
    limit = 0 if sample_size == 0 else sample_size
    for source, paths in source_files(input_dir).items():
        for path in paths:
            if not path.exists():
                continue
            if path.suffix == ".jsonl":
                for rec in read_jsonl(path, limit):
                    yield source, rec
            elif source == "proof":
                continue
            else:
                for rec in read_json_records(path, limit):
                    yield source, rec


def write_sqlite(path: Path, records: Sequence[Dict[str, Any]], node_counts: Counter, source_counts: Counter, tag_counts: Counter, review_rows: Sequence[Dict[str, Any]], rejected_rows: Sequence[Dict[str, Any]], high_yield_rows: Sequence[Dict[str, Any]]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE curriculum_nodes (tag TEXT, root TEXT, record_count INTEGER)")
        conn.execute("CREATE TABLE curriculum_records (record_id TEXT, source TEXT, approved_tag TEXT, status TEXT, visible INTEGER, title TEXT)")
        conn.execute("CREATE TABLE source_counts (source TEXT, record_count INTEGER)")
        conn.execute("CREATE TABLE tag_counts (source TEXT, tag TEXT, count INTEGER)")
        conn.execute("CREATE TABLE review_queue (record_id TEXT, source TEXT, original_tag TEXT, review_reason TEXT, title TEXT)")
        conn.execute("CREATE TABLE rejected_tags (record_id TEXT, source TEXT, original_tag TEXT, rejection_reason TEXT, title TEXT)")
        conn.execute("CREATE TABLE high_yield_examples (root TEXT, tag TEXT, source TEXT, record_id TEXT, title TEXT)")
        for tag, count in sorted(node_counts.items()):
            conn.execute("INSERT INTO curriculum_nodes VALUES (?, ?, ?)", (tag, root_for_tag(tag), count))
        for row in records:
            conn.execute(
                "INSERT INTO curriculum_records VALUES (?, ?, ?, ?, ?, ?)",
                (row["record_id"], row["source"], row["approved_tag"], row["status"], int(row["visible"]), row["title"]),
            )
        for source, count in sorted(source_counts.items()):
            conn.execute("INSERT INTO source_counts VALUES (?, ?)", (source, count))
        for (source, tag), count in sorted(tag_counts.items()):
            conn.execute("INSERT INTO tag_counts VALUES (?, ?, ?)", (source, tag, count))
        for row in review_rows:
            conn.execute("INSERT INTO review_queue VALUES (?, ?, ?, ?, ?)", (row["record_id"], row["source"], row["original_tag"], row["review_reason"], row["title"]))
        for row in rejected_rows:
            conn.execute("INSERT INTO rejected_tags VALUES (?, ?, ?, ?, ?)", (row["record_id"], row["source"], row["original_tag"], row["rejection_reason"], row["title"]))
        for row in high_yield_rows:
            conn.execute("INSERT INTO high_yield_examples VALUES (?, ?, ?, ?, ?)", (row["root"], row["tag"], row["source"], row["record_id"], row["title"]))
        conn.commit()
    finally:
        conn.close()


def write_browser(path: Path, summary: Dict[str, Any], nodes: List[Dict[str, Any]], review_count: int, rejected_count: int, high_yield_rows: List[Dict[str, Any]]) -> None:
    roots = sorted({row["root"] for row in nodes if row["root"]})
    root_counts = Counter(row["root"] for row in nodes for _ in range(int(row["record_count"])))
    node_rows = "\n".join(
        f"<tr data-root='{html.escape(row['root'])}'><td>{html.escape(row['root'])}</td><td>{html.escape(row['tag'])}</td><td>{row['record_count']}</td></tr>"
        for row in nodes[:5000]
    )
    high_rows = "\n".join(
        f"<tr><td>{html.escape(row['root'])}</td><td>{html.escape(row['tag'])}</td><td>{html.escape(row['source'])}</td><td>{html.escape(row['title'])}</td></tr>"
        for row in high_yield_rows
    )
    root_options = "\n".join(f"<option value='{html.escape(root)}'>{html.escape(root)} ({root_counts[root]})</option>" for root in roots)
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Curriculum Map v0.2</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2933; }}
h1, h2 {{ margin-bottom: 8px; }}
.metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; margin: 16px 0; }}
.metric {{ border: 1px solid #d9e2ec; border-radius: 6px; padding: 10px; background: #f8fafc; }}
label {{ margin-right: 8px; }}
input, select {{ padding: 6px; margin: 4px 12px 12px 0; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
th, td {{ border-bottom: 1px solid #e5e7eb; padding: 6px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f7; position: sticky; top: 0; }}
.status {{ font-weight: 700; }}
</style>
</head>
<body>
<h1>Curriculum Map v0.2</h1>
<p class="status">Build status: {html.escape(summary['build_status'])}</p>
<div class="metrics">
<div class="metric">Total records<br><strong>{summary['total_records_processed']}</strong></div>
<div class="metric">Visible curriculum records<br><strong>{summary['records_visible_in_curriculum']}</strong></div>
<div class="metric">Review queue<br><strong>{review_count}</strong></div>
<div class="metric">Rejected/hidden<br><strong>{rejected_count}</strong></div>
<div class="metric">Forbidden visible tags<br><strong>{summary['forbidden_visible_tag_count']}</strong></div>
</div>
<label for="search">Search</label><input id="search" type="search" placeholder="tag text">
<label for="root">Root</label><select id="root"><option value="">All roots</option>{root_options}</select>
<table id="nodes"><thead><tr><th>Root</th><th>Curriculum node</th><th>Records</th></tr></thead><tbody>{node_rows}</tbody></table>
<h2>High-yield Sections</h2>
<table><thead><tr><th>Root</th><th>Tag</th><th>Source</th><th>Example</th></tr></thead><tbody>{high_rows}</tbody></table>
<script>
const search = document.getElementById('search');
const root = document.getElementById('root');
const rows = [...document.querySelectorAll('#nodes tbody tr')];
function filterRows() {{
  const q = search.value.toLowerCase();
  const r = root.value;
  rows.forEach(row => {{
    const text = row.innerText.toLowerCase();
    const show = (!q || text.includes(q)) && (!r || row.dataset.root === r);
    row.style.display = show ? '' : 'none';
  }});
}}
search.addEventListener('input', filterRows);
root.addEventListener('change', filterRows);
</script>
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")


def build(input_dir: Path, output_dir: Path, sample_size: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    abpath_tags, abpath_by_lower = load_abpath_tags(input_dir)
    if not abpath_tags:
        raise RuntimeError("No ABPath tags found at input-dir/abpath_source_tags.jsonl")

    records: List[Dict[str, Any]] = []
    source_counts: Counter = Counter()
    tag_counts: Counter = Counter()
    node_counts: Counter = Counter()
    review_rows: List[Dict[str, Any]] = []
    rejected_rows: List[Dict[str, Any]] = []
    forbidden_examples: List[Dict[str, Any]] = []

    out_jsonl = output_dir / "curriculum_records_v0_2.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as handle:
        fallback = 0
        for source, rec in iter_source_records(input_dir, sample_size):
            fallback += 1
            rid = record_id(source, rec, fallback)
            governed = govern_record(source, rec, rid, abpath_tags, abpath_by_lower)
            records.append(governed)
            source_counts[source] += 1
            if governed["visible"]:
                tag_counts[(source, governed["approved_tag"])] += 1
                node_counts[governed["approved_tag"]] += 1
                forbidden, pattern = has_forbidden(governed["approved_tag"])
                if forbidden:
                    forbidden_examples.append(
                        {
                            "record_id": rid,
                            "source": source,
                            "tag": governed["approved_tag"],
                            "pattern": pattern,
                            "title": governed["title"],
                        }
                    )
            elif governed["status"] in {"pathout_local_review", "who_review"}:
                review_rows.append(governed)
            else:
                rejected_rows.append(governed)
            handle.write(json.dumps(governed, ensure_ascii=False, sort_keys=True) + "\n")

    node_rows = [
        {"tag": tag, "root": root_for_tag(tag), "record_count": count}
        for tag, count in sorted(node_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    review_csv_rows = [
        {
            "record_id": row["record_id"],
            "source": row["source"],
            "original_tag": row["original_tag"],
            "review_reason": row["review_reason"],
            "fuzzy_score": row["fuzzy_score"] if row["fuzzy_score"] is not None else "",
            "title": row["title"],
            "input_path": row["input_path"],
        }
        for row in review_rows
    ]
    rejected_csv_rows = [
        {
            "record_id": row["record_id"],
            "source": row["source"],
            "original_tag": row["original_tag"],
            "rejection_reason": row["rejection_reason"],
            "title": row["title"],
            "input_path": row["input_path"],
        }
        for row in rejected_rows
    ]

    high_yield_rows: List[Dict[str, Any]] = []
    visible_by_root: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in records:
        if row["visible"]:
            visible_by_root[row["root"]].append(row)
    for root in HIGH_YIELD_ROOTS:
        matches = []
        root_l = root.lower()
        for row in records:
            tag = row["approved_tag"]
            if row["visible"] and (tag.lower().startswith(root_l) or root_l in tag.lower()):
                matches.append(
                    {
                        "root": root,
                        "tag": tag,
                        "source": row["source"],
                        "record_id": row["record_id"],
                        "title": row["title"],
                    }
                )
            if len(matches) >= 25:
                break
        high_yield_rows.extend(matches or [{"root": root, "tag": "", "source": "", "record_id": "", "title": ""}])

    write_csv(output_dir / "curriculum_nodes_v0_2.csv", ["tag", "root", "record_count"], node_rows)
    write_csv(output_dir / "review_queue_v0_2.csv", ["record_id", "source", "original_tag", "review_reason", "fuzzy_score", "title", "input_path"], review_csv_rows)
    write_csv(output_dir / "rejected_tags_v0_2.csv", ["record_id", "source", "original_tag", "rejection_reason", "title", "input_path"], rejected_csv_rows)
    write_sqlite(output_dir / "curriculum_tag_index_v0_2.sqlite", records, node_counts, source_counts, tag_counts, review_rows, rejected_rows, high_yield_rows)

    total_records = len(records)
    visible_records = sum(1 for row in records if row["visible"])
    status_counts = Counter(row["status"] for row in records)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now_utc(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "sample_size": sample_size,
        "gcs_read_only_inputs_downloaded": True,
        "gcs_uploaded_or_mutated": False,
        "total_records_processed": total_records,
        "records_visible_in_curriculum": visible_records,
        "records_hidden_rejected": len(rejected_rows),
        "review_queue_count": len(review_rows),
        "abpath_approved_tag_count": status_counts["approved_abpath"],
        "who_mapped_count": status_counts["mapped_who_abpath"],
        "pathout_local_review_count": status_counts["pathout_local_review"],
        "forbidden_visible_tag_count": len(forbidden_examples),
        "forbidden_examples": forbidden_examples[:25],
        "source_counts": dict(sorted(source_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "curriculum_node_count": len(node_counts),
        "build_status": "failed_visibility_gate" if forbidden_examples else "passed_local_visibility_gate",
        "known_limitations": [
            "Local build only; curriculum mapping is not live and no GCS upload/deployment/schema update was performed.",
            "PathOut non-ABPath tags are placed in review_queue and not exposed as curriculum nodes.",
            "WHO mappings use standard-library fuzzy matching; accepted mappings require score >= 90.",
            "Textbook and lecture tags only become visible when they exactly match loaded ABPath tags and contain no forbidden pattern.",
        ],
    }
    (output_dir / "acceptance_summary_v0_2.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    write_browser(output_dir / "curriculum_browser_v0_2.html", summary, node_rows, len(review_rows), len(rejected_rows), high_yield_rows)
    write_readme(output_dir, summary)
    return summary


def write_readme(output_dir: Path, summary: Dict[str, Any]) -> None:
    text = f"""# Curriculum Map v0.2

Generated: {summary['generated_at_utc']}

This is a local Curriculum Map build for Evidence/Lesson/Research RAG. It is not live, not uploaded, and not deployed.

## Outputs

- `curriculum_records_v0_2.jsonl`
- `curriculum_nodes_v0_2.csv`
- `review_queue_v0_2.csv`
- `rejected_tags_v0_2.csv`
- `curriculum_tag_index_v0_2.sqlite`
- `curriculum_browser_v0_2.html`
- `acceptance_summary_v0_2.json`

## Acceptance

- Build status: `{summary['build_status']}`
- Total records processed: {summary['total_records_processed']}
- Visible curriculum records: {summary['records_visible_in_curriculum']}
- Review queue count: {summary['review_queue_count']}
- Rejected/hidden count: {summary['records_hidden_rejected']}
- Forbidden visible tag count: {summary['forbidden_visible_tag_count']}

## Safety

- No GCS upload or mutation.
- No Cloud Run deploy.
- No GPT Builder schema update.
- No v11 promotion.
- Forbidden patterns are never exposed as curriculum nodes.
"""
    (output_dir / "README_CURRICULUM_MAP_v0_2.md").write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local Curriculum Map v0.2")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sample-size", type=int, default=0, help="0 means full local files; positive value caps records per input file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build(Path(args.input_dir), Path(args.output_dir), args.sample_size)
    print(f"Wrote Curriculum Map v0.2 to {args.output_dir}")
    print(f"Build status: {summary['build_status']}")
    print(f"Visible curriculum records: {summary['records_visible_in_curriculum']}")
    print(f"Review queue count: {summary['review_queue_count']}")
    print(f"Rejected/hidden count: {summary['records_hidden_rejected']}")
    print(f"Forbidden visible tag count: {summary['forbidden_visible_tag_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
