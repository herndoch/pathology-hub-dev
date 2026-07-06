#!/usr/bin/env bash
# run_v0_2_staging_validation.sh
#
# Staging-only validation wrapper for Evidence Search Reliability v0_2.
# Runs smoke tests and optionally live v0_2 benchmark against STAGING URL.
#
# GUARDRAILS:
#   - REFUSES to run against production URL unless you explicitly edit ALLOW_PRODUCTION below
#   - Does NOT deploy, mutate GCS, or print API keys
#   - Requires PATHOLOGY_HUB_API_KEY in environment (not in repo)
#
# Usage:
#   export PATHOLOGY_HUB_API_KEY="..."   # from Secret Manager — do not commit
#   export STAGING_BASE_URL="https://pathology-hub-v04-curriculum-staging-vorn5q2kga-uc.a.run.app"
#   bash commands/run_v0_2_staging_validation.sh
#
# Optional:
#   RUN_LIVE_BENCHMARK=1 bash commands/run_v0_2_staging_validation.sh

set -euo pipefail

# =============================================================================
# PRODUCTION GUARDRAIL — DO NOT SET TO 1 unless you explicitly intend production
# =============================================================================
ALLOW_PRODUCTION=0

PRODUCTION_URL="https://pathology-hub-v04-vorn5q2kga-uc.a.run.app"
STAGING_BASE_URL="${STAGING_BASE_URL:-https://pathology-hub-v04-curriculum-staging-vorn5q2kga-uc.a.run.app}"
RUN_LIVE_BENCHMARK="${RUN_LIVE_BENCHMARK:-0}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="audits/v0_2_staging_validation/${TS}"
mkdir -p "${OUT_DIR}"

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "${OUT_DIR}/run.log"; }

# --- URL guardrail ---
if [[ "${STAGING_BASE_URL}" == "${PRODUCTION_URL}" ]]; then
  echo "ERROR: STAGING_BASE_URL equals production URL." >&2
  echo "Set STAGING_BASE_URL to a staging service or edit ALLOW_PRODUCTION=1 (not recommended)." >&2
  exit 1
fi

if [[ "${STAGING_BASE_URL}" == *"pathology-hub-v04-vorn5q2kga"* ]] && [[ "${ALLOW_PRODUCTION}" != "1" ]]; then
  echo "ERROR: URL appears to be production pathology-hub-v04." >&2
  echo "Use curriculum-staging or dedicated evidence-staging URL." >&2
  echo "To override (DANGEROUS): set ALLOW_PRODUCTION=1" >&2
  exit 1
fi

if [[ "${ALLOW_PRODUCTION}" == "1" ]]; then
  log "WARNING: ALLOW_PRODUCTION=1 — running against production-like URL at user risk"
fi

# --- API key guardrail ---
if [[ -z "${PATHOLOGY_HUB_API_KEY:-}" ]]; then
  echo "ERROR: PATHOLOGY_HUB_API_KEY not set." >&2
  echo "Export from Secret Manager: pathology-hub-api-key" >&2
  echo "Do not write the key to disk in this repo." >&2
  exit 1
fi

log "v0_2 staging validation starting"
log "STAGING_BASE_URL=${STAGING_BASE_URL}"
log "OUT_DIR=${OUT_DIR}"
log "RUN_LIVE_BENCHMARK=${RUN_LIVE_BENCHMARK}"

export PATHOLOGY_HUB_BASE="${STAGING_BASE_URL}"

# --- Step 1: Health check (no key) ---
log "Step 1: GET /health"
HTTP_CODE=$(curl -sS -o "${OUT_DIR}/health.json" -w "%{http_code}" "${STAGING_BASE_URL}/health" || echo "000")
echo "${HTTP_CODE}" > "${OUT_DIR}/health.http_code.txt"
log "  health HTTP ${HTTP_CODE}"
if [[ "${HTTP_CODE}" != "200" ]]; then
  log "FAIL: health not 200 — aborting"
  exit 2
fi

# Redact any key-like fields from health output copy for sharing
python3 - <<'PY' "${OUT_DIR}/health.json" "${OUT_DIR}/health.redacted.json" 2>/dev/null || cp "${OUT_DIR}/health.json" "${OUT_DIR}/health.redacted.json"
import json, sys, re
inp, outp = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(inp))
    blob = json.dumps(data)
    blob = re.sub(r'(?i)(api[_-]?key|token|secret)["\']?\s*[:=]\s*["\'][^"\']+', r'\1":"REDACTED"', blob)
    json.dump(json.loads(blob), open(outp, "w"), indent=2)
except Exception:
    open(outp, "w").write(open(inp).read())
PY

# --- Step 2: v10.5 smoke (forbidden tags) ---
log "Step 2: v10.5 smoke test"
SMOKE_SCRIPT="project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/codex_local/api_smoke_test.py"
if [[ -f "${SMOKE_SCRIPT}" ]]; then
  set +e
  python3 "${SMOKE_SCRIPT}" > "${OUT_DIR}/smoke.stdout.txt" 2> "${OUT_DIR}/smoke.stderr.txt"
  SMOKE_RC=$?
  set -e
  echo "${SMOKE_RC}" > "${OUT_DIR}/smoke.exit_code.txt"
  log "  smoke exit=${SMOKE_RC}"
  if [[ "${SMOKE_RC}" != "0" ]]; then
    log "FAIL: smoke test failed — see ${OUT_DIR}/smoke.stderr.txt"
    exit 3
  fi
else
  log "WARN: smoke script not found at ${SMOKE_SCRIPT}"
fi

# --- Step 3: v0_2 abbreviation probes (manual payloads) ---
log "Step 3: v0_2 abbreviation probes"
export STAGING_BASE_URL OUT_DIR
python3 - <<PY
import json, os, urllib.request

base = os.environ["PATHOLOGY_HUB_BASE"]
key = os.environ["PATHOLOGY_HUB_API_KEY"]
out = os.path.join(os.environ["OUT_DIR"], "abbreviation_probes.json")
probes = [
    {"query": "LCIS", "sources": ["who"], "max_results": 5, "compact": True},
    {"query": "SSL", "sources": ["textbooks"], "max_results": 5, "compact": True},
    {"query": "IPMN", "sources": ["textbooks"], "max_results": 5, "compact": True, "include_figures": True, "max_figures": 5},
    {"query": "bullous pemphigoid", "sources": ["who"], "max_results": 5, "compact": True},
    {"query": "CMF", "sources": ["textbooks"], "max_results": 5, "compact": True},
]
results = []
for p in probes:
    req = urllib.request.Request(
        f"{base}/evidence/search",
        data=json.dumps(p).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode())
            results.append({
                "payload": p,
                "status": resp.status,
                "schema_version": body.get("schema_version"),
                "source_status": body.get("source_status"),
                "warnings": body.get("warnings"),
            })
    except Exception as e:
        results.append({"payload": p, "error": str(e)})
json.dump(results, open(out, "w"), indent=2)
print(f"Wrote {out}")
PY

log "  abbreviation probes written to ${OUT_DIR}/abbreviation_probes.json"

# --- Step 4: Offline regression (no API) ---
log "Step 4: offline v0_2 replay (no API)"
REPLAY="06_audits/evidence_retrieval_writable/benchmark_v0_2/run_offline_v0_2_replay.py"
if [[ -f "${REPLAY}" ]]; then
  set +e
  python3 "${REPLAY}" > "${OUT_DIR}/offline_replay.stdout.txt" 2> "${OUT_DIR}/offline_replay.stderr.txt"
  REPLAY_RC=$?
  set -e
  echo "${REPLAY_RC}" > "${OUT_DIR}/offline_replay.exit_code.txt"
  log "  offline replay exit=${REPLAY_RC}"
else
  log "WARN: offline replay script not found"
fi

# --- Step 5: Optional live benchmark (staging only) ---
if [[ "${RUN_LIVE_BENCHMARK}" == "1" ]]; then
  log "Step 5: live v0_2 benchmark (STAGING ONLY)"
  BENCH="06_audits/evidence_retrieval_writable/benchmark_v0_2/run_live_v0_2_benchmark.py"
  if [[ -f "${BENCH}" ]]; then
    BENCH_OUT="${OUT_DIR}/benchmark_v0_2_staging"
    mkdir -p "${BENCH_OUT}"
    set +e
    python3 "${BENCH}" --base-url "${STAGING_BASE_URL}" --output-dir "${BENCH_OUT}" \
      > "${OUT_DIR}/benchmark.stdout.txt" 2> "${OUT_DIR}/benchmark.stderr.txt"
    BENCH_RC=$?
    set -e
    echo "${BENCH_RC}" > "${OUT_DIR}/benchmark.exit_code.txt"
    log "  benchmark exit=${BENCH_RC}"
  else
    log "WARN: benchmark runner not found"
  fi
else
  log "Step 5: skipped live benchmark (set RUN_LIVE_BENCHMARK=1 to enable)"
fi

# --- Audit summary ---
python3 - <<PY
import json, datetime
from pathlib import Path
out = Path("${OUT_DIR}")
summary = {
    "schema_version": "v0_2_staging_validation_audit.v1",
    "generated_at_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    "staging_base_url": "${STAGING_BASE_URL}",
    "production_url_blocked": ${ALLOW_PRODUCTION} != 1,
    "live_benchmark_run": "${RUN_LIVE_BENCHMARK}" == "1",
    "deploy_performed": False,
    "gcs_mutated": False,
    "known_limitations": [
        "Validation assumes v0_2 is deployed server-side on staging.",
        "If staging lacks v0_2 module, abbreviation probes reflect pre-v0_2 behavior.",
        "Miss target (<=14) requires full 1008-row benchmark with RUN_LIVE_BENCHMARK=1.",
    ],
}
json.dump(summary, open(out / "audit.json", "w"), indent=2)
PY

log "Validation complete. Audit: ${OUT_DIR}/audit.json"
log "If smoke passed but abbreviation probes unchanged vs production, v0_2 may not be deployed server-side yet."
