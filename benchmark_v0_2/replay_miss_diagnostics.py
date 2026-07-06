#!/usr/bin/env python3
"""Offline replay of the cached v0_2 client-side benchmark raw results to classify
the known 29 misses vs the v0_1 baseline expected-hit set. No live API calls.

Reuses the scoring logic (`classify_failure`, `hit_matches_expected`) from
06_audits/evidence_retrieval/benchmark_v0_1/benchmark_lib.py so classification
is consistent with how the original 979/1008 and 29-miss numbers were computed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_V0_1_DIR = ROOT / "06_audits" / "evidence_retrieval" / "benchmark_v0_1"
RAW_V0_2_PATH = ROOT / "06_audits" / "evidence_retrieval_writable" / "benchmark_v0_2" / "benchmark_v0_2_results_raw.json"

sys.path.insert(0, str(BENCH_V0_1_DIR))
from benchmark_lib import (  # noqa: E402
    classify_failure,
    flatten_hit,
    hit_matches_expected,
    load_entities_csv,
    load_expected_hits,
)

RESULT_GROUP_FOR_SOURCE = {
    "who": "who_results",
    "pathout": "pathout_results",
    "textbooks": "textbook_results",
    "journals": "journal_results",
    "lectures": "lecture_results",
    "videos": "video_results",
    "curriculum": "curriculum_results",
}


def main() -> int:
    entities = {e["entity_id"]: e for e in load_entities_csv(BENCH_V0_1_DIR / "benchmark_entities_v0_1.csv")}
    expected_doc = load_expected_hits(BENCH_V0_1_DIR / "benchmark_expected_hits_v0_1.json")
    expected_by_id = expected_doc.get("entities") or {}

    raw = json.loads(RAW_V0_2_PATH.read_text(encoding="utf-8"))
    runs = raw.get("runs") or []

    diagnostics = []
    total = 0
    misses = 0
    for run in runs:
        total += 1
        entity_id = run["entity_id"]
        entity = entities.get(entity_id)
        if not entity:
            continue
        expected = expected_by_id.get(entity_id, {})
        source = run["source"]
        include_figures = run["include_figures"]
        response = run.get("response") or {}
        source_status = (response.get("source_status") or {}).get(source, "unknown")
        group = RESULT_GROUP_FOR_SOURCE.get(source, f"{source}_results")
        hits = [flatten_hit(h, source, i) for i, h in enumerate(response.get(group) or [], start=1)]
        figure_urls = []
        for fig in response.get("figures") or []:
            url = fig.get("image_url") or fig.get("figure_url") or fig.get("url")
            if url:
                figure_urls.append(url)

        expected_found = any(hit_matches_expected(h, expected, entity) for h in hits)
        failure_mode = classify_failure(
            source=source,
            include_figures=include_figures,
            source_status=source_status,
            hits=hits,
            expected=expected,
            entity=entity,
            local_corpus_present=True,
            api_ran=True,
            figure_urls=figure_urls,
        )
        if expected_found:
            failure_mode = "expected_hit_found"
        else:
            misses += 1
            diagnostics.append(
                {
                    "entity_id": entity_id,
                    "entity_name": entity["entity_name"],
                    "root": entity["root"],
                    "query": run["query"],
                    "query_type": run["query_type"],
                    "source": source,
                    "include_figures": include_figures,
                    "source_status": source_status,
                    "failure_mode": failure_mode,
                    "top_hit_titles": [h.get("title") for h in hits[:3]],
                }
            )

    out_path = ROOT / "benchmark_v0_2" / "miss_diagnostics_20260705.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for row in diagnostics:
            fh.write(json.dumps(row) + "\n")

    print(json.dumps({"total_runs": total, "misses": misses, "output": str(out_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
