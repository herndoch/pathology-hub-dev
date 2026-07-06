"""Drop-in integration hooks for pathology-hub-v04 /evidence/search handler."""

from __future__ import annotations

from typing import Any

from .config import ExpansionConfig, load_config
from .query_expansion import ExpansionResult, expand_query
from .who_ranking import apply_who_title_boost


def preprocess_evidence_search_request(
    payload: dict[str, Any],
    *,
    config: ExpansionConfig | None = None,
    entity_metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ExpansionResult, dict[str, Any] | None]:
    """
    Mutate outbound search payload with governed query expansion.

    Backward compatible: preserves original query in payload['query'] history field
    only when debug enabled; effective query replaces payload['query'] for dispatch.
    """
    cfg = config or load_config()
    original_payload = dict(payload)
    query = str(payload.get("query") or "").strip()
    sources = list(payload.get("sources") or [])

    expansion = expand_query(
        query,
        sources=sources,
        entity_metadata=entity_metadata,
        config=cfg,
    )

    out = dict(payload)
    if expansion.effective_query != query:
        out["query"] = expansion.effective_query
        out.setdefault("query_original", query)

    title_boost_terms: list[str] = []
    for applied in expansion.expansions_applied:
        if applied.get("expansion_mode") == "title_boost_only":
            title_boost_terms.extend(applied.get("expansion_terms") or [])

    if title_boost_terms and "who" in sources:
        out.setdefault("who_title_boost_terms", title_boost_terms)

    diagnostics = expansion.to_diagnostics(debug=cfg.debug)
    return out, expansion, diagnostics


def rerank_who_results(
    response: dict[str, Any],
    *,
    query: str,
    expansion: ExpansionResult,
) -> dict[str, Any]:
    """Apply WHO title boost reranking to an existing searchEvidence response."""
    out = dict(response)
    who_hits = list(out.get("who_results") or [])
    if not who_hits:
        return out
    out["who_results"] = apply_who_title_boost(
        who_hits,
        query=query,
        expansion=expansion,
    )
    return out


def patch_search_response(
    response: dict[str, Any],
    *,
    original_query: str,
    expansion: ExpansionResult,
    diagnostics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Post-process response: WHO rerank + optional diagnostics."""
    out = rerank_who_results(response, query=original_query, expansion=expansion)
    if diagnostics:
        out.setdefault("diagnostics", {}).update(diagnostics)
    return out
