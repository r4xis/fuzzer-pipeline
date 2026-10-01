#!/usr/bin/env bash
# Builds the frontend inside a throwaway node container (so the host needs no
# node toolchain) and syncs the static output to /srv/fuzzer-ui, which Caddy
# serves directly. Runs as the invoking user's uid:gid so node_modules/dist
# stay host-owned instead of root-owned.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$REPO_DIR/frontend"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e VITE_API_BASE=/api \
  -v "$FRONTEND_DIR:/app" \
  -w /app \
  node:22-alpine \
  sh -c "npm ci && npm run build"

rsync -a --delete "$FRONTEND_DIR/dist/" /srv/fuzzer-ui/
