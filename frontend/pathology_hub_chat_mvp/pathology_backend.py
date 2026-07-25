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
import json
import os
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
# Raised again 2026-07-25 alongside the richer TOPIC_PAGE_SECTIONS taxonomy
# (Staging/Cytology/Radiology/Prognostic Factors/Illustrative Cases) — those
# extra sections need extra source material (radiology descriptions, case
# reports, cytology chunks) that the tighter 120/40 caps were likely
# crowding out. Same context-window headroom argument as above applies at
# this new size (well under 20% of gpt-4.1's 1M-token window even at full
# JSON verbosity).
TOPIC_PAGE_MAX_CARDS = 180
TOPIC_PAGE_MAX_FIGURES = 60

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
        # Live-observed 2026-07-25: the upstream backend occasionally has a
        # transient slow spell where a single source (e.g. textbooks) times
        # out at DEFAULT_TIMEOUT_SECONDS across every parallel query variant
        # for a request, while a retry moments later returns in <1s — a
        # topic_page request can otherwise land on 0 usable cards purely from
        # bad luck on backend timing, not a real coverage gap. One quick retry
        # on a network-level failure (timeout/connection error, never on a
        # real HTTP error response) catches this without materially slowing
        # down the common case where the first attempt already succeeds.
        last_exc: Optional[requests.RequestException] = None
        for attempt in range(2):
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
                last_exc = exc
                if attempt == 0:
                    time.sleep(1.0)
                    continue
        elapsed_ms = (time.monotonic() - start) * 1000
        return SearchOutcome(
            request_payload=payload,
            url=url,
            status_code=None,
            ok=False,
            elapsed_ms=elapsed_ms,
            response_json=None,
            error=f"{type(last_exc).__name__}: {last_exc} (after retry)",
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


def page_tag_leaf_phrase(page_tag: Optional[str]) -> str:
    seg = page_tag_segments(page_tag)
    return seg.get("leaf", "").replace("_", " ").strip()


# Known wrong-entity captions/entity_names that repeatedly pollute review pages.
_PAGE_TAG_CONFUSABLE_TERMS: dict[str, frozenset[str]] = {
    "hn::salivary_gland::malignant_tumor::adenoid_cystic_carcinoma": frozenset(
        {"cystadenoma", "papillary cystadenoma", "oncocytic cystadenoma", "mucocele", "ranula"}
    ),
    "hn::salivary_gland::malignant_tumor::secretory_carcinoma": frozenset(
        {
            "mucoepidermoid",
            "acinic cell",
            "salivary duct carcinoma",
            "adenoid cystic",
            "papillary thyroid",
            "thyroid carcinoma",
            "thyroid secretory",
        }
    ),
    "gu::kidney::renal_cell::clear_cell_rcc": frozenset(
        {
            "clear cell sarcoma",
            "collecting duct carcinoma",
            "pecoma",
            "epithelioid angiomyolipoma",
            "rhabdoid tumour of the kidney",
            "rhabdoid tumor of the kidney",
            "papillary renal cell",
            "chromophobe renal cell",
            # This leaf's PathOutlines "anchor" page is a multi-subtype RCC
            # overview whose figure captions are the ONLY per-image signal
            # (entity_name is generically "Renal cell carcinoma overview" for
            # every figure) — explicitly reject other RCC subtypes' captions
            # so they don't leak onto the clear cell RCC gallery.
            "papillary rcc",
            "prcc",
            "chromophobe",
            "chrcc",
            "fh deficient",
            "fh-deficient",
            "fh loss",
            "sdh deficient",
            "sdh-deficient",
            "sdhb",
        }
    ),
    "gu::prostate::glandular_neoplasms::prostatic_acinar_adenocarcinoma": frozenset(
        {"skene", "skene gland", "female urethra", "urethral carcinoma"}
    ),
    "bst::soft_tissueadipocytic::lipoma": frozenset(
        {"myolipoma", "liposarcoma", "atypical lipomatous", "spindle cell lipoma"}
    ),
    "gi::colon::neoplastic::adenocarcinoma::colonic_adenocarcinoma_arising_in_adenoma": frozenset(
        {
            "adenosquamous",
            "gastroblastoma",
            "non-ampullary",
            "ampullary adenoma",
            "signet ring cell carcinoma",
        }
    ),
    "skin::neoplastic::melanocytic::malignant::melanoma_invasive_overview_nos": frozenset(
        {"conjunctival melanoma", "conjunctiva", "uveal melanoma", "uveal", "choroidal melanoma"}
    ),
}

# Legitimate same-organ differential-diagnosis entities that must stay available
# as DDx *text* evidence but must never be selected as index/gallery figures
# (a figure literally captioned/entitled as the DDx entity, presented without
# DDx framing, reads as if it documents the page's own entity).
_FIGURE_ONLY_EXCLUDE_TERMS: dict[str, frozenset[str]] = {
    "hn::salivary_gland::malignant_tumor::secretory_carcinoma": frozenset(
        {"microsecretory adenocarcinoma"}
    ),
}

_SITE_CONTEXT_EXCLUSIONS: dict[str, frozenset[str]] = {
    "salivary_gland": frozenset({"thyroid", "thyroidal", "parathyroid", "laryngeal"}),
    "prostate": frozenset({"skene", "female urethra", "urethra"}),
}

# Some PathOutlines figures carry no title/entity_name at all — only a
# caption ("Clear cell renal tumors") and a source_url page slug
# ("kidneytumormalignantrcc"). The caption alone can fail strict word-boundary
# entity matching (no literal "RCC"/leaf token), so fall back to matching the
# PathOutlines URL slug against a per-tag allowlist — deliberately narrow
# (exact known-good topic pages only) so it can't reintroduce the substring
# false-positive bug fixed above.
_PAGE_TAG_URL_SLUG_ALIASES: dict[str, tuple[str, ...]] = {
    "gu::kidney::renal_cell::clear_cell_rcc": ("kidneytumormalignantrcc",),
}


def _matches_url_slug_alias(item: dict, tag_key: str) -> bool:
    """Exact-path match only — PathOutlines slugs share prefixes (e.g. the
    'kidneytumormalignantrcc' RCC-overview page vs the DIFFERENT, more
    specific 'kidneytumormalignantrccpap' papillary RCC page), so a bare
    substring check would treat every subtype's own dedicated page as a
    match too."""
    slugs = _PAGE_TAG_URL_SLUG_ALIASES.get(tag_key)
    if not slugs:
        return False
    url = str(item.get("source_url") or item.get("url") or item.get("figure_url") or "").casefold()
    return any(url.endswith(f"/{slug}.html") for slug in slugs)


_PAGE_TAG_ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
    "gu::kidney::renal_cell::clear_cell_rcc": (
        "clear cell renal cell carcinoma",
        "ccrcc",
        "conventional renal cell carcinoma",
    ),
    "gi::colon::neoplastic::adenocarcinoma::colonic_adenocarcinoma_arising_in_adenoma": (
        "adenoma with invasive carcinoma",
        "malignant polyp",
        "polyp with invasive carcinoma",
        "invasive adenocarcinoma arising in adenoma",
    ),
    "breast::neoplastic::epithelial::in_situ::ductal_carcinoma_in_situ_dcis": (
        "ductal carcinoma in situ",
        "dcis",
    ),
    "heme::mature_b_cell::large_b_cell::diffuse_large_b_cell_lymphoma_nos": (
        "diffuse large b-cell lymphoma",
        "diffuse large b cell lymphoma",
        "dlbcl",
    ),
    "skin::neoplastic::melanocytic::malignant::melanoma_invasive_overview_nos": (
        "invasive melanoma",
        "malignant melanoma",
        "melanoma nos",
    ),
}


def topic_page_essential_hints(page_tag: Optional[str]) -> str:
    """Per-leaf synthesis hints for definitional essentials ExpertPath/WHO expect."""
    if not page_tag:
        return ""
    key = page_tag.casefold()
    hints = {
        "hn::salivary_gland::benign_tumor::pleomorphic_adenoma": (
            "Essential criteria MUST include biphasic ductal+myoepithelial architecture, "
            "PLAG1/HMGA2 rearrangements when in evidence (~70%), and capsule/site differences "
            "(parotid vs minor glands)."
        ),
        "hn::salivary_gland::malignant_tumor::adenoid_cystic_carcinoma": (
            "Essential criteria MUST include biphasic ductal+myoepithelial tumor, cribriform/"
            "tubular/solid patterns, basophilic basement-membrane matrix, and MYB::NFIB / "
            "MYBL1::NFIB when in evidence."
        ),
        "hn::salivary_gland::malignant_tumor::secretory_carcinoma": (
            "Essential criteria MUST treat ETV6 rearrangement / ETV6::NTRK3 as DEFINITIONAL "
            "(not merely Desirable). Include negative p63/p40/DOG1 vs acinic cell when in evidence."
        ),
        "gu::prostate::glandular_neoplasms::prostatic_acinar_adenocarcinoma": (
            "Essential criteria MUST include Gleason pattern / Grade Group reporting framework, "
            "basal-cell marker loss (p63/HMWCK), and AMACR when in evidence — not just 'invasive "
            "glands'. Differential Diagnosis MUST include atypical small acinar proliferation "
            "(ASAP) as the top entry when in evidence, plus benign mimics (atrophy, adenosis, "
            "seminal vesicle, Cowper gland) — these are the practical everyday differentials, not "
            "rare carcinomas. Skene gland adenocarcinoma is a DIFFERENT ORGAN (female urethra), not "
            "a real prostate differential — do not mention it anywhere on this page even in DDx."
        ),
        "gi::colon::neoplastic::adenocarcinoma::colonic_adenocarcinoma_arising_in_adenoma": (
            "This is malignant polyp / adenoma with invasive carcinoma — NOT generic colorectal "
            "adenocarcinoma or adenosquamous carcinoma. Essential criteria MUST include invasion "
            "through muscularis mucosa (pT1), Haggitt levels (pedunculated), Kikuchi/Kudo Sm1–3 "
            "(sessile), and high-risk histology (poor differentiation, lymphovascular invasion, "
            "positive/close margin, high-grade tumor budding) when in evidence. Do NOT state that "
            "microsatellite instability is universal/defining for villous adenocarcinoma — MSI is a "
            "molecular subset finding, not an essential histologic criterion. Differential Diagnosis "
            "MUST include adenoma with pseudoinvasion (misplaced epithelium) and localized colitis "
            "cystica profunda when in evidence — these are the critical benign mimics, not "
            "adenosquamous carcinoma or gastroblastoma."
        ),
        "gu::kidney::renal_cell::clear_cell_rcc": (
            "Essential criteria MUST include delicate chicken-wire vasculature and CA9/CAIX "
            "box-like membranous staining when in evidence; CK7 typically negative/focal. "
            "Differential Diagnosis and figures must be about ACTUAL clear cell RCC mimics "
            "(papillary RCC, chromophobe RCC, clear cell papillary renal cell tumor, MiT/TFE "
            "translocation RCC) — clear cell sarcoma of the kidney, PEComa/epithelioid "
            "angiomyolipoma, collecting duct carcinoma, and rhabdoid tumour of the kidney are "
            "pediatric/rare unrelated entities and must not appear as this page's figures or "
            "differential diagnosis entries."
        ),
        "breast::neoplastic::epithelial::in_situ::ductal_carcinoma_in_situ_dcis": (
            "Essential criteria MUST emphasize intact myoepithelium / confinement to ductal-lobular "
            "system — NOT mammographic microcalcifications as a histologic essential. Differential "
            "Diagnosis MUST include usual ductal hyperplasia (UDH), atypical ductal hyperplasia "
            "(ADH), and collagenous spherulosis when in evidence."
        ),
        "heme::mature_b_cell::large_b_cell::diffuse_large_b_cell_lymphoma_nos": (
            "Essential criteria MUST include GCB vs ABC / Hans algorithm workup and rule-out of "
            "high-grade B-cell lymphoma with MYC and BCL2/BCL6 rearrangements when in evidence."
        ),
        "bst::soft_tissueadipocytic::lipoma": (
            "Essential criteria MUST include mature adipocyte morphology without atypia/lipoblasts; "
            "12q13-15/HMGA2 rearrangement is Desirable (supportive, not required). Figures MUST be "
            "of ordinary lipoma — myolipoma (smooth-muscle component), liposarcoma, and atypical "
            "lipomatous tumor are differential entities only, never index figures."
        ),
        "skin::neoplastic::melanocytic::malignant::melanoma_invasive_overview_nos": (
            "This is an OVERVIEW/NOS page — frame Essential criteria as the structured malignancy-"
            "vs-nevus checklist when in evidence: asymmetry, lack of maturation with depth, pagetoid "
            "melanocytic scatter, deep/atypical mitoses, and ulceration — plus Breslow thickness, "
            "mitotic rate, and ulceration as ESSENTIAL staging criteria (not merely Desirable). "
            "Mention the major pathway-based subtypes (low-CSD/SSM, high-CSD, acral, desmoplastic, "
            "Spitz-related) briefly if evidence supports it. Conjunctival melanoma and uveal "
            "melanoma are DIFFERENT ORGANS (ocular, not cutaneous) — do not mention or use figures "
            "of them anywhere on this page."
        ),
    }
    return hints.get(key, "")


def _excluded_by_site_context(blob: str, subcategory: str) -> bool:
    sub = (subcategory or "").casefold()
    for site_key, terms in _SITE_CONTEXT_EXCLUSIONS.items():
        if site_key in sub and any(term in blob for term in terms):
            return True
    return False


def _item_entity_blob(item: dict) -> str:
    return _text_blob(
        item.get("entity_name"),
        item.get("title"),
        item.get("heading"),
        item.get("caption"),
        item.get("source_url"),
    )


def _word_in_blob(word: str, blob: str) -> bool:
    """Whole-word match — plain `in` lets 'secretory' match inside 'microsecretory'
    and 'carcinoma' match inside 'adenocarcinoma', silently defeating multi-word
    entity disambiguation."""
    return re.search(rf"\b{re.escape(word)}\b", blob) is not None


def entity_matches_page_tag(
    item: dict, page_tag: Optional[str], *, figures_only: bool = False
) -> bool:
    """True when a card/figure clearly documents the browse-leaf entity.

    `figures_only=True` additionally excludes legitimate same-organ DDx
    entities that must remain available as evidence text but should never be
    selected as an index/gallery figure (see `_FIGURE_ONLY_EXCLUDE_TERMS`).
    """
    if not page_tag or not isinstance(item, dict):
        return True
    seg = page_tag_segments(page_tag)
    if not seg:
        return True

    blob = _item_entity_blob(item)
    # Include source_url here (unlike the plain entity/title/caption blob
    # used elsewhere) because some PathOutlines pages have a fully generic
    # entity_name that collides across organs (e.g. "Pleomorphic adenoma" is
    # the entity_name for BOTH the salivary gland page AND a distinct breast
    # page "breastmixedtumor.html" with no organ hint in its own
    # captions/entity_name) — the URL slug is often the only signal.
    entity_title_blob = _text_blob(
        item.get("entity_name"), item.get("title"), item.get("caption"), item.get("source_url")
    )
    tag_key = page_tag.casefold()
    leaf = page_tag_leaf_phrase(page_tag).casefold()

    for term in _PAGE_TAG_CONFUSABLE_TERMS.get(tag_key, frozenset()):
        if term in blob:
            return False

    if figures_only:
        for term in _FIGURE_ONLY_EXCLUDE_TERMS.get(tag_key, frozenset()):
            if term in blob:
                return False

    if _excluded_by_site_context(blob, seg.get("subcategory", "")):
        return False

    # Hard root-conflict check: the item's OWN title/entity/caption (not just
    # any incidental mention in a longer excerpt) names a term from a
    # conflicting organ — e.g. "conjunctival melanoma" figure on a skin page.
    root_conflicts = _ROOT_CONFLICT_TERMS.get(seg.get("root", ""), frozenset())
    if root_conflicts and any(term in entity_title_blob for term in root_conflicts):
        return False

    entity = str(item.get("entity_name") or item.get("title") or "").casefold().strip()
    if leaf and (leaf == entity or _word_in_blob(leaf, entity) or _word_in_blob(entity, leaf)):
        return True
    if leaf and _word_in_blob(leaf, blob):
        return True

    for alias in _PAGE_TAG_ENTITY_ALIASES.get(tag_key, ()):
        if alias in blob:
            return True

    if _matches_url_slug_alias(item, tag_key):
        return True

    leaf_words = [w for w in re.split(r"[_\s]+", leaf) if len(w) > 2]
    if len(leaf_words) >= 2 and all(_word_in_blob(w, blob) for w in leaf_words):
        return True
    if len(leaf_words) == 1:
        if _word_in_blob(leaf_words[0], blob):
            return True
    return False


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


_PATHOUT_DEEP_INDEX_CACHE: dict[str, Any] = {}


def load_pathout_deep_index(path: str) -> dict[str, Any]:
    """Load the compact PathOutlines deep-content index (see
    scripts/build_pathout_deep_index_v0_1.py). Frontend-only, read-time
    enrichment over staged/normalized data that is NOT live-indexed,
    vectorized, or API-exposed in the backend (see that script's docstring
    for the audit trail). Cached in-process; missing file is a silent no-op
    so the app runs fine without it (falls back to the capped live API)."""
    cached = _PATHOUT_DEEP_INDEX_CACHE.get(path)
    if cached is not None:
        return cached
    if not path or not os.path.isfile(path):
        _PATHOUT_DEEP_INDEX_CACHE[path] = {}
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    _PATHOUT_DEEP_INDEX_CACHE[path] = data
    return data


_DEEP_INDEX_ENTITY_LOOKUP_CACHE: dict[int, dict[str, list[str]]] = {}


def _deep_index_entity_lookup(deep_index: dict[str, Any]) -> dict[str, list[str]]:
    """casefold(entity_name) -> [urls] reverse index, cached per deep_index
    object identity (the index is loaded once and reused across requests)."""
    cache_key = id(deep_index)
    cached = _DEEP_INDEX_ENTITY_LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        return cached
    lookup: dict[str, list[str]] = {}
    for url, record in deep_index.items():
        name = str((record or {}).get("entity_name") or "").casefold().strip()
        if name:
            lookup.setdefault(name, []).append(url)
    _DEEP_INDEX_ENTITY_LOOKUP_CACHE[cache_key] = lookup
    return lookup


def _find_anchor_pathout_url(
    deep_index: dict[str, Any], page_tag: Optional[str], already_seen: set[str]
) -> Optional[str]:
    """Guaranteed-anchor fallback: the live backend's keyword-only FTS5 search
    sometimes fails to surface even the exact dedicated PathOutlines page for
    a leaf (e.g. 'Secretory Carcinoma' ranks other salivary pages above the
    dedicated 'salivaryglandssecretory' page unless a rare term like 'ETV6' is
    in the query). When the deep index has an EXACT entity_name match for this
    leaf and it wasn't already reached via the normal retrieval+enrich path,
    use it directly rather than silently shipping a page with zero figures."""
    leaf = page_tag_leaf_phrase(page_tag).casefold()
    if leaf:
        for url in _deep_index_entity_lookup(deep_index).get(leaf, []):
            if url in already_seen:
                continue
            # An exact entity_name match is NOT sufficient on its own —
            # PathOutlines has multiple, organ-distinct pages that share an
            # identical generic entity_name (e.g. "Pleomorphic adenoma" is
            # the entity_name for both the salivary gland page AND an
            # unrelated breast page "breastmixedtumor.html" with no organ
            # hint anywhere except the URL) — re-validate with the same
            # root-conflict/site-context check used everywhere else before
            # trusting it as an anchor.
            record = deep_index.get(url) or {}
            probe = {"entity_name": record.get("entity_name"), "title": record.get("entity_name"), "source_url": url}
            if entity_matches_page_tag(probe, page_tag):
                return url
    tag_key = (page_tag or "").casefold()
    for slug in _PAGE_TAG_URL_SLUG_ALIASES.get(tag_key, ()):
        for url in deep_index:
            if slug in url.casefold() and url not in already_seen:
                return url
    return None


def enrich_cards_with_pathout_deep(
    cards: list[dict],
    figures: list[dict],
    deep_index: dict[str, Any],
    page_tag: Optional[str] = None,
    max_chunks_per_url: int = 48,
    max_figures_per_url: int = 24,
) -> tuple[list[dict], list[dict]]:
    """Expand already root/tag-filtered PathOutlines cards using the full
    staged chunk+figure set for the same page_url, instead of the live
    backend's ~4000-char single-excerpt cap. Only enriches URLs that
    survived upstream filtering (never introduces a new, unvetted page) —
    except for the exact-entity-name anchor fallback (see
    `_find_anchor_pathout_url`), which is a known-good deep-index URL for
    this exact leaf, independent of whether live keyword search surfaced it."""
    if not deep_index:
        return cards, figures

    seen_urls: set[str] = set()
    extra_cards: list[dict] = []
    extra_figures: list[dict] = []
    kept_cards: list[dict] = []

    urls_to_enrich: list[tuple[str, dict]] = []
    for card in cards:
        if not isinstance(card, dict) or str(card.get("source") or "") != "pathout":
            kept_cards.append(card)
            continue
        url = card.get("source_url") or card.get("url") or ""
        record = deep_index.get(url)
        if not record or not record.get("chunks"):
            kept_cards.append(card)
            continue
        entity_name = record.get("entity_name") or card.get("title") or ""
        probe = {"entity_name": entity_name, "title": entity_name, "source_url": url}
        if page_tag and not entity_matches_page_tag(probe, page_tag):
            kept_cards.append(card)
            continue
        urls_to_enrich.append((url, card))

    anchor_url = _find_anchor_pathout_url(deep_index, page_tag, {u for u, _ in urls_to_enrich})
    if anchor_url:
        urls_to_enrich.append((anchor_url, {"source": "pathout"}))

    for url, card in urls_to_enrich:
        record = deep_index.get(url)
        if not record or not record.get("chunks"):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        entity_name = record.get("entity_name") or card.get("title") or ""
        base = {k: v for k, v in card.items() if not str(k).startswith("_")}
        for chunk in record["chunks"][:max_chunks_per_url]:
            heading = chunk.get("heading") or ""
            text = chunk.get("text") or ""
            if not text.strip():
                continue
            new_card = dict(base)
            new_card["title"] = f"{entity_name} — {heading}" if heading else entity_name
            new_card["heading"] = heading
            new_card["section"] = chunk.get("section_type")
            new_card["text_excerpt"] = text
            new_card["excerpt"] = text
            new_card["_pathout_deep"] = True
            extra_cards.append(new_card)

        # PathOutlines figures come in two tiers: full-resolution gross/micro
        # images ("pathout_direct_image", from imgau/) vs tiny clinical/
        # radiology thumbnails ("pathout_thumbnail_or_external", from thumb/).
        # The direct-image tier is far more useful for essential diagnostic
        # features (histology, IHC, cytology) — prioritize it over thumbnails
        # when capping, instead of taking figures in page order.
        ranked_figures = sorted(
            record.get("figures", []),
            key=lambda f: 0 if f.get("image_kind") in ("pathout_direct_image", "other") else 1,
        )
        for fig in ranked_figures[:max_figures_per_url]:
            extra_figures.append(
                {
                    "figure_url": fig.get("image_url"),
                    "image_url": fig.get("image_url"),
                    "url": fig.get("image_url"),
                    "caption": fig.get("caption") or entity_name,
                    "title": entity_name,
                    "entity_name": entity_name,
                    "source": "pathout",
                    "source_family": "PathOutlines",
                    "source_url": url,
                    "_pathout_deep_verified": True,
                }
            )

    merged_cards = kept_cards + extra_cards
    merged_figures = list(figures) + extra_figures
    return merged_cards, merged_figures


_WHO_VOLUME_TO_ROOT = {
    "hn": "hn",
    "breast": "breast",
    "gu": "gu",
    "gi": "gi",
    "gyn": "gyn",
    "skin": "skin",
    "bst": "bst",
    "heme": "heme",
    "thoracic": "thoracic",
    "eye": "eye_orbit",
    "cns": "cns",
    "endocrine": "endocrine",
}

_WHO_SOURCE_PATH_RE = re.compile(r"/WHO_(?:HTML|PICS)/([A-Za-z_]+)/", re.IGNORECASE)
_WHO_RECORD_ID_RE = re.compile(r"^who\w*:([a-z_]+):", re.IGNORECASE)


def card_who_volume_root(card: dict) -> Optional[str]:
    """Extract a normalized organ/root token from WHO structural metadata
    (volume_code, record_id, or WHO_HTML/WHO_PICS GCS path segment) — far
    more reliable than free-text matching, since a WHO chunk can legitimately
    mention another organ (e.g. Breast Tumours discussing salivary PA for
    contrast) while still being filed under the wrong book for this page."""
    volume_code = card.get("volume_code")
    if isinstance(volume_code, str) and volume_code.strip():
        return normalize_root_token(volume_code)
    for field in ("source_url", "url", "figure_url"):
        value = card.get(field)
        if isinstance(value, str):
            m = _WHO_SOURCE_PATH_RE.search(value)
            if m:
                return normalize_root_token(m.group(1))
    record_id = card.get("record_id")
    if isinstance(record_id, str):
        m = _WHO_RECORD_ID_RE.match(record_id)
        if m:
            return normalize_root_token(m.group(1))
    return None


def filter_cards_by_who_volume(cards: list[dict], page_root: Optional[str]) -> list[dict]:
    """Hard structural filter: drop WHO/journal cards whose WHO volume/book
    token unambiguously names a different organ than the browse page root.
    Runs before the softer text-blob heuristic in filter_cards_by_page_tag,
    and — unlike filter_cards_by_page_root — applies to WHO too, since WHO
    is otherwise exempt from root narrowing."""
    if not page_root:
        return cards
    target = normalize_root_token(page_root)
    target_mapped = _WHO_VOLUME_TO_ROOT.get(target, target)
    kept: list[dict] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        vol_root = card_who_volume_root(card)
        if vol_root and vol_root in _WHO_VOLUME_TO_ROOT and vol_root != target_mapped:
            continue
        kept.append(card)
    return kept


def filter_figures_by_who_volume(figures: list[dict], page_root: Optional[str]) -> list[dict]:
    if not page_root:
        return figures
    target = normalize_root_token(page_root)
    target_mapped = _WHO_VOLUME_TO_ROOT.get(target, target)
    kept: list[dict] = []
    for fig in figures:
        if not isinstance(fig, dict):
            continue
        vol_root = card_who_volume_root(fig)
        if vol_root and vol_root in _WHO_VOLUME_TO_ROOT and vol_root != target_mapped:
            continue
        kept.append(fig)
    return kept


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

        # source_url included here too — see entity_matches_page_tag's
        # entity_title_blob comment for why (generic PathOutlines
        # entity_names that collide across organs, e.g. the breast-specific
        # "breastmixedtumor.html" page also has entity_name "Pleomorphic
        # adenoma" with no organ hint anywhere except the URL slug).
        title_blob = _text_blob(
            card.get("title"), card.get("entity_name"), card.get("source_url") or card.get("url")
        )
        blob = _text_blob(
            card.get("title"),
            card.get("heading"),
            card.get("text_excerpt"),
            card.get("excerpt"),
            card.get("entity_name"),
        )
        # Hard exclude: the card's OWN title/entity names a conflicting-organ
        # term (e.g. title "Conjunctival melanoma" on a skin page) — a whole-
        # excerpt mention of the target organ elsewhere should not save it.
        if conflicts and any(term in title_blob for term in conflicts):
            continue
        if conflicts and any(term in blob for term in conflicts):
            if not any(hint in blob for hint in organ_hints):
                continue
        if _excluded_by_site_context(blob, seg.get("subcategory", "")):
            continue
        if seg.get("is_benign") and any(term in blob for term in _BENIGN_EXCLUDE_TERMS):
            continue
        kept.append(card)
    return kept


def filter_figures_by_entity_match(
    figures: list[dict],
    page_tag: Optional[str],
) -> list[dict]:
    """Keep figures whose entity/title/caption matches the browse leaf diagnosis."""
    if not page_tag:
        return figures
    seg = page_tag_segments(page_tag)
    if not seg:
        return figures
    kept: list[dict] = []
    for fig in figures:
        if not isinstance(fig, dict):
            continue
        if seg.get("is_benign") and any(term in _item_entity_blob(fig) for term in _BENIGN_EXCLUDE_TERMS):
            continue
        if entity_matches_page_tag(fig, page_tag, figures_only=True):
            kept.append(fig)
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
