"""Secret loading helper for the Pathology Hub Chat MVP.

Loads secrets from the process environment first. If a secret is not present
in the environment, falls back to Google Secret Manager via the `gcloud`
CLI (`gcloud secrets versions access latest --secret=<name> --project=<project>`).

SAFETY RULES (do not violate):
- Never print, log, or return a raw secret value in any exception message,
  log line, or API response.
- Only expose *presence*, *length*, and a short SHA-256 fingerprint
  (first 8 hex chars) for diagnostics.
- Never write secret values to disk or to Git.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

GCP_PROJECT = "830130787988"

OPENAI_SECRET_NAME = "OPENAI"
PATHOLOGY_HUB_SECRET_NAME = "PATHOLOGY_HUB_API_KEY"

OPENAI_ENV_VAR = "OPENAI_API_KEY"
PATHOLOGY_HUB_ENV_VAR = "PATHOLOGY_HUB_API_KEY"
PATHOLOGY_HUB_ALT_ENV_VARS = ("PATHOLOGY_HUB_API_KEY", "HUB_API")


@dataclass
class SecretStatus:
    """Diagnostic-only view of a secret. Never carries the raw value."""

    name: str
    present: bool
    source: str
    length: int
    fingerprint: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "present": self.present,
            "source": self.source,
            "length": self.length,
            "fingerprint": self.fingerprint,
        }


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def _fetch_from_gcloud(secret_id: str, project: str = GCP_PROJECT) -> Optional[str]:
    """Fetch the latest version of a secret from Google Secret Manager.

    Returns None (never raises the underlying stderr, which could echo
    identifying info) if the `gcloud` call fails for any reason.
    """
    try:
        result = subprocess.run(
            [
                "gcloud",
                "secrets",
                "versions",
                "access",
                "latest",
                f"--secret={secret_id}",
                f"--project={project}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        value = result.stdout.strip()
        return value or None
    except (subprocess.SubprocessError, OSError):
        return None


def load_secret(
    env_var: str,
    secret_id: str,
    project: str = GCP_PROJECT,
) -> tuple[Optional[str], str]:
    """Load a secret value and report where it came from.

    Returns (value_or_None, source) where source is one of
    "env", "gcloud_secret_manager", or "missing".
    """
    env_value = os.environ.get(env_var)
    if env_value:
        return env_value, "env"

    gcloud_value = _fetch_from_gcloud(secret_id, project=project)
    if gcloud_value:
        return gcloud_value, "gcloud_secret_manager"

    return None, "missing"


def get_openai_api_key() -> Optional[str]:
    value, _source = load_secret(OPENAI_ENV_VAR, OPENAI_SECRET_NAME)
    return value


def get_pathology_hub_api_key() -> Optional[str]:
    for env_var in PATHOLOGY_HUB_ALT_ENV_VARS:
        env_value = os.environ.get(env_var)
        if env_value:
            return env_value
    value, _source = load_secret(PATHOLOGY_HUB_ENV_VAR, PATHOLOGY_HUB_SECRET_NAME)
    return value


def status_for(
    env_var: str,
    secret_id: str,
    project: str = GCP_PROJECT,
) -> SecretStatus:
    value, source = load_secret(env_var, secret_id, project=project)
    return SecretStatus(
        name=env_var,
        present=bool(value),
        source=source,
        length=len(value) if value else 0,
        fingerprint=_fingerprint(value) if value else "",
    )


def all_secret_status() -> dict:
    """Return a diagnostic-only summary of both secrets. Safe to log/print/return."""
    return {
        "openai": status_for(OPENAI_ENV_VAR, OPENAI_SECRET_NAME).to_dict(),
        "pathology_hub": status_for(PATHOLOGY_HUB_ENV_VAR, PATHOLOGY_HUB_SECRET_NAME).to_dict(),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(all_secret_status(), indent=2))
