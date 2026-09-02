import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from . import logs, metrics
from .activities import routes as activities
from .auth import routes as auth
from .auth.tokens import reset_verifier_client
from .config import get_settings
from .db import dispose_engine
from .vendors import routes as vendors

# Before anything else logs: get_settings() itself can fail, and that message is the
# one you most need to see.
logs.configure(get_settings().log_level)

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# Static files are the bulk of the traffic and say nothing worth a line each. The
# prefix lives in `metrics`, which needs the same split to label a request that matched
# no route at all.
API_PREFIX = metrics.API_PREFIX


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "Kummo API starting (base url %s, secure cookies %s)",
        settings.app_base_url,
        settings.cookie_secure,
    )
    yield
    logger.info("Kummo API shutting down")
    await dispose_engine()
    reset_verifier_client()


app = FastAPI(title="Kummo API", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Give every request an id, log how each API call turned out, and count it.

    The id is bound to the task, so anything logged while handling this request
    carries it without the call sites knowing — including SQLAlchemy and httpx.

    The duration measured here is also the one Prometheus sees: one `perf_counter`
    span serves both the log line and the histogram, so they can never disagree.
    """
    request_id = logs.new_request_id(request.headers.get(REQUEST_ID_HEADER))
    token = logs.set_request_id(request_id)
    started = time.perf_counter()
    is_api = request.url.path.startswith(API_PREFIX)
    # A scrape counting itself would inflate the very series it reports.
    is_scrape = request.url.path == metrics.METRICS_PATH
    try:
        try:
            response = await call_next(request)
        except Exception:
            elapsed = time.perf_counter() - started
            # The handler will re-raise into Starlette's 500; this is the only place
            # the failure is tied to its request id.
            logger.exception(
                "%s %s failed after %.0fms",
                request.method,
                request.url.path,
                elapsed * 1000,
            )
            # Counted as the 500 the caller is about to receive, or an outage would
            # look like a drop in traffic rather than a spike in errors.
            if not is_scrape:
                metrics.record_request(request, 500, elapsed)
            raise

        elapsed = time.perf_counter() - started
        if not is_scrape:
            metrics.record_request(request, response.status_code, elapsed)

        if is_api:
            # Logged before the id is released, or the one line worth correlating
            # would be the one without an id on it.
            level = logging.WARNING if response.status_code >= 400 else logging.INFO
            logger.log(
                level,
                "%s %s -> %d (%.0fms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed * 1000,
            )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        logs.reset_request_id(token)


app.include_router(auth.router, prefix="/api")
app.include_router(vendors.router, prefix="/api")
app.include_router(activities.router, prefix="/api")

# Deliberately not under /api: it is scrape traffic, not the application's API, and
# keeping it out of the prefix keeps it out of the per-call request log.
app.include_router(metrics.router)

# Serve the site last so API routes take precedence. The directory is configuration
# (STATIC_DIR), not a walk up from this file, so the deployment decides the layout.
app.mount(
    "/",
    StaticFiles(directory=get_settings().static_dir, html=True),
    name="static",
)
