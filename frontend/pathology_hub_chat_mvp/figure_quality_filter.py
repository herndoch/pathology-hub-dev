"""Read-only Tier-A (`suppress_render`) filter for textbook figure evidence.

Joins live `POST /evidence/search` cards and figures against the existing
quality-flags sidecar at
`outputs/curriculum_map_v0_4/curriculum_figure_image_quality_flags_v0_1.jsonl`.
Does not mutate the sidecar. See
docs/CHAT_MVP_DIVERSITY_AND_LIMITS_MASTER_PLAN.md (Part 3, Phase 1).

Live-verified join keys (2026-07-10):
- Textbook cards: `chunk_id` matches sidecar byte-for-byte (`tbchunk:...` scheme).
  Live cards carry empty `record_id`, so join on `chunk_id` only.
- Standalone `figures[]` entries: no `chunk_id`; match via `(source_id, fig_slot)`
  parsed from `image_path` / `original_image_path` (e.g. `..._p0473_fig01_...`).

Also exports tiny-dimension / near-black classifiers used by the Chat MVP
client (canvas / naturalWidth sampling) for HTTP 200 extraction stubs that
never entered the sidecar audit population (e.g. cyto_thyroid_bethesda
90x90 unidentified JPEGs).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Local repo layout: frontend/pathology_hub_chat_mvp/ → repo root is parents[2].
# Cloud Run image layout: /app/figure_quality_filter.py → only parents[0]=/app,
# parents[1]=/ — parents[2] raises IndexError and kills container startup.
_MODULE_DIR = Path(__file__).resolve().parent
try:
    _REPO_ROOT = Path(__file__).resolve().parents[2]
except IndexError:
    _REPO_ROOT = _MODULE_DIR
DEFAULT_FLAGS_PATH = (
    _REPO_ROOT / "outputs/curriculum_map_v0_4/curriculum_figure_image_quality_flags_v0_1.jsonl"
)

_FIG_SLOT_RE = re.compile(r"_fig(\d+)(?:_|\.|$)", re.IGNORECASE)
_FIGURE_URL_FIELDS = ("figure_url", "image_url")

# Match scripts/audit_textbook_figure_image_dimensions_v0_1.py TINY_DIM.
# Live cyto_thyroid_bethesda extraction stubs are 90x90 near-black JPEGs
# (1150 bytes) that never entered the curriculum SQLite audit population, so
# they are absent from the quality-flags sidecar — Chat MVP hides them via
# decoded dimensions / pixel sampling instead of mutating that sidecar.
TINY_DIM = 120
NEAR_BLACK_CHANNEL_MAX = 16
NEAR_BLACK_FRACTION_STRICT = 0.85
NEAR_BLACK_MEAN_LUMINANCE_MAX = 35.0
NEAR_BLACK_FRACTION_LOOSE = 0.30


@lru_cache(maxsize=4)
def _load_index(flags_path: str) -> dict:
    path = Path(flags_path)
    chunk_ids: set[str] = set()
    source_fig_slots: set[tuple[str, str]] = set()

    if not path.is_file():
        return {"chunk_ids": chunk_ids, "source_fig_slots": source_fig_slots}

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("tier") != "suppress_render":
                continue
            chunk_id = row.get("chunk_id")
            if isinstance(chunk_id, str) and chunk_id:
                chunk_ids.add(chunk_id)
            source_id = row.get("source_id")
            fig_slot = row.get("fig_slot")
            if isinstance(source_id, str) and isinstance(fig_slot, str):
                source_fig_slots.add((source_id, fig_slot.lower()))

    return {"chunk_ids": chunk_ids, "source_fig_slots": source_fig_slots}


def _resolve_flags_path(flags_path: Optional[str]) -> str:
    if flags_path:
        return str(Path(flags_path))
    env_path = __import__("os").environ.get("FIGURE_QUALITY_FLAGS_PATH")
    if env_path:
        return env_path
    return str(DEFAULT_FLAGS_PATH)


def infer_fig_slot(item: dict) -> Optional[str]:
    """Best-effort fig_slot from evidence card/figure metadata."""
    if not isinstance(item, dict):
        return None
    for field in ("fig_slot", "figure_slot"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    for field in ("image_path", "original_image_path", "chunk_id"):
        value = item.get(field)
        if not isinstance(value, str):
            continue
        match = _FIG_SLOT_RE.search(value)
        if match:
            return f"fig{match.group(1)}"
    return None


def is_suppress_render(item: dict, flags_path: Optional[str] = None) -> bool:
    """True when a card or figure matches a Tier-A suppress_render sidecar row."""
    if not isinstance(item, dict):
        return False

    index = _load_index(_resolve_flags_path(flags_path))

    chunk_id = item.get("chunk_id")
    if isinstance(chunk_id, str) and chunk_id in index["chunk_ids"]:
        return True

    source_id = item.get("source_id")
    if isinstance(source_id, str):
        fig_slot = infer_fig_slot(item)
        if fig_slot and (source_id, fig_slot) in index["source_fig_slots"]:
            return True

    return False


def strip_suppress_render_image_urls(
    cards: list[dict],
    flags_path: Optional[str] = None,
) -> list[dict]:
    """Remove figure image URLs from flagged cards but keep text/page evidence."""
    if not cards:
        return cards

    cleaned: list[dict] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        if not is_suppress_render(card, flags_path=flags_path):
            cleaned.append(card)
            continue
        copy = dict(card)
        for field in _FIGURE_URL_FIELDS:
            copy.pop(field, None)
        cleaned.append(copy)
    return cleaned


def filter_suppress_render_figures(
    figures: list[dict],
    flags_path: Optional[str] = None,
) -> list[dict]:
    """Drop suppress_render-tier figures from the figures list entirely."""
    if not figures:
        return figures
    return [
        figure
        for figure in figures
        if isinstance(figure, dict) and not is_suppress_render(figure, flags_path=flags_path)
    ]


def is_tiny_decoded_image(width: int, height: int, tiny_dim: int = TINY_DIM) -> bool:
    """True when either decoded edge is below the dimension-audit tiny threshold."""
    try:
        w = int(width)
        h = int(height)
    except (TypeError, ValueError):
        return False
    return w > 0 and h > 0 and (w < tiny_dim or h < tiny_dim)


def is_near_black_sample(
    mean_luminance: float,
    near_black_fraction: float,
    *,
    channel_max: int = NEAR_BLACK_CHANNEL_MAX,
    fraction_strict: float = NEAR_BLACK_FRACTION_STRICT,
    mean_max: float = NEAR_BLACK_MEAN_LUMINANCE_MAX,
    fraction_loose: float = NEAR_BLACK_FRACTION_LOOSE,
) -> bool:
    """Classify a downsampled RGB sample as a near-black / empty extraction stub.

    ``channel_max`` is documented for callers that compute ``near_black_fraction``
    (pixels with R,G,B all < channel_max); it is not used in the comparison itself.
    """
    _ = channel_max  # documented contract for sample producers (client + tests)
    try:
        mean_l = float(mean_luminance)
        frac = float(near_black_fraction)
    except (TypeError, ValueError):
        return False
    if frac < 0 or frac > 1:
        return False
    return frac >= fraction_strict or (mean_l < mean_max and frac >= fraction_loose)
