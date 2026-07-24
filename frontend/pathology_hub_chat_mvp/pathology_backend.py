"""Thin client for the live Pathology Hub `searchEvidence` API.

This module makes ZERO assumptions that require changing backend behavior.
It only calls the single supported operation:

    POST /evidence/search   (operationId: searchEvidence)

It is intentionally defensive about response shape: the live schema is
`additionalProperties: true`, and different backend versions have used
per-source keys such as `who_results`, `textbook_results`, `journal_results`,
`pathout_results`, `lecture_results`, `video_results`, `curriculum_results`,
as well as `figures`, `source_status`, `warnings`, `search_mode`,
`curriculum_status`, `query_expansion_applied`, and (when render_html=true)
`html_result`.

Do not add new backend operations here. Do not mutate GCS or Cloud Run.
"""

from __future__ import annotations

import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Optional

import requests

from secrets_helper import get_pathology_hub_api_key

DEFAULT_API_URL = "https://pathology-hub-v04-vorn5q2kga-uc.a.run.app"
SEARCH_PATH = "/evidence/search"
HEALTH_PATH = "/health"

SUPPORTED_SOURCES = [
    "who",
    "textbooks",
    "journals",
    "pathout",
    "lectures",
    "videos",
    "curriculum",
]

RESULT_LIST_KEYS = [
    "who_results",
    "textbook_results",
    "journal_results",
    "pathout_results",
    "lecture_results",
    "video_results",
    "curriculum_results",
    "results",
]

DEFAULT_TIMEOUT_SECONDS = 60

# Topic-page multi-query fan-out: each variant runs the full source set in
# parallel, then results are deduped/diversified and capped before synthesis.
TOPIC_PAGE_QUERY_ASPECTS = (
    "histology microscopic morphology",
    "immunohistochemistry IHC ancillary molecular",
    "differential diagnosis",
)
TOPIC_PAGE_MAX_QUERY_VARIANTS = 4

# --- Limits, measured live (see docs/CHAT_MVP_DIVERSITY_AND_LIMITS_MASTER_PLAN.md) ---
#
# `max_results` (SearchRequest in app.py, `le=10`): NOT arbitrary. Live-probed
# directly against the Cloud Run backend (bypassing the client Pydantic bound
# entirely) with max_results=11..100 across every supported source family —
# the backend itself returns HTTP 422 `{"le": 10}` for every value above 10,
# for every source. 10 is the real backend ceiling, not a client guess; do not
# raise the client bound without first re-probing the live backend, since
# raising it will just convert to backend 422s.
#
# `TOPIC_PAGE_MAX_CARDS`/`TOPIC_PAGE_MAX_FIGURES`: WAS conservative. Measured
# live for two real topic-page probes ("ovarian high-grade serous carcinoma",
# "salivary mucoepidermoid carcinoma") at the old cap of 72: the full
# deduped/diversified evidence bundle was ~248k-255k JSON chars (~62k-64k
# approx tokens by len//4). The configured OPENAI_MODEL (gpt-4.1-mini) has a
# published 1,047,576-token context window (OpenAI API docs, verified during
# this session) — 62k-64k tokens is under 7% of that budget. The real
# deduped card count for both probes was only ~106-112 (well under a new
# 120 cap), and raw figures deduped to ~39-50 (well under a new 40 cap) — so
# raising these caps costs a modest amount of synthesis latency/$ (more input
# tokens) but does NOT approach the model's real context ceiling, and stops
# truncating evidence that was already unique and relevant. Re-probe if a
# future OPENAI_MODEL choice has a materially smaller context window.
TOPIC_PAGE_MAX_CARDS = 120
TOPIC_PAGE_MAX_FIGURES = 40

# Minimum cards guaranteed per source family (that has >=1 result) before the
# remaining cap budget is filled by round-robin relevance order in
# `cap_cards_diverse`. Protects thinner families (e.g. journals, videos) from
# being crowded out by a dominant family (e.g. PathOut/WHO) when the raw pool
# is heavily skewed — see cap_cards_diverse() docstring.
TOPIC_PAGE_MIN_CARDS_PER_SOURCE = 8

_RESULT_KEY_TO_SOURCE = {
    "who_results": "who",
    "textbook_results": "textbooks",
    "journal_results": "journals",
    "pathout_results": "pathout",
    "lecture_results": "lectures",
    "video_results": "videos",
    "curriculum_results": "curriculum",
    "results": "unknown",
}
_SOURCE_TO_RESULT_KEY = {v: k for k, v in _RESULT_KEY_TO_SOURCE.items() if k != "results"}


@dataclass
class SearchOutcome:
    """A single call to /evidence/search, with everything the debug panel needs."""

    request_payload: dict
    url: str
    status_code: Optional[int]
    ok: bool
    elapsed_ms: float
    response_json: Optional[dict] = None
    error: Optional[str] = None
    api_key_present: bool = False

    def to_debug_dict(self) -> dict:
        """Everything safe to show in the debug panel. Never includes the API key."""
        body = self.response_json or {}
        return {
            "url": self.url,
            "request_payload": self.request_payload,
            "status_code": self.status_code,
            "ok": self.ok,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "error": self.error,
            "api_key_present": self.api_key_present,
            "source_status": body.get("source_status") if isinstance(body, dict) else None,
            "warnings": body.get("warnings") if isinstance(body, dict) else None,
            "query_expansion_applied": body.get("query_expansion_applied")
            if isinstance(body, dict)
            else None,
            "curriculum_status": body.get("curriculum_status") if isinstance(body, dict) else None,
            "schema_version": body.get("schema_version") if isinstance(body, dict) else None,
        }


class PathologyHubClient:
    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.api_url = (api_url or DEFAULT_API_URL).rstrip("/")
        self._api_key = api_key

    def _resolve_api_key(self) -> Optional[str]:
        if self._api_key:
            return self._api_key
        return get_pathology_hub_api_key()

    def search(
        self,
        query: str,
        sources: Optional[list[str]] = None,
        max_results: int = 3,
        include_figures: bool = False,
        max_figures: int = 0,
        compact: bool = True,
        excerpt_char_limit: int = 900,
        render_html: bool = False,
        extra_fields: Optional[dict] = None,
    ) -> SearchOutcome:
        """Call POST /evidence/search exactly once (one backend operation only)."""
        payload: dict[str, Any] = {
            "query": query,
            "sources": sources if sources else ["textbooks"],
            "max_results": max_results,
            "include_figures": include_figures,
            "max_figures": max_figures,
            "compact": compact,
            "excerpt_char_limit": excerpt_char_limit,
        }
        if render_html:
            payload["render_html"] = True
        if extra_fields:
            payload.update(extra_fields)

        api_key = self._resolve_api_key()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key

        url = f"{self.api_url}{SEARCH_PATH}"
        start = time.monotonic()
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            try:
                body = resp.json()
            except ValueError:
                body = None
            return SearchOutcome(
                request_payload=payload,
                url=url,
                status_code=resp.status_code,
                ok=resp.ok,
                elapsed_ms=elapsed_ms,
                response_json=body if isinstance(body, dict) else None,
                error=None if resp.ok else f"HTTP {resp.status_code}: {resp.text[:500]}",
                api_key_present=bool(api_key),
            )
        except requests.RequestException as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            return SearchOutcome(
                request_payload=payload,
                url=url,
                status_code=None,
                ok=False,
                elapsed_ms=elapsed_ms,
                response_json=None,
                error=f"{type(exc).__name__}: {exc}",
                api_key_present=bool(api_key),
            )

    def health(self) -> dict:
        api_key = self._resolve_api_key()
        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key
        url = f"{self.api_url}{HEALTH_PATH}"
        start = time.monotonic()
        try:
            resp = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)
            elapsed_ms = (time.monotonic() - start) * 1000
            try:
                body = resp.json()
            except ValueError:
                body = {"raw_text": resp.text[:500]}
            return {
                "url": url,
                "status_code": resp.status_code,
                "ok": resp.ok,
                "elapsed_ms": round(elapsed_ms, 1),
                "body": body,
            }
        except requests.RequestException as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            return {
                "url": url,
                "status_code": None,
                "ok": False,
                "elapsed_ms": round(elapsed_ms, 1),
                "error": f"{type(exc).__name__}: {exc}",
            }


def staged_retrieve(
    client: PathologyHubClient,
    query: str,
    sources: list[str],
    max_results: int = 3,
    include_figures: bool = False,
    max_figures: int = 0,
    compact: bool = True,
    excerpt_char_limit: int = 900,
    render_html: bool = False,
) -> list[SearchOutcome]:
    """Call POST /evidence/search once per requested source (still the single
    supported backend operation — this just fans the same call out
    concurrently instead of one-at-a-time, since each source's request is
    independent and `requests` is synchronous). Order of the returned list
    always matches the order of `sources`."""
    sources = sources or ["textbooks"]
    if render_html or len(sources) <= 1:
        return [
            client.search(
                query=query,
                sources=sources,
                max_results=max_results,
                include_figures=include_figures,
                max_figures=max_figures,
                compact=compact,
                excerpt_char_limit=excerpt_char_limit,
                render_html=render_html,
            )
        ]

    def _search_one(source: str) -> SearchOutcome:
        return client.search(
            query=query,
            sources=[source],
            max_results=max_results,
            include_figures=include_figures,
            max_figures=max_figures,
            compact=compact,
            excerpt_char_limit=excerpt_char_limit,
            render_html=False,
        )

    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        return list(executor.map(_search_one, sources))


def page_tag_segments(page_tag: Optional[str]) -> dict[str, Any]:
    """Parse browse leaf tag into root/subcategory/leaf metadata."""
    if not isinstance(page_tag, str) or not page_tag.strip():
        return {}
    parts = [p.strip() for p in page_tag.split("::") if p.strip()]
    if not parts:
        return {}
    return {
        "root": normalize_root_token(parts[0]),
        "subcategory": parts[1] if len(parts) > 1 else "",
        "leaf": parts[-1],
        "path_lower": page_tag.casefold(),
        "is_benign": any("benign" in p.casefold() for p in parts),
    }


def topic_page_disambiguated_query(
    entity_name: str,
    category_context: Optional[str] = None,
    page_tag: Optional[str] = None,
) -> str:
    """Build a retrieval query anchored to the browse leaf, not the bare label.

    Ambiguous names like 'Pleomorphic Adenoma' exist in breast, salivary, skin,
    etc. When `page_tag` / `category_context` are present, append organ/site
    tokens so semantic search prefers the intended entity.
    """
    base = (entity_name or "").strip()
    if not base:
        return base

    parts: list[str] = [base]
    context = (category_context or "").strip()
    if context:
        parts.append(context.replace(">", " ").replace("_", " "))
    seg = page_tag_segments(page_tag)
    if seg.get("subcategory"):
        sub = seg["subcategory"].replace("_", " ")
        joined = " ".join(parts).casefold()
        if sub.casefold() not in joined:
            parts.append(sub)
    if seg.get("root") == "hn" and "salivary" not in " ".join(parts).casefold():
        parts.append("salivary gland parotid")
    return " ".join(parts)


def topic_page_query_variants(
    entity_name: str,
    category_context: Optional[str] = None,
    page_tag: Optional[str] = None,
) -> list[str]:
    """Derive up to 4 parallel query variants from a leaf entity label.

    Variants are programmatic (not per-disease hardcoded): base entity name,
    then aspect-specific suffixes for histology, ancillary/IHC, and DDx.
    Optional browse category context enriches short entity names.
    """
    enriched = topic_page_disambiguated_query(entity_name, category_context, page_tag)
    if not enriched:
        return [enriched]

    variants: list[str] = []
    seen: set[str] = set()
    for candidate in (enriched, *(f"{enriched} {aspect}" for aspect in TOPIC_PAGE_QUERY_ASPECTS)):
        normalized = candidate.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        variants.append(candidate.strip())

    return variants[:TOPIC_PAGE_MAX_QUERY_VARIANTS]


def card_identity_key(card: dict) -> Optional[str]:
    """Best-effort stable key for deduping evidence cards across query variants."""
    if not isinstance(card, dict):
        return None

    for field in ("chunk_id", "record_id", "vector_id"):
        value = card.get(field)
        if isinstance(value, str) and value.strip():
            return f"id:{value.strip()}"

    for field in (
        "source_url",
        "video_time_url",
        "figure_url",
        "page_image_url",
        "source_page_url",
        "video_url",
    ):
        value = card.get(field)
        if isinstance(value, str) and value.strip().startswith("http"):
            return f"url:{value.strip()}"

    title = (card.get("title") or card.get("name") or card.get("heading") or "").strip()
    source = str(card.get("source") or "")
    source_id = str(card.get("source_id") or "")
    excerpt = (card.get("text_excerpt") or card.get("excerpt") or "")[:80]
    if title or excerpt:
        blob = f"{source}|{source_id}|{title}|{excerpt}".lower()
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
        return f"hash:{digest}"

    return None


def dedupe_cards(cards: list[dict]) -> list[dict]:
    """Drop duplicate cards (by chunk_id/url/title hash), preserving first-seen order."""
    if not cards:
        return cards

    seen: set[str] = set()
    result: list[dict] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        key = card_identity_key(card)
        if key is None:
            result.append(card)
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(card)
    return result


def _is_video_card(card: dict) -> bool:
    source = str(card.get("source") or card.get("_result_key") or "")
    return source in ("videos", "lectures") or bool(card.get("video_id"))


def video_card_key(card: dict) -> Optional[str]:
    video_id = card.get("video_id")
    if isinstance(video_id, str) and video_id.strip():
        vid = video_id.strip()
        looks_like_path_blob = (
            vid.lower().startswith("gcs_gs_")
            or vid.lower().endswith("lecture_chunks")
            or "/" in vid
        )
        if not looks_like_path_blob:
            return vid
    title = card.get("title")
    if isinstance(title, str) and title.strip():
        return f"title:{title.strip()}"
    for field in ("chunk_id", "video_id"):
        value = card.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def dedupe_video_cards(cards: list[dict]) -> list[dict]:
    """Collapse lecture/video chunks that share the same parent video_id."""
    if not cards:
        return cards
    seen: set[str] = set()
    result: list[dict] = []
    for card in cards:
        if not isinstance(card, dict) or not _is_video_card(card):
            continue
        key = video_card_key(card)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(card)
    return result


def collapse_video_cards_for_citations(cards: list[dict]) -> list[dict]:
    """Keep first video chunk per video_id; pass through all non-video cards."""
    if not cards:
        return cards
    seen: set[str] = set()
    result: list[dict] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        if not _is_video_card(card):
            result.append(card)
            continue
        key = video_card_key(card)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(card)
    return result


def cap_cards_diverse(
    cards: list[dict],
    max_cards: int,
    min_per_source: int = 0,
) -> list[dict]:
    """Cap total cards while round-robin preserving source-family diversity.

    Plain round-robin (default `min_per_source=0`) already gives each present
    source family a roughly equal share, as long as `max_cards` is not tiny
    relative to the number of families — verified live: a 6-source ovarian
    HGSC probe with a heavily skewed raw pool (videos 160 raw vs who 20 raw)
    still capped down to a near-even ~14-15 cards per family. `min_per_source`
    makes that guarantee explicit and enforced up front instead of only
    emerging implicitly from interleave order: each source family with at
    least one result is first given up to `min_per_source` cards (capped by
    how many it actually has, and by the remaining budget), *before* the
    standard round-robin spends whatever budget is left. This only changes
    behavior from plain round-robin when a family would otherwise be
    shortchanged early (e.g. a very small `max_cards` relative to the number
    of families, or a family whose cards happen to sort later in `cards`).
    Never drops data beyond `max_cards`; never fabricates cards for an empty
    family.
    """
    if not cards or len(cards) <= max_cards:
        return cards

    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for card in cards:
        source = str(card.get("source") or "unknown")
        if source not in groups:
            groups[source] = []
            order.append(source)
        groups[source].append(card)

    capped: list[dict] = []
    if min_per_source > 0:
        for src in order:
            if len(capped) >= max_cards:
                break
            bucket = groups[src]
            take = min(min_per_source, len(bucket), max_cards - len(capped))
            for _ in range(take):
                capped.append(bucket.pop(0))

    while len(capped) < max_cards and any(groups[src] for src in order):
        for src in order:
            bucket = groups[src]
            if bucket and len(capped) < max_cards:
                capped.append(bucket.pop(0))
    return capped


def dedupe_figures(figures: list[dict]) -> list[dict]:
    """Drop duplicate figures by image/figure URL."""
    if not figures:
        return figures

    seen: set[str] = set()
    result: list[dict] = []
    for figure in figures:
        if not isinstance(figure, dict):
            continue
        key = None
        for field in ("figure_url", "image_url", "page_image_url"):
            value = figure.get(field)
            if isinstance(value, str) and value.strip().startswith("http"):
                key = value.strip()
                break
        if key is None:
            result.append(figure)
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(figure)
    return result


def slim_merged_from_cards(base_merged: dict, capped_cards: list[dict]) -> dict:
    """Rebuild per-source result lists from a capped card set for synthesis."""
    slim: dict[str, Any] = {
        "schema_version": base_merged.get("schema_version"),
        "query": base_merged.get("query"),
        "source_status": dict(base_merged.get("source_status") or {}),
        "warnings": list(base_merged.get("warnings") or []),
        "figures": list(base_merged.get("figures") or []),
        "query_expansion_applied": base_merged.get("query_expansion_applied"),
        "curriculum_status": base_merged.get("curriculum_status"),
    }
    for key in RESULT_LIST_KEYS:
        slim[key] = []

    for card in capped_cards:
        if not isinstance(card, dict):
            continue
        result_key = card.get("_result_key")
        if not isinstance(result_key, str) or result_key not in slim:
            source = card.get("source")
            result_key = _SOURCE_TO_RESULT_KEY.get(source)
        if not result_key or result_key not in slim:
            continue
        clean = {k: v for k, v in card.items() if not str(k).startswith("_")}
        slim[result_key].append(clean)

    if base_merged.get("html_result"):
        slim["html_result"] = base_merged.get("html_result")

    return slim


def diversify_by_source_id(items: list[dict], key: str = "source_id") -> list[dict]:
    """Round-robin re-rank a result list by `key` (default `source_id`) so a
    single dominant source doesn't crowd out other distinct sources covering
    the same topic. Never drops any item — only reorders. Each source's own
    relative rank order is preserved; sources are then interleaved one-per-
    round. No-ops (returns the input unchanged) if there's 0 or 1 distinct
    values for `key`, or if items aren't dicts."""
    if not items or not isinstance(items, list):
        return items

    groups: dict[Any, list[dict]] = {}
    order: list[Any] = []
    for item in items:
        group_key = item.get(key) if isinstance(item, dict) else None
        if group_key not in groups:
            groups[group_key] = []
            order.append(group_key)
        groups[group_key].append(item)

    if len(order) <= 1:
        return items

    result: list[dict] = []
    while any(groups[group_key] for group_key in order):
        for group_key in order:
            bucket = groups[group_key]
            if bucket:
                result.append(bucket.pop(0))
    return result


def merge_outcomes(outcomes: list[SearchOutcome]) -> dict:
    """Merge multiple staged SearchOutcome response bodies into one evidence bundle."""
    merged: dict[str, Any] = {
        "schema_version": None,
        "query": None,
        "source_status": {},
        "warnings": [],
        "figures": [],
        "query_expansion_applied": False,
        "curriculum_status": None,
    }

    for outcome in outcomes:
        body = outcome.response_json if isinstance(outcome.response_json, dict) else {}

        if merged["schema_version"] is None:
            merged["schema_version"] = body.get("schema_version")
        if merged["query"] is None:
            merged["query"] = body.get("query")

        for k, v in (body.get("source_status") or {}).items():
            existing = merged["source_status"].get(k)
            if v == "not_requested" and existing not in (None, "not_requested"):
                continue
            merged["source_status"][k] = v

        merged["warnings"].extend(body.get("warnings") or [])
        if outcome.error:
            merged["warnings"].append(f"request_error: {outcome.error}")

        merged["figures"].extend(body.get("figures") or [])
        if body.get("query_expansion_applied"):
            merged["query_expansion_applied"] = True
        if body.get("curriculum_status") and not merged["curriculum_status"]:
            merged["curriculum_status"] = body.get("curriculum_status")

        for key in RESULT_LIST_KEYS:
            if key in body and isinstance(body[key], list):
                merged.setdefault(key, []).extend(body[key])

        if body.get("html_result"):
            merged["html_result"] = body.get("html_result")

    return merged


def extract_evidence_cards(response_json: dict) -> list[dict]:
    key_to_source = _RESULT_KEY_TO_SOURCE
    cards: list[dict] = []
    if not isinstance(response_json, dict):
        return cards

    for key, inferred_source in key_to_source.items():
        items = response_json.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            card = dict(item)
            card.setdefault("source", inferred_source)
            card["_result_key"] = key
            cards.append(card)

    generic = response_json.get("results")
    if isinstance(generic, list):
        for item in generic:
            if not isinstance(item, dict):
                continue
            card = dict(item)
            card.setdefault("source", card.get("source") or "unknown")
            card["_result_key"] = "results"
            cards.append(card)

    return cards


def extract_figures(response_json: dict) -> list[dict]:
    if not isinstance(response_json, dict):
        return []
    figures = response_json.get("figures")
    return list(figures) if isinstance(figures, list) else []


_ROOT_FILTERABLE_SOURCES = frozenset({"textbooks", "pathout", "videos"})


def normalize_root_token(token: str) -> str:
    """Case/punctuation-insensitive root token for cross-field matching."""
    return re.sub(r"[^a-z0-9]+", "", (token or "").casefold())


def card_root_token(card: dict) -> Optional[str]:
    """Detect organ/root from primary_tag or textbook/video source_id prefix."""
    primary_tag = card.get("primary_tag")
    if isinstance(primary_tag, str) and primary_tag.strip():
        return normalize_root_token(primary_tag.split("::", 1)[0])
    source_id = card.get("source_id")
    if isinstance(source_id, str) and "_" in source_id:
        return normalize_root_token(source_id.split("_", 1)[0])
    return None


def page_root_from_tag(tag: Optional[str]) -> Optional[str]:
    if not isinstance(tag, str) or "::" not in tag:
        return None
    return normalize_root_token(tag.split("::", 1)[0])


_ROOT_CONFLICT_TERMS: dict[str, frozenset[str]] = {
    "hn": frozenset({"breast", "mammary", "cyto_breast", "lacrimal", "conjunctival"}),
    "breast": frozenset({"salivary", "parotid", "submandibular", "sublingual"}),
    "gu": frozenset({"breast", "mammary", "salivary", "parotid"}),
    "skin": frozenset({"uveal", "conjunctival", "lacrimal"}),
}

_BENIGN_EXCLUDE_TERMS = (
    "carcinosarcoma",
    "carcinoma ex pleomorphic",
    "carcinoma ex mixed",
    "adenocarcinoma",
    "malignant transformation",
)


def _text_blob(*values: Any) -> str:
    return " ".join(str(v) for v in values if v).casefold()


def filter_cards_by_page_tag(cards: list[dict], page_tag: Optional[str]) -> list[dict]:
    """Stricter than root-only filter: drop cross-organ tagged cards and text."""
    seg = page_tag_segments(page_tag)
    if not seg:
        return cards
    target_root = seg["root"]
    conflicts = _ROOT_CONFLICT_TERMS.get(target_root, frozenset())
    organ_hints = {
        "hn": ("salivary", "parotid", "submandibular", "sublingual", "minor salivary"),
        "breast": ("breast", "mammary", "nipple"),
        "gu": ("prostate", "kidney", "renal", "bladder", "testis"),
        "skin": ("skin", "cutaneous", "dermal"),
    }.get(target_root, ())

    kept: list[dict] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        primary_tag = card.get("primary_tag")
        if isinstance(primary_tag, str) and "::" in primary_tag:
            pt_root = normalize_root_token(primary_tag.split("::", 1)[0])
            if pt_root and pt_root != target_root:
                continue

        blob = _text_blob(
            card.get("title"),
            card.get("heading"),
            card.get("text_excerpt"),
            card.get("excerpt"),
            card.get("entity_name"),
        )
        if conflicts and any(term in blob for term in conflicts):
            if not any(hint in blob for hint in organ_hints):
                continue
        if seg.get("is_benign") and any(term in blob for term in _BENIGN_EXCLUDE_TERMS):
            continue
        kept.append(card)
    return kept


def filter_figures_by_entity_match(
    figures: list[dict],
    page_tag: Optional[str],
) -> list[dict]:
    """Keep figures whose WHO entity/title matches the browse leaf diagnosis."""
    seg = page_tag_segments(page_tag)
    if not seg:
        return figures
    leaf = seg["leaf"].replace("_", " ").casefold()
    leaf_words = [w for w in re.split(r"[_\s]+", leaf) if len(w) > 3]
    kept: list[dict] = []
    for fig in figures:
        if not isinstance(fig, dict):
            continue
        blob = _text_blob(fig.get("entity_name"), fig.get("title"), fig.get("caption"))
        if seg.get("is_benign") and any(term in blob for term in _BENIGN_EXCLUDE_TERMS):
            continue
        if leaf in blob:
            kept.append(fig)
            continue
        if leaf_words and all(word in blob for word in leaf_words):
            kept.append(fig)
            continue
    return kept


def filter_cards_by_page_root(cards: list[dict], page_root: Optional[str]) -> list[dict]:
    """Post-retrieval root filter (B8): keep WHO/journals; narrow textbooks/pathout/videos."""
    if not page_root:
        return cards
    target = normalize_root_token(page_root)
    if not target:
        return cards

    kept: list[dict] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        src = str(card.get("source") or "")
        if src not in _ROOT_FILTERABLE_SOURCES:
            kept.append(card)
            continue
        card_root = card_root_token(card)
        if card_root is None:
            if src == "videos":
                continue
            kept.append(card)
            continue
        if card_root == target:
            kept.append(card)
    return kept


def filter_figures_by_page_root(figures: list[dict], page_root: Optional[str]) -> list[dict]:
    if not page_root:
        return figures
    target = normalize_root_token(page_root)
    if not target:
        return figures
    kept: list[dict] = []
    for fig in figures:
        if not isinstance(fig, dict):
            continue
        sid = fig.get("source_id")
        if isinstance(sid, str) and "_" in sid:
            if normalize_root_token(sid.split("_", 1)[0]) == target:
                kept.append(fig)
            continue
        # Untagged figures are only kept for WHO (entity match handled separately).
        if str(fig.get("source") or "") == "who":
            kept.append(fig)
    return kept
