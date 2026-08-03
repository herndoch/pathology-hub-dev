#!/usr/bin/env python3
"""Prebuild topic-page sidecars for pilot or arbitrary leaf sets (v0_1).

For each leaf, calls the already-running local Chat MVP's existing
`POST /api/chat` (`mode: "topic_page"`) — the same code path the live Browse
UI uses (multi-query fan-out, figure quality filters, WHO cross-mentions).

Requires the local app to already be running (see
`frontend/pathology_hub_chat_mvp/scripts/run_local.sh`) with
`PATHOLOGY_HUB_API_KEY`/`HUB_API` and `OPENAI_API_KEY` resolvable (env or
Secret Manager) — verify via `GET /api/health` first.

Outputs (per leaf):
    outputs/chat_mvp_topic_prepop_v0_1/pages/<tag_slug>.json
    outputs/chat_mvp_topic_prepop_v0_1/pages/<tag_slug>.md

Plus a batch audit (default path overwritable via --audit-out):
    outputs/chat_mvp_topic_prepop_v0_1/pilot_prebuild_audit_v0_1.json

Examples:
    # Original pilot sample
    python3 scripts/prebuild_topic_pages_pilot_v0_1.py

    # High-traffic post-rebuild batch (draw sample first)
    python3 scripts/draw_high_traffic_sample_v0_1.py
    python3 scripts/prebuild_topic_pages_pilot_v0_1.py \\
        --sample outputs/chat_mvp_topic_prepop_v0_1/high_traffic_sample_v0_1.json \\
        --parallel 2 \\
        --audit-out outputs/chat_mvp_topic_prepop_v0_1/high_traffic_prebuild_audit_v0_1.json

    # Explicit tags
    python3 scripts/prebuild_topic_pages_pilot_v0_1.py \\
        --tags "HN::Salivary_Gland::Benign_Tumor::Pleomorphic_Adenoma"
"""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
INDEX_PATH = OUTPUT_DIR / "browse_tag_index_v0_1.json"
DEFAULT_SAMPLE_PATH = OUTPUT_DIR / "pilot_sample_v0_1.json"
PAGES_DIR = OUTPUT_DIR / "pages"
DEFAULT_AUDIT_PATH = OUTPUT_DIR / "pilot_prebuild_audit_v0_1.json"

PAGE_SCHEMA_VERSION = "topic_page_prebuild_v0_1"
AUDIT_SCHEMA_VERSION = "topic_prepop_batch_audit_v0_2"

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def _slugify_tag(tag: str) -> str:
    slug = tag.replace("::", "__")
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", slug)
    return slug


def _flatten_index(index: dict) -> dict[str, dict]:
    by_tag: dict[str, dict] = {}
    for root in index["roots"]:
        for sub in root["subcategories"]:
            for leaf in sub["leaves"]:
                by_tag[leaf["tag"]] = {
                    "tag": leaf["tag"],
                    "label": leaf["label"],
                    "provenance": leaf.get("provenance", "unknown"),
                    "query": leaf["query"],
                    "root_id": root["id"],
                    "subcategory_id": sub["id"],
                }
    return by_tag


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
        "page_tag": leaf["tag"],
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
        "root_narrow_enabled": debug.get("root_narrow_enabled"),
        "page_root": debug.get("page_root"),
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


def _resolve_leaves(
    index: dict,
    sample_path: Optional[Path],
    tags: Optional[list[str]],
) -> tuple[list[dict], list[str]]:
    input_paths: list[str] = [str(INDEX_PATH.relative_to(REPO_ROOT))]

    if tags:
        by_tag = _flatten_index(index)
        leaves: list[dict] = []
        missing: list[str] = []
        for tag in tags:
            if tag in by_tag:
                leaves.append(by_tag[tag])
            else:
                missing.append(tag)
        if missing:
            raise SystemExit(f"Tags not found in browse index: {missing}")
        input_paths.append(f"cli_tags: {len(tags)}")
        return leaves, input_paths

    path = sample_path or DEFAULT_SAMPLE_PATH
    if not path.exists():
        raise SystemExit(f"Missing sample file: {path}")
    sample = json.loads(path.read_text(encoding="utf-8"))
    input_paths.append(str(path.relative_to(REPO_ROOT)))
    return sample["leaves"], input_paths


def _process_leaf(
    base_url: str,
    index: dict,
    leaf: dict,
    timeout_s: int,
) -> dict:
    root_label, sub_label = _root_and_subcategory_labels(index, leaf["root_id"], leaf["subcategory_id"])
    category_context = f"{root_label} > {sub_label}"
    page = _prebuild_one(base_url, leaf, category_context, timeout_s)
    json_path, md_path = _write_page(page)
    return {
        "tag": leaf["tag"],
        "ok": page["ok"],
        "json_path": str(json_path.relative_to(REPO_ROOT)),
        "md_path": str(md_path.relative_to(REPO_ROOT)),
        "cards": len(page["cards"]),
        "figures": len(page["figures"]),
        "elapsed_s": page["retrieval_debug_summary"].get("elapsed_s"),
        "model": page.get("model"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout-s", type=int, default=180)
    parser.add_argument(
        "--sample",
        type=Path,
        default=None,
        help=f"Sample JSON path (default: {DEFAULT_SAMPLE_PATH.name})",
    )
    parser.add_argument(
        "--tags",
        nargs="+",
        default=None,
        help="Explicit leaf tags (overrides --sample)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Concurrent /api/chat workers (default 1)",
    )
    parser.add_argument(
        "--audit-out",
        type=Path,
        default=DEFAULT_AUDIT_PATH,
        help="Audit JSON output path",
    )
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        raise SystemExit(f"Missing {INDEX_PATH}. Run build_browse_tag_index_v0_1.py first.")

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    leaves, input_paths = _resolve_leaves(index, args.sample, args.tags)

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
    args.audit_out.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    n_ok = 0
    n_failed = 0
    total_cards = 0
    total_figures = 0
    parallel = max(1, args.parallel)

    print(f"Prebuilding {len(leaves)} leaves (parallel={parallel}) model={health.get('openai_model')}")

    if parallel == 1:
        for leaf in leaves:
            print(f"Prebuilding: {leaf['tag']}")
            try:
                result = _process_leaf(args.base_url, index, leaf, args.timeout_s)
                total_cards += result["cards"]
                total_figures += result["figures"]
                if result["ok"]:
                    n_ok += 1
                else:
                    n_failed += 1
                results.append(result)
                print(f"  -> ok={result['ok']} cards={result['cards']} figures={result['figures']}")
            except Exception as exc:  # noqa: BLE001
                n_failed += 1
                results.append({"tag": leaf["tag"], "ok": False, "error": str(exc)})
                print(f"  -> FAILED: {exc}")
    else:
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = {
                pool.submit(_process_leaf, args.base_url, index, leaf, args.timeout_s): leaf
                for leaf in leaves
            }
            for fut in as_completed(futures):
                leaf = futures[fut]
                try:
                    result = fut.result()
                    total_cards += result["cards"]
                    total_figures += result["figures"]
                    if result["ok"]:
                        n_ok += 1
                    else:
                        n_failed += 1
                    results.append(result)
                    print(f"  {leaf['tag']} -> ok={result['ok']} cards={result['cards']} elapsed={result.get('elapsed_s')}s")
                except Exception as exc:  # noqa: BLE001
                    n_failed += 1
                    results.append({"tag": leaf["tag"], "ok": False, "error": str(exc)})
                    print(f"  {leaf['tag']} -> FAILED: {exc}")

    audit = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_paths": input_paths + [f"api_base_url: {args.base_url}"],
        "output_paths": [str(PAGES_DIR.relative_to(REPO_ROOT)), str(args.audit_out.relative_to(REPO_ROOT))],
        "counts": {
            "n_requested": len(leaves),
            "n_ok": n_ok,
            "n_failed": n_failed,
            "total_cards": total_cards,
            "total_figures": total_figures,
        },
        "parallel_workers": parallel,
        "openai_model_at_build": health.get("openai_model"),
        "topic_page_root_narrow_at_build": health.get("topic_page_root_narrow"),
        "tags": [leaf["tag"] for leaf in leaves],
        "results": results,
        "known_limitations": [
            "Prebuilt sidecars are a point-in-time cache; live corpus/backend changes can make them stale.",
            "Parallel workers increase load on local app + OpenAI; tune --parallel conservatively.",
            "--parallel 3+ measurably degrades the backend's textbook/pathout hybrid search under "
            "load (source_status reports 'not_requested' though WHO/literature still succeed) — "
            "see README.md 'Textbook retrieval degrades under concurrent prebuild load'. Prefer "
            "--parallel 2 for large batches and check per-source source_status, not just n_ok.",
        ],
        "figure_quality_note": (
            "Phase 1 suppress_render figure quality filters applied via the same "
            "_apply_figure_quality_filters() call used by the live /api/chat path; "
            "curriculum_figure_image_quality_flags_v0_1.jsonl and curriculum SQLite were not read or written."
        ),
    }
    args.audit_out.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {args.audit_out}")
    print(json.dumps(audit["counts"], indent=2))


if __name__ == "__main__":
    main()
