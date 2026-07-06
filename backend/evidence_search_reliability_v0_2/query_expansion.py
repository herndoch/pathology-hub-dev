"""Governed query expansion for evidence search reliability v0_2."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .config import ExpansionConfig
from .root_inference import (
    contains_generic_override_term,
    has_required_context,
    infer_roots_from_context,
    is_blocked_root,
    normalize_text,
    root_allowed,
    tokenize,
)


@dataclass
class ExpansionResult:
    original_query: str
    effective_query: str
    expansions_applied: list[dict[str, Any]] = field(default_factory=list)
    inferred_roots: list[str] = field(default_factory=list)
    skipped_rules: list[dict[str, str]] = field(default_factory=list)
    enabled: bool = True

    def to_diagnostics(self, *, debug: bool) -> dict[str, Any] | None:
        if not debug and not self.expansions_applied:
            return None
        out: dict[str, Any] = {
            "query_expansion_v0_2": {
                "applied": bool(self.expansions_applied),
                "inferred_roots": self.inferred_roots,
            }
        }
        if debug:
            out["query_expansion_v0_2"].update(
                {
                    "original_query": self.original_query,
                    "effective_query": self.effective_query,
                    "expansions_applied": self.expansions_applied,
                    "skipped_rules": self.skipped_rules,
                }
            )
        return out


def _find_rule_token(query: str, abbreviation: str) -> bool:
    abbr = abbreviation.strip()
    if not abbr:
        return False
    pattern = rf"\b{re.escape(abbr)}\b"
    return re.search(pattern, query, flags=re.IGNORECASE) is not None


def _apply_mode(original: str, abbr: str, expansion_terms: list[str], mode: str) -> str:
    if mode == "replace_short_token":
        pattern = rf"\b{re.escape(abbr)}\b"
        replacement = expansion_terms[0]
        return re.sub(pattern, replacement, original, count=1, flags=re.IGNORECASE)
    if mode == "add_disjunction":
        joined = " OR ".join(expansion_terms)
        return f"{original} ({joined})"
    if mode == "title_boost_only":
        return original
    # append_query (default): preserve original, append expansion terms
    extra = " ".join(expansion_terms)
    return f"{original} {extra}".strip()


def expand_query(
    query: str,
    *,
    sources: list[str] | None = None,
    entity_metadata: dict[str, Any] | None = None,
    config: ExpansionConfig,
) -> ExpansionResult:
    original = (query or "").strip()
    result = ExpansionResult(original_query=original, effective_query=original, enabled=config.enabled)
    if not config.enabled or not original:
        return result

    inferred = infer_roots_from_context(
        original, sources=sources, entity_metadata=entity_metadata, config=config
    )
    result.inferred_roots = sorted(inferred)

    effective = original
    for rule in config.rules:
        if not rule.get("enabled", True):
            continue
        abbr = str(rule.get("abbreviation") or "").strip()
        if not abbr or not _find_rule_token(effective, abbr):
            continue

        expansions = [str(x).strip() for x in (rule.get("expansions") or []) if str(x).strip()]
        if not expansions:
            continue

        allowed = list(rule.get("allowed_roots") or [])
        blocked = list(rule.get("blocked_roots") or [])
        required = list(rule.get("required_context_terms") or [])
        mode = str(rule.get("expansion_mode") or "append_query")

        # A rule may declare itself safe to apply even with zero inferable organ
        # context, but ONLY when it has exactly one allowed_root (no ambiguity
        # about which root to assume). This must be resolved before the
        # root_allowed gate below, otherwise a standalone query with no organ
        # words (e.g. a bare abbreviation) always fails root_allowed first and
        # allow_standalone can never take effect.
        allow_standalone = bool(rule.get("allow_standalone")) and len(allowed) == 1
        if allow_standalone and not root_allowed(inferred, allowed):
            inferred = set(inferred) | set(allowed)
            result.inferred_roots = sorted(inferred)

        if config.root_gating_enabled and is_blocked_root(inferred, blocked):
            result.skipped_rules.append({"abbreviation": abbr, "reason": "blocked_root"})
            continue
        if config.root_gating_enabled and allowed and not root_allowed(inferred, allowed) and not allow_standalone:
            result.skipped_rules.append({"abbreviation": abbr, "reason": "root_not_allowed"})
            continue
        if required and not has_required_context(original, required) and not allow_standalone:
            result.skipped_rules.append({"abbreviation": abbr, "reason": "missing_context"})
            continue
        if mode != "title_boost_only" and contains_generic_override_term(original, config):
            # Conservative: generic carcinoma/fibroma alone should not trigger risky expansion
            if abbr.upper() in {"CMF", "CIS", "AIS", "CRC", "SSL"}:
                result.skipped_rules.append({"abbreviation": abbr, "reason": "generic_term_guard"})
                continue

        before = effective
        effective = _apply_mode(effective, abbr, expansions, mode)
        if effective != before or mode == "title_boost_only":
            result.expansions_applied.append(
                {
                    "abbreviation": abbr,
                    "expansion_mode": mode,
                    "expansion_terms": expansions,
                    "ambiguity_risk": rule.get("ambiguity_risk"),
                }
            )

    result.effective_query = re.sub(r"\s+", " ", effective).strip()
    return result
