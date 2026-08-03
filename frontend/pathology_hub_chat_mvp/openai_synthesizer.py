"""OpenAI Responses API synthesis for the Pathology Hub Chat MVP."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from secrets_helper import get_openai_api_key

# Both chat and topic-page synthesis use the same modern default so free-text
# Ask/compare/visual answers don't silently fall back to the older, weaker
# `gpt-4o` while only topic pages got upgraded. Override independently via
# OPENAI_MODEL / OPENAI_TOPIC_PAGE_MODEL if you need to diverge on purpose.
TOPIC_PAGE_DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_MODEL = TOPIC_PAGE_DEFAULT_MODEL

# Per-request model override allowlist (2026-08-02: "would like option to be
# able to select model" — user wants to A/B luna vs terra for prebuild
# synthesis quality/latency without redeploying). Live-probed against
# GET https://api.openai.com/v1/models with this project's key — all three
# gpt-5.6-<codename> variants are present and callable via responses.create.
# Deliberately an allowlist, not "accept any string the client sends" — an
# unrecognized model name fails the OpenAI call with an opaque 400 far away
# from where the mistake was made.
SUPPORTED_SYNTHESIS_MODELS: tuple[str, ...] = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")


def get_model() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)


def get_topic_page_model() -> str:
    return os.environ.get("OPENAI_TOPIC_PAGE_MODEL", TOPIC_PAGE_DEFAULT_MODEL)


def resolve_synthesis_model(requested: Optional[str]) -> str:
    """Per-request model override, validated against SUPPORTED_SYNTHESIS_MODELS
    — an unrecognized/empty value silently falls back to the configured
    topic-page default rather than erroring the whole request."""
    if requested and requested in SUPPORTED_SYNTHESIS_MODELS:
        return requested
    return get_topic_page_model()


def _get_client():
    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not available (checked env and Secret Manager 'OPENAI'). "
            "Synthesis modes require it; search-only mode does not."
        )
    from openai import OpenAI

    return OpenAI(api_key=api_key)


@dataclass
class SynthesisResult:
    text: str
    model: str
    ok: bool
    error: Optional[str] = None
    raw_debug: Optional[dict] = None
    evidence_truncated: bool = False
    evidence_char_len: int = 0


# Measured live (2026-07-26): a modest 4-source x10-results search bundle alone
# serializes to ~331k chars; a full topic_page bundle (up to 120 cards + 40
# figures + 10 literature cards + citation index) is materially larger. The
# previous 60,000-char cap silently discarded most of that on every
# topic_page/gpt_like call — and because json.dumps(..., sort_keys=True)
# alphabetizes keys, the cut always landed the same way: who_results/
# video_results/textbook_results/pathout_results (alphabetically late) were
# routinely dropped entirely while figures/literature_results (alphabetically
# early) survived. Raised to match the context-window headroom already
# established in pathology_backend.py's TOPIC_PAGE_MAX_CARDS comment (gpt-4o's
# ~128k-token window comfortably fits this at ~3-4 chars/token). Re-probe if a
# future OPENAI_MODEL/topic-page model has a materially smaller context window.
_EVIDENCE_JSON_CHAR_CAP = 350000


def _compact_evidence_json(evidence_bundle: dict) -> tuple[str, bool, int]:
    """Returns (json_text, was_truncated, original_char_len)."""
    try:
        full = json.dumps(evidence_bundle, indent=2, sort_keys=True)
    except Exception:
        full = str(evidence_bundle)
    original_len = len(full)
    return full[:_EVIDENCE_JSON_CHAR_CAP], original_len > _EVIDENCE_JSON_CHAR_CAP, original_len


def synthesize(
    system_prompt: str,
    user_question: str,
    evidence_bundle: dict,
    extra_instructions: Optional[str] = None,
    model: Optional[str] = None,
) -> SynthesisResult:
    """One Responses API call: system prompt + user question + JSON evidence bundle."""
    model = model or get_model()
    try:
        client = _get_client()
    except RuntimeError as exc:
        return SynthesisResult(text="", model=model, ok=False, error=str(exc))

    evidence_json, was_truncated, original_len = _compact_evidence_json(evidence_bundle)
    user_content = (
        f"User question:\n{user_question}\n\n"
        "Evidence bundle (JSON, from Pathology Hub /evidence/search — the ONLY source of truth):\n"
        f"```json\n{evidence_json}\n```"
    )
    if extra_instructions:
        user_content += f"\n\nAdditional instructions:\n{extra_instructions}"

    try:
        response = client.responses.create(
            model=model,
            instructions=system_prompt,
            input=user_content,
        )
        text = getattr(response, "output_text", None)
        if not text:
            text = _fallback_extract_text(response)
        return SynthesisResult(
            text=text or "",
            model=model,
            ok=True,
            evidence_truncated=was_truncated,
            evidence_char_len=original_len,
        )
    except Exception as exc:
        return SynthesisResult(
            text="",
            model=model,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            evidence_truncated=was_truncated,
            evidence_char_len=original_len,
        )


def _fallback_extract_text(response) -> str:
    """Best-effort text extraction if output_text is unavailable on this SDK version."""
    try:
        parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for block in getattr(item, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
        return "\n".join(parts)
    except Exception:
        return ""


def ping() -> SynthesisResult:
    """Minimal connectivity smoke test — no evidence bundle involved."""
    model = get_model()
    try:
        client = _get_client()
    except RuntimeError as exc:
        return SynthesisResult(text="", model=model, ok=False, error=str(exc))

    try:
        response = client.responses.create(
            model=model,
            instructions="Reply with exactly one word.",
            input="Say: pong",
        )
        text = getattr(response, "output_text", None) or _fallback_extract_text(response)
        return SynthesisResult(text=text or "", model=model, ok=True)
    except Exception as exc:
        return SynthesisResult(
            text="",
            model=model,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )
