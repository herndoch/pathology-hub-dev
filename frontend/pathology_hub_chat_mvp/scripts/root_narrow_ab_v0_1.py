#!/usr/bin/env python3
"""A/B root-narrowed topic-page retrieval (B8) on fixed entities.

Compares card/figure counts with TOPIC_PAGE_ROOT_NARROW off vs on by calling
the same `_run_topic_page_retrieval` path the live app uses (no server restart).

Writes audit JSON to outputs/chat_mvp_topic_prepop_v0_1/root_narrow_ab_v0_1.json

Usage:
    python3 scripts/root_narrow_ab_v0_1.py
    python3 scripts/root_narrow_ab_v0_1.py --entities hn_pleomorphic eye_melanoma
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

MVP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = MVP_DIR.parents[1]
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
AUDIT_PATH = OUTPUT_DIR / "root_narrow_ab_v0_1.json"

if str(MVP_DIR) not in sys.path:
    sys.path.insert(0, str(MVP_DIR))

import app as app_module  # noqa: E402
from app import TOPIC_PAGE_SOURCES, ChatRequest, _run_topic_page_retrieval  # noqa: E402

ENTITIES = {
    "hn_pleomorphic": {
        "tag": "HN::Salivary_Gland::Benign_Tumor::Pleomorphic_Adenoma",
        "label": "Pleomorphic Adenoma",
        "query": "pleomorphic adenoma salivary gland",
        "category_context": "Head & Neck > Salivary Gland",
    },
    "eye_melanoma": {
        "tag": "Eye_Orbit::Uveal_Tract::Ciliary_Body_Choroid::Malignant_Melanocytic::Choroidal_Ciliary_Body_Melanoma",
        "label": "Choroidal Ciliary Body Melanoma",
        "query": "choroidal ciliary body melanoma uveal",
        "category_context": "Eye & Orbit > Uveal Tract",
    },
    "middle_ear_scc": {
        "tag": "HN::Ear::Middle_Ear_Squamous_Cell_Carcinoma",
        "label": "Middle Ear Squamous Cell Carcinoma",
        "query": "middle ear squamous cell carcinoma",
        "category_context": "Head & Neck > Ear",
    },
}


def _source_counts(cards: list[dict]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for card in cards:
        c[str(card.get("source") or "unknown")] += 1
    return dict(sorted(c.items()))


def _run_one(entity: dict, narrow: bool) -> dict:
    app_module.TOPIC_PAGE_ROOT_NARROW = narrow
    req = ChatRequest(
        query=entity["query"],
        mode="topic_page",
        sources=TOPIC_PAGE_SOURCES,
        category_context=entity["category_context"],
        page_tag=entity["tag"],
        max_results=5,
        include_figures=True,
        max_figures=8,
    )
    started = time.monotonic()
    _outcomes, merged, cards, meta, _mentions = _run_topic_page_retrieval(req)
    elapsed_s = round(time.monotonic() - started, 1)
    figures = (merged.get("figures") or []) if isinstance(merged, dict) else []
    return {
        "root_narrow": narrow,
        "elapsed_s": elapsed_s,
        "cards": len(cards),
        "figures": len(figures),
        "cards_by_source": _source_counts(cards),
        "page_root": meta.get("page_root"),
        "cards_before_root_filter": meta.get("cards_before_root_filter"),
        "cards_after_root_filter": meta.get("cards_after_root_filter"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--entities",
        nargs="+",
        choices=sorted(ENTITIES.keys()),
        default=["hn_pleomorphic", "eye_melanoma"],
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    for key in args.entities:
        entity = ENTITIES[key]
        print(f"\n{entity['label']} ({entity['tag']})")
        off = _run_one(entity, narrow=False)
        on = _run_one(entity, narrow=True)
        delta_cards = on["cards"] - off["cards"]
        delta_figs = on["figures"] - off["figures"]
        print(
            f"  narrow OFF: {off['cards']} cards, {off['figures']} figs, {off['elapsed_s']}s "
            f"{off['cards_by_source']}"
        )
        print(
            f"  narrow ON:  {on['cards']} cards, {on['figures']} figs, {on['elapsed_s']}s "
            f"{on['cards_by_source']} (Δ cards {delta_cards:+d}, figs {delta_figs:+d})"
        )
        starvation = on["cards"] < 12
        if starvation:
            print("  WARNING: narrow ON may be starving this root (<12 cards after cap)")
        results.append(
            {
                "entity_key": key,
                "tag": entity["tag"],
                "label": entity["label"],
                "off": off,
                "on": on,
                "delta_cards": delta_cards,
                "delta_figures": delta_figs,
                "possible_starvation": starvation,
            }
        )

    audit = {
        "schema_version": "root_narrow_ab_v0_1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_paths": ["app._run_topic_page_retrieval"],
        "output_paths": [str(AUDIT_PATH.relative_to(REPO_ROOT))],
        "entities_tested": args.entities,
        "results": results,
        "known_limitations": [
            "Retrieval-only timing; synthesis latency unchanged by root narrow.",
            "Live backend required; results vary with corpus/backend state.",
        ],
        "recommendation_notes": (
            "Enable TOPIC_PAGE_ROOT_NARROW=1 when off-root textbook/video noise dominates "
            "and card count after narrow remains >= ~12. Re-check thin roots individually."
        ),
    }
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {AUDIT_PATH}")


if __name__ == "__main__":
    main()
