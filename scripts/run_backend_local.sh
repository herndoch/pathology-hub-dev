#!/usr/bin/env bash
# Run the canonical Pathology Hub backend (pathology_hub_v04_live_recovered)
# locally with the production GCS artifact env vars.
#
# Non-secret GCS artifact paths are derived from the committed canonical Cloud
# Run service descriptor so they never drift from production. Secrets come from
# the environment (injected by Cursor Cloud secrets on VM start):
#   - OPENAI_API_KEY
#   - PATHOLOGY_HUB_API_KEY
#   - GOOGLE_APPLICATION_CREDENTIALS_JSON  (service-account key JSON contents)
#
# Usage:
#   bash scripts/run_backend_local.sh                 # start uvicorn on :8080
#   PORT=9090 bash scripts/run_backend_local.sh       # custom port
#   DRY_RUN=1 bash scripts/run_backend_local.sh        # print env wiring, don't start
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/backend/pathology_hub_v04_live_recovered"
DESCRIPTOR="$ROOT/audits/prod_deploy_20260706/upload_package/preflight/service.describe.json"
PORT="${PORT:-8080}"
PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python3"

if [[ ! -f "$DESCRIPTOR" ]]; then
  echo "Missing canonical env descriptor: $DESCRIPTOR" >&2
  exit 1
fi

# Export every plain-value (non-secret) env var from the canonical descriptor.
while IFS='=' read -r name value; do
  [[ -z "$name" ]] && continue
  export "$name=$value"
done < <("$PYTHON" - "$DESCRIPTOR" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
for c in doc["spec"]["template"]["spec"]["containers"]:
    for e in c.get("env", []):
        if "value" in e:
            print(f"{e['name']}={e['value']}")
PY
)

# Wire GCS Application Default Credentials from the JSON secret if present.
if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" && -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
  ADC_FILE="/tmp/pathology_hub_gcp_adc.json"
  printf '%s' "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > "$ADC_FILE"
  chmod 600 "$ADC_FILE"
  export GOOGLE_APPLICATION_CREDENTIALS="$ADC_FILE"
fi

# Enable the v0_2 reliability layer by default.
export EVIDENCE_V0_2_ENABLED="${EVIDENCE_V0_2_ENABLED:-true}"
export EVIDENCE_QUERY_EXPANSION_ENABLED="${EVIDENCE_QUERY_EXPANSION_ENABLED:-true}"

missing=()
[[ -z "${OPENAI_API_KEY:-}" ]] && missing+=(OPENAI_API_KEY)
[[ -z "${PATHOLOGY_HUB_API_KEY:-}" ]] && missing+=(PATHOLOGY_HUB_API_KEY)
[[ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]] && missing+=(GOOGLE_APPLICATION_CREDENTIALS/JSON)
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "WARNING: missing credentials: ${missing[*]}" >&2
  echo "         The API will still boot but real retrieval will degrade." >&2
fi

echo "Backend: $APP_DIR"
echo "Descriptor env vars exported (non-secret GCS paths)."
echo "GOOGLE_APPLICATION_CREDENTIALS=${GOOGLE_APPLICATION_CREDENTIALS:-<unset>}"
echo "Open: http://127.0.0.1:${PORT}/health"

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "DRY_RUN=1: not starting uvicorn."
  exit 0
fi

cd "$APP_DIR"
exec "$PYTHON" -m uvicorn app:app --host 0.0.0.0 --port "$PORT"
