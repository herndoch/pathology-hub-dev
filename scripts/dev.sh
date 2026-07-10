#!/usr/bin/env bash
# Pathology Hub local dev helper — you do NOT need to learn virtualenv commands.
# This script always uses the repo's .venv for you.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

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
  help       Show this message

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

main() {
  case "${1:-help}" in
    setup) cmd_setup ;;
    test) cmd_test ;;
    test-v02) cmd_test_v02 ;;
    check) cmd_check ;;
    browser) cmd_browser ;;
    api) cmd_api ;;
    help|-h|--help) usage ;;
    *)
      echo "Unknown command: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
