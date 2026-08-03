#!/usr/bin/env python3
"""Upload local topic_page prebuild sidecars to GCS (v0_1).

Backfills gcs_topic_cache's read-through bucket/prefix for pages that were
built before the live write-through (gcs_topic_cache.write_page_async, wired
into app.py's /api/chat and /api/chat/stream) was deployed, or for a batch
run against a server instance without GCS write-through. Ordinary live
write-through already keeps this bucket current for pages built after that
change shipped — this script exists for backfill / bulk (re)sync only.

Reads:
    outputs/chat_mvp_topic_prepop_v0_1/pages/<slug>.json   (only ok=true, has answer_markdown)

Writes:
    gs://<bucket>/<prefix>/<slug>.json   (one object per page)
    outputs/chat_mvp_topic_prepop_v0_1/<audit_out>          (upload audit JSON)

Usage:
    # Upload every ok=true page currently on disk (default; matches
    # gcs_topic_cache.GCS_BUCKET / GCS_PREFIX defaults).
    python3 scripts/upload_topic_prebuilds_to_gcs_v0_1.py

    # Scope to one browse root (matches the leaf tag's ROOT:: prefix or the
    # ABPathSpec::<root>:: prefix), e.g. just BST:
    python3 scripts/upload_topic_prebuilds_to_gcs_v0_1.py --root bst

    # Explicit sample file (same shape as prebuild_topic_pages_pilot_v0_1.py --sample)
    python3 scripts/upload_topic_prebuilds_to_gcs_v0_1.py --sample outputs/chat_mvp_topic_prepop_v0_1/bst_sample_v0_1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
PAGES_DIR = OUTPUT_DIR / "pages"

sys.path.insert(0, str(APP_DIR))
import gcs_topic_cache  # noqa: E402


def _root_of_tag(tag: str) -> str:
    parts = tag.split("::")
    if parts and parts[0] == "ABPathSpec" and len(parts) > 1:
        return parts[1].lower()
    return (parts[0] if parts else "").lower()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=None, help="Only upload pages whose tag's root matches this (case-insensitive), e.g. bst")
    parser.add_argument("--sample", type=Path, default=None, help="Restrict to tags listed in this sample JSON (leaves[].tag)")
    parser.add_argument(
        "--audit-out",
        type=Path,
        default=OUTPUT_DIR / "topic_prebuild_gcs_upload_audit_v0_1.json",
    )
    args = parser.parse_args()

    if not gcs_topic_cache.is_configured():
        raise SystemExit(
            "gcs_topic_cache reports not configured (missing google-cloud-storage, "
            "credentials, or TOPIC_PREBUILD_GCS_ENABLED=0). Aborting — will not "
            "silently skip the upload."
        )

    allowed_tags = None
    input_paths = ["gcs_topic_cache.py (bucket/prefix config)"]
    if args.sample:
        sample = json.loads(args.sample.read_text(encoding="utf-8"))
        allowed_tags = {leaf["tag"] for leaf in sample["leaves"]}
        input_paths.append(str(args.sample.relative_to(REPO_ROOT)))

    n_scanned = 0
    n_uploaded = 0
    n_skipped_not_ok = 0
    n_skipped_root_mismatch = 0
    n_skipped_not_in_sample = 0
    n_failed = 0
    uploaded_tags: list[str] = []
    failed_tags: list[str] = []

    for json_path in sorted(PAGES_DIR.glob("*.json")):
        n_scanned += 1
        try:
            page = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            n_failed += 1
            failed_tags.append(json_path.name)
            continue
        tag = page.get("tag") or ""
        if not page.get("ok") or not page.get("answer_markdown"):
            n_skipped_not_ok += 1
            continue
        if allowed_tags is not None and tag not in allowed_tags:
            n_skipped_not_in_sample += 1
            continue
        if args.root and _root_of_tag(tag) != args.root.lower():
            n_skipped_root_mismatch += 1
            continue
        slug = json_path.stem
        ok = gcs_topic_cache.write_page_sync(slug, page)
        if ok:
            n_uploaded += 1
            uploaded_tags.append(tag)
        else:
            n_failed += 1
            failed_tags.append(tag)

    audit = {
        "schema_version": "topic_prebuild_gcs_upload_audit_v0_1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_paths": input_paths + [str(PAGES_DIR.relative_to(REPO_ROOT))],
        "output_paths": [
            f"gs://{gcs_topic_cache.GCS_BUCKET}/{gcs_topic_cache.GCS_PREFIX}/",
            str(args.audit_out.relative_to(REPO_ROOT)),
        ],
        "filters": {"root": args.root, "sample": str(args.sample) if args.sample else None},
        "counts": {
            "n_scanned_local_pages": n_scanned,
            "n_uploaded": n_uploaded,
            "n_skipped_not_ok_or_no_answer": n_skipped_not_ok,
            "n_skipped_root_mismatch": n_skipped_root_mismatch,
            "n_skipped_not_in_sample": n_skipped_not_in_sample,
            "n_failed": n_failed,
        },
        "uploaded_tags": uploaded_tags,
        "failed_tags": failed_tags,
        "known_limitations": [
            "One-shot backfill/sync; does not delete GCS objects whose local sidecar was removed.",
            "Ordinary live write-through (gcs_topic_cache.write_page_async in app.py) keeps this "
            "bucket current for pages built after that change shipped — this script is for "
            "backfill/bulk (re)sync of pages built before/outside that path only.",
        ],
    }
    args.audit_out.parent.mkdir(parents=True, exist_ok=True)
    args.audit_out.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(audit["counts"], indent=2))
    print(f"Wrote {args.audit_out}")


if __name__ == "__main__":
    main()
