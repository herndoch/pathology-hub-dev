#!/usr/bin/env python3
"""Build staged Curriculum Map v0.3 from v0.2 plus full hybrid gap-fill."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import html
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "curriculum_map_v0_3"
DEFAULT_V02_DIR = Path("outputs/curriculum_map_v0_2")
DEFAULT_GAPFILL_DIR = Path("outputs/curriculum_gapfill_v0_3")
DEFAULT_OUTPUT_DIR = Path("outputs/curriculum_map_v0_3")
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
GCS_PATHS = {
    "gapfill": "gs://pathology_hub/02_normalized/curriculum_gapfill/v0_3/",
    "map": "gs://pathology_hub/02_normalized/curriculum_map/v0_3/",
    "html": "gs://pathology_hub/05_html/curriculum_map/v0_3/",
    "gapfill_audits": "gs://pathology_hub/06_audits/curriculum_gapfill/v0_3/",
    "map_audits": "gs://pathology_hub/06_audits/curriculum_map/v0_3/",
}


def has_forbidden(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else str(value)
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


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


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def gapfill_record(row: dict[str, Any], source_family: str) -> dict[str, Any]:
    tag = str(row.get("abpath_tag") or "")
    chunk_id = str(row.get("chunk_id") or "")
    source = str(row.get("content_source") or source_family)
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": f"gapfill_v0_3:{source}:{chunk_id}:{tag}",
        "source": source,
        "content_source": source,
        "ontology_source": "abpath",
        "status": "approved_gapfill_v0_3",
        "visible": True,
        "approved_tag": tag,
        "root": str(row.get("root") or tag.split("::", 1)[0]),
        "title": str(row.get("source_id") or chunk_id),
        "original_tag": str(row.get("original_existing_tag") or ""),
        "original_tag_field": "hybrid_gapfill_abpath_tag",
        "mapped_from": "gapfill_v0_3",
        "fuzzy_score": row.get("hybrid_score"),
        "review_reason": "",
        "rejection_reason": "",
        "input_path": str(row.get("_input_path") or ""),
        "raw_source_gcs_uri": "",
        "normalized_artifact_gcs_uri": "",
        "original_record": row,
    }


def review_row(row: dict[str, str], source_family: str, reason: str, input_path: str) -> dict[str, str]:
    return {
        "record_id": f"{source_family}_gapfill_v0_3_{reason}:{row.get('chunk_id', '')}:{row.get('abpath_tag', '')}",
        "source": f"{source_family}_gapfill_v0_3",
        "original_tag": row.get("abpath_tag", ""),
        "review_reason": reason if reason.startswith("review") else "",
        "fuzzy_score": row.get("hybrid_score", ""),
        "title": row.get("source_id", ""),
        "input_path": input_path,
        "rejection_reason": reason if not reason.startswith("review") else "",
    }


def append_queue(base_rows: list[dict[str, str]], gap_rows: list[dict[str, str]], fields: list[str], source_family: str, reason: str, input_path: str) -> list[dict[str, str]]:
    out = list(base_rows)
    for row in gap_rows:
        mapped = review_row(row, source_family, reason, input_path)
        out.append({field: mapped.get(field, "") for field in fields})
    return out


def source_family_for_record(row: dict[str, Any]) -> str:
    return str(row.get("content_source") or row.get("source") or "")


def decision_status_for_record(row: dict[str, Any]) -> str:
    return str(row.get("status") or row.get("review_status") or row.get("approval_status") or "")


def row_identity(row: dict[str, Any]) -> tuple[str, ...]:
    original = row.get("original_record") if isinstance(row.get("original_record"), dict) else {}
    chunk_id = str(original.get("chunk_id") or row.get("chunk_id") or "")
    source_id = str(original.get("source_id") or original.get("video_id") or row.get("source_id") or row.get("title") or "")
    return (
        source_family_for_record(row),
        source_id,
        chunk_id,
        str(row.get("record_id") or ""),
        str(row.get("approved_tag") or ""),
        decision_status_for_record(row),
        str(row.get("input_path") or ""),
        str(row.get("original_tag") or ""),
        str(row.get("title") or ""),
    )


def row_key(identity: tuple[str, ...], occurrence: int) -> str:
    payload = json.dumps({"identity": identity, "occurrence": occurrence}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def count_records(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(rows),
        "by_status": dict(Counter(decision_status_for_record(row) for row in rows).most_common()),
        "by_root": dict(Counter(str(row.get("root") or "") for row in rows).most_common()),
        "by_source_family": dict(Counter(source_family_for_record(row) for row in rows).most_common()),
    }


def write_sqlite(path: Path, records: list[dict[str, Any]], node_rows: list[dict[str, Any]], audit_path: Path | None = None) -> dict[str, Any]:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    conn = sqlite3.connect(tmp_path)
    conn.execute(
        "CREATE TABLE curriculum_records ("
        "curriculum_row_key TEXT PRIMARY KEY, "
        "record_id TEXT, approved_tag TEXT, root TEXT, source TEXT, title TEXT, input_path TEXT, "
        "content_source TEXT, ontology_source TEXT, gapfill_version TEXT, decision_status TEXT, "
        "source_family TEXT, source_id TEXT, chunk_id TEXT, row_identity TEXT, duplicate_ordinal INTEGER)"
    )
    conn.execute("CREATE TABLE curriculum_nodes (tag TEXT PRIMARY KEY, root TEXT, record_count INTEGER)")
    identity_counts: Counter[tuple[str, ...]] = Counter()
    for row in records:
        identity = row_identity(row)
        identity_counts[identity] += 1
        occurrence = identity_counts[identity]
        original = row.get("original_record") if isinstance(row.get("original_record"), dict) else {}
        chunk_id = str(original.get("chunk_id") or row.get("chunk_id") or "")
        source_id = str(original.get("source_id") or original.get("video_id") or row.get("source_id") or row.get("title") or "")
        decision_status = decision_status_for_record(row)
        source_family = source_family_for_record(row)
        conn.execute(
            "INSERT INTO curriculum_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row_key(identity, occurrence),
                row.get("record_id"),
                row.get("approved_tag"),
                row.get("root"),
                row.get("source"),
                row.get("title"),
                row.get("input_path"),
                row.get("content_source") or ("" if row.get("source") == "abpath" else row.get("source")),
                row.get("ontology_source") or ("abpath" if row.get("source") == "abpath" else ""),
                "v0_3" if str(row.get("record_id", "")).startswith("gapfill_v0_3:") else "",
                decision_status,
                source_family,
                source_id,
                chunk_id,
                json.dumps(identity, ensure_ascii=False),
                occurrence,
            ),
        )
    for row in node_rows:
        conn.execute("INSERT OR REPLACE INTO curriculum_nodes VALUES (?, ?, ?)", (row["tag"], row["root"], int(row["record_count"])))
    conn.execute("CREATE INDEX idx_curriculum_records_tag ON curriculum_records(approved_tag)")
    conn.execute("CREATE INDEX idx_curriculum_records_source ON curriculum_records(source)")
    conn.execute("CREATE INDEX idx_curriculum_records_row_record_id ON curriculum_records(record_id)")
    conn.execute("CREATE INDEX idx_curriculum_records_status ON curriculum_records(decision_status)")
    conn.execute("CREATE INDEX idx_curriculum_records_source_family ON curriculum_records(source_family)")
    sqlite_record_count = conn.execute("SELECT COUNT(*) FROM curriculum_records").fetchone()[0]
    sqlite_counts = {
        "total": sqlite_record_count,
        "by_status": dict(conn.execute("SELECT decision_status, COUNT(*) FROM curriculum_records GROUP BY decision_status ORDER BY COUNT(*) DESC").fetchall()),
        "by_root": dict(conn.execute("SELECT root, COUNT(*) FROM curriculum_records GROUP BY root ORDER BY COUNT(*) DESC").fetchall()),
        "by_source_family": dict(conn.execute("SELECT source_family, COUNT(*) FROM curriculum_records GROUP BY source_family ORDER BY COUNT(*) DESC").fetchall()),
    }
    conn.commit()
    conn.close()
    tmp_path.replace(path)
    input_counts = count_records(records)
    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifact": str(path),
        "status": "passed",
        "intended_uniqueness_key": [
            "source_family/content_source",
            "source_id",
            "chunk_id",
            "record_id",
            "approved_tag/proposed_primary_tag",
            "decision_status",
            "input_path",
            "original_tag",
            "title",
            "duplicate_ordinal_for_exact_identity_repeats",
        ],
        "rationale": "record_id is not unique in v0.2 records. curriculum_row_key hashes a stable source/tag/status identity plus duplicate ordinal to preserve every distinct source/tag decision row while keeping a primary key for SQLite lookup integrity.",
        "input_rows": input_counts,
        "sqlite_rows": sqlite_counts,
        "duplicate_identity_groups": sum(1 for count in identity_counts.values() if count > 1),
        "duplicate_identity_rows": sum(count for count in identity_counts.values() if count > 1),
        "dropped_rows": len(records) - sqlite_record_count,
    }
    if sqlite_record_count != len(records):
        audit["status"] = "failed"
    if audit_path:
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if sqlite_record_count != len(records):
        raise RuntimeError(f"SQLite row count mismatch: input={len(records)} sqlite={sqlite_record_count}")
    return audit


def regenerate_sqlite_only(output_dir: Path) -> dict[str, Any]:
    records_path = output_dir / "curriculum_records_v0_3.jsonl"
    nodes_path = output_dir / "curriculum_nodes_v0_3.csv"
    if not records_path.exists():
        raise SystemExit(f"Missing records input for SQLite regeneration: {records_path}")
    if not nodes_path.exists():
        raise SystemExit(f"Missing nodes input for SQLite regeneration: {nodes_path}")
    records = list(read_jsonl(records_path))
    _, node_rows = read_csv(nodes_path)
    return write_sqlite(
        output_dir / "curriculum_tag_index_v0_3.sqlite",
        records,
        node_rows,
        output_dir / "curriculum_tag_index_v0_3_sqlite_audit.json",
    )


def write_browser(path: Path, summary: dict[str, Any], nodes: list[dict[str, Any]]) -> None:
    top_roots = "".join(f"<tr><td>{html.escape(root)}</td><td>{count}</td></tr>" for root, count in summary["roots_improved"].items())
    top_tags = "".join(f"<tr><td>{html.escape(tag)}</td><td>{count}</td></tr>" for tag, count in summary["tags_improved"].items())
    top_nodes = "".join(
        f"<tr><td>{html.escape(row['tag'])}</td><td>{html.escape(row['root'])}</td><td>{row['record_count']}</td></tr>"
        for row in sorted(nodes, key=lambda r: (-int(r["record_count"]), r["tag"]))[:100]
    )
    text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Curriculum Map v0.3</title>
  <style>
    body {{ margin: 0; font-family: Georgia, 'Times New Roman', serif; color: #202520; background: #f5f7f2; }}
    header {{ background: #183d35; color: white; padding: 24px 32px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 26px 24px 44px; }}
    .banner {{ border: 1px solid #d2aa72; background: #fff8eb; color: #5a3404; padding: 12px 14px; margin: 0 0 18px; font-weight: 700; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 18px 0 24px; }}
    .metric {{ background: white; border: 1px solid #dce1d5; padding: 13px; }}
    .metric strong {{ display: block; font-size: 1.35rem; }}
    table {{ width: 100%; border-collapse: collapse; background: white; margin: 14px 0 26px; }}
    th, td {{ border: 1px solid #dce1d5; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #e9eee3; }}
  </style>
</head>
<body>
  <header><h1>Curriculum Map v0.3</h1><div>STAGED DATA PRODUCT, NOT LIVE API</div></header>
  <main>
    <div class="banner">STAGED DATA PRODUCT, NOT LIVE API. ABPath is ontology/tag provenance only, not a content source.</div>
    <section class="metrics">
      <div class="metric"><strong>{summary['v0_2_visible_records']}</strong>v0.2 visible records</div>
      <div class="metric"><strong>{summary['v0_3_visible_records']}</strong>v0.3 visible records</div>
      <div class="metric"><strong>{summary['net_added_records']}</strong>net added records</div>
      <div class="metric"><strong>{summary['lecture_gapfill']['approved']}</strong>lecture approved</div>
      <div class="metric"><strong>{summary['textbook_gapfill']['approved']}</strong>textbook approved</div>
      <div class="metric"><strong>{summary['forbidden_visible_tag_count']}</strong>forbidden visible tags</div>
    </section>
    <h2>Roots Improved</h2><table><thead><tr><th>Root</th><th>Added Records</th></tr></thead><tbody>{top_roots}</tbody></table>
    <h2>Tags Improved</h2><table><thead><tr><th>Tag</th><th>Added Records</th></tr></thead><tbody>{top_tags}</tbody></table>
    <h2>Largest Nodes</h2><table><thead><tr><th>Tag</th><th>Root</th><th>Records</th></tr></thead><tbody>{top_nodes}</tbody></table>
  </main>
</body>
</html>
"""
    path.write_text(text, encoding="utf-8")


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    text = f"""# Curriculum Map v0.3

Staged Curriculum Map v0.3 built from v0.2 approved records plus full hybrid lecture and textbook ABPath gap-fill sidecars.

Counts:
- v0.2 visible records: {summary["v0_2_visible_records"]}
- v0.3 visible records: {summary["v0_3_visible_records"]}
- net added records: {summary["net_added_records"]}
- lecture approved/review/rejected: {summary["lecture_gapfill"]["approved"]}/{summary["lecture_gapfill"]["review"]}/{summary["lecture_gapfill"]["rejected"]}
- textbook approved/review/rejected: {summary["textbook_gapfill"]["approved"]}/{summary["textbook_gapfill"]["review"]}/{summary["textbook_gapfill"]["rejected"]}
- forbidden visible tag count: {summary["forbidden_visible_tag_count"]}

ABPath is ontology/tag provenance only. It is not counted as a content source.
"""
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02-dir", type=Path, default=DEFAULT_V02_DIR)
    parser.add_argument("--gapfill-dir", type=Path, default=DEFAULT_GAPFILL_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--sqlite-only",
        action="store_true",
        help="Regenerate only curriculum_tag_index_v0_3.sqlite and its SQLite audit from existing v0.3 records/nodes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.sqlite_only:
        audit = regenerate_sqlite_only(args.output_dir)
        print(json.dumps(audit, ensure_ascii=False, sort_keys=True))
        return 0
    v02_summary = json.loads((args.v02_dir / "acceptance_summary_v0_2.json").read_text(encoding="utf-8"))
    _, v02_nodes = read_csv(args.v02_dir / "curriculum_nodes_v0_2.csv")
    review_fields, review_base = read_csv(args.v02_dir / "review_queue_v0_2.csv")
    rejected_fields, rejected_base = read_csv(args.v02_dir / "rejected_tags_v0_2.csv")
    gap_audit = json.loads((args.gapfill_dir / "curriculum_gapfill_v0_3_audit.json").read_text(encoding="utf-8"))

    lecture_approved_path = args.gapfill_dir / "lecture_abpath_gapfill_approved_FULL_v0_3.jsonl"
    textbook_approved_path = args.gapfill_dir / "textbook_abpath_gapfill_approved_FULL_v0_3.jsonl"
    lecture_review_path = args.gapfill_dir / "lecture_abpath_gapfill_review_FULL_v0_3.csv"
    textbook_review_path = args.gapfill_dir / "textbook_abpath_gapfill_review_FULL_v0_3.csv"
    lecture_rejected_path = args.gapfill_dir / "lecture_abpath_gapfill_rejected_FULL_v0_3.csv"
    textbook_rejected_path = args.gapfill_dir / "textbook_abpath_gapfill_rejected_FULL_v0_3.csv"

    lecture_approved = list(read_jsonl(lecture_approved_path))
    textbook_approved = list(read_jsonl(textbook_approved_path))
    _, lecture_review = read_csv(lecture_review_path)
    _, textbook_review = read_csv(textbook_review_path)
    _, lecture_rejected = read_csv(lecture_rejected_path)
    _, textbook_rejected = read_csv(textbook_rejected_path)

    records: list[dict[str, Any]] = []
    forbidden_visible = 0
    for row in read_jsonl(args.v02_dir / "curriculum_records_v0_2.jsonl"):
        if row.get("visible") and not has_forbidden(row.get("approved_tag")):
            records.append(row)
        elif row.get("visible"):
            forbidden_visible += 1
    for source_family, rows, input_path in (
        ("lectures", lecture_approved, str(lecture_approved_path)),
        ("textbooks", textbook_approved, str(textbook_approved_path)),
    ):
        for row in rows:
            if has_forbidden(row.get("abpath_tag")):
                forbidden_visible += 1
                continue
            item = dict(row)
            item["_input_path"] = input_path
            records.append(gapfill_record(item, source_family))

    node_counts = {row["tag"]: int(row.get("record_count") or 0) for row in v02_nodes}
    node_roots = {row["tag"]: row.get("root", "") for row in v02_nodes}
    added_counts = Counter(str(row.get("abpath_tag") or "") for row in lecture_approved + textbook_approved if not has_forbidden(row.get("abpath_tag")))
    for tag, count in added_counts.items():
        node_counts[tag] = node_counts.get(tag, 0) + count
        node_roots.setdefault(tag, tag.split("::", 1)[0])
    nodes = [{"tag": tag, "root": node_roots.get(tag, ""), "record_count": node_counts[tag]} for tag in sorted(node_counts)]

    review_rows = append_queue(review_base, lecture_review, review_fields, "lecture", "review_hybrid", str(lecture_review_path))
    review_rows = append_queue(review_rows, textbook_review, review_fields, "textbook", "review_hybrid", str(textbook_review_path))
    rejected_rows = append_queue(rejected_base, lecture_rejected, rejected_fields, "lecture", "rejected_hybrid", str(lecture_rejected_path))
    rejected_rows = append_queue(rejected_rows, textbook_rejected, rejected_fields, "textbook", "rejected_hybrid", str(textbook_rejected_path))

    records_path = args.output_dir / "curriculum_records_v0_3.jsonl"
    write_jsonl(records_path, records)
    with records_path.open("rb") as src, gzip.open(args.output_dir / "curriculum_records_v0_3.jsonl.gz", "wb") as dst:
        dst.writelines(src)
    write_csv(args.output_dir / "curriculum_nodes_v0_3.csv", ["tag", "root", "record_count"], nodes)
    write_csv(args.output_dir / "review_queue_v0_3.csv", review_fields, review_rows)
    write_csv(args.output_dir / "rejected_tags_v0_3.csv", rejected_fields, rejected_rows)
    write_sqlite(
        args.output_dir / "curriculum_tag_index_v0_3.sqlite",
        records,
        nodes,
        args.output_dir / "curriculum_tag_index_v0_3_sqlite_audit.json",
    )

    root_counts = Counter(str(row.get("root") or str(row.get("abpath_tag") or "").split("::", 1)[0]) for row in lecture_approved + textbook_approved)
    content_source_counts = {k: v for k, v in (v02_summary.get("source_counts") or {}).items() if k != "abpath"}
    content_source_counts["lecture_gapfill_v0_3"] = len(lecture_approved)
    content_source_counts["textbook_gapfill_v0_3"] = len(textbook_approved)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "build_status": "passed_staging_gate" if forbidden_visible == 0 else "failed_forbidden_visible_gate",
        "v0_2_visible_records": int(v02_summary.get("records_visible_in_curriculum") or 0),
        "v0_3_visible_records": int(v02_summary.get("records_visible_in_curriculum") or 0) + len(lecture_approved) + len(textbook_approved),
        "net_added_records": len(lecture_approved) + len(textbook_approved),
        "lecture_gapfill": {"approved": len(lecture_approved), "review": len(lecture_review), "rejected": len(lecture_rejected)},
        "textbook_gapfill": {"approved": len(textbook_approved), "review": len(textbook_review), "rejected": len(textbook_rejected)},
        "tags_improved": dict(added_counts.most_common(30)),
        "roots_improved": dict(root_counts.most_common(30)),
        "tags_lacking_seed_profiles": gap_audit.get("counts", {}).get("tags_lacking_seed_profiles"),
        "vector_status": gap_audit.get("vector_status"),
        "forbidden_visible_tag_count": forbidden_visible,
        "content_source_counts_excluding_abpath": content_source_counts,
        "ontology_provenance": {"abpath": "tag ontology only; not counted as content source"},
        "review_queue_count": len(review_rows),
        "rejected_tags_count": len(rejected_rows),
        "curriculum_node_count": len(nodes),
        "input_paths": {
            "v0_2_dir": str(args.v02_dir),
            "gapfill_dir": str(args.gapfill_dir),
        },
        "output_paths": {
            "records_jsonl": str(records_path),
            "records_jsonl_gz": str(args.output_dir / "curriculum_records_v0_3.jsonl.gz"),
            "nodes_csv": str(args.output_dir / "curriculum_nodes_v0_3.csv"),
            "review_queue_csv": str(args.output_dir / "review_queue_v0_3.csv"),
            "rejected_tags_csv": str(args.output_dir / "rejected_tags_v0_3.csv"),
            "sqlite": str(args.output_dir / "curriculum_tag_index_v0_3.sqlite"),
            "sqlite_audit": str(args.output_dir / "curriculum_tag_index_v0_3_sqlite_audit.json"),
            "browser_html": str(args.output_dir / "curriculum_browser_v0_3.html"),
        },
        "limitations": [
            "No API deployment or GPT Builder update was performed.",
            "No raw normalized source records, vector docstores, FAISS indexes, or v0.2 outputs were modified.",
            "Gap-fill approvals use lexical/exemplar hybrid support; vectors were unavailable as a complete local similarity index.",
        ],
    }
    (args.output_dir / "acceptance_summary_v0_3.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_browser(args.output_dir / "curriculum_browser_v0_3.html", summary, nodes)
    write_readme(args.output_dir / "README_CURRICULUM_MAP_V0_3.md", summary)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "build_status": summary["build_status"],
        "allowed_gcs_paths": GCS_PATHS,
        "local_outputs": summary["output_paths"] | {
            "acceptance_summary": str(args.output_dir / "acceptance_summary_v0_3.json"),
            "readme": str(args.output_dir / "README_CURRICULUM_MAP_V0_3.md"),
            "staging_manifest": str(args.output_dir / "staging_manifest_v0_3.json"),
        },
        "gapfill_outputs": (gap_audit.get("outputs") or {}),
        "counts": summary,
        "known_limitations": summary["limitations"],
    }
    (args.output_dir / "staging_manifest_v0_3.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
