"""Non-destructive WHO result reranking using title/subsection signals."""

from __future__ import annotations

import re
from typing import Any

from .query_expansion import ExpansionResult
from .root_inference import normalize_text, tokenize


def _hit_text(hit: dict[str, Any]) -> str:
    parts = [
        hit.get("title"),
        hit.get("entity_name"),
        hit.get("subtitle"),
        hit.get("subsection"),
        hit.get("section"),
        hit.get("excerpt"),
        hit.get("text"),
        hit.get("tag"),
        hit.get("primary_tag"),
    ]
    return normalize_text(" ".join(str(p) for p in parts if p))


def _title_boost_score(query: str, hit: dict[str, Any], expansion: ExpansionResult) -> float:
    q_norm = normalize_text(query)
    hit_norm = _hit_text(hit)
    if not hit_norm:
        return 0.0

    boost = 0.0
    q_tokens = set(tokenize(q_norm))
    hit_tokens = set(tokenize(hit_norm))

    overlap = len(q_tokens.intersection(hit_tokens))
    boost += min(overlap * 0.15, 1.5)

    if q_norm and q_norm in hit_norm:
        boost += 2.0

    title = normalize_text(str(hit.get("title") or hit.get("entity_name") or ""))
    if title and (title in q_norm or q_norm in title):
        boost += 1.5

    for applied in expansion.expansions_applied:
        for term in applied.get("expansion_terms") or []:
            t = normalize_text(term)
            if t and t in hit_norm:
                boost += 0.75

    # Penalize obvious wrong-organ leakage when expansion inferred roots present
    if expansion.inferred_roots:
        organ_markers = {
            "Breast": ("breast", "mammary", "ductal"),
            "GI": ("colon", "colorectal", "pancreas", "gastrointestinal"),
            "GU": ("kidney", "renal", "bladder", "urothelial"),
            "GYN": ("cervix", "endometrium", "ovary"),
            "Skin": ("skin", "dermal", "cutaneous"),
            "BST": ("bone", "chondro", "osteo"),
            "HN": ("thyroid", "salivary", "head neck"),
        }
        for root in expansion.inferred_roots:
            markers = organ_markers.get(root, ())
            if markers and not any(m in hit_norm for m in markers):
                # Only penalize if query had organ context
                if any(m in q_norm for m in markers):
                    boost -= 0.5

    return boost


def apply_who_title_boost(
    hits: list[dict[str, Any]],
    *,
    query: str,
    expansion: ExpansionResult,
    preserve_upstream_order: bool = True,
) -> list[dict[str, Any]]:
    """Rerank WHO hits by title/subsection boost without dropping upstream results."""
    if not hits:
        return hits

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for idx, hit in enumerate(hits):
        base_score = float(hit.get("score") or 0.0)
        boost = _title_boost_score(query, hit, expansion)
        combined = base_score + boost
        enriched = dict(hit)
        enriched["retrieval_mode"] = hit.get("retrieval_mode") or "who_upstream_title_boost_v0_2"
        if expansion.expansions_applied:
            enriched["who_title_boost_v0_2"] = round(boost, 4)
        scored.append((combined, idx, enriched))

    scored.sort(key=lambda x: (-x[0], x[1] if preserve_upstream_order else 0))
    out = []
    for rank, (_, _, hit) in enumerate(scored, start=1):
        hit = dict(hit)
        hit["rank"] = rank
        out.append(hit)
    return out
