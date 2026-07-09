#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
APP_DIR="$ROOT/tools/curriculum_provenance_browser"
PORT="${PORT:-8765}"

cd "$APP_DIR"

if [[ -x "$APP_DIR/.venv/bin/python" ]]; then
  PYTHON="$APP_DIR/.venv/bin/python"
else
  PYTHON="python3"
fi

export CURRICULUM_LOCATOR_SQLITE="${CURRICULUM_LOCATOR_SQLITE:-$ROOT/outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_2.sqlite}"

if [[ ! -f "$CURRICULUM_LOCATOR_SQLITE" ]]; then
  echo "Missing SQLite index: $CURRICULUM_LOCATOR_SQLITE" >&2
  exit 1
fi

echo "Curriculum provenance browser (read-only)"
echo "SQLite: $CURRICULUM_LOCATOR_SQLITE"
echo "Open: http://127.0.0.1:${PORT}/"
echo

exec "$PYTHON" -m uvicorn app:app --host 127.0.0.1 --port "$PORT" --reload
