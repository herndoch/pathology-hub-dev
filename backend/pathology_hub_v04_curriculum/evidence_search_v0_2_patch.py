"""
Drop-in patch for pathology-hub-v04 /evidence/search — Evidence Search Reliability v0_2.

Integrate into backend app.py (FastAPI) BEFORE per-source dispatch:

    from evidence_search_reliability_v0_2.integration import (
        preprocess_evidence_search_request,
        patch_search_response,
    )
    from evidence_search_reliability_v0_2.config import load_config

    @app.post("/evidence/search")
    async def search_evidence(request: SearchRequest):
        cfg = load_config()
        payload = request.model_dump()
        dispatch_payload, expansion, diagnostics = preprocess_evidence_search_request(payload, config=cfg)
        response = await _dispatch_evidence_search(dispatch_payload)  # existing router
        if "who" in (payload.get("sources") or []):
            response = patch_search_response(
                response,
                original_query=str(payload.get("query") or ""),
                expansion=expansion,
                diagnostics=diagnostics,
            )
        return response

Environment variables:
    EVIDENCE_QUERY_EXPANSION_ENABLED=true|false  (default true in staging/local)
    EVIDENCE_QUERY_EXPANSION_DEBUG=true|false
    EVIDENCE_QUERY_EXPANSION_RULES_PATH=/path/to/query_expansion_rules_v0_2.json

Disable immediately in production:
    gcloud run services update pathology-hub-v04 --set-env-vars EVIDENCE_QUERY_EXPANSION_ENABLED=false
"""

from __future__ import annotations

# Re-export for backend Dockerfile COPY backend/evidence_search_reliability_v0_2
from evidence_search_reliability_v0_2.config import ExpansionConfig, load_config
from evidence_search_reliability_v0_2.integration import (
    patch_search_response,
    preprocess_evidence_search_request,
    rerank_who_results,
)

__all__ = [
    "ExpansionConfig",
    "load_config",
    "patch_search_response",
    "preprocess_evidence_search_request",
    "rerank_who_results",
]
