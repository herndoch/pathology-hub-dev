#!/usr/bin/env python3
"""Build a textbook-only OncoTree index from catalog + vector docstore.

Inputs:
  --catalog  textbook_primary_tag_catalog_v2_1.jsonl
  --docstore textbook_lean_vector_docstore_v2_1.jsonl
  --webmap   textbook_figure_web_map_v1_FILTERED_NO_MCKEE_DORFMAN.jsonl (optional)
  --page-inv textbook_page_image_inventory_v1.jsonl (optional; joins page PNG + PDF page URLs)

Output:
  frontend/textbook_oncotree_v0_1/data/textbook_oncotree_index_v0_1.json

Leaves keep capped sample excerpts (page text + figures with public URLs) so the
static site stays shareable without shipping the full ~80k-row docstore.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO_ROOT / "frontend" / "textbook_oncotree_v0_1" / "data" / "textbook_oncotree_index_v0_1.json"
)
SCHEMA = "textbook_oncotree_index.v0_1"
MAX_TEXT_PER_LEAF = 4
MAX_FIGURES_PER_LEAF = 4
EXCERPT_CHARS = 320


def _pretty_label(part: str) -> str:
    text = (part or "").replace("_", " ").strip()
    return re.sub(r"\s+", " ", text) or "(untitled)"


def _gs_to_https(uri: str | None) -> str | None:
    if not uri:
        return None
    if uri.startswith("gs://"):
        return "https://storage.googleapis.com/" + uri[len("gs://") :]
    return uri


def load_webmap(path: Path | None) -> dict[str, str]:
    """Map original gs:// figure URI → public_url."""
    out: dict[str, str] = {}
    if not path or not path.is_file():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("status") not in {None, "copied", "ok", "converted"} and row.get("error"):
                continue
            pub = row.get("public_url")
            orig = row.get("original_gs_uri") or row.get("original_path_value")
            if not pub:
                continue
            if orig:
                key = orig if orig.startswith("gs://") else None
                if key:
                    out[key] = pub
                # also index https original as gs-equivalent path
                if isinstance(orig, str) and "storage.googleapis.com/" in orig:
                    gs = "gs://" + orig.split("storage.googleapis.com/", 1)[1]
                    out[gs] = pub
            # basename fallback
            rel = row.get("public_rel_path") or ""
            if rel:
                out["basename:" + Path(rel).name] = pub
    return out


def load_page_inventory(path: Path | None) -> dict[tuple[str, int], dict]:
    """Map (source_id, page) → page_image_url / source_page_url / source_pdf_url."""
    out: dict[tuple[str, int], dict] = {}
    if not path or not path.is_file():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            sid = (row.get("source_id") or "").strip()
            page = row.get("page")
            if not sid or page is None:
                continue
            try:
                page_i = int(page)
            except (TypeError, ValueError):
                continue
            page_image = row.get("page_image_url")
            if row.get("page_image_status") not in {None, "exists", "ok"} and not page_image:
                page_image = None
            out[(sid, page_i)] = {
                "page_image_url": page_image,
                "source_page_url": row.get("source_page_url"),
                "source_pdf_url": row.get("source_pdf_url"),
            }
    return out


def load_catalog(path: Path) -> dict[str, dict]:
    by_tag: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            tag = (row.get("primary_tag") or "").strip()
            if not tag:
                continue
            if row.get("is_generated_review_required") or row.get("is_consolidated_review_required"):
                continue
            if "::Textbooks::Review_Required::" in tag or tag.startswith("Textbooks::"):
                continue
            by_tag[tag] = row
    return by_tag


def sample_card(row: dict, webmap: dict[str, str], page_inv: dict[tuple[str, int], dict]) -> dict:
    chunk_type = row.get("chunk_type") or "page_text"
    image_path = row.get("image_path")
    public = None
    if image_path:
        public = webmap.get(image_path)
        if not public and isinstance(image_path, str):
            public = webmap.get("basename:" + Path(image_path).name)
        if not public:
            public = _gs_to_https(image_path)
    text = (row.get("text") or "").strip()
    sid = row.get("source_id")
    page = row.get("page")
    page_meta: dict = {}
    if sid is not None and page is not None:
        try:
            page_meta = page_inv.get((str(sid), int(page))) or {}
        except (TypeError, ValueError):
            page_meta = {}
    return {
        "chunk_id": row.get("chunk_id"),
        "chunk_type": chunk_type,
        "source_id": sid,
        "source_title": row.get("source_title") or sid,
        "page": page,
        "section": row.get("section") or row.get("chapter_title"),
        "figure_id": row.get("figure_id"),
        "image_url": public,
        "page_image_url": page_meta.get("page_image_url"),
        "source_page_url": page_meta.get("source_page_url"),
        "source_pdf_url": page_meta.get("source_pdf_url"),
        "excerpt": text[:EXCERPT_CHARS],
        "primary_tag": row.get("primary_tag"),
    }


def stream_samples(
    docstore: Path,
    allowed_tags: set[str],
    webmap: dict[str, str],
    page_inv: dict[tuple[str, int], dict],
) -> tuple[dict[str, dict], set[str]]:
    """Per tag: totals + capped text/figure samples."""
    buckets: dict[str, dict] = {}
    books: set[str] = set()
    with docstore.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            tag = (row.get("primary_tag") or "").strip()
            if not tag or tag not in allowed_tags:
                continue
            b = buckets.get(tag)
            if b is None:
                b = {
                    "chunk_count": 0,
                    "page_text_count": 0,
                    "figure_count": 0,
                    "texts": [],
                    "figures": [],
                    "books": set(),
                }
                buckets[tag] = b
            b["chunk_count"] += 1
            sid = row.get("source_id")
            if sid:
                b["books"].add(sid)
                books.add(sid)
            ctype = row.get("chunk_type") or "page_text"
            card = sample_card(row, webmap, page_inv)
            if ctype == "figure_caption":
                b["figure_count"] += 1
                if len(b["figures"]) < MAX_FIGURES_PER_LEAF and card.get("image_url"):
                    b["figures"].append(card)
                elif len(b["figures"]) < MAX_FIGURES_PER_LEAF:
                    b["figures"].append(card)
            else:
                b["page_text_count"] += 1
                if len(b["texts"]) < MAX_TEXT_PER_LEAF and card.get("excerpt"):
                    b["texts"].append(card)
    return buckets, books


def ensure_child(node: dict, part: str) -> dict:
    for child in node["children"]:
        if child["id"] == part:
            return child
    child = {
        "id": part,
        "label": _pretty_label(part),
        "path": f"{node['path']}::{part}" if node.get("path") else part,
        "chunk_count": 0,
        "page_count": 0,
        "children": [],
        "items": [],
        "kind": "branch",
    }
    node["children"].append(child)
    return child


def build_tree(catalog: dict[str, dict], samples: dict[str, dict]) -> tuple[list[dict], dict]:
    roots: dict[str, dict] = {}
    for tag, meta in catalog.items():
        parts = [p for p in tag.split("::") if p]
        if not parts:
            continue
        root_id = parts[0]
        if root_id not in roots:
            roots[root_id] = {
                "id": root_id,
                "label": _pretty_label(root_id),
                "path": root_id,
                "chunk_count": 0,
                "page_count": 0,
                "children": [],
                "items": [],
                "kind": "root",
            }
        node = roots[root_id]
        for part in parts[1:]:
            node = ensure_child(node, part)
        node["kind"] = "leaf"
        samp = samples.get(tag) or {}
        items = list(samp.get("figures") or []) + list(samp.get("texts") or [])
        node["items"] = items
        node["chunk_count"] = int(samp.get("chunk_count") or meta.get("chunk_count") or meta.get("vector_docstore_count") or 0)
        node["page_count"] = int(meta.get("page_count") or 0)
        node["sample_books"] = sorted(samp.get("books") or [])

    def finalize(node: dict) -> tuple[int, int]:
        chunks = int(node.get("chunk_count") or 0) if node.get("kind") == "leaf" else 0
        pages = int(node.get("page_count") or 0) if node.get("kind") == "leaf" else 0
        for child in node["children"]:
            c, p = finalize(child)
            chunks += c
            pages += p
        node["chunk_count"] = chunks
        node["page_count"] = pages
        node["children"].sort(key=lambda c: c["label"].lower())
        return chunks, pages

    root_list = sorted(roots.values(), key=lambda r: r["label"].lower())
    for r in root_list:
        finalize(r)

    leaf_count = sum(1 for t in catalog)
    total_chunks = sum(int((samples.get(t) or {}).get("chunk_count") or catalog[t].get("chunk_count") or 0) for t in catalog)
    counts = {
        "leaves": leaf_count,
        "roots": len(root_list),
        "chunks_indexed": total_chunks,
        "sample_items": sum(len(n.get("items") or []) for r in root_list for n in _iter_leaves(r)),
    }
    return root_list, counts


def _iter_leaves(node: dict):
    if node.get("kind") == "leaf" or not node.get("children"):
        yield node
        return
    for child in node.get("children") or []:
        yield from _iter_leaves(child)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--docstore", type=Path, required=True)
    ap.add_argument("--webmap", type=Path, default=None)
    ap.add_argument(
        "--page-inv",
        type=Path,
        default=None,
        help="textbook_page_image_inventory_v1.jsonl for page PNG + PDF page links",
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    catalog = load_catalog(args.catalog)
    webmap = load_webmap(args.webmap)
    page_inv = load_page_inventory(args.page_inv)
    samples, books = stream_samples(args.docstore, set(catalog.keys()), webmap, page_inv)
    roots, counts = build_tree(catalog, samples)
    counts["books"] = len(books)
    counts["page_inventory_keys"] = len(page_inv)

    def _count_joined(items_key: str) -> int:
        n = 0
        for samp in samples.values():
            for card in samp.get(items_key) or []:
                if card.get("page_image_url") or card.get("source_page_url"):
                    n += 1
        return n

    counts["samples_with_page_or_pdf"] = _count_joined("texts") + _count_joined("figures")

    payload = {
        "schema_version": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": "Pathology Hub — Textbook OncoTree",
        "subtitle": "Textbook excerpts and figures indexed by primary taxonomy tag.",
        "source": {
            "catalog": str(args.catalog),
            "docstore": str(args.docstore),
            "webmap": str(args.webmap) if args.webmap else None,
            "page_inventory": str(args.page_inv) if args.page_inv else None,
            "canonical_catalog_gcs": (
                "gs://pathology_hub/02_normalized/textbooks/lean/tags/tag_consolidation_v2_1/"
                "textbook_primary_tag_catalog_v2_1.jsonl"
            ),
            "canonical_docstore_gcs": (
                "gs://pathology_hub/03_indexes/textbooks/vector_v2_1_tag_consolidation/"
                "textbook_lean_vector_docstore_v2_1.jsonl"
            ),
            "canonical_page_inventory_gcs": (
                "gs://pathology_hub/02_normalized/source_registry/textbook_page_image_inventory_v1.jsonl"
            ),
        },
        "counts": counts,
        "known_limitations": [
            "Tree includes controlled v2.1 tags only (generated/review-required tags omitted).",
            f"Each leaf shows up to {MAX_TEXT_PER_LEAF} text + {MAX_FIGURES_PER_LEAF} figure samples, not the full chunk list.",
            "Figure images use public web-map URLs when available; otherwise HTTPS rewrite of gs:// may 404.",
            "Page PNG + PDF page links come from page inventory join on (source_id, page); missing inventory rows omit those fields.",
            "Separate from the Lecture Video OncoTree; not deployed to chat.pathologynotebook.com by this package.",
        ],
        "roots": roots,
    }
    # Convert book sets left in leaves
    def scrub(node: dict) -> None:
        node.pop("sample_books", None)
        for child in node.get("children") or []:
            scrub(child)

    for r in roots:
        scrub(r)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "counts": counts,
                "webmap_keys": len(webmap),
                "page_inv_keys": len(page_inv),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
