#!/usr/bin/env python3
"""Embed canonical Heme::* browse leaves for semantic tagging.

Model: text-embedding-3-small (same as live Hub API default).
Writes sidecar leaf embedding matrix + metadata; does not touch indexes.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from openai import OpenAI


EMBEDDING_MODEL = "text-embedding-3-small"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def leaf_embed_text(leaf: dict[str, Any]) -> str:
    tag = leaf["tag"]
    label = leaf.get("label") or tag.split("::")[-1]
    query = leaf.get("query") or label.replace("_", " ")
    # Path context helps disambiguate similarly named leaves.
    path = " > ".join(tag.split("::"))
    return f"{query}. Pathology taxonomy leaf: {label}. Full path: {path}."


def embed_texts(client: OpenAI, texts: list[str], *, batch_size: int = 64) -> np.ndarray:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch, encoding_format="float")
        # API returns in input order
        by_idx = sorted(resp.data, key=lambda d: d.index)
        vectors.extend([d.embedding for d in by_idx])
    arr = np.asarray(vectors, dtype=np.float32)
    # L2 normalize for cosine via dot product
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return arr / norms


def load_leaves(browse_index: Path) -> list[dict[str, Any]]:
    idx = json.loads(browse_index.read_text(encoding="utf-8"))
    heme = next(r for r in idx["roots"] if r.get("label") == "Heme")
    tags: list[dict[str, Any]] = []

    def walk(n: Any) -> None:
        if isinstance(n, dict):
            tag = n.get("tag")
            if isinstance(tag, str) and tag.startswith("Heme::"):
                tags.append(
                    {
                        "tag": tag,
                        "label": n.get("label"),
                        "query": n.get("query"),
                        "provenance": n.get("provenance"),
                    }
                )
            for v in n.values():
                if isinstance(v, (list, dict)):
                    walk(v)
        elif isinstance(n, list):
            for x in n:
                walk(x)

    walk(heme)
    uniq = {t["tag"]: t for t in tags}
    return sorted(uniq.values(), key=lambda x: x["tag"])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--browse-index",
        type=Path,
        default=Path("frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json"),
    )
    p.add_argument("--out-dir", type=Path, default=Path("outputs/heme_browse_leaf_embeddings_v0_1"))
    args = p.parse_args()

    leaves = load_leaves(args.browse_index)
    texts = [leaf_embed_text(leaf) for leaf in leaves]
    client = OpenAI()
    matrix = embed_texts(client, texts)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    npy_path = args.out_dir / "heme_leaf_embeddings.npy"
    meta_path = args.out_dir / "heme_leaf_embeddings_meta.json"
    np.save(npy_path, matrix)

    meta = {
        "schema_version": "heme_browse_leaf_embeddings.v0_1",
        "created_at_utc": utc_now(),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": int(matrix.shape[1]),
        "leaf_count": len(leaves),
        "leaves": [
            {
                **leaf,
                "embed_text": texts[i],
                "row_index": i,
            }
            for i, leaf in enumerate(leaves)
        ],
        "known_limitations": [
            "Leaf embeddings only — segment embeddings computed at tag time.",
            "Cosine similarity is not human curation.",
        ],
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "leaves": len(leaves), "dim": int(matrix.shape[1]), "npy": str(npy_path)}, indent=2))


if __name__ == "__main__":
    main()
