"""Multi-round topic-page retrieval with progress events for SSE streaming.

Round 1 — broad hub multi-query + live literature
Round 2 — gap-fill aspect queries (gross / imaging / IHC / DDx / molecular)
Round 3 — literature deepen using genes + titles found in rounds 1–2

Each step yields a progress dict suitable for `event: progress` SSE frames.
Does not call OpenAI; synthesis stays in the caller.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Generator, Optional

from literature_apis import fetch_live_literature, live_literature_enabled
from pathology_backend import (
    TOPIC_PAGE_MAX_CARDS,
    TOPIC_PAGE_MAX_FIGURES,
    TOPIC_PAGE_MIN_CARDS_PER_SOURCE,
    PathologyHubClient,
    cap_cards_diverse,
    dedupe_cards,
    dedupe_figures,
    extract_evidence_cards,
    extract_figures,
    filter_cards_by_page_root,
    filter_figures_by_page_root,
    merge_outcomes,
    page_root_from_tag,
    slim_merged_from_cards,
    staged_retrieve,
    topic_page_query_variants,
)


def iterative_enabled() -> bool:
    raw = os.environ.get("TOPIC_PAGE_ITERATIVE", "1")
    return str(raw).strip().lower() not in {"0", "false", "off", "no"}


def max_rounds() -> int:
    try:
        return max(1, min(3, int(os.environ.get("TOPIC_PAGE_ITERATIVE_ROUNDS", "3"))))
    except ValueError:
        return 3


# Aspect probes for gap-fill (round 2). Keys are coarse section families.
_GAP_ASPECTS: list[tuple[str, str, tuple[str, ...]]] = [
    ("imaging", "imaging mammogram ultrasound MRI CT radiology", ("radiology", "imaging", "mammog", "ultrasound", "mri")),
    ("gross", "gross macroscopic cut surface specimen", ("gross", "macroscopic", "cut surface", "specimen")),
    (
        "cytology",
        "cytology FNA smear cytopathology Pap",
        ("cytolog", "cytopath", "fna", "smear", "bethesda", "yokohama"),
    ),
    ("ihc", "immunohistochemistry IHC stains markers", ("ihc", "immunohistochem", "stain", "positive for")),
    ("molecular", "molecular genetics fusion mutation", ("fusion", "mutation", "molecular", "gene", "etv6", "ntrk")),
    ("ddx", "differential diagnosis distinguish from", ("differential", "versus", "distinguish", "ddx")),
]


def _blob(card: dict) -> str:
    parts = [
        card.get("title"),
        card.get("excerpt"),
        card.get("text"),
        card.get("text_excerpt"),
        card.get("section"),
        card.get("chunk_type"),
    ]
    return " ".join(str(p or "") for p in parts).lower()


def _coverage_gaps(cards: list[dict], figures: list[dict]) -> list[str]:
    """Return aspect keys that look thin in the current evidence pool."""
    all_text = " ".join(_blob(c) for c in cards if isinstance(c, dict))
    fig_text = " ".join(
        str((f or {}).get("caption") or (f or {}).get("title") or "").lower() for f in figures
    )
    combined = all_text + " " + fig_text
    gaps: list[str] = []
    for key, _suffix, needles in _GAP_ASPECTS:
        hits = sum(1 for n in needles if n in combined)
        if hits < 2:
            gaps.append(key)
    return gaps


def _retrieve_queries(
    client: PathologyHubClient,
    queries: list[str],
    sources: list[str],
    *,
    max_results: int,
    include_figures: bool,
    max_figures: int,
    compact: bool,
    excerpt_char_limit: int,
) -> tuple[list, list[dict]]:
    """Run staged_retrieve for each query; return outcomes + timing rows."""
    from concurrent.futures import ThreadPoolExecutor

    def _one(q: str) -> dict:
        start = time.monotonic()
        outcomes = staged_retrieve(
            client,
            q,
            sources,
            max_results=max_results,
            include_figures=include_figures,
            max_figures=max_figures,
            compact=compact,
            excerpt_char_limit=excerpt_char_limit,
            render_html=False,
        )
        return {
            "query": q,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
            "outcomes": outcomes,
            "source_call_count": len(outcomes),
        }

    with ThreadPoolExecutor(max_workers=max(1, len(queries))) as pool:
        rows = list(pool.map(_one, queries))
    outcomes: list = []
    timing: list[dict] = []
    for row in rows:
        outcomes.extend(row["outcomes"])
        timing.append(
            {
                "query": row["query"],
                "elapsed_ms": row["elapsed_ms"],
                "source_call_count": row["source_call_count"],
            }
        )
    return outcomes, timing


def run_iterative_topic_retrieval(
    client: PathologyHubClient,
    *,
    query: str,
    sources: list[str],
    max_results: int = 5,
    include_figures: bool = True,
    max_figures: int = 8,
    compact: bool = True,
    excerpt_char_limit: int = 900,
    page_tag: Optional[str] = None,
    category_context: Optional[str] = None,
    root_narrow: bool = True,
    apply_figure_quality: Optional[Callable[[list, list], tuple[list, list]]] = None,
    extract_who_mentions: Optional[Callable[[list], list]] = None,
    tumor_type: Optional[str] = None,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    """Yield progress events; return final retrieval bundle as the generator's value.

    Use as:
        gen = run_iterative_topic_retrieval(...)
        try:
            while True:
                ev = next(gen)
                # stream ev
        except StopIteration as stop:
            final = stop.value
    """
    rounds = max_rounds() if iterative_enabled() else 1
    yield {
        "phase": "plan",
        "status": "running",
        "label": "Planning retrieval rounds",
        "detail": f"Up to {rounds} rounds · hub sources + live literature",
        "rounds_planned": rounds,
        "live_literature": live_literature_enabled(),
    }

    all_outcomes: list = []
    variant_timing: list[dict] = []
    literature_all: list[dict] = []
    literature_providers: dict = {}
    literature_warnings: list[str] = []
    literature_filter: dict = {}
    round_summaries: list[dict] = []

    # ----- Round 1: broad -----
    variants = topic_page_query_variants(query, category_context)
    yield {
        "phase": "round",
        "round": 1,
        "status": "running",
        "label": "Round 1 — broad hub retrieval",
        "detail": f"{len(variants)} query variants × {len(sources)} sources",
        "queries": variants,
    }
    t0 = time.monotonic()
    outcomes, timing = _retrieve_queries(
        client,
        variants,
        sources,
        max_results=max_results,
        include_figures=include_figures,
        max_figures=max_figures,
        compact=compact,
        excerpt_char_limit=excerpt_char_limit,
    )
    all_outcomes.extend(outcomes)
    variant_timing.extend(timing)
    merged = merge_outcomes(all_outcomes)
    merged["query"] = query
    cards = dedupe_cards(extract_evidence_cards(merged))
    figures = dedupe_figures(extract_figures(merged))
    if apply_figure_quality:
        cards, figures = apply_figure_quality(cards, figures)

    # If the broad multi-query fan-out somehow returns nothing (transient hub
    # blip / overloaded parallel calls), retry once with the bare entity only.
    if not cards and query.strip():
        yield {
            "phase": "round",
            "round": 1,
            "status": "running",
            "label": "Round 1 — retry bare hub query",
            "detail": f"First pass empty — retrying `{query.strip()}`",
            "queries": [query.strip()],
        }
        outcomes_retry, timing_retry = _retrieve_queries(
            client,
            [query.strip()],
            sources,
            max_results=max_results,
            include_figures=include_figures,
            max_figures=max_figures,
            compact=compact,
            excerpt_char_limit=excerpt_char_limit,
        )
        all_outcomes.extend(outcomes_retry)
        variant_timing.extend(timing_retry)
        merged = merge_outcomes(all_outcomes)
        merged["query"] = query
        cards = dedupe_cards(extract_evidence_cards(merged))
        figures = dedupe_figures(extract_figures(merged))
        if apply_figure_quality:
            cards, figures = apply_figure_quality(cards, figures)

    by_source: dict[str, int] = {}
    for card in cards:
        src = str(card.get("source") or "unknown")
        by_source[src] = by_source.get(src, 0) + 1
    source_detail = " · ".join(f"{k} {v}" for k, v in sorted(by_source.items(), key=lambda kv: (-kv[1], kv[0])))
    if not source_detail:
        source_detail = "no hub cards"

    round_summaries.append(
        {
            "round": 1,
            "label": "broad",
            "queries": variants,
            "cards": len(cards),
            "figures": len(figures),
            "by_source": by_source,
            "elapsed_ms": round((time.monotonic() - t0) * 1000, 1),
        }
    )
    yield {
        "phase": "round",
        "round": 1,
        "status": "done",
        "label": "Round 1 — broad hub retrieval",
        "detail": f"{len(cards)} unique cards · {len(figures)} figures · {source_detail}",
        "cards": len(cards),
        "figures": len(figures),
        "by_source": by_source,
    }

    # Literature pass (after round 1 so genes in query still work; also before gap-fill)
    if live_literature_enabled():
        yield {
            "phase": "literature",
            "round": 1,
            "status": "running",
            "label": "Live literature — Elsevier / PubMed / OncoKB",
            "detail": f"Query: {query}",
        }
        lit = fetch_live_literature(query, max_per_provider=4, tumor_type=tumor_type)
        literature_all = list(lit.get("cards") or [])
        # Copy so later deepen rounds can annotate without mutating provider payloads.
        literature_providers = dict(lit.get("providers") or {})
        literature_warnings = list(lit.get("warnings") or [])
        literature_filter = lit.get("filter") or {}
        yield {
            "phase": "literature",
            "round": 1,
            "status": "done",
            "label": "Live literature — Elsevier / PubMed / OncoKB",
            "detail": (
                f"{len(literature_all)} on-topic literature cards"
                + (
                    f" · filtered {lit.get('dropped_offtopic', 0)} off-target"
                    if lit.get("dropped_offtopic")
                    else ""
                )
            ),
            "cards": len(literature_all),
            "providers": {
                k: {"ok": v.get("ok"), "returned": v.get("returned"), "total": v.get("total")}
                for k, v in literature_providers.items()
            },
            "filter": literature_filter,
        }

    # ----- Round 2: gap fill -----
    if rounds >= 2:
        gaps = _coverage_gaps(cards, figures)
        gap_queries = [f"{query} {suffix}" for key, suffix, _ in _GAP_ASPECTS if key in gaps][:4]
        if not gap_queries:
            gap_queries = [f"{query} differential diagnosis", f"{query} immunohistochemistry"]
        yield {
            "phase": "round",
            "round": 2,
            "status": "running",
            "label": "Round 2 — gap-fill aspects",
            "detail": f"Gaps: {', '.join(gaps) or 'none (running safety probes)'} · {len(gap_queries)} queries",
            "gaps": gaps,
            "queries": gap_queries,
        }
        t0 = time.monotonic()
        outcomes2, timing2 = _retrieve_queries(
            client,
            gap_queries,
            sources,
            max_results=max_results,
            include_figures=include_figures,
            max_figures=max_figures,
            compact=compact,
            excerpt_char_limit=excerpt_char_limit,
        )
        all_outcomes.extend(outcomes2)
        variant_timing.extend(timing2)
        merged = merge_outcomes(all_outcomes)
        merged["query"] = query
        before = len(cards)
        cards = dedupe_cards(extract_evidence_cards(merged))
        figures = dedupe_figures(extract_figures(merged))
        if apply_figure_quality:
            cards, figures = apply_figure_quality(cards, figures)
        round_summaries.append(
            {
                "round": 2,
                "label": "gap_fill",
                "queries": gap_queries,
                "gaps": gaps,
                "cards": len(cards),
                "cards_added": max(0, len(cards) - before),
                "figures": len(figures),
                "elapsed_ms": round((time.monotonic() - t0) * 1000, 1),
            }
        )
        yield {
            "phase": "round",
            "round": 2,
            "status": "done",
            "label": "Round 2 — gap-fill aspects",
            "detail": f"+{max(0, len(cards) - before)} cards · now {len(cards)} unique",
            "cards": len(cards),
            "cards_added": max(0, len(cards) - before),
        }

    # ----- Round 3: literature deepen -----
    if rounds >= 3 and live_literature_enabled():
        from literature_apis import extract_genes

        genes = []
        for c in cards + literature_all:
            genes.extend(extract_genes(_blob(c) if isinstance(c, dict) else ""))
        genes = list(dict.fromkeys(genes))[:3]
        deepen_q = query
        if genes:
            deepen_q = f"{query} {' '.join(genes)}"
        # Prefer a review/clinicopathologic slant for deepen
        deepen_queries = [deepen_q, f"{query} clinicopathologic review"]
        yield {
            "phase": "literature",
            "round": 3,
            "status": "running",
            "label": "Round 3 — deepen literature",
            "detail": f"Refined: {deepen_q}" + (f" · genes {', '.join(genes)}" if genes else ""),
            "queries": deepen_queries,
            "genes": genes,
        }
        t0 = time.monotonic()
        before_lit = len(literature_all)
        seen_keys = {
            ((c.get("doi") or "").lower() or (c.get("title") or "").strip().lower())
            for c in literature_all
        }
        for dq in deepen_queries:
            lit = fetch_live_literature(dq, max_per_provider=3, tumor_type=tumor_type)
            for k, v in list((lit.get("providers") or {}).items()):
                literature_providers[f"r3_{k}"] = v
            literature_warnings.extend(lit.get("warnings") or [])
            for c in lit.get("cards") or []:
                key = ((c.get("doi") or "").lower() or (c.get("title") or "").strip().lower())
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    literature_all.append(c)
        round_summaries.append(
            {
                "round": 3,
                "label": "literature_deepen",
                "queries": deepen_queries,
                "genes": genes,
                "literature_added": max(0, len(literature_all) - before_lit),
                "literature_total": len(literature_all),
                "elapsed_ms": round((time.monotonic() - t0) * 1000, 1),
            }
        )
        yield {
            "phase": "literature",
            "round": 3,
            "status": "done",
            "label": "Round 3 — deepen literature",
            "detail": f"+{max(0, len(literature_all) - before_lit)} literature · now {len(literature_all)}",
            "cards_added": max(0, len(literature_all) - before_lit),
            "cards": len(literature_all),
        }

    # Cap / root-narrow hub cards; keep literature separate then append
    hub_cards = [c for c in cards if (c.get("source") or "") != "literature"]
    capped = cap_cards_diverse(
        hub_cards, TOPIC_PAGE_MAX_CARDS, min_per_source=TOPIC_PAGE_MIN_CARDS_PER_SOURCE
    )
    page_root = page_root_from_tag(page_tag)
    cards_before_root = len(capped)
    if root_narrow and page_root:
        capped = filter_cards_by_page_root(capped, page_root)
    figures = figures[:TOPIC_PAGE_MAX_FIGURES]
    if root_narrow and page_root:
        figures = filter_figures_by_page_root(figures, page_root)

    literature_cards = literature_all[:10]
    final_cards = list(capped) + literature_cards

    who_cross_mentions: list = []
    if extract_who_mentions:
        who_cross_mentions = extract_who_mentions(final_cards)

    slim = slim_merged_from_cards(merged, capped)
    slim["figures"] = figures
    slim["literature_results"] = literature_cards

    counts_after: dict[str, int] = {}
    for card in final_cards:
        src = card.get("source") or "unknown"
        counts_after[src] = counts_after.get(src, 0) + 1

    meta = {
        "multi_query": True,
        "iterative": True,
        "iterative_rounds": rounds,
        "round_summaries": round_summaries,
        "query_variants": [t["query"] for t in variant_timing],
        "variant_timing": variant_timing,
        "cards_capped": len(final_cards),
        "cards_cap_limit": TOPIC_PAGE_MAX_CARDS,
        "cards_by_source_after_cap": counts_after,
        "who_cross_mentions_count": len(who_cross_mentions),
        "root_narrow_enabled": root_narrow,
        "page_root": page_root,
        "cards_before_root_filter": cards_before_root,
        "cards_after_root_filter": len(capped),
        "live_literature_enabled": live_literature_enabled(),
        "literature_count": len(literature_cards),
        "literature_providers": literature_providers,
        "literature_warnings": literature_warnings,
        "literature_filter": literature_filter,
    }

    yield {
        "phase": "assemble",
        "status": "done",
        "label": "Assembled evidence bundle",
        "detail": f"{len(final_cards)} cards for synthesis ({len(literature_cards)} literature)",
        "cards": len(final_cards),
        "literature": len(literature_cards),
    }

    return {
        "outcomes": all_outcomes,
        "merged": slim,
        "cards": final_cards,
        "figures": figures,
        "literature": literature_cards,
        "retrieval_meta": meta,
        "who_cross_mentions": who_cross_mentions,
    }
