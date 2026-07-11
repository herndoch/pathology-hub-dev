"""Prototype/spike: WHO section-scoped multi-entity mention extraction.

NOT wired into the live UI/synthesis pipeline. Pure text processing on
already-fetched `who_results[]` card excerpts from `POST /evidence/search`
(no new backend operation). See
docs/CHAT_MVP_DIVERSITY_AND_LIMITS_MASTER_PLAN.md ("Part 2") for the live
probe findings that motivated this module's design.

Live-probed finding (this session): WHO cards are already pre-chunked by the
backend at a per-entity, per-section granularity — every `who_results[]` item
carries `entity_name` and `section` fields (e.g. `section` in {"core",
"microscopic", "related_terminology", "differential_diagnosis", "subtypes",
...}), and this survives `compact=True`. Excerpts are short (a few hundred
chars observed, well under the 4000-char `excerpt_char_limit` ceiling) but
information-dense — NOT truncated mid-thought. `differential_diagnosis`-
section chunks in particular reliably contain real "includes X, Y, and Z" /
"distinguished from X" multi-entity enumerations, which is exactly the
DDx-signal pattern this module looks for. This is a better join key than the
originally-planned inline-markdown-header regex approach (there is no inline
"## Terminology" header to find — the section boundary is already a
first-class API field).

Only returns GROUNDED matches: a candidate phrase pulled verbatim from a real
card's excerpt, fuzzy-matched to a real `BROWSE_TAXONOMY` leaf name, together
with the literal snippet it came from and the source WHO card's own URL.
Never returns a bare unmatched phrase as if it were a link.
"""

from __future__ import annotations

import os
import re
from typing import Optional

# Section values (per the live-probed `section` field on who_results[] cards)
# worth mining for cross-entity mentions. Ordered roughly by observed signal
# density, not by the user's original stated priority (Terminology/
# Microscopic first) — `differential_diagnosis` turned out to be the
# highest-signal section in live probes this session, so it is included as a
# first-class target alongside Terminology/Microscopic/Histopathology.
TARGET_SECTIONS = frozenset(
    {
        "differential_diagnosis",
        "microscopic",
        "histopathology",
        "terminology",
        "related_terminology",
    }
)

# DDx-signal cue phrases that introduce a nearby list of named entities.
# Case-insensitive; each pattern captures the tail text after the cue so
# candidate phrases can be split out of it. Deliberately scoped to cues that
# are immediately followed by the actual entity list (e.g. "such as X, Y") —
# an earlier version also matched broader lead-ins like "differential
# diagnosis includes", which pulled in preceding descriptive clauses (tissue
# morphology text, not entity names) as false candidates. Live-probed and
# corrected against real WHO differential_diagnosis excerpts this session.
_DDX_CUE_RE = re.compile(
    r"(?:"
    r"such\s+as|"
    r"distinguished\s+from|"
    r"distinguish(?:ed)?\s+(?:it\s+)?from|"
    r"differentiate(?:d)?\s+from|"
    r"compared\s+(?:with|to)|"
    r"mimic(?:ked|s)?\s+by|"
    r"\bvs\.?\b"
    r")\s*[:]?\s*([^.]{3,220})",
    re.IGNORECASE,
)

# Splits a cue's tail text into individual candidate entity phrases: commas
# and "and"/"or" as separate words. "and/or" is normalized to a comma first
# so it doesn't get chopped mid-token by the plain \band\b/\bor\b split.
_AND_OR_RE = re.compile(r"\band\s*/\s*or\b", re.IGNORECASE)
_CANDIDATE_SPLIT_RE = re.compile(r",|;|\band\b|\bor\b", re.IGNORECASE)

_STOPWORD_TRIM_RE = re.compile(
    r"^\s*(?:other|the|a|an|especially|particularly|including|also|and|or)\s+", re.IGNORECASE
)

_TRAILING_JUNK_RE = re.compile(
    r"\s*(?:with distinction[^,]*|with[^,]*molecular[^,]*|especially when[^,]*)$", re.IGNORECASE
)


def extract_ddx_candidates(text: str) -> list[str]:
    """Pull candidate named-entity phrases out of DDx-signal cue sentences.

    Grounded in the literal input text only — every returned phrase is a
    verbatim substring split out of `text` (after trimming stopwords/
    whitespace), never invented or reconstructed.
    """
    if not text:
        return []

    candidates: list[str] = []
    seen: set[str] = set()
    for match in _DDX_CUE_RE.finditer(text):
        tail = _AND_OR_RE.sub(",", match.group(1))
        tail = _TRAILING_JUNK_RE.sub("", tail)
        for piece in _CANDIDATE_SPLIT_RE.split(tail):
            phrase = piece.strip(" \t.;:")
            phrase = _STOPWORD_TRIM_RE.sub("", phrase).strip()
            if not phrase:
                continue
            # Discard obvious non-entity fragments: too short, no letters,
            # or looks like a dangling clause rather than a noun phrase.
            if len(phrase) < 4 or not re.search(r"[A-Za-z]", phrase):
                continue
            if len(phrase.split()) > 6:
                continue
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(phrase)
    return candidates


_ABBREVIATION_EXPANSIONS = {
    "lcis": "lobular carcinoma in situ",
    "dcis": "ductal carcinoma in situ",
    "plcis": "pleomorphic lobular carcinoma in situ",
    "alh": "atypical lobular hyperplasia",
    "adh": "atypical ductal hyperplasia",
    "cin": "cervical intraepithelial neoplasia",
    "hsil": "high grade squamous intraepithelial lesion",
    "lsil": "low grade squamous intraepithelial lesion",
    "vin": "vulvar intraepithelial neoplasia",
    "hgpin": "high grade prostatic intraepithelial neoplasia",
    "gist": "gastrointestinal stromal tumor",
    "ipmn": "intraductal papillary mucinous neoplasm",
    "dlbcl": "diffuse large b cell lymphoma",
    "sll": "small lymphocytic lymphoma",
    "cll": "chronic lymphocytic leukemia",
    "pa": "pleomorphic adenoma",
    "meca": "myoepithelial carcinoma",
}


def normalize_entity_name(name: str) -> str:
    """Python mirror of app.js's `normalizeEntityName` (kept in sync
    manually — this is a small, stable function; if it drifts, taxonomy
    matches will just get more conservative, never wrong)."""
    base = re.sub(r"\([^)]*\)", " ", str(name or "").lower())
    base = re.sub(r"[^a-z0-9\s]", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    tokens = [_ABBREVIATION_EXPANSIONS.get(tok, tok) for tok in base.split(" ") if tok]
    return " ".join(tokens)


_ENTITIES_ARRAY_RE = re.compile(r"entities:\s*\[([^\]]*)\]")
_QUOTED_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')

_FALLBACK_TAXONOMY_LEAVES = [
    "Tubular adenoma",
    "Sessile serrated lesion",
    "Hyperplastic polyp",
    "Pleomorphic adenoma",
    "Warthin tumor",
    "Mucoepidermoid carcinoma",
    "Adenoid cystic carcinoma",
]


def load_taxonomy_leaf_names(app_js_path: Optional[str] = None) -> list[str]:
    """Lightweight mirror of `BROWSE_TAXONOMY` leaf entity names from
    `static/app.js`, for fuzzy-matching extracted candidates without
    duplicating the whole taxonomy structure in Python.

    This is a regex-based extraction of `entities: ["...", "..."]` string
    literals, not a JS parser — it works because `BROWSE_TAXONOMY` in app.js
    is a simple, static, editorially-curated array (see app.js's own
    docstring comment above that constant). If app.js's structure changes in
    a way this regex can't follow, this falls back to a small built-in list
    rather than raising, so the prototype degrades gracefully instead of
    crashing a caller.
    """
    path = app_js_path or os.path.join(os.path.dirname(__file__), "static", "app.js")
    try:
        with open(path, "r", encoding="utf-8") as f:
            js_source = f.read()
    except OSError:
        return list(_FALLBACK_TAXONOMY_LEAVES)

    leaves: list[str] = []
    seen: set[str] = set()
    for block in _ENTITIES_ARRAY_RE.findall(js_source):
        for name in _QUOTED_STRING_RE.findall(block):
            if name not in seen:
                seen.add(name)
                leaves.append(name)
    return leaves or list(_FALLBACK_TAXONOMY_LEAVES)


# Pathology suffix/descriptor tokens that are too generic to count as a
# meaningful match signal on their own — "carcinoma" or "clear cell" overlap
# alone must never be enough to link two otherwise-unrelated entities (found
# live this session: naive token overlap wrongly linked "myoepithelial
# carcinoma" to "Endometrioid carcinoma" on the shared word "carcinoma", and
# "clear cell carcinoma" to "Clear cell renal cell carcinoma" on "clear
# cell" — both corrected by excluding these tokens from overlap scoring).
_GENERIC_PATHOLOGY_TOKENS = {
    "carcinoma",
    "carcinomas",
    "adenocarcinoma",
    "adenocarcinomas",
    "tumor",
    "tumour",
    "tumors",
    "tumours",
    "neoplasm",
    "neoplasms",
    "lesion",
    "lesions",
    "cell",
    "cells",
    "clear",
    "gland",
    "glands",
    "malignant",
    "benign",
    "carcinosarcoma",
    "of",
    "in",
    "situ",
}


def fuzzy_match_taxonomy(candidate: str, taxonomy_leaves: list[str]) -> Optional[str]:
    """Conservative fuzzy match — mirrors app.js's `findTaxonomyMatch`
    thresholds, plus a distinctive-token requirement (see
    `_GENERIC_PATHOLOGY_TOKENS`) that app.js's version doesn't need, since
    app.js only fuzzy-matches a single already-curated DDx bullet per call,
    while this module scans many raw candidate phrases per excerpt and needs
    a stronger guard against generic-word-only overlap. False negatives (no
    match) are safer than false positives (wrong match), so this stays
    deliberately strict."""
    norm = normalize_entity_name(candidate)
    if not norm:
        return None
    norm_tokens = {t for t in norm.split(" ") if len(t) > 2}
    norm_distinctive = norm_tokens - _GENERIC_PATHOLOGY_TOKENS

    best: Optional[str] = None
    best_score = 0.0
    for leaf in taxonomy_leaves:
        leaf_norm = normalize_entity_name(leaf)
        if not leaf_norm:
            continue
        if leaf_norm == norm:
            return leaf
        if norm in leaf_norm or leaf_norm in norm:
            # A substring relationship still needs a real distinctive word in
            # the shorter phrase, or "carcinoma" alone would substring-match
            # dozens of unrelated "<X> carcinoma" leaves.
            if not norm_distinctive:
                continue
            score = min(len(leaf_norm), len(norm)) / max(len(leaf_norm), len(norm))
            if score > best_score:
                best_score = score
                best = leaf
            continue
        leaf_tokens = {t for t in leaf_norm.split(" ") if len(t) > 2}
        leaf_distinctive = leaf_tokens - _GENERIC_PATHOLOGY_TOKENS
        if not leaf_tokens or not norm_distinctive or not leaf_distinctive:
            continue
        overlap = len(norm_distinctive & leaf_distinctive)
        if overlap == 0:
            continue
        ratio = overlap / max(len(leaf_distinctive), len(norm_distinctive), 1)
        if ratio > best_score:
            best_score = ratio
            best = leaf

    if best is not None and best_score >= 0.5:
        return best
    return None


def who_section_mentions(card: dict, taxonomy_leaves: Optional[list[str]] = None) -> list[dict]:
    """Extract grounded cross-entity mentions from one WHO evidence card.

    Returns a list of dicts, each ONLY when a candidate phrase pulled
    verbatim from the card's excerpt fuzzy-matches a real taxonomy leaf:
        {
            "candidate_phrase": <verbatim substring from the excerpt>,
            "matched_leaf": <BROWSE_TAXONOMY leaf name>,
            "snippet": <the excerpt text the phrase came from>,
            "source_url": <card's own source_url, never fabricated>,
            "source_entity": <card['entity_name']>,
            "source_section": <card['section']>,
        }
    Returns [] (never raises) for a non-dict card, a card whose `section`
    isn't in TARGET_SECTIONS, or a card with no matched candidates.
    """
    if not isinstance(card, dict):
        return []
    section = str(card.get("section") or "").lower()
    if section not in TARGET_SECTIONS:
        return []

    excerpt = card.get("excerpt") or card.get("text_excerpt") or ""
    if not isinstance(excerpt, str) or not excerpt.strip():
        return []

    leaves = taxonomy_leaves if taxonomy_leaves is not None else load_taxonomy_leaf_names()
    source_url = card.get("source_url") or card.get("url")
    source_entity = card.get("entity_name")

    results: list[dict] = []
    seen_leaves: set[str] = set()
    for candidate in extract_ddx_candidates(excerpt):
        # Never surface the entity's own page as a "cross"-mention of itself.
        if source_entity and normalize_entity_name(candidate) == normalize_entity_name(source_entity):
            continue
        matched_leaf = fuzzy_match_taxonomy(candidate, leaves)
        if not matched_leaf or matched_leaf in seen_leaves:
            continue
        seen_leaves.add(matched_leaf)
        results.append(
            {
                "candidate_phrase": candidate,
                "matched_leaf": matched_leaf,
                "snippet": excerpt,
                "source_url": source_url,
                "source_entity": source_entity,
                "source_section": card.get("section"),
            }
        )
    return results
