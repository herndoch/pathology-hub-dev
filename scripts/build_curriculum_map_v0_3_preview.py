#!/usr/bin/env python3
"""Build a local Curriculum Map v0.3 preview from v0.2 plus hybrid lecture gap-fill."""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "curriculum_map_v0_3_preview"
DEFAULT_V02_DIR = Path("outputs/curriculum_map_v0_2")
DEFAULT_GAPFILL_DIR = Path("outputs/curriculum_gapfill_v0_3")
DEFAULT_OUTPUT_DIR = Path("outputs/curriculum_map_v0_3_preview")
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


def has_forbidden(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else str(value)
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def append_review_rows(v02_rows: list[dict[str, str]], hybrid_rows: list[dict[str, str]], fieldnames: list[str]) -> list[dict[str, str]]:
    rows = list(v02_rows)
    for row in hybrid_rows:
        rows.append(
            {
                "record_id": "lecture_gapfill_v0_3_preview_review:" + row.get("chunk_id", "") + ":" + row.get("abpath_tag", ""),
                "source": "lecture_gapfill_v0_3_preview",
                "original_tag": row.get("abpath_tag", ""),
                "review_reason": "review_hybrid",
                "fuzzy_score": row.get("hybrid_score", ""),
                "title": row.get("source_id", ""),
                "input_path": "outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_review_hybrid_v0_3.csv",
            }
        )
    return [{field: row.get(field, "") for field in fieldnames} for row in rows]


def append_rejected_rows(v02_rows: list[dict[str, str]], hybrid_rows: list[dict[str, str]], fieldnames: list[str]) -> list[dict[str, str]]:
    rows = list(v02_rows)
    for row in hybrid_rows:
        rows.append(
            {
                "record_id": "lecture_gapfill_v0_3_preview_rejected:" + row.get("chunk_id", "") + ":" + row.get("abpath_tag", ""),
                "source": "lecture_gapfill_v0_3_preview",
                "original_tag": row.get("abpath_tag", ""),
                "rejection_reason": row.get("rejection_reason") or row.get("hybrid_decision") or "rejected_hybrid",
                "title": row.get("source_id", ""),
                "input_path": "outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_rejected_hybrid_v0_3.csv",
            }
        )
    return [{field: row.get(field, "") for field in fieldnames} for row in rows]


def write_browser(path: Path, summary: dict[str, Any], nodes: list[dict[str, Any]], additions: list[dict[str, Any]]) -> None:
    top_nodes = sorted(nodes, key=lambda row: int(row.get("record_count") or 0), reverse=True)[:100]
    top_added = Counter(str(row.get("abpath_tag") or "") for row in additions).most_common(50)
    node_rows = "\n".join(
        f"<tr><td>{html.escape(row['tag'])}</td><td>{html.escape(row['root'])}</td><td>{html.escape(str(row['record_count']))}</td></tr>"
        for row in top_nodes
    )
    added_rows = "\n".join(
        f"<tr><td>{html.escape(tag)}</td><td>{html.escape(str(count))}</td></tr>"
        for tag, count in top_added
    )
    text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Curriculum Map v0.3 Preview</title>
  <style>
    body {{ font-family: Georgia, 'Times New Roman', serif; margin: 0; color: #1d2329; background: #f6f8f5; }}
    header {{ background: #173f35; color: white; padding: 24px 32px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px 24px 48px; }}
    .banner {{ font-weight: 700; color: #7a1f16; background: #fff1eb; border: 1px solid #e2b6a8; padding: 12px 14px; margin-bottom: 20px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0 24px; }}
    .metric {{ background: white; border: 1px solid #d9dfd8; padding: 14px; }}
    .metric strong {{ display: block; font-size: 1.35rem; }}
    table {{ width: 100%; border-collapse: collapse; background: white; margin: 16px 0 28px; }}
    th, td {{ border: 1px solid #d9dfd8; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #e8eee7; }}
    h1, h2 {{ margin: 0 0 10px; }}
  </style>
</head>
<body>
  <header>
    <h1>Curriculum Map v0.3 Preview</h1>
    <div>LOCAL PREVIEW ONLY, NOT LIVE API</div>
  </header>
  <main>
    <div class="banner">LOCAL PREVIEW ONLY, NOT LIVE API. No GCS upload, deploy, GPT Builder update, vector rebuild, or production artifact creation was performed.</div>
    <section class="metrics">
      <div class="metric"><strong>{summary['v0_2_visible_records']}</strong>v0.2 visible records</div>
      <div class="metric"><strong>{summary['v0_3_preview_visible_records']}</strong>v0.3 preview visible records</div>
      <div class="metric"><strong>{summary['net_added_visible_records']}</strong>net added visible records</div>
      <div class="metric"><strong>{summary['approved_lecture_gapfill_rows_added']}</strong>approved lecture gapfill rows</div>
      <div class="metric"><strong>{summary['review_rows']}</strong>review rows</div>
      <div class="metric"><strong>{summary['rejected_rows']}</strong>rejected rows</div>
      <div class="metric"><strong>{summary['forbidden_visible_tag_count']}</strong>forbidden visible tags</div>
    </section>
    <h2>Top Added Tags</h2>
    <table><thead><tr><th>Tag</th><th>Added Records</th></tr></thead><tbody>{added_rows}</tbody></table>
    <h2>Top Curriculum Nodes</h2>
    <table><thead><tr><th>Tag</th><th>Root</th><th>Preview Record Count</th></tr></thead><tbody>{node_rows}</tbody></table>
  </main>
</body>
</html>
"""
    path.write_text(text, encoding="utf-8")


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    text = f"""# Curriculum Map v0.3 Preview

This is a local preview built from Curriculum Map v0.2 plus conservative approved hybrid lecture gap-fill rows.

Counts:
- v0.2 visible records: {summary["v0_2_visible_records"]}
- v0.3 preview visible records: {summary["v0_3_preview_visible_records"]}
- net added visible records: {summary["net_added_visible_records"]}
- approved lecture gapfill rows added: {summary["approved_lecture_gapfill_rows_added"]}
- review rows: {summary["review_rows"]}
- rejected rows: {summary["rejected_rows"]}
- forbidden visible tag count: {summary["forbidden_visible_tag_count"]}

ABPath is ontology/tag provenance only. The added content source is `lecture_gapfill_v0_3_preview`.

This preview is not live, not API-exposed, not uploaded, not deployed, and not a production artifact.
"""
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02-dir", type=Path, default=DEFAULT_V02_DIR)
    parser.add_argument("--gapfill-dir", type=Path, default=DEFAULT_GAPFILL_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    v02_summary = json.loads((args.v02_dir / "acceptance_summary_v0_2.json").read_text(encoding="utf-8"))
    node_fields, node_rows = read_csv(args.v02_dir / "curriculum_nodes_v0_2.csv")
    review_fields, review_rows = read_csv(args.v02_dir / "review_queue_v0_2.csv")
    rejected_fields, rejected_rows = read_csv(args.v02_dir / "rejected_tags_v0_2.csv")
    approved = read_jsonl(args.gapfill_dir / "lecture_abpath_gapfill_approved_v0_3_HYBRID_HIGHCONF.jsonl")
    _, hybrid_review = read_csv(args.gapfill_dir / "lecture_abpath_gapfill_review_hybrid_v0_3.csv")
    _, hybrid_rejected = read_csv(args.gapfill_dir / "lecture_abpath_gapfill_rejected_hybrid_v0_3.csv")
    approval_audit = json.loads((args.gapfill_dir / "lecture_abpath_gapfill_hybrid_approval_audit_v0_3.json").read_text(encoding="utf-8"))

    node_counts = {row["tag"]: int(row.get("record_count") or 0) for row in node_rows}
    node_roots = {row["tag"]: row.get("root", "") for row in node_rows}
    added_tag_counts = Counter(str(row.get("abpath_tag") or "") for row in approved if not has_forbidden(row.get("abpath_tag")))
    forbidden_visible = 0
    for tag, count in added_tag_counts.items():
        if has_forbidden(tag):
            forbidden_visible += count
            continue
        node_counts[tag] = node_counts.get(tag, 0) + count
        node_roots.setdefault(tag, str(tag).split("::", 1)[0])
    preview_nodes = [{"tag": tag, "root": node_roots.get(tag, ""), "record_count": node_counts[tag]} for tag in sorted(node_counts)]
    preview_nodes.sort(key=lambda row: (-int(row["record_count"]), row["tag"]))

    preview_review = append_review_rows(review_rows, hybrid_review, review_fields)
    preview_rejected = append_rejected_rows(rejected_rows, hybrid_rejected, rejected_fields)
    root_counts = Counter(str(row.get("root") or str(row.get("abpath_tag") or "").split("::", 1)[0]) for row in approved)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "build_status": "passed_local_preview_gate" if forbidden_visible == 0 else "failed_forbidden_visible_gate",
        "v0_2_visible_records": int(v02_summary.get("records_visible_in_curriculum") or 0),
        "v0_3_preview_visible_records": int(v02_summary.get("records_visible_in_curriculum") or 0) + len(approved),
        "net_added_visible_records": len(approved),
        "approved_lecture_gapfill_rows_added": len(approved),
        "review_rows": len(preview_review),
        "rejected_rows": len(preview_rejected),
        "hybrid_review_rows_added": len(hybrid_review),
        "hybrid_rejected_rows_added": len(hybrid_rejected),
        "forbidden_visible_tag_count": forbidden_visible,
        "roots_most_affected": dict(root_counts.most_common(20)),
        "tags_most_affected": dict(added_tag_counts.most_common(20)),
        "vector_status": approval_audit.get("vector_status"),
        "source_counts": {
            **{k: v for k, v in (v02_summary.get("source_counts") or {}).items() if k != "abpath"},
            "lecture_gapfill_v0_3_preview": len(approved),
        },
        "ontology_provenance": {"abpath": "tag ontology only; not counted as content source"},
        "input_paths": {
            "v0_2_dir": str(args.v02_dir),
            "approved_hybrid_sidecar": str(args.gapfill_dir / "lecture_abpath_gapfill_approved_v0_3_HYBRID_HIGHCONF.jsonl"),
        },
        "output_paths": {
            "curriculum_nodes": str(args.output_dir / "curriculum_nodes_v0_3_preview.csv"),
            "review_queue": str(args.output_dir / "review_queue_v0_3_preview.csv"),
            "rejected_tags": str(args.output_dir / "rejected_tags_v0_3_preview.csv"),
            "browser": str(args.output_dir / "curriculum_browser_v0_3_preview.html"),
        },
        "known_limitations": [
            "Local preview only; no API/live files were created.",
            "Hybrid rows use cross-source lexical/exemplar support; vectors were unavailable.",
            "Textbook gap-fill was not processed.",
        ],
    }
    write_csv(args.output_dir / "curriculum_nodes_v0_3_preview.csv", node_fields, preview_nodes)
    write_csv(args.output_dir / "review_queue_v0_3_preview.csv", review_fields, preview_review)
    write_csv(args.output_dir / "rejected_tags_v0_3_preview.csv", rejected_fields, preview_rejected)
    (args.output_dir / "acceptance_summary_v0_3_preview.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_browser(args.output_dir / "curriculum_browser_v0_3_preview.html", summary, preview_nodes, approved)
    write_readme(args.output_dir / "README_CURRICULUM_MAP_V0_3_PREVIEW.md", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
