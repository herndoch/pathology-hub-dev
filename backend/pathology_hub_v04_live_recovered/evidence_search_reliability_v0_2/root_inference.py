"""Root and organ context inference for governed query expansion."""

from __future__ import annotations

import re
from typing import Any

from .config import ExpansionConfig

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def normalize_text(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokenize(value: str) -> list[str]:
    return _TOKEN_RE.findall(value or "")


def infer_roots_from_context(
    query: str,
    *,
    sources: list[str] | None = None,
    entity_metadata: dict[str, Any] | None = None,
    config: ExpansionConfig,
) -> set[str]:
    """Infer candidate curriculum/API roots from query, sources, and optional entity hints."""
    del sources  # reserved for future source-specific root hints
    roots: set[str] = set()
    norm = normalize_text(query)
    tokens = set(tokenize(query))

    for term, root in config.organ_root_hints.items():
        if term in norm.split() or term in tokens:
            roots.add(root)

    if entity_metadata:
        if root := (entity_metadata.get("root") or "").strip():
            roots.add(root)
        organ = normalize_text(entity_metadata.get("organ_context") or "")
        for term, mapped in config.organ_root_hints.items():
            if term in organ.split():
                roots.add(mapped)

    return roots


def has_required_context(query: str, required_terms: list[str]) -> bool:
    if not required_terms:
        return True
    norm = normalize_text(query)
    tokens = set(tokenize(query))
    for term in required_terms:
        t = term.lower()
        if t in norm.split() or t in tokens or t in norm:
            return True
    return False


def is_blocked_root(inferred_roots: set[str], blocked_roots: list[str]) -> bool:
    if not blocked_roots or not inferred_roots:
        return False
    return bool(inferred_roots.intersection(set(blocked_roots)))


def root_allowed(inferred_roots: set[str], allowed_roots: list[str]) -> bool:
    if not allowed_roots:
        return True
    if not inferred_roots:
        return False
    return bool(inferred_roots.intersection(set(allowed_roots)))


def contains_generic_override_term(query: str, config: ExpansionConfig) -> bool:
    norm = normalize_text(query)
    for term in config.generic_terms_never_override_root:
        if re.search(rf"\b{re.escape(term.lower())}\b", norm):
            return True
    return False
