#!/usr/bin/env python3
"""Build a no-AI content map from Chat MVP topic prebuild pages.

Reads prebuilt topic page JSON (cards + figures only — no answer_markdown
synthesis) and emits a browseable OncoTree inventory of source content that
feeds those pages.

Intended host path (not claimed live by this package):
  pathologynotebook.com/chat-no-ai

Output:
  frontend/chat_no_ai_content_map_v0_1/data/chat_no_ai_content_map_v0_1.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO_ROOT
    / "frontend"
    / "chat_no_ai_content_map_v0_1"
    / "data"
    / "chat_no_ai_content_map_v0_1.json"
)
SCHEMA = "chat_no_ai_content_map.v0_1"
MAX_CARDS_PER_LEAF = 6
MAX_FIGURES_PER_LEAF = 4
EXCERPT_CHARS = 180


def _pretty_label(part: str) -> str:
    text = (part or "").replace("_", " ").strip()
    return re.sub(r"\s+", " ", text) or "(untitled)"


def _gs_to_https(uri: str | None) -> str | None:
    if not uri:
        return None
    if uri.startswith("gs://"):
        return "https://storage.googleapis.com/" + uri[len("gs://") :]
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    return None


def _pick_http(*values: object) -> str | None:
    for v in values:
        if isinstance(v, str):
            https = _gs_to_https(v)
            if https and https.startswith("http"):
                return https
    return None


def lean_card(card: dict) -> dict | None:
    excerpt = (card.get("excerpt") or card.get("text") or card.get("caption") or "").strip()
    title = card.get("title") or card.get("source_name") or card.get("entity_name")
    family = card.get("source_family") or card.get("source") or "unknown"
    figure_url = _pick_http(
        card.get("figure_url"),
        card.get("image_url"),
        card.get("url"),
    )
    page_image_url = _pick_http(card.get("page_image_url"))
    source_page_url = _pick_http(card.get("source_page_url"), card.get("source_pdf_url"))
    source_url = _pick_http(card.get("source_url"), card.get("url"))
    if not any([excerpt, figure_url, page_image_url, source_page_url, source_url, title]):
        return None
    return {
        "kind": "card",
        "title": title,
        "source_family": family,
        "source_name": card.get("source_name") or card.get("source"),
        "source_id": card.get("source_id"),
        "page": card.get("page"),
        "section": card.get("section") or card.get("chapter_title") or card.get("entity_name"),
        "excerpt": excerpt[:EXCERPT_CHARS] if excerpt else None,
        "figure_url": figure_url,
        "page_image_url": page_image_url,
        "source_page_url": source_page_url,
        "source_url": source_url,
        "record_id": card.get("record_id") or card.get("chunk_id") or card.get("figure_record_id"),
    }


def lean_figure(fig: dict) -> dict | None:
    figure_url = _pick_http(fig.get("figure_url"), fig.get("image_url"), fig.get("url"), fig.get("source_url"))
    page_image_url = _pick_http(fig.get("page_image_url"))
    source_page_url = _pick_http(fig.get("source_page_url"), fig.get("source_pdf_url"))
    caption = (fig.get("caption") or fig.get("title") or "").strip()
    if not any([figure_url, page_image_url, source_page_url, caption]):
        return None
    return {
        "kind": "figure",
        "title": fig.get("title") or fig.get("entity_name") or fig.get("figure_id"),
        "caption": caption[:EXCERPT_CHARS] if caption else None,
        "source_family": fig.get("source_family") or fig.get("source") or "unknown",
        "source_name": fig.get("source_name") or fig.get("source"),
        "source_id": fig.get("source_id"),
        "page": fig.get("page"),
        "figure_id": fig.get("figure_id"),
        "figure_url": figure_url,
        "page_image_url": page_image_url,
        "source_page_url": source_page_url,
        "source_url": _pick_http(fig.get("source_url"), fig.get("url")),
        "record_id": fig.get("figure_record_id") or fig.get("record_id"),
    }


def ensure_child(node: dict, part: str) -> dict:
    for child in node["children"]:
        if child["id"] == part:
            return child
    child = {
        "id": part,
        "label": _pretty_label(part),
        "path": f"{node['path']}::{part}" if node.get("path") else part,
        "page_count": 0,
        "card_count": 0,
        "figure_count": 0,
        "children": [],
        "items": [],
        "kind": "branch",
    }
    node["children"].append(child)
    return child


def load_prebuild_pages(pages_dir: Path) -> list[dict]:
    pages: list[dict] = []
    for path in sorted(pages_dir.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tag = (row.get("tag") or "").strip()
        if not tag:
            continue
        cards = []
        for c in row.get("cards") or []:
            lean = lean_card(c if isinstance(c, dict) else {})
            if lean:
                cards.append(lean)
        figures = []
        for f in row.get("figures") or []:
            lean = lean_figure(f if isinstance(f, dict) else {})
            if lean:
                figures.append(lean)
        pages.append(
            {
                "tag": tag,
                "label": row.get("label") or _pretty_label(tag.split("::")[-1]),
                "schema_version": row.get("schema_version"),
                "generated_at": row.get("generated_at"),
                "card_count": len(row.get("cards") or []),
                "figure_count": len(row.get("figures") or []),
                "cards": cards[:MAX_CARDS_PER_LEAF],
                "figures": figures[:MAX_FIGURES_PER_LEAF],
                "who_cross_mentions": len(row.get("who_cross_mentions") or []),
            }
        )
    return pages


def normalize_tag_parts(tag: str) -> list[str]:
    """Split tag path; nest all Cyto_* roots under Cytopathology."""
    parts = [p for p in (tag or "").split("::") if p]
    if not parts:
        return parts
    root = parts[0]
    if root.startswith("Cyto_"):
        site = root[len("Cyto_") :] or root
        return ["Cytopathology", site, *parts[1:]]
    return parts


def build_tree(pages: list[dict]) -> tuple[list[dict], dict]:
    roots: dict[str, dict] = {}
    family_counter: Counter[str] = Counter()
    for page in pages:
        parts = normalize_tag_parts(page["tag"])
        if not parts:
            continue
        root_id = parts[0]
        if root_id not in roots:
            roots[root_id] = {
                "id": root_id,
                "label": _pretty_label(root_id),
                "path": root_id,
                "page_count": 0,
                "card_count": 0,
                "figure_count": 0,
                "children": [],
                "items": [],
                "kind": "root",
            }
        node = roots[root_id]
        for part in parts[1:]:
            node = ensure_child(node, part)
        node["kind"] = "leaf"
        items = list(page["figures"]) + list(page["cards"])
        node["items"] = items
        node["page_count"] = 1
        node["card_count"] = int(page["card_count"])
        node["figure_count"] = int(page["figure_count"])
        node["prebuild_label"] = page["label"]
        node["prebuild_tag"] = page["tag"]
        node["who_cross_mentions"] = page["who_cross_mentions"]
        for it in items:
            family_counter[str(it.get("source_family") or "unknown")] += 1

    def finalize(node: dict) -> tuple[int, int, int]:
        pages_n = int(node.get("page_count") or 0) if node.get("kind") == "leaf" else 0
        cards_n = int(node.get("card_count") or 0) if node.get("kind") == "leaf" else 0
        figs_n = int(node.get("figure_count") or 0) if node.get("kind") == "leaf" else 0
        for child in node["children"]:
            p, c, f = finalize(child)
            pages_n += p
            cards_n += c
            figs_n += f
        node["page_count"] = pages_n
        node["card_count"] = cards_n
        node["figure_count"] = figs_n
        node["children"].sort(key=lambda x: x["label"].lower())
        return pages_n, cards_n, figs_n

    root_list = sorted(roots.values(), key=lambda r: r["label"].lower())
    for r in root_list:
        finalize(r)

    cyto = next((r for r in root_list if r["id"] == "Cytopathology"), None)
    counts = {
        "prebuild_pages": len(pages),
        "roots": len(root_list),
        "leaves": sum(1 for p in pages),
        "cards_indexed": sum(int(p["card_count"]) for p in pages),
        "figures_indexed": sum(int(p["figure_count"]) for p in pages),
        "sample_items": sum(len(p["cards"]) + len(p["figures"]) for p in pages),
        "source_families": dict(family_counter.most_common()),
        "cytopathology_sites": len(cyto["children"]) if cyto else 0,
        "cytopathology_pages": int(cyto["page_count"]) if cyto else 0,
    }
    return root_list, counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pages-dir",
        type=Path,
        required=True,
        help="Local directory of prebuild page JSON files",
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    pages = load_prebuild_pages(args.pages_dir)
    roots, counts = build_tree(pages)

    payload = {
        "schema_version": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": "Pathology Notebook — Chat content map (no AI)",
        "subtitle": (
            "Inventory of source cards and figures used by prebuilt topic pages. "
            "No live retrieval and no AI answer synthesis."
        ),
        "intended_host_path": "pathologynotebook.com/chat-no-ai",
        "source": {
            "pages_dir": str(args.pages_dir),
            "canonical_prebuilds_gcs": (
                "gs://pathology_hub/api_exposed/chat_mvp_topic_prebuilds_v0_1/pages/"
            ),
            "prebuild_schema": "topic_page_prebuild_v0_1",
        },
        "counts": counts,
        "known_limitations": [
            "This map is built from prebuilt page JSON only; it is not a claim that /chat-no-ai is live on the public domain.",
            "answer_markdown and other AI synthesis fields are intentionally omitted.",
            f"Each leaf shows up to {MAX_CARDS_PER_LEAF} cards + {MAX_FIGURES_PER_LEAF} figures (samples), not every retrieval hit.",
            "All Cyto_* prebuild roots are nested under a single Cytopathology root (Cyto_Adrenal → Cytopathology::Adrenal, etc.).",
            "Some figure URLs are gs:// rewritten to storage.googleapis.com and may 404 if the object is not public.",
            "Page image / PDF links appear when present on the prebuild card; many WHO/PathOut cards lack textbook page inventory fields.",
        ],
        "roots": roots,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
