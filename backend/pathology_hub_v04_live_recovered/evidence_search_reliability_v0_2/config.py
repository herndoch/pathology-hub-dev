"""Environment-driven configuration for evidence search reliability v0_2."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "query_expansion_rules_v0_2.json"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ExpansionConfig:
    enabled: bool
    debug: bool
    rules_path: Path
    rules_doc: dict[str, Any]
    root_gating_enabled: bool = True

    @property
    def rules(self) -> list[dict[str, Any]]:
        return list(self.rules_doc.get("rules") or [])

    @property
    def organ_root_hints(self) -> dict[str, str]:
        return dict(self.rules_doc.get("organ_root_hints") or {})

    @property
    def generic_terms_never_override_root(self) -> list[str]:
        return list(self.rules_doc.get("generic_terms_never_override_root") or [])


def load_rules(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(
    *,
    enabled: bool | None = None,
    debug: bool | None = None,
    root_gating_enabled: bool | None = None,
    rules_path: Path | str | None = None,
) -> ExpansionConfig:
    path = Path(rules_path or os.environ.get("EVIDENCE_QUERY_EXPANSION_RULES_PATH") or DEFAULT_RULES_PATH)
    return ExpansionConfig(
        enabled=_env_bool("EVIDENCE_QUERY_EXPANSION_ENABLED", True) if enabled is None else enabled,
        debug=_env_bool("EVIDENCE_QUERY_EXPANSION_DEBUG", False) if debug is None else debug,
        root_gating_enabled=(
            _env_bool("EVIDENCE_ROOT_GATING_ENABLED", True) if root_gating_enabled is None else root_gating_enabled
        ),
        rules_path=path,
        rules_doc=load_rules(path),
    )
