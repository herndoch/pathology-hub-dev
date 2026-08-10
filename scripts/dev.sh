#!/usr/bin/env bash
# Pathology Hub local dev helper — you do NOT need to learn virtualenv commands.
# This script always uses the repo's .venv for you.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"
GCP_ADC_FILE="/tmp/pathology-hub-gcp-adc.json"

# Load secrets from .env (local) or from Cursor-injected environment variables (cloud).
load_secrets() {
  if [[ -f "$ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/.env"
    set +a
  fi

  export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-pathology-annotation-project}"

  if [[ -n "${GCP_SERVICE_ACCOUNT_JSON:-}" && -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
    printf '%s' "$GCP_SERVICE_ACCOUNT_JSON" > "$GCP_ADC_FILE"
    chmod 600 "$GCP_ADC_FILE"
    export GOOGLE_APPLICATION_CREDENTIALS="$GCP_ADC_FILE"
  fi
}

secret_status() {
  local name="$1"
  if [[ -n "${!name:-}" ]]; then
    echo "  ✓ $name"
  else
    echo "  ✗ $name (missing)"
  fi
}

ensure_venv() {
  if [[ ! -x "$PY" ]]; then
    echo "First-time setup: creating .venv and installing dependencies…"
    python3 -m venv "$VENV"
    "$PIP" install --upgrade pip
    "$PIP" install \
      -r "$ROOT/backend/pathology_hub_v04_curriculum/requirements.txt" \
      -r "$ROOT/tools/curriculum_provenance_browser/requirements.txt" \
      pytest
    echo "Done. You're ready to run: ./scripts/dev.sh test"
    echo
  fi
}

usage() {
  cat <<'EOF'
Pathology Hub dev helper (virtualenv is handled for you)

Usage: ./scripts/dev.sh <command>

Commands:
  setup      Create .venv and install dependencies (first time only)
  test       Run the offline test suite
  test-v02   Run only v0_2 evidence-search unit tests
  check      Syntax-check Python sources (compileall)
  browser    Start Curriculum Provenance Browser on http://127.0.0.1:8765
  api        Start Backend Evidence API on http://127.0.0.1:8080
  secrets    Show which secrets are configured (values never printed)
  help       Show this message

Secrets: add them in Cursor Cloud project settings, or copy .env.example → .env locally.
  PATHOLOGY_HUB_API_KEY   — API auth (GCP Secret Manager: pathology-hub-api-key)
  OPENAI_API_KEY          — query embeddings for local backend
  GCP_SERVICE_ACCOUNT_JSON — full service-account JSON for gs://pathology_hub access
    (or set GOOGLE_APPLICATION_CREDENTIALS to a JSON file path)

You never need to run "source .venv/bin/activate" — this script uses .venv for you.

Examples:
  ./scripts/dev.sh setup
  ./scripts/dev.sh test
  CURRICULUM_LOCATOR_SQLITE=/path/to/index.sqlite ./scripts/dev.sh browser
EOF
}

cmd_setup() {
  ensure_venv
  echo ".venv is ready at $VENV"
}

cmd_test() {
  ensure_venv
  cd "$ROOT"
  "$PY" -m pytest -v
}

cmd_test_v02() {
  ensure_venv
  cd "$ROOT"
  "$PY" -m pytest -v tests/test_evidence_query_expansion_v0_2.py tests/test_evidence_root_gating_v0_2.py
}

cmd_check() {
  ensure_venv
  "$PY" -m compileall -q "$ROOT/backend" "$ROOT/tools" "$ROOT/scripts" "$ROOT/tests"
  echo "Syntax check passed."
}

cmd_browser() {
  ensure_venv
  export CURRICULUM_LOCATOR_SQLITE="${CURRICULUM_LOCATOR_SQLITE:-$ROOT/outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_2.sqlite}"
  if [[ ! -f "$CURRICULUM_LOCATOR_SQLITE" ]]; then
    echo "Missing SQLite index: $CURRICULUM_LOCATOR_SQLITE" >&2
    echo "Set CURRICULUM_LOCATOR_SQLITE to an existing index file, or build one locally." >&2
    exit 1
  fi
  cd "$ROOT/tools/curriculum_provenance_browser"
  echo "Curriculum browser → http://127.0.0.1:8765/"
  exec "$PY" -m uvicorn app:app --host 127.0.0.1 --port 8765 --reload
}

cmd_api() {
  ensure_venv
  cd "$ROOT/backend/pathology_hub_v04_curriculum"
  echo "Backend API → http://127.0.0.1:8080/ (needs GCS + OpenAI creds for /health and /evidence/search)"
  exec "$PY" -m uvicorn app:app --host 127.0.0.1 --port 8080
}

cmd_secrets() {
  load_secrets
  echo "Secret status (values are never shown):"
  secret_status PATHOLOGY_HUB_API_KEY
  secret_status OPENAI_API_KEY
  secret_status GOOGLE_APPLICATION_CREDENTIALS
  secret_status GCP_SERVICE_ACCOUNT_JSON
  secret_status GOOGLE_CLOUD_PROJECT
  echo
  if [[ -f "$ROOT/.env" ]]; then
    echo "Loaded from: $ROOT/.env"
  else
    echo "No .env file — using environment variables only."
    echo "Copy .env.example → .env locally, or add secrets in Cursor Cloud settings."
  fi
}

main() {
  case "${1:-help}" in
    setup) load_secrets; cmd_setup ;;
    test) load_secrets; cmd_test ;;
    test-v02) load_secrets; cmd_test_v02 ;;
    check) load_secrets; cmd_check ;;
    browser) load_secrets; cmd_browser ;;
    api) load_secrets; cmd_api ;;
    secrets) cmd_secrets ;;
    help|-h|--help) usage ;;
    *)
      echo "Unknown command: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
