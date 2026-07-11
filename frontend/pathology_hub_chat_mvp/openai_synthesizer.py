"""OpenAI Responses API synthesis for the Pathology Hub Chat MVP."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from secrets_helper import get_openai_api_key

DEFAULT_MODEL = "gpt-4o"


def get_model() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)


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


def _compact_evidence_json(evidence_bundle: dict) -> str:
    try:
        return json.dumps(evidence_bundle, indent=2, sort_keys=True)[:60000]
    except Exception:
        return str(evidence_bundle)[:60000]


def synthesize(
    system_prompt: str,
    user_question: str,
    evidence_bundle: dict,
    extra_instructions: Optional[str] = None,
) -> SynthesisResult:
    """One Responses API call: system prompt + user question + JSON evidence bundle."""
    model = get_model()
    try:
        client = _get_client()
    except RuntimeError as exc:
        return SynthesisResult(text="", model=model, ok=False, error=str(exc))

    evidence_json = _compact_evidence_json(evidence_bundle)
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
        return SynthesisResult(text=text or "", model=model, ok=True)
    except Exception as exc:
        return SynthesisResult(
            text="",
            model=model,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
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
