#!/usr/bin/env bash
# read_only_cloudrun_source_recovery.sh
#
# Pathology Hub — read-only Cloud Run / Artifact Registry / Cloud Build recovery audit.
# Collects service descriptions, image URLs, revision metadata, and optional GCS backend_api listings.
# Writes outputs into audits/backend_source_recovery/<timestamp>/
#
# SAFETY:
#   - Read-only gcloud and gcloud storage ls/describe only
#   - Does NOT deploy, update traffic, push images, or mutate GCS
#   - Does NOT print Secret Manager values or API keys
#   - Docker pull/export is optional and local-only (commented by default)
#
# Usage:
#   bash commands/read_only_cloudrun_source_recovery.sh
#   PROJECT=pathology-annotation-project REGION=us-central1 bash commands/read_only_cloudrun_source_recovery.sh

set -euo pipefail

PROJECT="${PROJECT:-pathology-annotation-project}"
REGION="${REGION:-us-central1}"
PROD_SERVICE="${PROD_SERVICE:-pathology-hub-v04}"
STAGING_SERVICE="${STAGING_SERVICE:-pathology-hub-v04-curriculum-staging}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
AUDIT_DIR="audits/backend_source_recovery/${TS}"
mkdir -p "${AUDIT_DIR}"

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "${AUDIT_DIR}/run.log"; }

run_capture() {
  local name="$1"
  shift
  local out="${AUDIT_DIR}/${name}.stdout.txt"
  local err="${AUDIT_DIR}/${name}.stderr.txt"
  local status="${AUDIT_DIR}/${name}.exit_code.txt"
  log "RUN: $*"
  set +e
  "$@" >"${out}" 2>"${err}"
  local rc=$?
  set -e
  echo "${rc}" >"${status}"
  log "  exit=${rc} stdout=$(wc -l <"${out}" | tr -d ' ') lines"
  return 0
}

log "Starting read-only backend source recovery audit"
log "AUDIT_DIR=${AUDIT_DIR}"
log "PROJECT=${PROJECT} REGION=${REGION}"

# --- Preflight (read-only) ---
run_capture "gcloud.config.list" \
  gcloud config list --format=json

run_capture "gcloud.auth.list" \
  gcloud auth list --filter=status:ACTIVE --format=json

# --- Production Cloud Run ---
run_capture "prod.service.describe" \
  gcloud run services describe "${PROD_SERVICE}" \
    --project="${PROJECT}" --region="${REGION}" --format=json

run_capture "prod.revisions.list" \
  gcloud run revisions list \
    --service="${PROD_SERVICE}" --project="${PROJECT}" --region="${REGION}" \
    --format=json

# Resolve latest ready revision name from describe output (best effort)
LATEST_REV=""
if command -v python3 >/dev/null 2>&1; then
  LATEST_REV="$(python3 - <<'PY' "${AUDIT_DIR}/prod.service.describe.stdout.txt"
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path))
    print(data.get("status", {}).get("latestReadyRevisionName", "") or "")
except Exception:
    print("")
PY
)"
fi

if [[ -n "${LATEST_REV}" ]]; then
  log "Latest ready revision: ${LATEST_REV}"
  run_capture "prod.revision.describe" \
    gcloud run revisions describe "${LATEST_REV}" \
      --project="${PROJECT}" --region="${REGION}" --format=json

  # Image URI extraction (no pull)
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<PY >"${AUDIT_DIR}/prod.image.uri.txt"
import json
data = json.load(open("${AUDIT_DIR}/prod.revision.describe.stdout.txt"))
containers = data.get("spec", {}).get("containers", [])
image = containers[0].get("image", "") if containers else ""
print(image)
PY
    IMAGE_URI="$(tr -d '\n' <"${AUDIT_DIR}/prod.image.uri.txt")"
    log "Production image URI: ${IMAGE_URI}"

    if [[ -n "${IMAGE_URI}" ]]; then
      run_capture "prod.image.describe" \
        gcloud artifacts docker images describe "${IMAGE_URI}" --format=json
    fi
  fi
else
  log "WARN: Could not resolve latest ready revision — check prod.service.describe output"
fi

# --- Staging Cloud Run (may not exist) ---
run_capture "staging.service.describe" \
  gcloud run services describe "${STAGING_SERVICE}" \
    --project="${PROJECT}" --region="${REGION}" --format=json

run_capture "staging.revisions.list" \
  gcloud run revisions list \
    --service="${STAGING_SERVICE}" --project="${PROJECT}" --region="${REGION}" \
    --format=json

# --- Artifact Registry listing (read-only) ---
run_capture "artifact_registry.images.pathology-hub" \
  gcloud artifacts docker images list \
    "us-central1-docker.pkg.dev/${PROJECT}/pathology-hub" \
    --include-tags --limit=100 --format=json

# Fallback repository names (common variants)
for REPO in pathology-hub pathology_hub cloud-run-source-deploy; do
  run_capture "artifact_registry.images.${REPO}" \
    gcloud artifacts docker images list \
      "us-central1-docker.pkg.dev/${PROJECT}/${REPO}" \
      --include-tags --limit=50 --format=json
done

# --- Cloud Build history (read-only) ---
run_capture "cloudbuild.list" \
  gcloud builds list --project="${PROJECT}" --limit=50 --format=json

# Filter builds mentioning pathology-hub (best effort)
if command -v python3 >/dev/null 2>&1; then
  python3 - <<PY >"${AUDIT_DIR}/cloudbuild.pathology_hub.filtered.json"
import json
try:
    builds = json.load(open("${AUDIT_DIR}/cloudbuild.list.stdout.txt"))
except Exception:
    builds = []
needle = "pathology-hub"
filtered = []
for b in builds if isinstance(builds, list) else []:
    blob = json.dumps(b).lower()
    if needle in blob:
        filtered.append({"id": b.get("id"), "status": b.get("status"), "createTime": b.get("createTime"), "images": b.get("images"), "substitutions": b.get("substitutions")})
json.dump(filtered, open("${AUDIT_DIR}/cloudbuild.pathology_hub.filtered.json", "w"), indent=2)
print(len(filtered))
PY
  log "Cloud Build entries mentioning pathology-hub: $(cat "${AUDIT_DIR}/cloudbuild.pathology_hub.filtered.json" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null || echo '?')"
fi

# --- GCS backend_api audit paths (read-only ls) ---
run_capture "gcs.backend_api_audits.ls" \
  gcloud storage ls -l "gs://pathology_hub/06_audits/backend_api/**"

run_capture "gcs.backend_api_backups.ls" \
  gcloud storage ls -l "gs://pathology_hub/99_backups/backend_api/**"

run_capture "gcs.api_artifacts.openapi.ls" \
  gcloud storage ls "gs://pathology_hub/04_api_artifacts/**"

# --- Optional: Cloud Run logs sample (read-only, may contain sensitive data — review before sharing) ---
run_capture "logging.run.sample" \
  gcloud logging read \
    "resource.type=cloud_run_revision AND resource.labels.service_name=${PROD_SERVICE}" \
    --project="${PROJECT}" --limit=15 --format=json

# --- Optional Docker extract (DISABLED by default) ---
# Uncomment ONLY if you need local filesystem extract and have docker + artifact registry auth.
# This does NOT deploy anything.
#
# if [[ -n "${IMAGE_URI:-}" ]] && command -v docker >/dev/null 2>&1; then
#   log "Docker pull (local only): ${IMAGE_URI}"
#   docker pull "${IMAGE_URI}"
#   CID=$(docker create "${IMAGE_URI}")
#   docker export "${CID}" | tar -t > "${AUDIT_DIR}/image.filelist.txt"
#   mkdir -p "${AUDIT_DIR}/extracted_app"
#   docker cp "${CID}:/app/." "${AUDIT_DIR}/extracted_app/" 2>"${AUDIT_DIR}/docker.cp.stderr.txt" || true
#   docker rm "${CID}" >/dev/null
#   log "Extracted app tree to ${AUDIT_DIR}/extracted_app/"
# fi

# --- Compare to repo copy if present ---
REPO_APP="backend/pathology_hub_v04_curriculum/app.py"
if [[ -f "${REPO_APP}" ]]; then
  cp "${REPO_APP}" "${AUDIT_DIR}/repo.app.py.copy"
  wc -l "${REPO_APP}" > "${AUDIT_DIR}/repo.app.py.linecount.txt"
  grep -n "APP_VERSION" "${REPO_APP}" > "${AUDIT_DIR}/repo.app.version.txt" || true
  log "Repo app.py copied for diff reference ($(wc -l <"${REPO_APP}") lines)"
fi

# --- Audit manifest JSON ---
python3 - <<PY
import json, os, hashlib, datetime
from pathlib import Path

audit_dir = Path("${AUDIT_DIR}")
files = sorted(p for p in audit_dir.rglob("*") if p.is_file())

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

manifest = {
    "schema_version": "backend_source_recovery_audit.v1",
    "generated_at_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    "project": "${PROJECT}",
    "region": "${REGION}",
    "prod_service": "${PROD_SERVICE}",
    "staging_service": "${STAGING_SERVICE}",
    "output_directory": str(audit_dir),
    "commands_mode": "read_only",
    "deploy_performed": False,
    "gcs_mutated": False,
    "secrets_printed": False,
    "artifacts": [
        {"path": str(p.relative_to(audit_dir)), "size_bytes": p.stat().st_size, "sha256": sha256(p)}
        for p in files if p.name != "audit.json"
    ],
    "known_limitations": [
        "Read-only describe/list only unless Docker extract block is manually enabled.",
        "Cloud Build source tarballs may require separate download approval.",
        "Log samples may contain sensitive lines — review before sharing.",
        "Recovery is NOT complete until extracted image APP_VERSION matches live health.",
    ],
    "recovery_status": "audit_collected_pending_analysis",
}
json.dump(manifest, open(audit_dir / "audit.json", "w"), indent=2)
print("Wrote", audit_dir / "audit.json")
PY

log "Done. Review ${AUDIT_DIR}/audit.json"
log "Next: compare prod.image.uri.txt with Artifact Registry; optional Docker extract for /app tree."
