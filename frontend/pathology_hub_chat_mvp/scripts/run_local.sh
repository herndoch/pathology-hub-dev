#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -r requirements.txt

PORT="${PORT:-8000}"
echo "Pathology Hub Chat MVP → http://127.0.0.1:${PORT}/"
echo "Set PATHOLOGY_HUB_API_KEY or HUB_API for evidence search."
echo "Set OPENAI_API_KEY for GPT-like synthesis modes."

exec uvicorn app:app --host 127.0.0.1 --port "$PORT" --reload
