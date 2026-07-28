#!/usr/bin/env bash
# Pull the latest Chat MVP branch and restart the local server.
# Use this on WSL whenever a cloud agent pushed changes and your UI looks stale.
set -euo pipefail

BRANCH="${1:-cursor/topic-iterative-sse-layout-9231}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
MVP="$ROOT/frontend/pathology_hub_chat_mvp"

cd "$ROOT"
echo "==> repo: $ROOT"
echo "==> target branch: $BRANCH"

git fetch origin "$BRANCH"
# Stash only if dirty — never lose work silently without a stash entry.
if ! git diff --quiet || ! git diff --cached --quiet || [[ -n "$(git status --porcelain)" ]]; then
  echo "==> local changes detected — stashing before checkout"
  git stash push -u -m "auto-stash before sync_and_run_local $(date -u +%Y%m%dT%H%M%SZ)" || true
fi

git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

SHA="$(git rev-parse --short HEAD)"
echo "==> now on $(git branch --show-current) @ $SHA"

# Stop any prior uvicorn for this app (ignore if none).
pkill -f 'uvicorn app:app' 2>/dev/null || true
sleep 0.5

cd "$MVP"
echo "==> starting Chat MVP (hard-refresh browser after startup: Ctrl+Shift+R)"
echo "==> expect startup log: BUILD=topic-iterative-sse-layout-9231 sha=$SHA"
exec ./scripts/run_local.sh
