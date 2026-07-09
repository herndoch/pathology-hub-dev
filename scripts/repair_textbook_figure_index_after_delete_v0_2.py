#!/usr/bin/env python3
"""Repair textbook vector docstore and web figure map after v0_2 GCS figure deletes.

Loads the executed delete manifest (gs:// URIs), streams the textbook vector
docstore and web figure map JSONL artifacts, and:

- Docstore: null `image_path` when it references a deleted figure (keep row).
- Web map: drop rows whose original private figure URI was deleted (row is
  useless without a live original).

Writes repaired outputs locally with a v0_2 suffix, emits a repair audit JSON,
and optionally uploads to canonical GCS paths after a separate upload audit.

Does not modify normalized curriculum records, FAISS indexes, or raw chunks.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "textbook_figure_index_repair.v0_2"
UPLOAD_AUDIT_SCHEMA = "textbook_figure_index_repair_upload.v0_2"

DEFAULT_DELETE_MANIFEST = (
    "06_audits/curriculum_provenance_links/v0_1/figure_image_gcs_delete_v0_2/"
    "delete_manifest_execute_20260708.txt"
)
DEFAULT_DOCSTORE_GCS = (
    "gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_docstore.jsonl"
)
DEFAULT_WEB_MAP_GCS = (
    "gs://pathology_hub/02_normalized/textbooks/lean/"
    "textbook_figure_web_map_v1_FILTERED_NO_MCKEE_DORFMAN.jsonl"
)
DEFAULT_OUTPUT_DIR = "outputs/textbook_figure_index_repair_v0_2"
DEFAULT_AUDIT_DIR = "06_audits/curriculum_provenance_links/v0_1/textbook_figure_index_repair_v0_2"

DOCSTORE_IMAGE_FIELDS = ("image_path", "image_url")
WEB_MAP_ORIGIN_FIELDS = (
    "original_gs_uri",
    "original_image_path",
    "original_path_value",
    "image_path",
    "image_url",
    "path",
    "url",
)


def https_to_gs(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    if url.startswith("gs://"):
        return url
    if url.startswith("https://storage.googleapis.com/"):
        return "gs://" + url[len("https://storage.googleapis.com/") :]
    if url.startswith("http://storage.googleapis.com/"):
        return "gs://" + url[len("http://storage.googleapis.com/") :]
    return None


def load_deleted_uris(manifest_path: Path) -> set[str]:
    uris: set[str] = set()
    with manifest_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            uri = line.strip()
            if uri:
                uris.add(uri)
    return uris


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


def row_origin_gs_uris(obj: dict[str, Any], fields: tuple[str, ...]) -> set[str]:
    found: set[str] = set()
    for field in fields:
        gs = https_to_gs(obj.get(field))
        if gs:
            found.add(gs)
    return found


def repair_docstore(
    input_path: Path,
    output_path: Path,
    deleted: set[str],
) -> dict[str, Any]:
    total = 0
    with_image_before = 0
    lines_repaired = 0
    fields_nulled: Counter[str] = Counter()

    def rows() -> Iterable[dict[str, Any]]:
        nonlocal total, with_image_before, lines_repaired
        for row in iter_jsonl(input_path):
            total += 1
            origins = row_origin_gs_uris(row, DOCSTORE_IMAGE_FIELDS)
            if origins:
                with_image_before += 1
            hit = origins & deleted
            if not hit:
                yield row
                continue

            repaired = dict(row)
            changed = False
            for field in DOCSTORE_IMAGE_FIELDS:
                gs = https_to_gs(repaired.get(field))
                if gs and gs in deleted:
                    repaired[field] = None
                    fields_nulled[field] += 1
                    changed = True
            if changed:
                lines_repaired += 1
            yield repaired

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_lines = write_jsonl(output_path, rows())
    return {
        "input_lines": total,
        "output_lines": out_lines,
        "lines_with_image_path_before": with_image_before,
        "lines_repaired": lines_repaired,
        "fields_nulled": dict(fields_nulled),
    }


def repair_web_map(
    input_path: Path,
    output_path: Path,
    deleted: set[str],
) -> dict[str, Any]:
    total = 0
    lines_with_deleted_origin = 0
    kept = 0

    def rows() -> Iterable[dict[str, Any]]:
        nonlocal total, lines_with_deleted_origin, kept
        for row in iter_jsonl(input_path):
            total += 1
            origins = row_origin_gs_uris(row, WEB_MAP_ORIGIN_FIELDS)
            if origins & deleted:
                lines_with_deleted_origin += 1
                continue
            kept += 1
            yield row

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_lines = write_jsonl(output_path, rows())
    return {
        "input_lines": total,
        "output_lines": out_lines,
        "lines_dropped": lines_with_deleted_origin,
        "lines_kept": kept,
    }


def download_gcs(uri: str, dest: Path, project: str | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["gsutil"]
    if project:
        cmd.extend(["-u", project])
    cmd.extend(["cp", uri, str(dest)])
    subprocess.run(cmd, check=True)


def upload_gcs(local_path: Path, uri: str, project: str | None) -> dict[str, Any]:
    cmd = ["gsutil"]
    if project:
        cmd.extend(["-u", project])
    cmd.extend(["cp", str(local_path), uri])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "local_path": str(local_path.resolve()),
        "gcs_uri": uri,
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def verify_no_deleted_refs(path: Path, deleted: set[str], fields: tuple[str, ...]) -> int:
    hits = 0
    for row in iter_jsonl(path):
        if row_origin_gs_uris(row, fields) & deleted:
            hits += 1
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete-manifest", default=DEFAULT_DELETE_MANIFEST)
    parser.add_argument("--docstore-gcs", default=DEFAULT_DOCSTORE_GCS)
    parser.add_argument("--web-map-gcs", default=DEFAULT_WEB_MAP_GCS)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--audit-dir", default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--project", default="pathology-annotation-project")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use existing local inputs under output-dir/inputs/",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="After repair audit, write upload audit and copy repaired files to canonical GCS paths.",
    )
    parser.add_argument(
        "--run-tag",
        default=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    )
    args = parser.parse_args()

    manifest_path = Path(args.delete_manifest)
    if not manifest_path.exists():
        print(f"Missing delete manifest: {manifest_path}", file=sys.stderr)
        return 1

    deleted = load_deleted_uris(manifest_path)
    out_dir = Path(args.output_dir)
    inputs_dir = out_dir / "inputs"
    docstore_in = inputs_dir / "textbook_lean_vector_docstore.jsonl"
    web_map_in = inputs_dir / "textbook_figure_web_map_v1_FILTERED_NO_MCKEE_DORFMAN.jsonl"
    docstore_out = out_dir / "textbook_lean_vector_docstore_v0_2.jsonl"
    web_map_out = out_dir / "textbook_figure_web_map_v1_FILTERED_NO_MCKEE_DORFMAN_v0_2.jsonl"

    if not args.skip_download:
        download_gcs(args.docstore_gcs, docstore_in, args.project)
        download_gcs(args.web_map_gcs, web_map_in, args.project)
    elif not docstore_in.exists() or not web_map_in.exists():
        print("Missing local inputs; run without --skip-download first.", file=sys.stderr)
        return 1

    docstore_counts = repair_docstore(docstore_in, docstore_out, deleted)
    web_map_counts = repair_web_map(web_map_in, web_map_out, deleted)

    post_docstore_deleted_refs = verify_no_deleted_refs(
        docstore_out, deleted, DOCSTORE_IMAGE_FIELDS
    )
    post_web_map_deleted_refs = verify_no_deleted_refs(
        web_map_out, deleted, WEB_MAP_ORIGIN_FIELDS
    )

    audit_dir = Path(args.audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    repair_audit_path = audit_dir / f"repair_audit_{args.run_tag}.json"

    audit: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_paths": {
            "delete_manifest": str(manifest_path.resolve()),
            "docstore_gcs": args.docstore_gcs,
            "web_map_gcs": args.web_map_gcs,
            "docstore_local_input": str(docstore_in.resolve()),
            "web_map_local_input": str(web_map_in.resolve()),
        },
        "output_paths": {
            "docstore_repaired": str(docstore_out.resolve()),
            "web_map_repaired": str(web_map_out.resolve()),
            "repair_audit": str(repair_audit_path.resolve()),
        },
        "counts": {
            "deleted_uris_in_manifest": len(deleted),
            "docstore": docstore_counts,
            "web_map": web_map_counts,
            "post_repair_deleted_ref_docstore_lines": post_docstore_deleted_refs,
            "post_repair_deleted_ref_web_map_lines": post_web_map_deleted_refs,
        },
        "known_limitations": [
            "Repairs only docstore image_path/image_url and web-map origin URI fields.",
            "Does not rebuild FAISS, textbook_lean_figures.jsonl, or SQLite FTS indexes.",
            "Web-map rows referencing deleted originals are dropped, not partially stripped.",
            "Canonical GCS objects are not overwritten unless --upload is passed after this audit.",
        ],
    }
    repair_audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    result = {
        "repair_audit": str(repair_audit_path),
        "docstore_lines_repaired": docstore_counts["lines_repaired"],
        "web_map_lines_dropped": web_map_counts["lines_dropped"],
        "post_repair_deleted_ref_docstore_lines": post_docstore_deleted_refs,
        "post_repair_deleted_ref_web_map_lines": post_web_map_deleted_refs,
    }
    print(json.dumps(result, indent=2))

    if not args.upload:
        return 0

    upload_audit_path = audit_dir / f"upload_audit_{args.run_tag}.json"
    upload_targets = [
        {
            "local_path": str(docstore_out.resolve()),
            "gcs_uri": args.docstore_gcs,
            "artifact": "docstore",
        },
        {
            "local_path": str(web_map_out.resolve()),
            "gcs_uri": args.web_map_gcs,
            "artifact": "web_map",
        },
    ]
    upload_audit: dict[str, Any] = {
        "schema_version": UPLOAD_AUDIT_SCHEMA,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_paths": {
            "repair_audit": str(repair_audit_path.resolve()),
            "docstore_repaired_local": str(docstore_out.resolve()),
            "web_map_repaired_local": str(web_map_out.resolve()),
        },
        "output_paths": {
            "docstore_gcs": args.docstore_gcs,
            "web_map_gcs": args.web_map_gcs,
            "upload_audit": str(upload_audit_path.resolve()),
        },
        "counts": {
            "deleted_uris_in_manifest": len(deleted),
            "docstore_lines_repaired": docstore_counts["lines_repaired"],
            "web_map_lines_dropped": web_map_counts["lines_dropped"],
            "upload_targets": len(upload_targets),
        },
        "known_limitations": [
            "Overwrites canonical GCS docstore and web-map objects in place.",
            "Cloud Run pods cache downloaded artifacts until cold restart.",
            "textbook_lean_figures.jsonl and FAISS index not updated in this upload.",
        ],
    }
    upload_audit_path.write_text(json.dumps(upload_audit, indent=2) + "\n", encoding="utf-8")

    upload_results = []
    for target in upload_targets:
        upload_results.append(
            upload_gcs(Path(target["local_path"]), target["gcs_uri"], args.project)
        )
    upload_audit["upload_results"] = upload_results
    upload_audit_path.write_text(json.dumps(upload_audit, indent=2) + "\n", encoding="utf-8")

    ok = all(r["ok"] for r in upload_results)
    print(json.dumps({"upload_audit": str(upload_audit_path), "ok": ok}, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
