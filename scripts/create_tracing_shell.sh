#!/usr/bin/env bash
# Creates a minimal DataRobot custom application shell whose sole purpose is to
# provide a valid tracing context (entity_id) for local development.
#
# The app is stopped immediately after creation — no container ever runs and no
# compute resources are consumed. The entity_id is valid as soon as the app
# record is created in the database.
#
# On failure, any resources created during the run are deleted automatically.
#
# Usage:
#   ./scripts/create_tracing_shell.sh
#
# Required env vars:
#   DATAROBOT_ENDPOINT   base URL or /api/v2 URL, e.g. https://app.datarobot.com
#   DATAROBOT_API_TOKEN  your personal API token
#
# Optional env vars:
#   TRACING_SHELL_NAME   base name for the shell app (default: local-dev-tracing-shell)

set -euo pipefail

# ── Helpers ───────────────────────────────────────────────────────────────────

die()     { echo "Error: $*" >&2; exit 1; }
info()    { echo "$*"; }
require() { command -v "$1" &>/dev/null || die "'$1' is required but not installed."; }

require curl
require python3

json_field() {
  local field="$1"
  python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except json.JSONDecodeError as e:
    raise SystemExit(f'Failed to parse API response as JSON: {e}')
if '${field}' not in d:
    raise SystemExit(f'Field \"${field}\" missing from API response: ' + str(d))
print(d['${field}'])
"
}

dr_get() {
  local path="$1"
  local response http_code body
  response=$(curl -s --max-time 30 -w "\n%{http_code}" "${API}/${path}" \
    -H "Authorization: Bearer ${DATAROBOT_API_TOKEN}" 2>&1) || \
    die "Network error calling GET ${path}"
  http_code=$(echo "${response}" | tail -1)
  body=$(echo "${response}" | sed '$d')
  [[ "${http_code}" -lt 400 ]] || die "GET ${path} returned HTTP ${http_code}: ${body}"
  echo "${body}"
}

dr_post() {
  local path="$1" payload="$2"
  local response http_code body
  response=$(curl -s --max-time 30 -w "\n%{http_code}" -X POST "${API}/${path}" \
    -H "Authorization: Bearer ${DATAROBOT_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${payload}" 2>&1) || \
    die "Network error calling POST ${path}"
  http_code=$(echo "${response}" | tail -1)
  body=$(echo "${response}" | sed '$d')
  [[ "${http_code}" -lt 400 ]] || die "POST ${path} returned HTTP ${http_code}: ${body}"
  echo "${body}"
}

dr_delete() {
  local path="$1"
  curl -s --max-time 15 -X DELETE "${API}/${path}" \
    -H "Authorization: Bearer ${DATAROBOT_API_TOKEN}" > /dev/null 2>&1 || true
}

# ── Cleanup on failure ────────────────────────────────────────────────────────

SOURCE_ID=""
APP_ID=""
SUCCESS=false
TMPDIR_SHELL=""

cleanup() {
  rm -rf "${TMPDIR_SHELL}"
  [[ "${SUCCESS}" == "true" ]] && return
  if [[ -n "${APP_ID}" ]]; then
    echo "  rolling back: deleting app ${APP_ID}..." >&2
    dr_delete "customApplications/${APP_ID}/"
  fi
  if [[ -n "${SOURCE_ID}" ]]; then
    echo "  rolling back: deleting source ${SOURCE_ID}..." >&2
    dr_delete "customApplicationSources/${SOURCE_ID}/"
  fi
}
trap cleanup EXIT

# ── Validate env vars ─────────────────────────────────────────────────────────

[[ -n "${DATAROBOT_ENDPOINT:-}" ]]  || die "DATAROBOT_ENDPOINT must be set."
[[ -n "${DATAROBOT_API_TOKEN:-}" ]] || die "DATAROBOT_API_TOKEN must be set."

BASE_URL="${DATAROBOT_ENDPOINT%/}"
BASE_URL="${BASE_URL%/api/v2}"
API="${BASE_URL}/api/v2"

SUFFIX=$(python3 -c "import uuid; print(uuid.uuid4().hex[:6])")
SHELL_NAME="${TRACING_SHELL_NAME:-local-dev-tracing-shell}-${SUFFIX}"

# ── Find base Python environment ──────────────────────────────────────────────

TARGET_ENV="[DataRobot] Python 3.12 Applications Base"

info "Looking up execution environment..."
ENV_ID=$(dr_get "executionEnvironments/?useCases=customApplication&limit=50" | \
  TARGET_ENV="${TARGET_ENV}" python3 -c "
import sys, json, os
target = os.environ['TARGET_ENV']
envs = json.load(sys.stdin)['data']
match = next((e['id'] for e in envs if e['name'] == target), None)
if match:
    print(match)
")
[[ -n "${ENV_ID}" ]] || die "'${TARGET_ENV}' not found — is DATAROBOT_ENDPOINT correct?"
info "  ${TARGET_ENV} (${ENV_ID})"

# ── Create application source ─────────────────────────────────────────────────

info "Creating application source '${SHELL_NAME}'..."
SOURCE_ID=$(dr_post "customApplicationSources/" "{\"name\": \"${SHELL_NAME}\"}" | json_field id)
info "  id: ${SOURCE_ID}"

# ── Create source version with minimal entrypoint ────────────────────────────

info "Creating source version..."
TMPDIR_SHELL=$(mktemp -d)

cat > "${TMPDIR_SHELL}/start-app.sh" <<'ENTRYPOINT'
#!/bin/bash
# Tracing shell — this app is intentionally never started.
echo "Tracing shell started."
ENTRYPOINT

version_response=$(curl -s --max-time 60 -w "\n%{http_code}" -X POST \
  "${API}/customApplicationSources/${SOURCE_ID}/versions/" \
  -H "Authorization: Bearer ${DATAROBOT_API_TOKEN}" \
  -F "label=v1" \
  -F "baseEnvironmentId=${ENV_ID}" \
  -F "filePath=start-app.sh" \
  -F "file=@${TMPDIR_SHELL}/start-app.sh;type=application/octet-stream" 2>&1) || \
  die "Network error creating source version"
http_code=$(echo "${version_response}" | tail -1)
body=$(echo "${version_response}" | sed '$d')
[[ "${http_code}" -lt 400 ]] || die "Source version creation returned HTTP ${http_code}: ${body}"
VERSION_ID=$(echo "${body}" | json_field id)
info "  id: ${VERSION_ID}"

# ── Create application ────────────────────────────────────────────────────────

info "Creating application..."
APP_ID=$(dr_post "customApplications/" \
  "{\"name\": \"${SHELL_NAME}\", \"applicationSourceVersionId\": \"${VERSION_ID}\"}" | json_field id)
info "  id: ${APP_ID}"

ENTITY_ID="custom_application-${APP_ID}"

# ── Stop immediately ──────────────────────────────────────────────────────────

info "Stopping app..."
dr_post "customApplications/${APP_ID}/stop/" "{}" > /dev/null
info "  done"

# ── Done ──────────────────────────────────────────────────────────────────────

SUCCESS=true

echo ""
echo "✓ Tracing shell ready. Export these before starting local dev:"
echo ""
echo "  export OTEL_EXPORTER_OTLP_ENDPOINT=\"${BASE_URL}/otel\""
echo "  export OTEL_EXPORTER_OTLP_HEADERS=\"x-datarobot-entity-id=${ENTITY_ID},x-datarobot-api-key=${DATAROBOT_API_TOKEN}\""
echo "  export OTEL_SERVICE_NAME=\"${ENTITY_ID}\""
echo ""
echo "  # To use the scoped OTEL key instead of your personal token, find 'OTEL Key ${APP_ID}'"
echo "  # under ${BASE_URL}/account/developer-tools → Application API keys"
echo "  # and replace the x-datarobot-api-key value above."
echo ""
echo "View traces: ${BASE_URL}/apps/applications/${APP_ID}"
