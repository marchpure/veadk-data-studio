#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_SHA="${BASE_SHA:-86fbace663a68dff40d1a2e8713056d4599b60d8}"
BRANCH="${BRANCH:-verification/data-studio-commercial-p0}"
BACKEND_PORT="${BACKEND_PORT:-18123}"
FRONTEND_PORT="${FRONTEND_PORT:-15179}"
POSTGRES_PORT="${POSTGRES_PORT:-15432}"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-$HOME/.codex/data-studio-commercial-p0-evidence}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVIDENCE_DIR="${EVIDENCE_DIR:-$EVIDENCE_ROOT/$RUN_ID}"
APP_DATA_DIR="$EVIDENCE_DIR/runtime"
SQLITE_DB="${SQLITE_DB:-$APP_DATA_DIR/sqlite/app.db}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-byaan-commercial-p0-postgres}"
POSTGRES_VOLUME="${POSTGRES_VOLUME:-byaan-commercial-p0-postgres-data}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:16-alpine}"
MODE="${1:-sqlite}"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

log() {
  printf '[commercial-p0] %s\n' "$*"
}

die() {
  printf '[commercial-p0] ERROR: %s\n' "$*" >&2
  exit 1
}

assert_worktree() {
  local branch
  branch="$(git -C "$ROOT" branch --show-current)"
  [[ "$branch" == "$BRANCH" ]] || die "expected branch $BRANCH, got $branch"
  git -C "$ROOT" cat-file -e "$BASE_SHA^{commit}" || die "BASE_SHA cannot be resolved: $BASE_SHA"
  git -C "$ROOT" merge-base --is-ancestor "$BASE_SHA" HEAD || die "HEAD is not based on BASE_SHA $BASE_SHA"
}

check_forbidden_diff() {
  local changed
  changed="$(git -C "$ROOT" diff --name-only "$BASE_SHA"...HEAD || true)"
  if [[ -z "$changed" ]]; then
    return
  fi
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    case "$path" in
      server/migrations/*|server/main.py|server/auth/*|server/models/*|server/services/*|server/Dockerfile|Dockerfile.self-hosted)
        die "forbidden path changed on verification branch: $path"
        ;;
    esac
  done <<< "$changed"
}

require_port_free() {
  local port="$1"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2 || true
    die "port $port is already in use"
  fi
}

wait_http() {
  local url="$1"
  local label="$2"
  local attempts="${3:-90}"
  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "$label is ready: $url"
      return
    fi
    sleep 1
  done
  die "$label did not become ready: $url"
}

install_deps_if_needed() {
  if [[ "${COMMERCIAL_P0_SKIP_INSTALL:-}" == "1" ]]; then
    log "dependency install skipped by COMMERCIAL_P0_SKIP_INSTALL=1"
    return
  fi
  if [[ ! -d "$ROOT/client/node_modules" ]]; then
    log "installing client dependencies"
    pnpm --dir "$ROOT/client" install --frozen-lockfile
  fi
}

start_postgres() {
  log "starting dedicated PostgreSQL container $POSTGRES_CONTAINER using volume $POSTGRES_VOLUME"
  docker volume create "$POSTGRES_VOLUME" >/dev/null
  if docker ps -a --format '{{.Names}}' | grep -qx "$POSTGRES_CONTAINER"; then
    docker rm -f "$POSTGRES_CONTAINER" >/dev/null
  fi
  docker run -d \
    --name "$POSTGRES_CONTAINER" \
    -v "$POSTGRES_VOLUME:/var/lib/postgresql/data" \
    -e POSTGRES_USER=byaan \
    -e POSTGRES_PASSWORD=byaan_commercial_p0 \
    -e POSTGRES_DB=byaan_commercial_p0 \
    -p "127.0.0.1:$POSTGRES_PORT:5432" \
    "$POSTGRES_IMAGE" >/dev/null
  for _ in $(seq 1 90); do
    if docker exec "$POSTGRES_CONTAINER" pg_isready -U byaan -d byaan_commercial_p0 >/dev/null 2>&1; then
      log "dedicated PostgreSQL is ready on 127.0.0.1:$POSTGRES_PORT"
      return
    fi
    sleep 1
  done
  die "dedicated PostgreSQL did not become ready"
}

start_backend() {
  mkdir -p "$EVIDENCE_DIR/logs" "$(dirname "$SQLITE_DB")"
  local database_url
  local app_mode="community"
  if [[ "$MODE" == "postgres" ]]; then
    start_postgres
    database_url="postgresql+asyncpg://byaan:byaan_commercial_p0@127.0.0.1:$POSTGRES_PORT/byaan_commercial_p0"
    app_mode="self-hosted"
  else
    database_url="sqlite+aiosqlite:///$SQLITE_DB"
  fi

  log "starting backend on 127.0.0.1:$BACKEND_PORT with $MODE database"
  (
    cd "$ROOT"
    APP_MODE="$app_mode" \
    DATA_DIR="$APP_DATA_DIR" \
    DATABASE_URL="$database_url" \
    SKILL_LOOP_ENABLED=false \
    POSTHOG_DISABLED=true \
    MASTER_USER_EMAIL="${MASTER_USER_EMAIL:-admin@example.com}" \
    MASTER_USER_PASSWORD="${MASTER_USER_PASSWORD:-commercial-p0-password}" \
    ORG_NAME="${ORG_NAME:-Commercial P0 Verification}" \
    uv run uvicorn server.main:app --host 127.0.0.1 --port "$BACKEND_PORT"
  ) >"$EVIDENCE_DIR/logs/backend.log" 2>&1 &
  BACKEND_PID="$!"
  wait_http "http://127.0.0.1:$BACKEND_PORT/api/app/config" "backend"
}

start_frontend() {
  mkdir -p "$EVIDENCE_DIR/logs"
  log "starting frontend on 127.0.0.1:$FRONTEND_PORT"
  (
    cd "$ROOT"
    FRONTEND_PORT="$FRONTEND_PORT" \
    VITE_API_URL="http://127.0.0.1:$BACKEND_PORT" \
    pnpm --dir client dev --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort
  ) >"$EVIDENCE_DIR/logs/frontend.log" 2>&1 &
  FRONTEND_PID="$!"
  wait_http "http://127.0.0.1:$FRONTEND_PORT" "frontend"
}

run_collector() {
  log "collecting browser/API evidence into $EVIDENCE_DIR"
  BASE_URL="http://127.0.0.1:$FRONTEND_PORT" \
  API_URL="http://127.0.0.1:$BACKEND_PORT" \
  EVIDENCE_DIR="$EVIDENCE_DIR" \
  node "$ROOT/scripts/commercial_p0_verification.mjs"
}

main() {
  assert_worktree
  check_forbidden_diff
  mkdir -p "$EVIDENCE_DIR"

  if [[ "$MODE" == "collect-only" ]]; then
    node "$ROOT/scripts/commercial_p0_verification.mjs"
    return
  fi

  [[ "$MODE" == "sqlite" || "$MODE" == "postgres" ]] || die "mode must be sqlite, postgres, or collect-only"
  require_port_free "$BACKEND_PORT"
  require_port_free "$FRONTEND_PORT"
  install_deps_if_needed
  start_backend
  start_frontend
  run_collector
}

main "$@"
