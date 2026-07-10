#!/usr/bin/env python3
"""Repair textbook_lean_figures.jsonl after v0_2 GCS figure deletes.

Loads the executed delete manifest (gs:// URIs), streams the textbook lean
figures JSONL, and drops rows whose image_path/image_url (or equivalent)
references a deleted figure object.

Writes a repaired local copy, emits a repair audit JSON, and optionally
uploads to the canonical GCS path after a separate upload audit.

Does not modify curriculum normalized records, quality-flags sidecar,
curriculum SQLite, FAISS indexes, or the already-repaired docstore/web map.
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

SCHEMA_VERSION = "textbook_lean_figures_repair.v0_3"
UPLOAD_AUDIT_SCHEMA = "textbook_lean_figures_repair_upload.v0_3"

DEFAULT_DELETE_MANIFEST = (
    "06_audits/curriculum_provenance_links/v0_1/figure_image_gcs_delete_v0_2/"
    "delete_manifest_execute_20260708.txt"
)
DEFAULT_FIGURES_GCS = (
    "gs://pathology_hub/02_normalized/textbooks/lean/textbook_lean_figures.jsonl"
)
DEFAULT_OUTPUT_DIR = "outputs/textbook_lean_figures_repair_v0_3"
DEFAULT_AUDIT_DIR = (
    "06_audits/curriculum_provenance_links/v0_1/textbook_lean_figures_repair_v0_3"
)

FIGURE_IMAGE_FIELDS = (
    "image_path",
    "image_url",
    "figure_url",
    "path",
    "gcs_uri",
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


def row_image_gs_uris(obj: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for field in FIGURE_IMAGE_FIELDS:
        gs = https_to_gs(obj.get(field))
        if gs:
            found.add(gs)
    return found


def repair_figures(
    input_path: Path,
    output_path: Path,
    deleted: set[str],
) -> dict[str, Any]:
    total = 0
    lines_dropped = 0
    kept = 0
    dropped_by_source: Counter[str] = Counter()
    sample_dropped: list[dict[str, Any]] = []

    def rows() -> Iterable[dict[str, Any]]:
        nonlocal total, lines_dropped, kept
        for row in iter_jsonl(input_path):
            total += 1
            origins = row_image_gs_uris(row)
            hit = origins & deleted
            if hit:
                lines_dropped += 1
                sid = str(row.get("source_id") or "__unknown__")
                dropped_by_source[sid] += 1
                if len(sample_dropped) < 10:
                    sample_dropped.append(
                        {
                            "figure_record_id": row.get("figure_record_id"),
                            "source_id": row.get("source_id"),
                            "page": row.get("page"),
                            "figure_id": row.get("figure_id"),
                            "deleted_uris": sorted(hit),
                        }
                    )
                continue
            kept += 1
            yield row

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_lines = write_jsonl(output_path, rows())
    return {
        "input_lines": total,
        "output_lines": out_lines,
        "lines_dropped": lines_dropped,
        "lines_kept": kept,
        "dropped_by_source_id": dict(dropped_by_source.most_common()),
        "sample_dropped_rows": sample_dropped,
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


def verify_no_deleted_refs(path: Path, deleted: set[str]) -> int:
    hits = 0
    for row in iter_jsonl(path):
        if row_image_gs_uris(row) & deleted:
            hits += 1
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete-manifest", default=DEFAULT_DELETE_MANIFEST)
    parser.add_argument("--figures-gcs", default=DEFAULT_FIGURES_GCS)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--audit-dir", default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--project", default="pathology-annotation-project")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use existing local input under output-dir/inputs/",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="After repair audit + verification, write upload audit and copy to canonical GCS.",
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
    figures_in = inputs_dir / "textbook_lean_figures.jsonl"
    figures_out = out_dir / "textbook_lean_figures_v0_3.jsonl"

    if not args.skip_download:
        download_gcs(args.figures_gcs, figures_in, args.project)
    elif not figures_in.exists():
        print("Missing local input; run without --skip-download first.", file=sys.stderr)
        return 1

    figures_counts = repair_figures(figures_in, figures_out, deleted)
    post_deleted_refs = verify_no_deleted_refs(figures_out, deleted)

    audit_dir = Path(args.audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    repair_audit_path = audit_dir / f"repair_audit_{args.run_tag}.json"

    audit: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "script": "scripts/repair_textbook_lean_figures_after_delete_v0_3.py",
        "input_paths": {
            "delete_manifest": str(manifest_path.resolve()),
            "figures_gcs": args.figures_gcs,
            "figures_local_input": str(figures_in.resolve()),
        },
        "output_paths": {
            "figures_repaired": str(figures_out.resolve()),
            "repair_audit": str(repair_audit_path.resolve()),
        },
        "counts": {
            "deleted_uris_in_manifest": len(deleted),
            "figures": figures_counts,
            "post_repair_deleted_ref_lines": post_deleted_refs,
        },
        "known_limitations": [
            "Drops figure rows whose image URI is in the v0_2 delete manifest; does not null fields.",
            "Does not rebuild FAISS, docstore, web figure map, or curriculum SQLite.",
            "Does not address Tier-A suppress_render quality defects (handled by Chat MVP Phase 1 filter).",
            "Cloud Run pods cache downloaded artifacts until cold restart.",
            "Canonical GCS object is not overwritten unless --upload is passed after verification.",
        ],
    }
    repair_audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    result = {
        "repair_audit": str(repair_audit_path),
        "input_lines": figures_counts["input_lines"],
        "output_lines": figures_counts["output_lines"],
        "lines_dropped": figures_counts["lines_dropped"],
        "post_repair_deleted_ref_lines": post_deleted_refs,
    }
    print(json.dumps(result, indent=2))

    if post_deleted_refs != 0:
        print(
            f"Verification failed: {post_deleted_refs} deleted-URI refs remain.",
            file=sys.stderr,
        )
        return 2

    if not args.upload:
        return 0

    upload_audit_path = audit_dir / f"upload_audit_{args.run_tag}.json"
    upload_audit: dict[str, Any] = {
        "schema_version": UPLOAD_AUDIT_SCHEMA,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_paths": {
            "repair_audit": str(repair_audit_path.resolve()),
            "figures_repaired_local": str(figures_out.resolve()),
        },
        "output_paths": {
            "figures_gcs": args.figures_gcs,
            "upload_audit": str(upload_audit_path.resolve()),
        },
        "counts": {
            "deleted_uris_in_manifest": len(deleted),
            "input_lines": figures_counts["input_lines"],
            "output_lines": figures_counts["output_lines"],
            "lines_dropped": figures_counts["lines_dropped"],
            "post_repair_deleted_ref_lines": post_deleted_refs,
        },
        "known_limitations": [
            "Overwrites canonical GCS textbook_lean_figures.jsonl in place.",
            "Cloud Run pods cache downloaded artifacts until cold restart.",
            "FAISS / docstore / web map / quality-flags sidecar unchanged.",
        ],
    }
    upload_audit_path.write_text(json.dumps(upload_audit, indent=2) + "\n", encoding="utf-8")

    upload_result = upload_gcs(figures_out, args.figures_gcs, args.project)
    upload_audit["upload_results"] = [upload_result]
    upload_audit_path.write_text(json.dumps(upload_audit, indent=2) + "\n", encoding="utf-8")

    ok = bool(upload_result["ok"])
    print(json.dumps({"upload_audit": str(upload_audit_path), "ok": ok}, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
