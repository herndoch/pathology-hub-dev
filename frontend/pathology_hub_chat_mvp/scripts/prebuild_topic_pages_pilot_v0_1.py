#!/usr/bin/env python3
"""Prebuild topic-page sidecars for the pilot sample (v0_1).

For each leaf in `pilot_sample_v0_1.json`, calls the already-running local
Chat MVP's existing `POST /api/chat` (`mode: "topic_page"`) — the same code
path the live Browse UI uses (multi-query fan-out, figure quality filters,
WHO cross-mentions). Does NOT invent a second retrieval stack and does NOT
bypass `_apply_figure_quality_filters` / Phase 1 `suppress_render`.

Requires the local app to already be running (see
`frontend/pathology_hub_chat_mvp/scripts/run_local.sh`) with
`PATHOLOGY_HUB_API_KEY`/`HUB_API` and `OPENAI_API_KEY` resolvable (env or
Secret Manager) — verify via `GET /api/health` first.

Outputs (per leaf):
    outputs/chat_mvp_topic_prepop_v0_1/pages/<tag_slug>.json
    outputs/chat_mvp_topic_prepop_v0_1/pages/<tag_slug>.md

Plus a pilot-wide audit:
    outputs/chat_mvp_topic_prepop_v0_1/pilot_prebuild_audit_v0_1.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
INDEX_PATH = OUTPUT_DIR / "browse_tag_index_v0_1.json"
SAMPLE_PATH = OUTPUT_DIR / "pilot_sample_v0_1.json"
PAGES_DIR = OUTPUT_DIR / "pages"
AUDIT_PATH = OUTPUT_DIR / "pilot_prebuild_audit_v0_1.json"

PAGE_SCHEMA_VERSION = "topic_page_prebuild_v0_1"
AUDIT_SCHEMA_VERSION = "topic_prepop_pilot_audit_v0_1"

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def _slugify_tag(tag: str) -> str:
    slug = tag.replace("::", "__")
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", slug)
    return slug


def _root_and_subcategory_labels(index: dict, root_id: str, subcategory_id: str) -> tuple[str, str]:
    for root in index["roots"]:
        if root["id"] != root_id:
            continue
        for sub in root["subcategories"]:
            if sub["id"] == subcategory_id:
                return root["label"], sub["label"]
        return root["label"], subcategory_id
    return root_id, subcategory_id


def _health_check(base_url: str) -> dict:
    resp = requests.get(f"{base_url}/api/health", timeout=15)
    resp.raise_for_status()
    return resp.json()


def _prebuild_one(base_url: str, leaf: dict, category_context: str, timeout_s: int) -> dict:
    payload = {
        "query": leaf["query"],
        "mode": "topic_page",
        "category_context": category_context,
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
    retrieval_debug_summary = {
        "cards_capped": debug.get("cards_capped"),
        "cards_cap_limit": debug.get("cards_cap_limit"),
        "cards_raw": debug.get("cards_raw"),
        "cards_deduped": debug.get("cards_deduped"),
        "query_variants": debug.get("query_variants") or [],
        "call_count": debug.get("call_count"),
        "source_status": source_status,
        "elapsed_s": elapsed_s,
    }

    ok = bool(data.get("ok")) and bool(data.get("answer"))
    known_limitations = [
        "Prebuilt snapshot; live /api/chat may differ after corpus/backend changes.",
        "Figure list already passed Chat MVP suppress_render / quality filters at build time.",
    ]
    if not data.get("ok"):
        known_limitations.append(f"Retrieval/synthesis error: {data.get('error') or data.get('answer_error')}")
    elif not data.get("answer"):
        known_limitations.append("No synthesized answer_markdown returned (synthesis_status: skipped or empty).")

    page = {
        "schema_version": PAGE_SCHEMA_VERSION,
        "tag": leaf["tag"],
        "label": leaf["label"],
        "provenance": leaf["provenance"],
        "query": leaf["query"],
        "category_context": category_context,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "model": data.get("model"),
        "answer_markdown": data.get("answer"),
        "cards": data.get("cards") or [],
        "figures": data.get("figures") or [],
        "who_cross_mentions": data.get("who_cross_mentions") or [],
        "retrieval_debug_summary": retrieval_debug_summary,
        "known_limitations": known_limitations,
    }
    return page


def _write_page(page: dict) -> tuple[Path, Path]:
    slug = _slugify_tag(page["tag"])
    json_path = PAGES_DIR / f"{slug}.json"
    md_path = PAGES_DIR / f"{slug}.md"
    json_path.write_text(json.dumps(page, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_body = f"# {page['label']}\n\n_tag: `{page['tag']}` · provenance: {page['provenance']}_\n\n"
    md_body += page.get("answer_markdown") or "_(no synthesized answer — see JSON sidecar for details)_"
    md_path.write_text(md_body + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout-s", type=int, default=120)
    args = parser.parse_args()

    if not INDEX_PATH.exists() or not SAMPLE_PATH.exists():
        raise SystemExit(
            f"Missing {INDEX_PATH} or {SAMPLE_PATH}. Run build_browse_tag_index_v0_1.py and "
            "draw_pilot_sample_v0_1.py first."
        )

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))

    health = _health_check(args.base_url)
    secrets = health.get("secrets") or {}
    openai_present = bool((secrets.get("openai") or {}).get("present"))
    hub_present = bool((secrets.get("pathology_hub") or {}).get("present"))
    if not (openai_present and hub_present):
        raise SystemExit(
            f"Missing required secrets at {args.base_url}/api/health "
            f"(openai_present={openai_present}, pathology_hub_present={hub_present}). "
            "Stopping — will not fake synthesis."
        )

    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    n_ok = 0
    n_failed = 0
    total_cards = 0
    total_figures = 0

    for leaf in sample["leaves"]:
        root_label, sub_label = _root_and_subcategory_labels(index, leaf["root_id"], leaf["subcategory_id"])
        category_context = f"{root_label} > {sub_label}"
        print(f"Prebuilding: {leaf['tag']}  (category_context={category_context!r})")
        try:
            page = _prebuild_one(args.base_url, leaf, category_context, args.timeout_s)
            json_path, md_path = _write_page(page)
            total_cards += len(page["cards"])
            total_figures += len(page["figures"])
            if page["ok"]:
                n_ok += 1
            else:
                n_failed += 1
            results.append(
                {
                    "tag": leaf["tag"],
                    "ok": page["ok"],
                    "json_path": str(json_path.relative_to(REPO_ROOT)),
                    "md_path": str(md_path.relative_to(REPO_ROOT)),
                    "cards": len(page["cards"]),
                    "figures": len(page["figures"]),
                    "elapsed_s": page["retrieval_debug_summary"].get("elapsed_s"),
                }
            )
            print(f"  -> ok={page['ok']} cards={len(page['cards'])} figures={len(page['figures'])}")
        except Exception as exc:  # noqa: BLE001 — pilot script, record and continue
            n_failed += 1
            results.append({"tag": leaf["tag"], "ok": False, "error": str(exc)})
            print(f"  -> FAILED: {exc}")

    audit = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_paths": [
            str(INDEX_PATH.relative_to(REPO_ROOT)),
            str(SAMPLE_PATH.relative_to(REPO_ROOT)),
            f"api_base_url_host: {args.base_url}",
        ],
        "output_paths": [str(PAGES_DIR.relative_to(REPO_ROOT))],
        "counts": {
            "n_requested": len(sample["leaves"]),
            "n_ok": n_ok,
            "n_failed": n_failed,
            "total_cards": total_cards,
            "total_figures": total_figures,
        },
        "seed": sample.get("seed"),
        "pilot_tags": [leaf["tag"] for leaf in sample["leaves"]],
        "results": results,
        "known_limitations": [
            "Pilot-scale only (N from pilot_sample_v0_1.json); not a full-corpus prebuild.",
            "Prebuilt sidecars are a point-in-time cache; live corpus/backend changes can make them stale.",
        ],
        "figure_quality_note": (
            "Phase 1 suppress_render figure quality filters applied via the same "
            "_apply_figure_quality_filters() call used by the live /api/chat path; "
            "curriculum_figure_image_quality_flags_v0_1.jsonl and curriculum SQLite were not read or written."
        ),
    }
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {AUDIT_PATH}")
    print(json.dumps(audit["counts"], indent=2))


if __name__ == "__main__":
    main()
