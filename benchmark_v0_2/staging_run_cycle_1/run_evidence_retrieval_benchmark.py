#!/usr/bin/env python3
"""Run read-only live API evidence retrieval benchmark v0_1."""

from __future__ import annotations

import argparse
import os

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import json
import sys
import urllib.error
from pathlib import Path

from benchmark_lib import (
    DEFAULT_BASE_URL,
    DEFAULT_SOURCES,
    SCHEMA_VERSION,
    build_queries_for_entity,
    classify_failure,
    extract_figure_urls,
    flatten_hit,
    hit_matches_expected,
    load_entities_csv,
    load_expected_hits,
    request_json,
    utc_now,
    write_csv,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = Path(__file__).resolve().parent

SUMMARY_FIELDS = [
    "entity_id",
    "entity_name",
    "root",
    "query",
    "query_type",
    "source",
    "include_figures",
    "rank",
    "title",
    "score",
    "source_id",
    "doc_id",
    "page_id",
    "chunk_id",
    "text_excerpt",
    "figure_urls",
    "figure_url_count",
    "expected_hit_found",
    "failure_mode",
    "source_status",
    "retrieval_mode",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument(
        "--api-key",
        default=os.environ.get("PATHOLOGY_HUB_API_KEY") or os.environ.get("API_KEY", ""),
        help="Read from environment only; never written to output files.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--entities-csv", type=Path, default=DEFAULT_OUT / "benchmark_entities_v0_1.csv")
    parser.add_argument("--expected-json", type=Path, default=DEFAULT_OUT / "benchmark_expected_hits_v0_1.json")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--max-figures", type=int, default=10)
    parser.add_argument("--skip-api", action="store_true", help="Record api_not_run_missing_key without calling API.")
    return parser.parse_args()


def result_group_for_source(source: str) -> str:
    return {
        "who": "who_results",
        "pathout": "pathout_results",
        "textbooks": "textbook_results",
        "journals": "journal_results",
        "lectures": "lecture_results",
        "videos": "video_results",
        "curriculum": "curriculum_results",
    }.get(source, f"{source}_results")


def run_benchmark(args: argparse.Namespace) -> dict:
    entities = load_entities_csv(args.entities_csv)
    expected_doc = load_expected_hits(args.expected_json)
    expected_by_id = expected_doc.get("entities") or {}

    api_key = (args.api_key or "").strip()
    api_enabled = bool(api_key) and not args.skip_api

    health: dict = {}
    health_status = "not_run"
    journal_supported = False
    raw_runs: list[dict] = []
    summary_rows: list[dict] = []
    figure_rows: list[dict] = []

    if api_enabled:
        try:
            status, health = request_json(args.base_url, api_key, "GET", "/health")
            health_status = "ok" if status == 200 else f"http_{status}"
            ss = health.get("source_status") or {}
            journal_supported = ss.get("journals") not in {None, "not_requested"} or True
        except urllib.error.HTTPError as exc:
            health_status = f"http_error_{exc.code}"
            health = {"error": exc.read().decode("utf-8", errors="replace")[:1000]}
        except Exception as exc:
            health_status = f"error_{type(exc).__name__}"
            health = {"error": repr(exc)}
    else:
        health_status = "api_not_run_missing_key"

    sources_to_test = list(DEFAULT_SOURCES)
    if not journal_supported and api_enabled:
        sources_to_test = [s for s in sources_to_test if s != "journals"]

    for entity in entities:
        entity_id = entity["entity_id"]
        expected = expected_by_id.get(entity_id, {})
        queries = build_queries_for_entity(entity)

        for qspec in queries:
            for source in sources_to_test:
                for include_figures in (False, True):
                    payload = {
                        "query": qspec["query"],
                        "sources": [source],
                        "max_results": args.max_results,
                        "compact": True,
                        "excerpt_char_limit": 900,
                        "include_figures": include_figures,
                        "max_figures": args.max_figures if include_figures else 0,
                    }
                    response: dict = {}
                    source_status = "not_run"
                    error = None

                    if api_enabled:
                        try:
                            _, response = request_json(
                                args.base_url, api_key, "POST", "/evidence/search", payload
                            )
                            source_status = (response.get("source_status") or {}).get(source, "unknown")
                        except Exception as exc:
                            error = repr(exc)
                            source_status = "error"
                            response = {"error": error, "source_status": {source: "error"}}
                    else:
                        source_status = "not_run"

                    group = result_group_for_source(source)
                    hits = [flatten_hit(h, source, i) for i, h in enumerate(response.get(group) or [], start=1)]
                    figure_urls = extract_figure_urls(response) if include_figures else []
                    expected_found = any(hit_matches_expected(h, expected, entity) for h in hits)
                    failure_mode = classify_failure(
                        source=source,
                        include_figures=include_figures,
                        source_status=source_status if api_enabled else "not_run",
                        hits=hits,
                        expected=expected,
                        entity=entity,
                        local_corpus_present=True,
                        api_ran=api_enabled,
                        figure_urls=figure_urls,
                    )
                    if expected_found:
                        failure_mode = "expected_hit_found"

                    raw_runs.append(
                        {
                            "entity_id": entity_id,
                            "query": qspec["query"],
                            "query_type": qspec["query_type"],
                            "source": source,
                            "include_figures": include_figures,
                            "payload": payload,
                            "source_status": source_status,
                            "response": response,
                            "error": error,
                        }
                    )

                    top = hits[0] if hits else {}
                    summary_rows.append(
                        {
                            "entity_id": entity_id,
                            "entity_name": entity["entity_name"],
                            "root": entity["root"],
                            "query": qspec["query"],
                            "query_type": qspec["query_type"],
                            "source": source,
                            "include_figures": include_figures,
                            "rank": top.get("rank"),
                            "title": top.get("title"),
                            "score": top.get("score"),
                            "source_id": top.get("source_id"),
                            "doc_id": top.get("source_id"),
                            "page_id": top.get("page_id"),
                            "chunk_id": top.get("chunk_id"),
                            "text_excerpt": top.get("excerpt"),
                            "figure_urls": "|".join(figure_urls[:10]),
                            "figure_url_count": len(figure_urls),
                            "expected_hit_found": expected_found,
                            "failure_mode": failure_mode,
                            "source_status": source_status,
                            "retrieval_mode": top.get("retrieval_mode"),
                        }
                    )
                    for rank, url in enumerate(figure_urls, start=1):
                        figure_rows.append(
                            {
                                "entity_id": entity_id,
                                "entity_name": entity["entity_name"],
                                "source": source,
                                "query": qspec["query"],
                                "include_figures": include_figures,
                                "figure_rank": rank,
                                "figure_url": url,
                            }
                        )

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_doc = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "base_url": args.base_url,
        "api_ran": api_enabled,
        "health_status": health_status,
        "health": health,
        "entity_count": len(entities),
        "run_count": len(raw_runs),
        "limitations": [
            "Read-only API benchmark; no deploy, no GCS upload, no promotion.",
            "Production API v1.5.8 may not expose curriculum source; curriculum checks use local v0_4 corpus separately.",
            "API key is never stored in output artifacts.",
        ],
        "runs": raw_runs,
    }
    (out_dir / "benchmark_results_raw.json").write_text(
        json.dumps(raw_doc, indent=2), encoding="utf-8"
    )
    write_csv(out_dir / "benchmark_results_summary.csv", summary_rows, SUMMARY_FIELDS)
    write_csv(
        out_dir / "benchmark_figure_url_inventory.csv",
        figure_rows,
        ["entity_id", "entity_name", "source", "query", "include_figures", "figure_rank", "figure_url"],
    )
    meta = {
        "api_ran": api_enabled,
        "health_status": health_status,
        "summary_rows": len(summary_rows),
        "figure_rows": len(figure_rows),
    }
    print(json.dumps(meta, indent=2))
    return meta


def main() -> int:
    args = parse_args()
    try:
        run_benchmark(args)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
