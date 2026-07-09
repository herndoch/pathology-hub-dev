#!/usr/bin/env python3
"""Strip flagged textbook figure image locators from repaired provenance sidecar.

For every row in the v0_1 flagged figure-image CSV (and any other repaired row
whose image_url matches a flagged URL), clears `image_path` and `image_url`,
updates locator completeness, and writes a new repaired sidecar plus a strip
repair sidecar. Does not overwrite v0_1 outputs.

Optionally rebuilds the derived SQLite provenance index (v0_2).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "curriculum_image_locator_strip_repairs.v0_2"
DEFAULT_FLAGGED_CSV = (
    "06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/"
    "flagged_figure_images_full_v0_1.csv"
)
DEFAULT_REPAIRED_SIDECAR = "outputs/curriculum_map_v0_4/curriculum_record_provenance_sidecar_repaired_v0_1.jsonl"
DEFAULT_OUTPUT_SIDECAR = "outputs/curriculum_map_v0_4/curriculum_record_provenance_sidecar_repaired_v0_2.jsonl"
DEFAULT_STRIP_SIDECAR = "outputs/curriculum_map_v0_4/curriculum_source_locator_image_strip_sidecar_v0_2.jsonl"
DEFAULT_SQLITE_OUT = "outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_2.sqlite"
INDEX_SCRIPT = "scripts/build_curriculum_source_locator_index_v0_1.py"


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def normalize_url(url: str | None) -> str:
    return (url or "").strip()


def load_flagged_targets(csv_path: Path) -> tuple[set[str], set[str]]:
    record_ids: set[str] = set()
    urls: set[str] = set()
    with csv_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rid = (row.get("record_id") or "").strip()
            url = normalize_url(row.get("url"))
            if rid:
                record_ids.add(rid)
            if url:
                urls.add(url)
    return record_ids, urls


def should_strip(row: dict[str, Any], record_ids: set[str], urls: set[str]) -> bool:
    rid = str(row.get("record_id") or "")
    image_url = normalize_url(row.get("image_url"))
    image_path = normalize_url(row.get("image_path"))
    if rid in record_ids:
        return True
    if image_url and image_url in urls:
        return True
    if image_path:
        https_path = image_path
        if image_path.startswith("gs://"):
            https_path = "https://storage.googleapis.com/" + image_path[len("gs://") :]
        if https_path in urls:
            return True
    return False


def strip_row(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    repaired = dict(row)
    before = {
        "image_path": repaired.get("image_path"),
        "image_url": repaired.get("image_url"),
        "locator_status": repaired.get("locator_status"),
    }
    repaired.pop("image_path", None)
    repaired.pop("image_url", None)
    repaired["image_path"] = None
    repaired["image_url"] = None

    missing = list(repaired.get("missing_locator_parts") or [])
    if "page_image_or_figure_image" not in missing:
        missing.append("page_image_or_figure_image")
    repaired["missing_locator_parts"] = missing
    repaired["locator_status"] = "partial"

    change = {
        "record_id": repaired.get("record_id"),
        "action": "strip_flagged_figure_image_locator",
        "before": before,
        "after": {
            "image_path": None,
            "image_url": None,
            "locator_status": "partial",
            "missing_locator_parts": missing,
        },
    }
    return repaired, change


def rebuild_sqlite(repaired_sidecar: Path, sqlite_out: Path, audit_out: Path) -> None:
    cmd = [
        sys.executable,
        INDEX_SCRIPT,
        "--repaired-sidecar",
        str(repaired_sidecar),
        "--sqlite-out",
        str(sqlite_out),
        "--audit-out",
        str(audit_out),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flagged-csv", default=DEFAULT_FLAGGED_CSV)
    parser.add_argument("--repaired-sidecar", default=DEFAULT_REPAIRED_SIDECAR)
    parser.add_argument("--output-sidecar", default=DEFAULT_OUTPUT_SIDECAR)
    parser.add_argument("--strip-sidecar", default=DEFAULT_STRIP_SIDECAR)
    parser.add_argument("--sqlite-out", default=DEFAULT_SQLITE_OUT)
    parser.add_argument(
        "--skip-sqlite-rebuild",
        action="store_true",
        help="Only write sidecars; do not rebuild the derived SQLite index.",
    )
    parser.add_argument(
        "--audit-out",
        default="06_audits/curriculum_provenance_links/v0_1/curriculum_image_locator_strip_audit_v0_2.json",
    )
    args = parser.parse_args()

    flagged_csv = Path(args.flagged_csv)
    repaired_in = Path(args.repaired_sidecar)
    if not flagged_csv.exists():
        print(f"Missing flagged CSV: {flagged_csv}", file=sys.stderr)
        return 1
    if not repaired_in.exists():
        print(f"Missing repaired sidecar: {repaired_in}", file=sys.stderr)
        return 1

    record_ids, urls = load_flagged_targets(flagged_csv)
    output_rows: list[dict[str, Any]] = []
    strip_rows: list[dict[str, Any]] = []
    stripped = 0
    total = 0

    for row in iter_jsonl(repaired_in):
        total += 1
        if row.get("source_family") == "textbooks" and should_strip(row, record_ids, urls):
            repaired, change = strip_row(row)
            output_rows.append(repaired)
            strip_rows.append(change)
            stripped += 1
        else:
            output_rows.append(row)

    output_sidecar = Path(args.output_sidecar)
    strip_sidecar = Path(args.strip_sidecar)
    output_sidecar.parent.mkdir(parents=True, exist_ok=True)
    strip_sidecar.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_sidecar, output_rows)
    write_jsonl(strip_sidecar, strip_rows)

    sqlite_out = Path(args.sqlite_out)
    index_audit = Path(args.audit_out).with_name("source_locator_index_audit_v0_2.json")
    if not args.skip_sqlite_rebuild:
        rebuild_sqlite(output_sidecar, sqlite_out, index_audit)

    audit = {
        "schema_version": SCHEMA_VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_paths": {
            "flagged_csv": str(flagged_csv.resolve()),
            "repaired_sidecar_v0_1": str(repaired_in.resolve()),
        },
        "output_paths": {
            "repaired_sidecar_v0_2": str(output_sidecar.resolve()),
            "strip_sidecar_v0_2": str(strip_sidecar.resolve()),
            "sqlite_index_v0_2": str(sqlite_out.resolve()) if not args.skip_sqlite_rebuild else None,
            "index_audit_v0_2": str(index_audit.resolve()) if not args.skip_sqlite_rebuild else None,
        },
        "counts": {
            "input_rows": total,
            "stripped_rows": stripped,
            "flagged_record_ids": len(record_ids),
            "flagged_unique_urls": len(urls),
        },
        "known_limitations": [
            "Only textbook rows with flagged record_id or flagged image_url are stripped.",
            "Does not delete GCS objects; run delete_flagged_textbook_figure_images_v0_2.py separately.",
            "v0_1 sidecar and sqlite outputs are preserved; v0_2 files are new.",
        ],
    }
    audit_path = Path(args.audit_out)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"audit_path": str(audit_path), "stripped_rows": stripped, "output_sidecar": str(output_sidecar)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
