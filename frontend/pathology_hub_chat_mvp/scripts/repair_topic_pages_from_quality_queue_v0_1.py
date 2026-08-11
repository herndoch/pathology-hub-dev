#!/usr/bin/env python3
"""Rebuild topic pages listed in the quality repair queue (v0_1).

Reads topic_page_quality_repair_queue_v0_1.json and re-runs
prebuild_topic_pages_pilot_v0_1.py for the worst N tags. Defaults to the
public Chat MVP so wild-prebuild workers on :8000/:8001 are not starved.

After rebuild, deletes stale *.quality.json / *.review*.json sidecars for
those tags so the quality burn re-scores and re-reviews them.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
MVP_DIR = SCRIPT_DIR.parent
REPO_ROOT = MVP_DIR.parents[1]
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
QUEUE_PATH = OUTPUT_DIR / "topic_page_quality_repair_queue_v0_1.json"
PAGES_DIR = OUTPUT_DIR / "pages"
DEFAULT_AUDIT = OUTPUT_DIR / "topic_page_quality_repair_run_audit_v0_1.json"
AUDITS_COPY = REPO_ROOT / "audits/topic_page_quality_burn_v0_1/repair_run_audit_v0_1.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify_tag(tag: str) -> str:
    slug = tag.replace("::", "__")
    return re.sub(r"[^a-zA-Z0-9_]+", "_", slug)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queue", type=Path, default=QUEUE_PATH)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--base-url", default="https://chat.pathologynotebook.com")
    ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--timeout-s", type=int, default=360)
    ap.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--rereview", action="store_true")
    ap.add_argument("--rereview-parallel", type=int, default=8)
    args = ap.parse_args()

    if not args.queue.exists():
        raise SystemExit(f"Missing repair queue: {args.queue}")
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    items = list(queue.get("items") or [])[: args.limit]
    if not items:
        raise SystemExit("Repair queue empty")

    tags = [str(i["tag"]) for i in items if i.get("tag")]

    # Drop stale quality/review sidecars so post-repair burn is fresh
    for tag in tags:
        stem = _slugify_tag(tag)
        for suf in (".quality.json", ".review.json", ".review2.json"):
            p = PAGES_DIR / f"{stem}{suf}"
            if p.exists():
                p.unlink()

    prebuild = SCRIPT_DIR / "prebuild_topic_pages_pilot_v0_1.py"
    cmd = [
        sys.executable,
        str(prebuild),
        "--tags",
        *tags,
        "--parallel",
        str(args.parallel),
        "--timeout-s",
        str(args.timeout_s),
        "--base-url",
        args.base_url,
        "--audit-out",
        str(OUTPUT_DIR / "topic_page_quality_repair_prebuild_audit_v0_1.json"),
    ]
    print(">>", " ".join(cmd[:5]), f"... ({len(tags)} tags)", flush=True)
    rc = subprocess.call(cmd, cwd=str(MVP_DIR))

    score_rc = subprocess.call(
        [sys.executable, str(SCRIPT_DIR / "score_topic_page_quality_v0_1.py")],
        cwd=str(MVP_DIR),
    )

    rereview_counts: dict[str, Any] = {"skipped": True}
    if args.rereview and tags and rc == 0:
        rr = [
            sys.executable,
            str(SCRIPT_DIR / "pathologist_review_topic_pages_v0_1.py"),
            "--tags",
            *tags,
            "--parallel",
            str(args.rereview_parallel),
            "--audit-out",
            str(OUTPUT_DIR / "topic_page_quality_repair_rereview_audit_v0_1.json"),
        ]
        print(">> rereview", len(tags), "tags", flush=True)
        rr_rc = subprocess.call(rr, cwd=str(MVP_DIR))
        rereview_counts = {"rc": rr_rc, "n_tags": len(tags)}

    audit = {
        "schema_version": "topic_page_quality_repair_run_audit_v0_1",
        "generated_at": _utcnow(),
        "input_paths": [str(args.queue)],
        "output_paths": [str(args.audit_out), str(AUDITS_COPY)],
        "counts": {
            "queued_requested": len(items),
            "tags": len(tags),
            "prebuild_rc": rc,
            "score_rc": score_rc,
            "rereview": rereview_counts,
        },
        "tags": tags,
        "base_url": args.base_url,
        "known_limitations": [
            "Rebuilds use live retrieval; corpus drift may change cards.",
            "Does not guarantee LLM verdict flips to ready_for_human_review.",
            "Prefer --parallel 2 to avoid textbook search degradation under load.",
        ],
    }
    args.audit_out.parent.mkdir(parents=True, exist_ok=True)
    args.audit_out.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    AUDITS_COPY.parent.mkdir(parents=True, exist_ok=True)
    AUDITS_COPY.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(audit["counts"], indent=2))
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
