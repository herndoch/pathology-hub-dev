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

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

_VISUAL_QUERY = re.compile(
    r"\b("
    r"show\s+me|show|picture|pictures|photo|photos|image|images|figure|figures|"
    r"histology|histologic|microscopic|microscopy|gross|"
    r"what\s+does|look\s+like|demonstrate|illustrate|visual"
    r")\b",
    re.IGNORECASE,
)

_SOURCE_LABELS = {
    "who": "WHO",
    "textbooks": "Textbooks",
    "pathout": "Pathoutlines",
    "journals": "Journals",
    "lectures": "Lectures",
    "videos": "Videos",
    "curriculum": "Curriculum",
}

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import prompts
import secrets_helper
from openai_synthesizer import SynthesisResult, ping as openai_ping, synthesize
from figure_quality_filter import (
    filter_suppress_render_figures,
    strip_suppress_render_image_urls,
)
from pathology_backend import (
    RESULT_LIST_KEYS,
    SUPPORTED_SOURCES,
    TOPIC_PAGE_MAX_CARDS,
    TOPIC_PAGE_MAX_FIGURES,
    TOPIC_PAGE_MIN_CARDS_PER_SOURCE,
    PathologyHubClient,
    cap_cards_diverse,
    dedupe_cards,
    dedupe_figures,
    diversify_by_source_id,
    filter_cards_by_page_root,
    filter_figures_by_page_root,
    extract_evidence_cards,
    extract_figures,
    merge_outcomes,
    page_root_from_tag,
    slim_merged_from_cards,
    staged_retrieve,
    topic_page_query_variants,
)
from who_section_mentions import load_taxonomy_leaf_names, who_section_mentions

# Full source set for topic_page (ExpertPath-style reference) requests —
# always comprehensive regardless of the sidebar checkbox state, since a
# topic page is meant to summarize everything available. Excludes
# `curriculum`, which is navigation-only per BASE_GROUNDING_RULES and is
# never treated as citable evidence. Also excludes `lectures`: live-probed
# this session and confirmed the backend returns byte-identical
# `lecture_results`/`video_results` content (same chunk_ids) for either
# source name — they are the same underlying corpus, not two distinct
# families. Requesting both wastes an entire redundant backend call per query
# variant and floods the raw card pool with duplicates that `dedupe_cards`
# then has to filter back out; requesting only `videos` gets the identical
# evidence for half the cost. `lectures` remains a valid standalone choice in
# `SUPPORTED_SOURCES` for the sidebar/non-topic-page modes.
TOPIC_PAGE_SOURCES = [s for s in SUPPORTED_SOURCES if s not in ("curriculum", "lectures")]

APP_TITLE = "Pathology Hub Chat MVP"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Topic-page prepop pilot (v0_1, read-only lookup only) — see
# docs/PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md. This directory is written
# only by frontend/pathology_hub_chat_mvp/scripts/prebuild_topic_pages_pilot_v0_1.py;
# app.py never writes into it.
TOPIC_PREBUILD_PAGES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "outputs", "chat_mvp_topic_prepop_v0_1", "pages")
)
PAGE_FLAGS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "outputs", "chat_mvp_page_flags_v0_1")
)
PAGE_FLAGS_PATH = os.path.join(PAGE_FLAGS_DIR, "page_flags_v0_1.jsonl")

TOPIC_PAGE_ROOT_NARROW = os.environ.get("TOPIC_PAGE_ROOT_NARROW", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

app = FastAPI(title=APP_TITLE)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_backend_client = PathologyHubClient(api_url=os.environ.get("PATHOLOGY_HUB_API_URL"))

VALID_MODES = frozenset(
    {"gpt_like", "compare_sources", "visual", "search_only", "html_teaching", "topic_page"}
)


class SearchRequest(BaseModel):
    query: str
    sources: list[str] = Field(default_factory=lambda: ["textbooks"])
    # le=10 is NOT an arbitrary client-side guess — live-probed directly
    # against the Cloud Run backend this session (see
    # docs/CHAT_MVP_DIVERSITY_AND_LIMITS_MASTER_PLAN.md, Part 1): the backend
    # itself rejects max_results>10 with HTTP 422 for every source family. 10
    # is the real, confirmed backend ceiling. Comprehensiveness for
    # `topic_page` comes from the multi-query fan-out (more calls at 10 each),
    # not from raising this bound.
    max_results: int = Field(default=3, ge=1, le=10)
    include_figures: bool = False
    max_figures: int = Field(default=0, ge=0, le=10)
    compact: bool = True
    excerpt_char_limit: int = Field(default=900, ge=200, le=4000)
    render_html: bool = False


class ChatRequest(SearchRequest):
    mode: str = "gpt_like"
    category_context: Optional[str] = None
    page_tag: Optional[str] = None


class FlagRequest(BaseModel):
    tag: Optional[str] = None
    label: str = ""
    query: str = ""
    comment: str = ""
    page_kind: str = "topic_page"


class CompareEntity(BaseModel):
    tag: Optional[str] = None
    label: str
    query: str
    category_context: Optional[str] = None


class CompareRequest(BaseModel):
    entities: list[CompareEntity] = Field(..., min_length=2, max_length=4)


def _validate_sources(sources: list[str]) -> list[str]:
    cleaned = [s.strip().lower() for s in sources if s and s.strip()]
    unknown = sorted({s for s in cleaned if s not in SUPPORTED_SOURCES})
    if unknown:
        raise ValueError(
            f"Unsupported source(s): {unknown}. Supported: {SUPPORTED_SOURCES}"
        )
    return cleaned or ["textbooks"]


def _apply_figure_quality_filters(cards: list[dict], figures: list[dict]) -> tuple[list[dict], list[dict]]:
    """Strip/drop Tier-A suppress_render textbook images using the read-only sidecar."""
    return (
        strip_suppress_render_image_urls(cards),
        filter_suppress_render_figures(figures),
    )


def _extract_who_cross_mentions(cards: list[dict]) -> list[dict]:
    """Grounded WHO cross-entity mentions from already-fetched who cards."""
    leaves = load_taxonomy_leaf_names()
    results: list[dict] = []
    seen_leaves: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        source = str(card.get("source") or card.get("source_name") or "").lower()
        if source != "who":
            continue
        for mention in who_section_mentions(card, leaves):
            leaf = mention.get("matched_leaf")
            if not leaf or leaf in seen_leaves:
                continue
            seen_leaves.add(leaf)
            results.append(mention)
    return results


def _diversify_merged_results(merged: dict) -> None:
    """In place: round-robin re-rank every per-source result list by
    `source_id` so one dominant textbook/lecture/video doesn't crowd out
    other distinct sources covering the same topic. No-ops per list when
    there's only one distinct source_id (e.g. WHO, PathOut single-source
    families) — never drops data, only reorders."""
    for key in RESULT_LIST_KEYS:
        items = merged.get(key)
        if isinstance(items, list) and items:
            merged[key] = diversify_by_source_id(items)


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
    _diversify_merged_results(merged)
    return outcomes, merged


def _run_topic_page_retrieval(req: ChatRequest) -> tuple[list, dict, list[dict], dict]:
    """Multi-query fan-out for topic pages: 3–4 query variants × full source set,
    merged/deduped/diversified, then capped before synthesis."""
    sources = _validate_sources(req.sources)
    variants = topic_page_query_variants(req.query, req.category_context)

    def _retrieve_variant(query: str) -> dict:
        start = time.monotonic()
        outcomes = staged_retrieve(
            _backend_client,
            query,
            sources,
            max_results=req.max_results,
            include_figures=req.include_figures,
            max_figures=req.max_figures,
            compact=req.compact,
            excerpt_char_limit=req.excerpt_char_limit,
            render_html=False,
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        return {"query": query, "elapsed_ms": elapsed_ms, "outcomes": outcomes}

    with ThreadPoolExecutor(max_workers=len(variants)) as executor:
        variant_results = list(executor.map(_retrieve_variant, variants))

    all_outcomes: list = []
    variant_timing: list[dict] = []
    for result in variant_results:
        all_outcomes.extend(result["outcomes"])
        variant_timing.append(
            {
                "query": result["query"],
                "elapsed_ms": round(result["elapsed_ms"], 1),
                "source_call_count": len(result["outcomes"]),
            }
        )

    merged = merge_outcomes(all_outcomes)
    merged["query"] = req.query
    _diversify_merged_results(merged)

    raw_cards = extract_evidence_cards(merged)
    deduped_cards = dedupe_cards(raw_cards)
    raw_figures = dedupe_figures(extract_figures(merged))
    deduped_cards, raw_figures = _apply_figure_quality_filters(deduped_cards, raw_figures)
    who_cross_mentions = _extract_who_cross_mentions(deduped_cards)

    capped_cards = cap_cards_diverse(
        deduped_cards, TOPIC_PAGE_MAX_CARDS, min_per_source=TOPIC_PAGE_MIN_CARDS_PER_SOURCE
    )

    page_root = page_root_from_tag(req.page_tag)
    cards_before_root = len(capped_cards)
    if TOPIC_PAGE_ROOT_NARROW and page_root:
        capped_cards = filter_cards_by_page_root(capped_cards, page_root)

    figures = raw_figures[:TOPIC_PAGE_MAX_FIGURES]
    if TOPIC_PAGE_ROOT_NARROW and page_root:
        figures = filter_figures_by_page_root(figures, page_root)

    slim_merged = slim_merged_from_cards(merged, capped_cards)
    slim_merged["figures"] = figures

    counts_before = {}
    counts_after = {}
    for card in raw_cards:
        src = card.get("source") or "unknown"
        counts_before[src] = counts_before.get(src, 0) + 1
    for card in capped_cards:
        src = card.get("source") or "unknown"
        counts_after[src] = counts_after.get(src, 0) + 1

    retrieval_meta = {
        "multi_query": True,
        "query_variants": variants,
        "variant_timing": variant_timing,
        "cards_raw": len(raw_cards),
        "cards_deduped": len(deduped_cards),
        "cards_capped": len(capped_cards),
        "cards_cap_limit": TOPIC_PAGE_MAX_CARDS,
        "cards_by_source_before_cap": counts_before,
        "cards_by_source_after_cap": counts_after,
        "who_cross_mentions_count": len(who_cross_mentions),
        "root_narrow_enabled": TOPIC_PAGE_ROOT_NARROW,
        "page_root": page_root,
        "cards_before_root_filter": cards_before_root,
        "cards_after_root_filter": len(capped_cards),
    }
    return all_outcomes, slim_merged, capped_cards, retrieval_meta, who_cross_mentions


def _debug_payload(outcomes: list, retrieval_meta: Optional[dict] = None) -> dict:
    payload = {
        "calls": [o.to_debug_dict() for o in outcomes],
        "call_count": len(outcomes),
    }
    if retrieval_meta:
        payload.update(retrieval_meta)
    return payload


def _apply_figure_defaults(req: ChatRequest, mode: str) -> None:
    """Enable figure retrieval for visual mode, topic pages, or show-me-style queries."""
    if mode in {"visual", "topic_page"}:
        req.include_figures = True
        if req.max_figures <= 0:
            req.max_figures = 5 if mode == "visual" else 8
        return
    if mode in {"gpt_like", "compare_sources"} and _VISUAL_QUERY.search(req.query or ""):
        req.include_figures = True
        if req.max_figures <= 0:
            req.max_figures = 5


def _build_citation_link_index(cards: list[dict]) -> list[dict]:
    """Compact deduped URL index for synthesis prompts (never overwrites evidence)."""
    index: list[dict] = []
    seen: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        src = card.get("source") or "unknown"
        source_label = _SOURCE_LABELS.get(src, src)
        title = (card.get("title") or card.get("name") or card.get("heading") or "")[:120]
        for field in (
            "source_url",
            "source_page_url",
            "figure_url",
            "page_image_url",
            "image_url",
            "video_time_url",
        ):
            url = card.get(field)
            if not isinstance(url, str) or not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            index.append(
                {
                    "source": src,
                    "source_label": source_label,
                    "field": field,
                    "url": url,
                    "title": title,
                }
            )
    return index[:48]


def _evidence_for_synthesis(merged: dict, cards: list[dict]) -> dict:
    bundle = dict(merged)
    bundle["_citation_link_index"] = _build_citation_link_index(cards)
    return bundle


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


def _slugify_prebuild_tag(tag: str) -> str:
    """Must match the slug scheme used by prebuild_topic_pages_pilot_v0_1.py."""
    slug = tag.replace("::", "__")
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", slug)
    return slug


@app.get("/api/topic_prebuild")
def api_topic_prebuild(tag: str):
    """Read-only lookup of a pilot-prebuilt topic_page sidecar by tag, if one exists.

    Only ever reads from TOPIC_PREBUILD_PAGES_DIR (local pilot cache written by
    prebuild_topic_pages_pilot_v0_1.py) — never mutates anything, never touches the
    figure quality-flags sidecar or curriculum SQLite. Returns
    {"ok": False, "found": False} (HTTP 200, not an error) when nothing is
    prebuilt yet for `tag`, so the client falls back to the live
    POST /api/chat topic_page path unchanged.
    """
    if not tag or not tag.strip():
        return {"ok": False, "found": False, "error": "Missing 'tag' query param."}
    slug = _slugify_prebuild_tag(tag.strip())
    json_path = os.path.join(TOPIC_PREBUILD_PAGES_DIR, f"{slug}.json")
    if not os.path.isfile(json_path):
        return {"ok": False, "found": False, "tag": tag}
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            page = json.load(f)
    except (OSError, ValueError) as exc:
        return {"ok": False, "found": False, "tag": tag, "error": str(exc)}
    page["found"] = True
    return page


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
        "topic_page_root_narrow": TOPIC_PAGE_ROOT_NARROW,
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
            "cards": dedupe_cards(extract_evidence_cards(merged)),
            "figures": dedupe_figures(extract_figures(merged)),
            "debug": _debug_payload(outcomes),
        }
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


def _answer_gpt_like(req: ChatRequest, merged: dict, cards: list[dict]) -> SynthesisResult:
    return synthesize(
        prompts.gpt_like_system_prompt(),
        req.query,
        _evidence_for_synthesis(merged, cards),
    )


def _answer_compare_sources(req: ChatRequest, merged: dict, cards: list[dict]) -> SynthesisResult:
    sources = _validate_sources(req.sources)
    extra = f"Requested source families for this comparison: {', '.join(sources)}"
    return synthesize(
        prompts.compare_sources_system_prompt(),
        req.query,
        _evidence_for_synthesis(merged, cards),
        extra_instructions=extra,
    )


def _answer_visual(req: ChatRequest, merged: dict, cards: list[dict]) -> SynthesisResult:
    extra = f"max_figures requested: {req.max_figures}"
    return synthesize(
        prompts.visual_figures_system_prompt(),
        req.query,
        _evidence_for_synthesis(merged, cards),
        extra_instructions=extra,
    )


def _answer_topic_page(req: ChatRequest, merged: dict, cards: list[dict]) -> SynthesisResult:
    return synthesize(
        prompts.topic_page_system_prompt(),
        req.query,
        _evidence_for_synthesis(merged, cards),
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

        if mode == "topic_page":
            # A topic page is meant to be comprehensive — always request the
            # full source set, regardless of sidebar checkbox state (server
            # enforced so it holds for any caller, not just this frontend).
            req.sources = TOPIC_PAGE_SOURCES

        if mode == "html_teaching":
            req.render_html = True
        _apply_figure_defaults(req, mode)

        retrieval_meta: Optional[dict] = None
        who_cross_mentions: list[dict] = []
        if mode == "topic_page":
            outcomes, merged, cards, retrieval_meta, who_cross_mentions = _run_topic_page_retrieval(req)
            figures = extract_figures(merged)
        else:
            outcomes, merged = _run_retrieval(req)
            # dedupe_cards/dedupe_figures also fix the "lectures" and "videos"
            # source names returning byte-identical corpus content live (see
            # TOPIC_PAGE_SOURCES comment above) — matters here whenever a
            # sidebar user checks both boxes for a non-topic-page mode.
            cards = dedupe_cards(extract_evidence_cards(merged))
            figures = dedupe_figures(extract_figures(merged))
            cards, figures = _apply_figure_quality_filters(cards, figures)

        if mode == "search_only":
            return {
                "ok": True,
                "mode": mode,
                "answer": None,
                "answer_note": prompts.search_only_note(),
                "evidence": merged,
                "cards": cards,
                "figures": figures,
                "who_cross_mentions": who_cross_mentions,
                "debug": _debug_payload(outcomes, retrieval_meta),
            }

        handlers = {
            "gpt_like": _answer_gpt_like,
            "compare_sources": _answer_compare_sources,
            "visual": _answer_visual,
            "html_teaching": _answer_html_teaching,
            "topic_page": _answer_topic_page,
        }
        handler = handlers[mode]
        if mode == "html_teaching":
            result = handler(req, merged)
        else:
            result = handler(req, merged, cards)

        return {
            "ok": result.ok,
            "mode": mode,
            "answer": result.text if result.ok else None,
            "answer_error": None if result.ok else result.error,
            "model": result.model,
            "evidence": merged,
            "cards": cards,
            "figures": figures,
            "who_cross_mentions": who_cross_mentions,
            "debug": _debug_payload(outcomes, retrieval_meta),
        }
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


def _load_prebuilt_page(tag: Optional[str]) -> Optional[dict]:
    if not tag or not tag.strip():
        return None
    slug = _slugify_prebuild_tag(tag.strip())
    json_path = os.path.join(TOPIC_PREBUILD_PAGES_DIR, f"{slug}.json")
    if not os.path.isfile(json_path):
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            page = json.load(f)
        if page.get("ok") and page.get("answer_markdown"):
            return page
    except (OSError, ValueError):
        return None
    return None


def _column_text_summary(cards: list[dict], prebuilt: Optional[dict]) -> str:
    if prebuilt and isinstance(prebuilt.get("answer_markdown"), str):
        text = prebuilt["answer_markdown"]
        match = re.search(
            r"##\s*Key Facts\s*\n(.*?)(?=\n##\s|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match and match.group(1).strip():
            return match.group(1).strip()
    bullets: list[str] = []
    for card in cards[:8]:
        excerpt = (card.get("text_excerpt") or card.get("excerpt") or "").strip()
        if excerpt:
            bullets.append(f"- {excerpt[:220]}")
    return "\n".join(bullets) if bullets else "- Not covered in retrieved evidence."


@app.post("/api/flag")
def api_flag(req: FlagRequest):
    """Append-only local page feedback log (separate from figure-quality sidecar)."""
    comment = (req.comment or "").strip()
    if not comment:
        return {"ok": False, "error": "Comment is required."}
    os.makedirs(PAGE_FLAGS_DIR, exist_ok=True)
    record = {
        "schema_version": "page_flags_v0_1",
        "flag_id": str(uuid.uuid4()),
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tag": req.tag,
        "label": req.label,
        "query": req.query,
        "page_kind": req.page_kind or "topic_page",
        "comment": comment,
        "app_version": APP_TITLE,
    }
    with open(PAGE_FLAGS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"ok": True, "flag_id": record["flag_id"]}


@app.post("/api/compare")
def api_compare(req: CompareRequest):
    """Compare 2–4 diagnoses: per-entity retrieval + one grounded synthesis."""
    try:
        columns: list[dict] = []
        compare_evidence: dict = {"entities": []}
        for entity in req.entities:
            sub_req = ChatRequest(
                query=entity.query,
                mode="topic_page",
                sources=TOPIC_PAGE_SOURCES,
                category_context=entity.category_context,
                page_tag=entity.tag,
                max_results=5,
                include_figures=True,
                max_figures=8,
            )
            _apply_figure_defaults(sub_req, "topic_page")
            _outcomes, merged, cards, _meta, _mentions = _run_topic_page_retrieval(sub_req)
            figures = extract_figures(merged)
            prebuilt = _load_prebuilt_page(entity.tag)
            text_summary = _column_text_summary(cards, prebuilt)
            column = {
                "label": entity.label,
                "tag": entity.tag,
                "query": entity.query,
                "cards": cards,
                "figures": figures,
                "text_summary": text_summary,
                "prebuilt": bool(prebuilt),
            }
            columns.append(column)
            compare_evidence["entities"].append(
                {
                    "label": entity.label,
                    "tag": entity.tag,
                    "cards": cards[:24],
                    "figures": figures[:8],
                    "text_summary": text_summary,
                }
            )

        labels = " vs ".join(e.label for e in req.entities)
        synth_query = f"Compare diagnoses: {labels}"
        result = synthesize(
            prompts.compare_diagnoses_system_prompt(),
            synth_query,
            compare_evidence,
        )
        return {
            "ok": result.ok,
            "columns": columns,
            "comparison": result.text if result.ok else None,
            "comparison_error": None if result.ok else result.error,
            "model": result.model,
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
