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


def get_topic_page_model() -> str:
    return os.environ.get("OPENAI_TOPIC_PAGE_MODEL") or get_model()


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
    """Serialize evidence for synthesis with a source-balanced budget."""
    max_chars = 80000
    bundle = dict(evidence_bundle or {})
    lists: list[tuple[str, list]] = []
    for key in (
        "who_results",
        "textbook_results",
        "journal_results",
        "pathout_results",
        "lecture_results",
        "video_results",
        "curriculum_results",
        "results",
    ):
        items = bundle.get(key)
        if isinstance(items, list) and items:
            lists.append((key, list(items)))

    if not lists:
        try:
            return json.dumps(bundle, indent=2)[:max_chars]
        except Exception:
            return str(bundle)[:max_chars]

    trimmed = dict(bundle)
    for key, _items in lists:
        trimmed[key] = []

    # Round-robin keep items across source lists until char budget fills.
    indices = {key: 0 for key, _ in lists}
    while True:
        progressed = False
        for key, items in lists:
            idx = indices[key]
            if idx >= len(items):
                continue
            candidate = dict(trimmed)
            candidate[key] = trimmed[key] + [items[idx]]
            try:
                encoded = json.dumps(candidate, indent=2)
            except Exception:
                encoded = str(candidate)
            if len(encoded) > max_chars and trimmed[key]:
                continue
            trimmed[key].append(items[idx])
            indices[key] += 1
            progressed = True
            if len(encoded) >= max_chars * 0.95:
                try:
                    return json.dumps(trimmed, indent=2)
                except Exception:
                    return str(trimmed)[:max_chars]
        if not progressed:
            break

    try:
        return json.dumps(trimmed, indent=2)
    except Exception:
        return str(trimmed)[:max_chars]


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
