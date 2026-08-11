#!/usr/bin/env python3
"""Rebuild topic pages listed in the quality repair queue (v0_1).

Reads topic_page_quality_repair_queue_v0_1.json and re-calls Chat MVP
`POST /api/chat` (mode=topic_page) using each page sidecar's own
tag/query/category_context — so orphan tags not in the current Browse index
can still be repaired.

Defaults to the public Chat MVP so wild-prebuild workers on :8000/:8001 are
not starved. After rebuild, drops stale quality/review sidecars and optionally
re-reviews.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
MVP_DIR = SCRIPT_DIR.parent
REPO_ROOT = MVP_DIR.parents[1]
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
QUEUE_PATH = OUTPUT_DIR / "topic_page_quality_repair_queue_v0_1.json"
PAGES_DIR = OUTPUT_DIR / "pages"
DEFAULT_AUDIT = OUTPUT_DIR / "topic_page_quality_repair_run_audit_v0_1.json"
AUDITS_COPY = REPO_ROOT / "audits/topic_page_quality_burn_v0_1/repair_run_audit_v0_1.json"
PAGE_SCHEMA_VERSION = "topic_page_prebuild_v0_1"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify_tag(tag: str) -> str:
    slug = tag.replace("::", "__")
    return re.sub(r"[^a-zA-Z0-9_]+", "_", slug)


def _load(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _health_check(base_url: str) -> dict:
    resp = requests.get(f"{base_url}/api/health", timeout=15)
    resp.raise_for_status()
    return resp.json()


def _rebuild_one(base_url: str, page: dict[str, Any], timeout_s: int) -> dict[str, Any]:
    tag = str(page.get("tag") or "")
    label = str(page.get("label") or tag)
    query = str(page.get("query") or label)
    category_context = str(page.get("category_context") or "")
    payload = {
        "query": query,
        "mode": "topic_page",
        "category_context": category_context,
        "page_tag": tag,
        "include_figures": True,
        "max_figures": 8,
    }
    started = time.monotonic()
    resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=timeout_s)
    elapsed_s = round(time.monotonic() - started, 1)
    resp.raise_for_status()
    data = resp.json()
    debug = data.get("debug") or {}
    source_status = (data.get("evidence") or {}).get("source_status") or {}
    ok = bool(data.get("ok")) and bool(data.get("answer"))
    known_limitations = [
        "Prebuilt snapshot; live /api/chat may differ after corpus/backend changes.",
        "Figure list already passed Chat MVP suppress_render / quality filters at build time.",
        "Rebuilt via quality repair queue (direct /api/chat, index-independent).",
    ]
    if not data.get("ok"):
        known_limitations.append(f"Retrieval/synthesis error: {data.get('error') or data.get('answer_error')}")
    elif not data.get("answer"):
        known_limitations.append("No synthesized answer_markdown returned (synthesis_status: skipped or empty).")

    new_page = {
        "schema_version": PAGE_SCHEMA_VERSION,
        "tag": tag,
        "label": label,
        "provenance": page.get("provenance") or "unknown",
        "query": query,
        "category_context": category_context,
        "generated_at": _utcnow(),
        "ok": ok,
        "model": data.get("model"),
        "answer_markdown": data.get("answer"),
        "cards": data.get("cards") or [],
        "figures": data.get("figures") or [],
        "who_cross_mentions": data.get("who_cross_mentions") or [],
        "retrieval_debug_summary": {
            "cards_capped": debug.get("cards_capped"),
            "cards_cap_limit": debug.get("cards_cap_limit"),
            "cards_raw": debug.get("cards_raw"),
            "cards_deduped": debug.get("cards_deduped"),
            "query_variants": debug.get("query_variants") or [],
            "call_count": debug.get("call_count"),
            "source_status": source_status,
            "root_narrow_enabled": debug.get("root_narrow_enabled"),
            "page_root": debug.get("page_root"),
            "elapsed_s": elapsed_s,
            "repaired_from_quality_queue": True,
        },
        "known_limitations": known_limitations,
    }
    slug = _slugify_tag(tag)
    json_path = PAGES_DIR / f"{slug}.json"
    md_path = PAGES_DIR / f"{slug}.md"
    json_path.write_text(json.dumps(new_page, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_body = f"# {label}\n\n_tag: `{tag}` · provenance: {new_page['provenance']}_\n\n"
    md_body += new_page.get("answer_markdown") or "_(no synthesized answer — see JSON sidecar for details)_"
    md_path.write_text(md_body + "\n", encoding="utf-8")
    return {
        "tag": tag,
        "ok": ok,
        "cards": len(new_page["cards"]),
        "figures": len(new_page["figures"]),
        "elapsed_s": elapsed_s,
        "model": new_page.get("model"),
        "json_path": str(json_path),
    }


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

    health = _health_check(args.base_url)
    secrets = health.get("secrets") or {}
    if not (secrets.get("openai") or {}).get("present") or not (secrets.get("pathology_hub") or {}).get("present"):
        raise SystemExit(f"Missing secrets at {args.base_url}/api/health")

    jobs: list[dict[str, Any]] = []
    missing_pages = []
    for item in items:
        tag = str(item.get("tag") or "")
        page_path = Path(item["page_json"]) if item.get("page_json") else PAGES_DIR / f"{_slugify_tag(tag)}.json"
        if not page_path.is_absolute():
            cand = REPO_ROOT / page_path
            page_path = cand if cand.exists() else PAGES_DIR / f"{_slugify_tag(tag)}.json"
        page = _load(page_path)
        if not page:
            missing_pages.append(tag)
            continue
        jobs.append(page)
        # Drop stale sidecars
        stem = _slugify_tag(str(page.get("tag") or tag))
        for suf in (".quality.json", ".review.json", ".review2.json"):
            p = PAGES_DIR / f"{stem}{suf}"
            if p.exists():
                p.unlink()

    print(f"Repairing {len(jobs)} pages via {args.base_url} parallel={args.parallel}", flush=True)
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futs = {pool.submit(_rebuild_one, args.base_url, page, args.timeout_s): page for page in jobs}
        for fut in as_completed(futs):
            page = futs[fut]
            try:
                r = fut.result()
                results.append(r)
                print(
                    f"  {r['tag']} -> ok={r['ok']} cards={r['cards']} figs={r['figures']} {r['elapsed_s']}s",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                results.append({"tag": page.get("tag"), "ok": False, "error": str(exc)})
                print(f"  {page.get('tag')} -> FAILED: {exc}", flush=True)

    # Rescore everything cheaply
    score_rc = 0
    try:
        import subprocess

        score_rc = subprocess.call(
            [sys.executable, str(SCRIPT_DIR / "score_topic_page_quality_v0_1.py")],
            cwd=str(MVP_DIR),
        )
    except Exception:
        score_rc = 1

    rereview_counts: dict[str, Any] = {"skipped": True}
    ok_tags = [str(r["tag"]) for r in results if r.get("ok") and r.get("tag")]
    if args.rereview and ok_tags:
        import subprocess

        rr = [
            sys.executable,
            str(SCRIPT_DIR / "pathologist_review_topic_pages_v0_1.py"),
            "--tags",
            *ok_tags,
            "--parallel",
            str(args.rereview_parallel),
            "--audit-out",
            str(OUTPUT_DIR / "topic_page_quality_repair_rereview_audit_v0_1.json"),
        ]
        print(">> rereview", len(ok_tags), "tags", flush=True)
        rr_rc = subprocess.call(rr, cwd=str(MVP_DIR))
        rereview_counts = {"rc": rr_rc, "n_tags": len(ok_tags)}

    n_ok = sum(1 for r in results if r.get("ok"))
    audit = {
        "schema_version": "topic_page_quality_repair_run_audit_v0_1",
        "generated_at": _utcnow(),
        "input_paths": [str(args.queue)],
        "output_paths": [str(args.audit_out), str(AUDITS_COPY)],
        "counts": {
            "queued_requested": len(items),
            "jobs": len(jobs),
            "missing_page_json": len(missing_pages),
            "n_ok": n_ok,
            "n_failed": len(results) - n_ok,
            "score_rc": score_rc,
            "rereview": rereview_counts,
            "total_cards": sum(int(r.get("cards") or 0) for r in results),
            "total_figures": sum(int(r.get("figures") or 0) for r in results),
        },
        "missing_pages": missing_pages,
        "results": results,
        "base_url": args.base_url,
        "known_limitations": [
            "Index-independent repair using page sidecar query/category_context.",
            "Does not guarantee LLM verdict flips to ready_for_human_review.",
            "Prefer --parallel 2 to avoid textbook search degradation under load.",
        ],
    }
    args.audit_out.parent.mkdir(parents=True, exist_ok=True)
    args.audit_out.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    AUDITS_COPY.parent.mkdir(parents=True, exist_ok=True)
    AUDITS_COPY.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(audit["counts"], indent=2))
    raise SystemExit(0 if n_ok == len(jobs) and jobs else 1)


if __name__ == "__main__":
    main()
