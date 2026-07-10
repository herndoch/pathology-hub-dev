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
    key_to_source = {
        "who_results": "who",
        "textbook_results": "textbooks",
        "journal_results": "journals",
        "pathout_results": "pathout",
        "lecture_results": "lectures",
        "video_results": "videos",
        "curriculum_results": "curriculum",
    }
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
