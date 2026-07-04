#!/usr/bin/env bash
set -euo pipefail

PROJECT="pathology-annotation-project"
BUCKETS=(
  "gs://pathology_hub"
  "gs://pathology-hub-0"
)
OUT_DIR="audits/gcs_inventory"
SCHEMA_VERSION="1.0"

usage() {
  cat <<'USAGE'
Usage: scripts/inventory_gcs_roots.sh [--yes]

Inventories the top two listing levels of:
  - gs://pathology_hub
  - gs://pathology-hub-0

Outputs are written to audits/gcs_inventory/.

The script prints the exact gcloud commands before running them and requires
typing RUN unless --yes is provided.
USAGE
}

ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --yes)
      ASSUME_YES=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
run_dir="${OUT_DIR}/${timestamp}"
mkdir -p "$run_dir"

slug_for() {
  local uri="$1"
  printf '%s' "${uri#gs://}" | tr -c 'A-Za-z0-9._-' '_'
}

json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\r'/\\r}"
  value="${value//$'\t'/\\t}"
  printf '%s' "$value"
}

commands=()
for bucket in "${BUCKETS[@]}"; do
  commands+=("gcloud storage ls --project=${PROJECT} \"${bucket}\"")
  commands+=("gcloud storage ls --project=${PROJECT} \"${bucket}/*\"")
done

cat <<EOF
About to run these read-only GCS inventory commands:
EOF
printf '  %s\n' "${commands[@]}"

if [[ "$ASSUME_YES" -ne 1 ]]; then
  printf '\nType RUN to execute these gcloud commands: '
  read -r approval
  if [[ "$approval" != "RUN" ]]; then
    echo "Aborted before running gcloud commands."
    exit 1
  fi
fi

run_command() {
  local bucket="$1"
  local level="$2"
  local pattern="$3"
  local slug
  local stdout_file
  local stderr_file
  local status_file
  local status

  slug="$(slug_for "$bucket")"
  stdout_file="${run_dir}/${slug}_${level}.stdout.txt"
  stderr_file="${run_dir}/${slug}_${level}.stderr.txt"
  status_file="${run_dir}/${slug}_${level}.status.txt"

  set +e
  gcloud storage ls --project="$PROJECT" "$pattern" >"$stdout_file" 2>"$stderr_file"
  status=$?
  set -e

  printf '%s\n' "$status" >"$status_file"
}

for bucket in "${BUCKETS[@]}"; do
  run_command "$bucket" "level1" "$bucket"
  run_command "$bucket" "level2" "${bucket}/*"
done

audit_file="${run_dir}/audit.json"
{
  printf '{\n'
  printf '  "schema_version": "%s",\n' "$(json_escape "$SCHEMA_VERSION")"
  printf '  "timestamp_utc": "%s",\n' "$(json_escape "$timestamp")"
  printf '  "project": "%s",\n' "$(json_escape "$PROJECT")"
  printf '  "buckets_checked": [\n'
  for i in "${!BUCKETS[@]}"; do
    comma=","
    [[ "$i" -eq "$((${#BUCKETS[@]} - 1))" ]] && comma=""
    printf '    "%s"%s\n' "$(json_escape "${BUCKETS[$i]}")" "$comma"
  done
  printf '  ],\n'
  printf '  "output_directory": "%s",\n' "$(json_escape "$run_dir")"
  printf '  "command_outputs_saved": [\n'

  entry_index=0
  total_entries="$((${#BUCKETS[@]} * 2))"
  for bucket in "${BUCKETS[@]}"; do
    slug="$(slug_for "$bucket")"
    for level in "level1" "level2"; do
      pattern="$bucket"
      [[ "$level" == "level2" ]] && pattern="${bucket}/*"
      command="gcloud storage ls --project=${PROJECT} \"${pattern}\""
      stdout_file="${run_dir}/${slug}_${level}.stdout.txt"
      stderr_file="${run_dir}/${slug}_${level}.stderr.txt"
      status_file="${run_dir}/${slug}_${level}.status.txt"
      status="$(cat "$status_file")"
      stdout_line_count="$(wc -l <"$stdout_file" | tr -d ' ')"
      stderr_line_count="$(wc -l <"$stderr_file" | tr -d ' ')"

      entry_index="$((entry_index + 1))"
      comma=","
      [[ "$entry_index" -eq "$total_entries" ]] && comma=""

      printf '    {\n'
      printf '      "bucket": "%s",\n' "$(json_escape "$bucket")"
      printf '      "listing_level": "%s",\n' "$(json_escape "$level")"
      printf '      "command": "%s",\n' "$(json_escape "$command")"
      printf '      "stdout_path": "%s",\n' "$(json_escape "$stdout_file")"
      printf '      "stderr_path": "%s",\n' "$(json_escape "$stderr_file")"
      printf '      "status_path": "%s",\n' "$(json_escape "$status_file")"
      printf '      "exit_status": %s,\n' "$status"
      printf '      "stdout_line_count": %s,\n' "$stdout_line_count"
      printf '      "stderr_line_count": %s\n' "$stderr_line_count"
      printf '    }%s\n' "$comma"
    done
  done
  printf '  ],\n'
  printf '  "known_limitations": [\n'
  printf '    "This is a read-only inventory using gcloud storage ls; it does not upload, modify, normalize, tag, vectorize, index, or API-expose any source.",\n'
  printf '    "GCS is a flat object store; level1 and level2 are prefix-oriented listings based on gcloud storage wildcard behavior, not authoritative directory traversal.",\n'
  printf '    "The inventory is intentionally limited to the top two listing levels and does not recursively enumerate deeper objects.",\n'
  printf '    "Line counts are counts of saved listing output lines, not independently verified object totals.",\n'
  printf '    "Permissions, transient API errors, shell environment, and gcloud version/configuration may affect listing completeness; stderr and exit status are saved for audit."\n'
  printf '  ]\n'
  printf '}\n'
} >"$audit_file"

echo "Inventory complete."
echo "Output directory: $run_dir"
echo "Audit JSON: $audit_file"
