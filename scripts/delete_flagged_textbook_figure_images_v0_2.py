#!/usr/bin/env python3
"""Delete GCS textbook figure image objects flagged by the v0_1 dimension audit.

Reads the already-produced `flagged_figure_images_full_v0_1.csv`, dedupes image
URLs, converts them to `gs://` URIs, and deletes the objects when `--execute` is
set. Default mode is dry-run (manifest + counts only).

Safety:
- Only deletes objects under the approved prefix:
  `gs://pathology_hub/01_staged/textbooks/assets/figure_images/`
- Never prints secret values.
- Writes audit JSON before and after execution.

Does not modify normalized curriculum records or SQLite indexes. Pair with
`build_curriculum_image_locator_strip_repairs_v0_2.py` to clear local locators.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCHEMA_VERSION = "textbook_figure_image_gcs_delete.v0_2"
DEFAULT_FLAGGED_CSV = (
    "06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/"
    "flagged_figure_images_full_v0_1.csv"
)
ALLOWED_GCS_PREFIX = "gs://pathology_hub/01_staged/textbooks/assets/figure_images/"


def https_to_gs(url: str) -> str | None:
    url = (url or "").strip()
    if url.startswith("gs://"):
        return url
    if url.startswith("https://storage.googleapis.com/"):
        return "gs://" + url[len("https://storage.googleapis.com/") :]
    if url.startswith("http://storage.googleapis.com/"):
        return "gs://" + url[len("http://storage.googleapis.com/") :]
    return None


def load_delete_targets(csv_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    gs_uris: list[str] = []
    seen: set[str] = set()
    rejected: Counter[str] = Counter()

    with csv_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            gs_uri = https_to_gs(row.get("url") or "")
            if not gs_uri:
                rejected["unparseable_url"] += 1
                continue
            if not gs_uri.startswith(ALLOWED_GCS_PREFIX):
                rejected["outside_allowed_prefix"] += 1
                continue
            rows.append(row)
            if gs_uri not in seen:
                seen.add(gs_uri)
                gs_uris.append(gs_uri)

    return rows, gs_uris


def write_manifest(path: Path, gs_uris: list[str]) -> None:
    path.write_text("\n".join(gs_uris) + ("\n" if gs_uris else ""), encoding="utf-8")


def run_gsutil_delete(manifest_path: Path, project: str | None) -> dict[str, Any]:
    cmd = ["gsutil", "-m"]
    if project:
        cmd.extend(["-u", project])
    cmd.extend(["rm", "-I"])
    proc = subprocess.run(
        cmd,
        input=manifest_path.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
        "ok": proc.returncode == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flagged-csv", default=DEFAULT_FLAGGED_CSV)
    parser.add_argument(
        "--audit-dir",
        default="06_audits/curriculum_provenance_links/v0_1/figure_image_gcs_delete_v0_2",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete GCS objects. Default is dry-run only.",
    )
    parser.add_argument("--project", default="pathology-annotation-project")
    parser.add_argument("--run-tag", default=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    args = parser.parse_args()

    csv_path = Path(args.flagged_csv)
    if not csv_path.exists():
        print(f"Missing flagged CSV: {csv_path}", file=sys.stderr)
        return 1

    flagged_rows, gs_uris = load_delete_targets(csv_path)
    audit_dir = Path(args.audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = audit_dir / f"delete_manifest_{args.run_tag}.txt"

    write_manifest(manifest_path, gs_uris)

    audit: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_paths": {"flagged_csv": str(csv_path.resolve())},
        "output_paths": {"manifest": str(manifest_path.resolve())},
        "counts": {
            "flagged_csv_rows": len(flagged_rows),
            "unique_gs_uris": len(gs_uris),
            "execute_requested": int(args.execute),
        },
        "allowed_gcs_prefix": ALLOWED_GCS_PREFIX,
        "known_limitations": [
            "Deletes only objects listed in the v0_1 flagged CSV and under the allowed prefix.",
            "Does not strip curriculum locators; run build_curriculum_image_locator_strip_repairs_v0_2.py separately.",
            "Shared URLs are deleted once even when multiple record_ids referenced them.",
        ],
    }

    if not args.execute:
        audit["mode"] = "dry_run"
        audit_path = audit_dir / f"delete_audit_dry_run_{args.run_tag}.json"
        audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"mode": "dry_run", "audit_path": str(audit_path), "unique_gs_uris": len(gs_uris)}, indent=2))
        return 0

    delete_result = run_gsutil_delete(manifest_path, args.project)
    audit["mode"] = "execute"
    audit["delete_result"] = delete_result
    audit_path = audit_dir / f"delete_audit_execute_{args.run_tag}.json"
    audit["output_paths"]["audit_json"] = str(audit_path.resolve())
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": "execute", "audit_path": str(audit_path), "ok": delete_result["ok"]}, indent=2))
    return 0 if delete_result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
