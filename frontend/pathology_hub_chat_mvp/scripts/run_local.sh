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
# Live Elsevier Scopus + PubMed + OncoKB on every topic_page (default ON).
export TOPIC_PAGE_LIVE_LITERATURE="${TOPIC_PAGE_LIVE_LITERATURE:-1}"
# Multi-round retrieval with SSE progress (default ON). Set 0 for single-pass.
export TOPIC_PAGE_ITERATIVE="${TOPIC_PAGE_ITERATIVE:-1}"
export TOPIC_PAGE_ITERATIVE_ROUNDS="${TOPIC_PAGE_ITERATIVE_ROUNDS:-3}"

echo "Pathology Hub Chat MVP → http://127.0.0.1:${PORT}/"
echo "Set PATHOLOGY_HUB_API_KEY or HUB_API for evidence search."
echo "Set OPENAI_API_KEY for GPT-like synthesis modes."
echo "TOPIC_PAGE_LIVE_LITERATURE=${TOPIC_PAGE_LIVE_LITERATURE} (Elsevier/PubMed/OncoKB; set 0 to disable)."
echo "TOPIC_PAGE_ITERATIVE=${TOPIC_PAGE_ITERATIVE} rounds=${TOPIC_PAGE_ITERATIVE_ROUNDS} (SSE: POST /api/chat/stream)."
echo "Hard-refresh the browser (Ctrl+Shift+R). Status badge should say 'live thinking' when this build is running."

exec uvicorn app:app --host 127.0.0.1 --port "$PORT" --reload
