#!/usr/bin/env bash
# ============================================================
#  Start Kummo locally (Linux/macOS).
#  Usage: ./start-kummo.sh [env]
#    env = local (default) | prod | any .env.<name> file
#  For "local": starts Supabase (Docker) if not already running,
#  then starts a web server and opens the browser.
#  Stop it with Ctrl+C.
#  (User-facing messages below are in English.)
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

ENV="${1:-local}"
ENV_FILE=".env.${ENV}"

if [ ! -f "$ENV_FILE" ]; then
  echo >&2
  echo "Environment file '${ENV_FILE}' not found." >&2
  echo "Available environments:" >&2
  for f in .env.*; do echo "  - ${f#.env.}" >&2; done
  echo >&2
  exit 1
fi

# Read credentials for the FastAPI backend
SUPABASE_URL=$(grep -E '^SUPABASE_URL=' "$ENV_FILE" | cut -d= -f2-)
SUPABASE_API_KEY=$(grep -E '^SUPABASE_API_KEY=' "$ENV_FILE" | cut -d= -f2-)
DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)
SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=$(
  grep -E '^SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=' "$ENV_FILE" | cut -d= -f2- || true
)
SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET=$(
  grep -E '^SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET=' "$ENV_FILE" | cut -d= -f2- || true
)
RESEND_API_KEY=$(
  grep -E '^RESEND_API_KEY=' "$ENV_FILE" | cut -d= -f2- || true
)

for var in SUPABASE_URL SUPABASE_API_KEY DATABASE_URL; do
  if [ -z "${!var}" ]; then
    echo >&2
    echo "${var} is missing in '${ENV_FILE}'." >&2
    echo "See backend/.env.example for the expected keys." >&2
    echo >&2
    exit 1
  fi
done

export SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID
export SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET
export RESEND_API_KEY

echo "Environment: ${ENV}" >&2


# --- Supabase (local only) ---
STARTED_SUPABASE=false
if [ "$ENV" = "local" ]; then
  # Stop any existing (possibly unhealthy) Supabase containers first
  pnpm exec supabase stop 2>/dev/null || true
  echo "Starting local Supabase instance ..." >&2
  pnpm exec supabase start
  STARTED_SUPABASE=true
fi

# --- FastAPI backend ---
PORT=8000
URL="http://localhost:${PORT}"

if ! command -v uv >/dev/null 2>&1; then
  echo >&2
  echo "uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/" >&2
  echo >&2
  exit 1
fi

export SUPABASE_URL SUPABASE_API_KEY DATABASE_URL

# `supabase start` above already applies pending migrations on a fresh stack; this
# also covers a stack whose volume survived from an earlier checkout.
if [ "$ENV" = "local" ]; then
  echo "Applying database migrations ..." >&2
  pnpm exec supabase migration up
fi

echo "Starting Kummo ..." >&2
if [ "$ENV" = "local" ]; then
  uv --directory backend run fastapi dev src/kummo/main.py --port "$PORT" &
else
  uv --directory backend run fastapi run src/kummo/main.py --port "$PORT" &
fi
SERVER_PID=$!

# Stop Supabase on exit only if we started it.
cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  if [ "$STARTED_SUPABASE" = true ]; then
    echo >&2
    echo "Stopping Supabase ..." >&2
    pnpm exec supabase stop 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Wait briefly, then open the browser.
sleep 2
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
  open "$URL" >/dev/null 2>&1 || true
fi

echo >&2
echo "Kummo is running at ${URL}" >&2
echo "Press Ctrl+C to stop." >&2
echo >&2
wait "$SERVER_PID"
