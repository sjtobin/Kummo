# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Dependency layer: resolve the locked environment with uv, the same tool the
# start scripts use. Only the manifests are copied, so a source edit does not
# invalidate the (slow) dependency install.
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS deps

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./

# --no-install-project: the app is run from its source tree (main.py resolves
# static/ relative to its own file), so installing a wheel would only duplicate it.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    STATIC_DIR=/app/static

# Non-root: the backend only reads its own files and talks to Postgres/GoTrue.
RUN useradd --system --create-home --uid 10001 kummo

COPY --from=deps /opt/venv /opt/venv

WORKDIR /app
# The site is found through STATIC_DIR above, so this layout is a choice, not a
# constraint the application code depends on.
COPY --chown=kummo:kummo backend/ ./backend/
COPY --chown=kummo:kummo static/ ./static/

USER kummo
WORKDIR /app/backend

# The rest of the configuration comes from the environment (SUPABASE_URL,
# SUPABASE_API_KEY, DATABASE_URL, APP_BASE_URL, COOKIE_SECURE, LOG_LEVEL) — no .env
# file is baked in.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/metrics', timeout=2).status == 200 else 1)"

CMD ["fastapi", "run", "src/kummo/main.py", "--host", "0.0.0.0", "--port", "8000"]
