#!/bin/bash
# Cron entry point for the fuzzing host: records fuzzer statistics and
# triages new AFL++ crashes for the active target.
#
# The active target is the newest row in `targets` — registering a new target
# in the database is enough to switch. Set TARGET_ID to override.
#
# Secrets and host-specific paths come from an env file outside the repo
# (default /data/fuzzer-pipeline.env), which must define FUZZER_DB_PASSWORD
# and may override: TARGET_ID, AFL_OUTPUT, CASR_OUTPUT, LOG_FILE,
# DB_CONTAINER, FUZZER_IMAGE, HARNESS, POC_ARCHIVE_ROOT, AFL_MASTER_CONTAINER.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${FUZZER_ENV_FILE:-/data/fuzzer-pipeline.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi
: "${FUZZER_DB_PASSWORD:?FUZZER_DB_PASSWORD is not set (expected in $ENV_FILE)}"

AFL_OUTPUT="${AFL_OUTPUT:-/data/afl-output}"
CASR_OUTPUT="${CASR_OUTPUT:-/data/casr-reports}"
LOG_FILE="${LOG_FILE:-/data/triage.log}"
DB_CONTAINER="${DB_CONTAINER:-fuzzer-db}"
FUZZER_IMAGE="${FUZZER_IMAGE:-fuzzer-pipeline-fuzzer0}"
HARNESS="${HARNESS:-/fuzzing/harness}"
POC_ARCHIVE_ROOT="${POC_ARCHIVE_ROOT:-/data/poc_archive}"
export FUZZER_DB_PASSWORD AFL_OUTPUT POC_ARCHIVE_ROOT

psql_scalar() {
  docker exec "$DB_CONTAINER" psql -U fuzzer -d fuzzer_db -tA -c "$1"
}

log() {
  echo "$*" >> "$LOG_FILE"
}

log "=== Triage run: $(date) ==="

TARGET_ID="${TARGET_ID:-$(psql_scalar "SELECT id FROM targets ORDER BY created_at DESC NULLS LAST, id DESC LIMIT 1")}"
if [ -z "$TARGET_ID" ]; then
  log "No target registered in the database, nothing to do."
  exit 0
fi
log "Active target: $TARGET_ID"

python3 "$REPO_DIR/triage/update_session_stats.py" "$TARGET_ID" >> "$LOG_FILE" 2>&1

sudo chown -R "$(id -un):$(id -gn)" "$AFL_OUTPUT" 2>/dev/null || true

CRASH_COUNT=$(find "$AFL_OUTPUT" -path "*/crashes/*" -type f 2>/dev/null | grep -vc README || true)
if [ "${CRASH_COUNT:-0}" -eq 0 ]; then
  log "No crashes found, skipping CASR triage."
  exit 0
fi
log "Found $CRASH_COUNT crash file(s), running CASR triage..."

SESSION_ID=$(psql_scalar "SELECT id FROM sessions WHERE target_id = $TARGET_ID ORDER BY started_at DESC NULLS LAST LIMIT 1")
if [ -z "$SESSION_ID" ]; then
  SESSION_ID=$(psql_scalar "INSERT INTO sessions (target_id, started_at) VALUES ($TARGET_ID, now()) RETURNING id")
  log "Created new session: $SESSION_ID"
fi

rm -rf "$CASR_OUTPUT"
docker run --rm --privileged -v /data:/data "$FUZZER_IMAGE" \
  /root/.cargo/bin/casr-afl -i "$AFL_OUTPUT" -o "$CASR_OUTPUT" -f --ignore-cmdline -- "$HARNESS" @@ \
  >> "$LOG_FILE" 2>&1
sudo chown -R "$(id -un):$(id -gn)" "$CASR_OUTPUT" 2>/dev/null || true

python3 "$REPO_DIR/triage/triage.py" "$CASR_OUTPUT" "$SESSION_ID" >> "$LOG_FILE" 2>&1
log "Triage run complete."
