#!/usr/bin/env python3
"""Draw a stratified high-traffic post-rebuild prebuild sample.

Picks leaves from priority roots (HN, Eye_Orbit, Breast, GU, GI, Cyto_Breast)
for Phase 6 batch prebuild scale-up.

Output:
    outputs/chat_mvp_topic_prepop_v0_1/high_traffic_sample_v0_1.json
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
SAMPLE_PATH = OUTPUT_DIR / "high_traffic_sample_v0_1.json"

SCHEMA_VERSION = "topic_prepop_high_traffic_sample_v0_1"
DEFAULT_ROOTS = ("hn", "eye_orbit", "breast", "gu", "gi", "cyto_breast")


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


def draw_high_traffic(index: dict, per_root: int, roots: tuple[str, ...], seed: int) -> dict:
    leaves = _flatten_leaves(index)
    by_root: dict[str, list[dict]] = {}
    for leaf in leaves:
        by_root.setdefault(leaf["root_id"], []).append(leaf)

    rng = random.Random(seed)
    chosen: list[dict] = []
    chosen_tags: set[str] = set()

    for root_id in roots:
        pool = by_root.get(root_id, [])
        if not pool:
            continue
        n = min(per_root, len(pool))
        picks = rng.sample(pool, n)
        for pick in picks:
            if pick["tag"] in chosen_tags:
                continue
            chosen.append(pick)
            chosen_tags.add(pick["tag"])

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_requested_per_root": per_root,
        "n_drawn": len(chosen),
        "seed": seed,
        "priority_roots": list(roots),
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
    parser.add_argument("--per-root", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260711)
    parser.add_argument(
        "--roots",
        default=",".join(DEFAULT_ROOTS),
        help="Comma-separated root_id values",
    )
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        raise SystemExit(f"Missing {INDEX_PATH}. Run build_browse_tag_index_v0_1.py first.")

    roots = tuple(r.strip() for r in args.roots.split(",") if r.strip())
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    sample = draw_high_traffic(index, per_root=args.per_root, roots=roots, seed=args.seed)
    SAMPLE_PATH.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {SAMPLE_PATH} ({sample['n_drawn']} leaves)")
    for leaf in sample["leaves"]:
        print(f"  [{leaf['provenance']:>7}] {leaf['root_id']:<14} {leaf['tag']}")


if __name__ == "__main__":
    main()
