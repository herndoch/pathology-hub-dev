#!/usr/bin/env python3
"""Draw the reproducible topic-page prepop pilot sample (v0_1).

Reads the combined Browse tag index built by
`build_browse_tag_index_v0_1.py` and draws a small, stratified,
reproducible random sample of leaves per
docs/PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md section 5.

Stratification (seeded `random.Random`, deterministic draw order):
    1. One leaf from the Cytopathology aggregate root (`root_id == "cyto"`).
    2. One WHO-only leaf (`provenance == "who"`) outside the cyto root, if any
       exist.
    3. Remaining leaves drawn uniformly from everything else (abpath-only or
       "both" provenance, outside cyto), excluding leaves already chosen.

Output:
    outputs/chat_mvp_topic_prepop_v0_1/pilot_sample_v0_1.json
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
INDEX_PATH = OUTPUT_DIR / "browse_tag_index_v0_1.json"
SAMPLE_PATH = OUTPUT_DIR / "pilot_sample_v0_1.json"

SCHEMA_VERSION = "topic_prepop_pilot_sample_v0_1"
ACCEPTED_NAV_PROVENANCES = frozenset({"abpath", "who", "both"})


def _flatten_leaves(index: dict) -> list[dict]:
    flat: list[dict] = []
    for root in index["roots"]:
        for sub in root["subcategories"]:
            for leaf in sub["leaves"]:
                flat.append(
                    {
                        "tag": leaf["tag"],
                        "label": leaf["label"],
                        "provenance": leaf["provenance"],
                        "query": leaf["query"],
                        "root_id": root["id"],
                        "root_label": root["label"],
                        "subcategory_id": sub["id"],
                        "subcategory_label": sub["label"],
                    }
                )
    return flat


def draw_sample(index: dict, n: int, seed: int) -> dict:
    leaves = _flatten_leaves(index)

    cyto_pool = [leaf for leaf in leaves if leaf["root_id"] == "cyto"]
    non_cyto = [leaf for leaf in leaves if leaf["root_id"] != "cyto"]
    who_only_pool = [leaf for leaf in non_cyto if leaf["provenance"] == "who"]
    other_pool = [
        leaf for leaf in non_cyto if leaf["provenance"] in ("abpath", "both")
    ]

    rng = random.Random(seed)
    chosen: list[dict] = []
    chosen_tags: set[str] = set()

    require_who_only_available = bool(who_only_pool)

    if cyto_pool:
        pick = rng.choice(cyto_pool)
        chosen.append(pick)
        chosen_tags.add(pick["tag"])

    if who_only_pool:
        remaining_who_pool = [leaf for leaf in who_only_pool if leaf["tag"] not in chosen_tags]
        pick = rng.choice(remaining_who_pool)
        chosen.append(pick)
        chosen_tags.add(pick["tag"])

    fill_pool = [leaf for leaf in other_pool if leaf["tag"] not in chosen_tags]
    n_remaining = max(0, n - len(chosen))
    n_remaining = min(n_remaining, len(fill_pool))
    if n_remaining:
        chosen.extend(rng.sample(fill_pool, n_remaining))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_requested": n,
        "n_drawn": len(chosen),
        "seed": seed,
        "accepted_nav_provenances": sorted(ACCEPTED_NAV_PROVENANCES),
        "stratification": {
            "require_cyto": True,
            "require_who_only": True,
            "who_only_pool_available": require_who_only_available,
            "who_only_pool_size": len(who_only_pool),
            "cyto_pool_size": len(cyto_pool),
            "other_pool_size": len(other_pool),
        },
        "leaves": [
            {
                "tag": leaf["tag"],
                "label": leaf["label"],
                "provenance": leaf["provenance"],
                "query": leaf["query"],
                "root_id": leaf["root_id"],
                "subcategory_id": leaf["subcategory_id"],
            }
            for leaf in chosen
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20260710)
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        raise SystemExit(
            f"Missing {INDEX_PATH}. Run build_browse_tag_index_v0_1.py first."
        )

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    sample = draw_sample(index, n=args.n, seed=args.seed)

    SAMPLE_PATH.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {SAMPLE_PATH}")
    for leaf in sample["leaves"]:
        print(f"  [{leaf['provenance']:>7}] {leaf['root_id']:<24} {leaf['tag']}")


if __name__ == "__main__":
    main()
