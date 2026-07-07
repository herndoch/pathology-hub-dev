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

QUICK_ROOT_CHIPS = [
    "Skin",
    "HN",
    "BST",
    "GI",
    "Molecular",
    "Breast",
    "Cyto_GYN",
    "Endo",
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
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    conn = sqlite3.connect(tmp_path)
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
    tmp_path.replace(path)


def fmt_num(value: int) -> str:
    return f"{value:,}"


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
    root_options = "\n".join(
        f"<option value='{html.escape(root)}'>{html.escape(root)} ({root_counts[root]})</option>" for root in roots
    )
    root_chip_buttons = "\n".join(
        f'<button type="button" class="chip" data-root="{html.escape(root)}">{html.escape(root)}</button>'
        for root in QUICK_ROOT_CHIPS
    )
    hy_root_chip_buttons = "\n".join(
        f'<button type="button" class="chip" data-hy-root="{html.escape(root)}">{html.escape(root)}</button>'
        for root in HIGH_YIELD_ROOTS
    )
    hy_sources = sorted({row["source"] for row in high_yield_rows if row.get("source")})
    hy_source_options = "\n".join(
        f'<option value="{html.escape(source)}">{html.escape(source)}</option>' for source in hy_sources
    )

    build_status = html.escape(summary["build_status"])
    generated_date = html.escape(str(summary.get("generated_at_utc", ""))[:10])
    node_count = summary.get("curriculum_node_count", len(nodes))
    visible = summary["records_visible_in_curriculum"]
    forbidden = summary["forbidden_visible_tag_count"]
    total = summary["total_records_processed"]
    badge_class = "badge-pass" if forbidden == 0 and summary["build_status"] == "passed_local_visibility_gate" else "badge"
    badge_prefix = "✓ " if summary["build_status"] == "passed_local_visibility_gate" else ""

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Curriculum Map v0.2</title>
<style>
:root {{
  --bg: #f4f6f9;
  --surface: #fff;
  --text: #1f2933;
  --muted: #52606d;
  --border: #d9e2ec;
  --accent: #2563eb;
  --pass: #059669;
  --pass-bg: #ecfdf5;
}}
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui, -apple-system, Segoe UI, Arial, sans-serif; margin: 0; color: var(--text); background: var(--bg); line-height: 1.45; }}
.page {{ max-width: 1280px; margin: 0 auto; padding: 20px 24px 48px; }}
h1 {{ margin: 0 0 4px; font-size: 1.6rem; }}
h2 {{ margin: 0 0 12px; font-size: 1.1rem; }}
.subtitle {{ color: var(--muted); margin: 0 0 16px; font-size: 0.92rem; }}
.summary-panel {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; margin-bottom: 16px; }}
.summary-top {{ display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 14px; }}
.badge {{ display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px; font-size: 0.82rem; font-weight: 600; }}
.badge-pass {{ background: var(--pass-bg); color: var(--pass); border: 1px solid #a7f3d0; }}
.meta {{ color: var(--muted); font-size: 0.85rem; }}
.metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }}
.metric {{ border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; background: #f8fafc; }}
.metric-label {{ font-size: 0.78rem; color: var(--muted); margin-bottom: 4px; }}
.metric-value {{ font-size: 1.25rem; font-weight: 700; }}
.metric-primary {{ background: #eff6ff; border-color: #bfdbfe; }}
.metric-safe {{ background: var(--pass-bg); border-color: #a7f3d0; }}
.metric-info {{ background: #fffbeb; border-color: #fde68a; }}
.metric-muted {{ background: #f1f5f9; }}
.guide {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0 16px; margin-bottom: 16px; }}
.guide summary {{ cursor: pointer; font-weight: 600; padding: 14px 0; }}
.guide ul {{ margin: 0 0 14px 1.2rem; padding: 0; color: var(--muted); font-size: 0.9rem; }}
.guide li {{ margin-bottom: 6px; }}
.queue-note {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; font-size: 0.9rem; color: var(--muted); }}
.queue-note strong {{ color: var(--text); }}
.tabs {{ display: flex; gap: 8px; margin-bottom: 12px; }}
.tab {{ padding: 8px 16px; border: 1px solid var(--border); border-radius: 8px 8px 0 0; background: #e2e8f0; cursor: pointer; font-size: 0.9rem; font-weight: 600; color: var(--muted); border-bottom: none; }}
.tab.active {{ background: var(--surface); color: var(--text); }}
.panel {{ display: none; background: var(--surface); border: 1px solid var(--border); border-radius: 0 10px 10px 10px; padding: 16px; }}
.panel.active {{ display: block; }}
.toolbar {{ display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px 16px; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }}
.field {{ display: flex; flex-direction: column; gap: 4px; }}
.field label {{ font-size: 0.78rem; font-weight: 600; color: var(--muted); }}
.field input, .field select {{ padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 0.9rem; min-width: 200px; }}
.field-grow {{ flex: 1 1 260px; }}
.field-grow input {{ width: 100%; min-width: 0; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 6px; width: 100%; }}
.chip {{ padding: 5px 10px; border: 1px solid var(--border); border-radius: 999px; background: #fff; font-size: 0.78rem; cursor: pointer; color: var(--muted); }}
.chip:hover {{ border-color: var(--accent); color: var(--accent); }}
.chip.active {{ background: #dbeafe; border-color: var(--accent); color: #1d4ed8; font-weight: 600; }}
.result-count {{ margin-left: auto; font-size: 0.85rem; color: var(--muted); align-self: center; }}
.table-wrap {{ max-height: 62vh; overflow: auto; border: 1px solid var(--border); border-radius: 8px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #e5e7eb; padding: 7px 10px; text-align: left; vertical-align: top; font-size: 0.88rem; }}
th {{ background: #eef2f7; position: sticky; top: 0; z-index: 1; }}
tbody tr:hover {{ background: #f8fafc; }}
.tag-cell {{ font-family: ui-monospace, Consolas, monospace; font-size: 0.82rem; word-break: break-word; }}
.section-intro {{ font-size: 0.88rem; color: var(--muted); margin: 0 0 12px; }}
@media (max-width: 640px) {{ .page {{ padding: 12px; }} .result-count {{ width: 100%; margin-left: 0; }} }}
</style>
</head>
<body>
<div class="page">
<h1>Curriculum Map v0.2</h1>
<p class="subtitle">Local Evidence/Lesson/Research RAG curriculum browser — not live, not uploaded.</p>

<section class="summary-panel" aria-label="Build summary">
<div class="summary-top">
<span class="badge {badge_class}" title="Local visibility gate">{badge_prefix}{build_status}</span>
<span class="meta">Generated {generated_date} · {fmt_num(node_count)} curriculum nodes · {fmt_num(total)} records processed</span>
</div>
<div class="metrics">
<div class="metric metric-primary"><div class="metric-label">Visible curriculum records</div><div class="metric-value">{fmt_num(visible)}</div></div>
<div class="metric metric-safe"><div class="metric-label">Forbidden visible tags</div><div class="metric-value">{fmt_num(forbidden)}</div></div>
<div class="metric metric-info"><div class="metric-label">Review queue</div><div class="metric-value">{fmt_num(review_count)}</div></div>
<div class="metric metric-muted"><div class="metric-label">Rejected / hidden</div><div class="metric-value">{fmt_num(rejected_count)}</div></div>
<div class="metric metric-muted"><div class="metric-label">Total processed</div><div class="metric-value">{fmt_num(total)}</div></div>
</div>
</section>

<details class="guide">
<summary>How to interpret this map</summary>
<ul>
<li><strong>Curriculum nodes</strong> are ABPath-approved tags with visible record counts. Only tags that passed the local visibility gate appear here.</li>
<li><strong>High-yield sections</strong> show representative tags for major organ systems (Ovary, Prostate, Breast, GI, Lung, Derm, Bone, Soft tissue, Cyto).</li>
<li><strong>Review queue</strong> ({fmt_num(review_count)}) holds PathOut and WHO tags awaiting manual review — they are not shown as curriculum nodes.</li>
<li><strong>Rejected / hidden</strong> ({fmt_num(rejected_count)}) includes non-matching textbook/lecture tags, forbidden patterns, and generated junk — intentionally excluded from this view.</li>
<li><strong>Forbidden visible tags = {fmt_num(forbidden)}</strong> confirms no lecture, textbook, slide, or error patterns leaked into the visible curriculum.</li>
</ul>
</details>

<p class="queue-note">The review queue and rejected counts are <strong>expected governance outcomes</strong>, not errors. They reflect tags held back until reviewed or matched to ABPath. Full lists live in <code>review_queue_v0_2.csv</code> and <code>rejected_tags_v0_2.csv</code>.</p>

<div class="tabs" role="tablist">
<button type="button" class="tab active" data-panel="panel-nodes" role="tab" aria-selected="true">Curriculum nodes</button>
<button type="button" class="tab" data-panel="panel-high-yield" role="tab" aria-selected="false">High-yield sections</button>
</div>

<section id="panel-nodes" class="panel active" role="tabpanel">
<div class="toolbar">
<div class="field field-grow"><label for="search">Search tags</label><input id="search" type="search" placeholder="Filter by tag or root name…" autocomplete="off"></div>
<div class="field"><label for="root">Root</label><select id="root"><option value="">All roots</option>{root_options}</select></div>
<span id="nodes-count" class="result-count"></span>
</div>
<div class="chips" id="root-chips" aria-label="Quick root filters">
<button type="button" class="chip active" data-root="">All</button>
{root_chip_buttons}
</div>
<div class="table-wrap">
<table id="nodes"><thead><tr><th>Root</th><th>Curriculum node</th><th>Records</th></tr></thead><tbody>{node_rows}</tbody></table>
</div>
</section>

<section id="panel-high-yield" class="panel" role="tabpanel" hidden>
<h2>High-yield sections</h2>
<p class="section-intro">Representative ABPath tags for major organ systems. Use filters to narrow by root or source.</p>
<div class="toolbar">
<div class="field field-grow"><label for="hy-search">Search</label><input id="hy-search" type="search" placeholder="Filter high-yield tags…" autocomplete="off"></div>
<div class="field"><label for="hy-source">Source</label><select id="hy-source"><option value="">All sources</option>{hy_source_options}</select></div>
<span id="hy-count" class="result-count"></span>
</div>
<div class="chips" id="hy-root-chips" aria-label="High-yield root filters">
<button type="button" class="chip active" data-hy-root="">All</button>
{hy_root_chip_buttons}
</div>
<div class="table-wrap">
<table id="high-yield"><thead><tr><th>Root</th><th>Tag</th><th>Source</th><th>Example</th></tr></thead><tbody>{high_rows}</tbody></table>
</div>
</section>
</div>
<script>
(function () {{
  const search = document.getElementById('search');
  const rootSelect = document.getElementById('root');
  const nodeRows = [...document.querySelectorAll('#nodes tbody tr')];
  const nodesCount = document.getElementById('nodes-count');
  const rootChips = document.getElementById('root-chips');

  const hySearch = document.getElementById('hy-search');
  const hySource = document.getElementById('hy-source');
  const hyRows = [...document.querySelectorAll('#high-yield tbody tr')];
  const hyCount = document.getElementById('hy-count');
  const hyRootChips = document.getElementById('hy-root-chips');

  let activeHyRoot = '';

  function setRootChips(value) {{
    rootChips.querySelectorAll('.chip').forEach(chip => {{
      chip.classList.toggle('active', chip.dataset.root === value);
    }});
  }}

  function setHyRootChips(value) {{
    activeHyRoot = value;
    hyRootChips.querySelectorAll('.chip').forEach(chip => {{
      chip.classList.toggle('active', chip.dataset.hyRoot === value);
    }});
  }}

  function filterNodes() {{
    const q = search.value.trim().toLowerCase();
    const r = rootSelect.value;
    let visible = 0;
    nodeRows.forEach(row => {{
      const text = row.innerText.toLowerCase();
      const show = (!q || text.includes(q)) && (!r || row.dataset.root === r);
      row.style.display = show ? '' : 'none';
      if (show) visible++;
    }});
    nodesCount.textContent = visible + ' of ' + nodeRows.length + ' nodes';
  }}

  function filterHighYield() {{
    const q = hySearch.value.trim().toLowerCase();
    const src = hySource.value;
    let visible = 0;
    hyRows.forEach(row => {{
      const cells = row.cells;
      const rowRoot = cells[0]?.innerText.trim() || '';
      const rowSource = cells[2]?.innerText.trim() || '';
      const text = row.innerText.toLowerCase();
      const show = (!q || text.includes(q))
        && (!src || rowSource === src)
        && (!activeHyRoot || rowRoot === activeHyRoot);
      row.style.display = show ? '' : 'none';
      if (show) visible++;
    }});
    hyCount.textContent = visible + ' of ' + hyRows.length + ' examples';
  }}

  search.addEventListener('input', filterNodes);
  rootSelect.addEventListener('change', () => {{
    setRootChips(rootSelect.value);
    filterNodes();
  }});
  rootChips.addEventListener('click', e => {{
    const chip = e.target.closest('.chip');
    if (!chip) return;
    rootSelect.value = chip.dataset.root;
    setRootChips(chip.dataset.root);
    filterNodes();
  }});

  hySearch.addEventListener('input', filterHighYield);
  hySource.addEventListener('change', filterHighYield);
  hyRootChips.addEventListener('click', e => {{
    const chip = e.target.closest('.chip');
    if (!chip) return;
    setHyRootChips(chip.dataset.hyRoot);
    filterHighYield();
  }});

  document.querySelectorAll('.tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
      document.querySelectorAll('.tab').forEach(t => {{
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      }});
      document.querySelectorAll('.panel').forEach(p => {{
        p.classList.remove('active');
        p.hidden = true;
      }});
      tab.classList.add('active');
      tab.setAttribute('aria-selected', 'true');
      const panel = document.getElementById(tab.dataset.panel);
      panel.classList.add('active');
      panel.hidden = false;
    }});
  }});

  filterNodes();
  filterHighYield();
}})();
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
