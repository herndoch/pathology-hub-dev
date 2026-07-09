"""Pathology Hub Chat MVP — local-first prototype frontend.

Local FastAPI app that:
1. Retrieves evidence from the live Pathology Hub `searchEvidence` API
   (POST /evidence/search — the ONE supported backend operation), and
2. Optionally synthesizes a source-grounded answer with the OpenAI Responses API.

This is a prototype/MVP shell over the already-live v0_2 backend.
It does NOT change backend code, retrieval rules, Cloud Run, GCS, or GPT Builder.

Run with: ./scripts/run_local.sh   (see README.md)
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import prompts
import secrets_helper
from openai_synthesizer import SynthesisResult, ping as openai_ping, synthesize
from pathology_backend import (
    SUPPORTED_SOURCES,
    PathologyHubClient,
    extract_evidence_cards,
    extract_figures,
    merge_outcomes,
    staged_retrieve,
)

APP_TITLE = "Pathology Hub Chat MVP"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title=APP_TITLE)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_backend_client = PathologyHubClient(api_url=os.environ.get("PATHOLOGY_HUB_API_URL"))

VALID_MODES = frozenset({"gpt_like", "compare_sources", "visual", "search_only", "html_teaching"})


class SearchRequest(BaseModel):
    query: str
    sources: list[str] = Field(default_factory=lambda: ["textbooks"])
    max_results: int = Field(default=3, ge=1, le=10)
    include_figures: bool = False
    max_figures: int = Field(default=0, ge=0, le=10)
    compact: bool = True
    excerpt_char_limit: int = Field(default=900, ge=200, le=4000)
    render_html: bool = False


class ChatRequest(SearchRequest):
    mode: str = "gpt_like"


def _validate_sources(sources: list[str]) -> list[str]:
    cleaned = [s.strip().lower() for s in sources if s and s.strip()]
    unknown = sorted({s for s in cleaned if s not in SUPPORTED_SOURCES})
    if unknown:
        raise ValueError(
            f"Unsupported source(s): {unknown}. Supported: {SUPPORTED_SOURCES}"
        )
    return cleaned or ["textbooks"]


def _run_retrieval(req: SearchRequest) -> tuple[list, dict]:
    sources = _validate_sources(req.sources)
    outcomes = staged_retrieve(
        _backend_client,
        req.query,
        sources,
        max_results=req.max_results,
        include_figures=req.include_figures,
        max_figures=req.max_figures,
        compact=req.compact,
        excerpt_char_limit=req.excerpt_char_limit,
        render_html=req.render_html,
    )
    merged = merge_outcomes(outcomes)
    return outcomes, merged


def _debug_payload(outcomes: list) -> dict:
    return {
        "calls": [o.to_debug_dict() for o in outcomes],
        "call_count": len(outcomes),
    }


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/health")
def api_health():
    backend_health = _backend_client.health()
    secret_status = secrets_helper.all_secret_status()
    return {
        "app": "ok",
        "app_title": APP_TITLE,
        "backend": backend_health,
        "secrets": secret_status,
        "openai_model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini (default, override with OPENAI_MODEL)"),
        "supported_sources": SUPPORTED_SOURCES,
        "supported_modes": sorted(VALID_MODES),
    }


@app.post("/api/search")
def api_search(req: SearchRequest):
    """Search-only: raw evidence, no OpenAI call."""
    try:
        sources = _validate_sources(req.sources)
        req.sources = sources
        outcomes, merged = _run_retrieval(req)
        return {
            "ok": True,
            "mode": "search_only",
            "evidence": merged,
            "cards": extract_evidence_cards(merged),
            "figures": extract_figures(merged),
            "debug": _debug_payload(outcomes),
        }
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


def _answer_gpt_like(req: ChatRequest, merged: dict) -> SynthesisResult:
    return synthesize(
        prompts.gpt_like_system_prompt(),
        req.query,
        merged,
    )


def _answer_compare_sources(req: ChatRequest, merged: dict) -> SynthesisResult:
    sources = _validate_sources(req.sources)
    extra = f"Requested source families for this comparison: {', '.join(sources)}"
    return synthesize(
        prompts.compare_sources_system_prompt(),
        req.query,
        merged,
        extra_instructions=extra,
    )


def _answer_visual(req: ChatRequest, merged: dict) -> SynthesisResult:
    extra = f"max_figures requested: {req.max_figures}"
    return synthesize(
        prompts.visual_figures_system_prompt(),
        req.query,
        merged,
        extra_instructions=extra,
    )


def _answer_html_teaching(req: ChatRequest, merged: dict) -> SynthesisResult:
    html_only = {
        "query": merged.get("query"),
        "source_status": merged.get("source_status"),
        "warnings": merged.get("warnings"),
        "html_result": merged.get("html_result"),
        "curriculum_status": merged.get("curriculum_status"),
    }
    return synthesize(
        prompts.html_teaching_system_prompt(),
        req.query,
        html_only,
    )


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    mode = (req.mode or "gpt_like").strip()
    if mode not in VALID_MODES:
        return {
            "ok": False,
            "error": f"Unknown mode '{mode}'. Valid modes: {sorted(VALID_MODES)}",
        }

    try:
        sources = _validate_sources(req.sources)
        req.sources = sources

        if mode == "html_teaching":
            req.render_html = True
        if mode == "visual":
            req.include_figures = True
            if req.max_figures <= 0:
                req.max_figures = 3

        outcomes, merged = _run_retrieval(req)
        cards = extract_evidence_cards(merged)
        figures = extract_figures(merged)

        if mode == "search_only":
            return {
                "ok": True,
                "mode": mode,
                "answer": None,
                "answer_note": prompts.search_only_note(),
                "evidence": merged,
                "cards": cards,
                "figures": figures,
                "debug": _debug_payload(outcomes),
            }

        handlers = {
            "gpt_like": _answer_gpt_like,
            "compare_sources": _answer_compare_sources,
            "visual": _answer_visual,
            "html_teaching": _answer_html_teaching,
        }
        result = handlers[mode](req, merged)

        return {
            "ok": result.ok,
            "mode": mode,
            "answer": result.text if result.ok else None,
            "answer_error": None if result.ok else result.error,
            "model": result.model,
            "evidence": merged,
            "cards": cards,
            "figures": figures,
            "debug": _debug_payload(outcomes),
        }
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/openai_ping")
def api_openai_ping():
    result = openai_ping()
    return {
        "ok": result.ok,
        "model": result.model,
        "text": result.text,
        "error": result.error,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        reload=False,
    )
