# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Kummo is a B2B2C web app for discovering and booking family/senior-friendly activities in Berlin. It is a static multi-page site (`static/`) served by a **FastAPI** backend (`backend/`). The backend talks to Postgres directly (SQLAlchemy async + asyncpg) and uses **Supabase** for Auth (GoTrue) only.

Documentation lives in `Docs/` (MkDocs site; index at `Docs/README.md`). Two entry points matter:
`Docs/engineering/implementation-status.md` is the **only** current-state document — what is built
and what remains — while `Docs/product/requirements.md` and `Docs/engineering/specification.md`
describe the **target** and do not change as code lands. The original PRD
(`Docs/archive/prd-glide-mvp.md`) describes a *Glide* no-code MVP; **the codebase does not use
Glide** — treat it as historical product intent. The root `README.md` carries the commands
(running, tests, migrations), not product content.

## Language rules

- **English** for everything developer-facing: code (identifiers, function/variable names), comments, documentation, commit messages, `console.log` debug output, and test descriptions.
- **No literal UI text in code** — everything an end user sees (page text, `alert()` messages, button labels, `aria-label`s, page titles) is a key resolved against `static/i18n/<lang>.json`. **English is the source language**: the text written in the markup is English, and the German translation lives in `de.json`. See *Localization* below. The German `echo` lines in the launcher scripts are the exception — they are not part of the site.
- **DB-mapped field names mirror the `kummo` schema columns**: `title`, `price`, `name`, `address`, `duration`, `picture`, `activity_type`, `age_group`, `participants_max`, `vendor_id`, etc. These are now English to match the actual columns — keep them spelled exactly as the column. There is **no `disponibilites`/availability column** in the schema; code that referenced it is guarded as optional, and the availability form field on `vendor.html` is not persisted (pending a product/schema decision).
- Historical note: the code (and originally the DB columns) was French — `titre`→`title`, `prix`→`price`, `nom`→`name`, `adresse`→`address`, `duree`→`duration`, `photo`→`picture`, `type_activites`→`activity_type` (and earlier `magasins`→`shops`, `activites`→`activities`). All identifiers are now English. If you find leftover French, translate it.
- Later rename: `shops`→`vendors` (a vendor is the business *and* the shop), `users`→`clients`, `shop_id`→`vendor_id`, `user_id`→`client_id`, `shopName`→`vendorName`. If you find leftover `shop`, it is stale.

## Running

There are two modes, selected by the `[env]` argument to the start scripts:

### Local mode (default) — `./start-kummo.sh local`
Uses a **Supabase instance running in Docker** (managed by the Supabase CLI).
Reads credentials from `.env.local`. The start script:
1. Stops any stale Supabase containers, then runs `pnpm exec supabase start` (Docker required).
2. Runs `pnpm exec supabase migration up` to apply any pending migrations.
3. Starts the FastAPI backend (`fastapi dev`, hot-reload) on port 8000.

Rebuild the local DB from scratch with `pnpm exec supabase db reset` — it replays every
migration and then applies `supabase/seed.sql`.

### Cloud mode — `./start-kummo.sh prod`
Uses the **hosted Supabase project** (`https://xusuvidhmuyzpfrtxutd.supabase.co`).
Reads credentials from `.env.prod` and starts the FastAPI backend (`fastapi run`, no hot-reload)
on port 8000. No Docker required. Migrations are not applied automatically in this mode.

Every `.env.*` file must contain `SUPABASE_URL`, `SUPABASE_API_KEY` and `DATABASE_URL` —
see `backend/.env.example`.

### Container
`docker compose up --build` (compose reads `.env` — `cp .env.prod .env`), or
`docker run -p 8000:8000 --env-file .env.prod kummo`. The image runs `fastapi run` as a
non-root user and serves the site from `STATIC_DIR`, set to `/app/static` in the image.

It starts **no database and applies no migrations** — those stay Supabase CLI tasks on the
host. `.env.local` does not work unchanged inside a container: its `127.0.0.1` is the
container itself, not the host's Supabase stack. Podman builds and runs the image fine; the
Podman caveat in `README.md` is about `supabase start`, not this image.

### Manual start (either mode)
```bash
# Export credentials first
export SUPABASE_URL=... SUPABASE_API_KEY=... DATABASE_URL=...

cd backend
uv run fastapi dev src/kummo/main.py   # local
uv run fastapi run src/kummo/main.py   # cloud
```
Then open `http://localhost:8000`. Do not open HTML files with `file://` — the `/api/*` routes won't resolve.

## Testing

**Backend** (from `backend/`):

- `uv run pytest -m 'not integration'` — route tests with a stubbed session; no database needed.
- `uv run pytest -m integration` — real queries against the local Supabase Postgres. Each test
  runs in a transaction that is rolled back, so seed data survives.
- `tests/integration/test_schema_matches_data_model.py` is the guard that replaced Alembic
  autogenerate: it reflects the live `kummo` schema and compares it to `Entity.metadata`, so a
  migration without the matching `data_model.py` change (or the reverse) fails here.
- Auth routes are tested by stubbing the `service` module — it is the only boundary that
  talks to the provider, so replacing it exercises cookies, profile linking and status
  codes without a network call.

**Frontend** regression tests use **Vitest + jsdom** (Node dev tooling only — not needed to run the app).

- `pnpm install` once, then `pnpm test` (single run) or `pnpm run test:watch`.
- Tests live in `test/app.test.js` and cover `app.js`'s pure logic (filtering, search-URL building, card HTML, vendor enrichment, localStorage helpers) — including guards for the bugs already fixed (escaped `${}` template literals, undefined `STORAGE_*` constants).
- `app.js` is a classic browser script, so it can't be `import`ed normally. Its bottom block attaches a `globalThis.KummoApp` API (incl. a test-only `__setData(vendors, activities)` to inject fixture data). This is inert in the browser. When adding a function worth testing, add it to that export object.

## Versioning

**A change to the source bumps the version, in the same commit.** Use the helper — it moves
all four places at once and refuses to run on a dirty version file:

```sh
./bump-version.sh minor    # 0.2.0 -> 0.3.0
./bump-version.sh 1.0.0    # or set it outright
```

`uv version` owns the number (it rewrites `backend/pyproject.toml` and re-locks); the script
copies what uv landed on into the two files uv knows nothing about. Doing it by hand means
touching all four, since nothing generates one from another:

| File | Field |
|---|---|
| `backend/pyproject.toml` | `version` — the one uv edits |
| `backend/uv.lock` | the `kummo` package entry; **CI runs `uv sync --locked`, so a stale lock fails the build** |
| `package.json` | `"version"` |
| `backend/src/kummo/main.py` | the `version=` argument to `FastAPI(...)` — this is what `/docs` and the OpenAPI schema advertise |

Semantic versioning, keyed to the conventional-commit type the message already carries:

- `feat(...)` → minor (`0.1.0` → `0.2.0`)
- `fix(...)`, `refactor(...)`, `perf(...)` → patch (`0.1.0` → `0.1.1`)
- a breaking change to the API or the schema → major
- `docs:`, `chore:`, `test:`, `ci(...)` → **no bump**: they change nothing a caller can observe

**One bump per feature branch, not per commit.** Branches are squashed on merge, so a bump on
every commit would produce versions no merged commit corresponds to. Bump once, on the commit
that carries the behaviour change; later commits on the same branch leave it alone.

## Architecture

**Pages** (each is a standalone HTML file, all sharing `js/app.js`):
- `index.html` — homepage (featured activities + search box)
- `search.html` — search/filter results, reads filters from URL query params
- `activity.html` — activity detail + booking modal (`?id=<activity-id>`)
- `login.html` — sign in / register (client or vendor) + "Mit Google anmelden"; **self-contained** inline script
- `client.html` — B2C client prefs, booking history, favorites. Clients only — `KummoAuth.requireUser('client')`. Nothing renders before the guard resolves, so a stale profile is never shown. Name and email come from `GET /api/auth/me` and are read-only; the rest is localStorage.
- `vendor.html` — B2B dashboard; **self-contained** inline script, deliberately skipped by `app.js`. Vendors only — `KummoAuth.requireUser('vendor')`. Calls `GET /api/activities?vendor_id=` and `POST /api/activities`.

- `admin.html` — admin stats (business/activity/booking counts, revenue)

**Role routing.** `client.html` and `vendor.html` are the two role homes (`KummoAuth.homeFor`) — the pages were named `profile.html` / `business.html` before; if you find those, they are stale. The nav carries **no per-role link**: the session badge itself is the anchor to the signed-in user's own page, so a role page is only ever reached by somebody who has that role. `requireUser(role)` sends an anonymous visitor to `login.html` and a signed-in user with the *other* role to their own home — not back to the login page. Sign-in, registration and the OAuth callback (`auth/routes.py`) all land on the same two pages.

**`js/app.js`** is the single shared script for all B2C pages. Flow:
1. `DOMContentLoaded` → `initApp()` → `loadData()` fetches `GET /api/vendors` and `GET /api/activities` in parallel.
2. `initPage()` is a path-based router (`window.location.pathname.includes(...)`) that dispatches to the right page initializer.
3. Activities are joined to their vendor client-side via `enrichActivity()` (`activity.vendor_id === vendor.id`); the joined object exposes `vendorName` and `vendor`.

**Authentication** (`backend/src/kummo/auth/`, layered outermost first):

| Module | Responsibility |
|---|---|
| `routes.py` | `/api/auth/*`; cookies and status codes |
| `dependencies.py` | `get_current_identity` / `get_current_client` / `get_current_vendor` |
| `profiles.py` | links a verified identity to `kummo.clients` / `kummo.vendors` |
| `cookies.py` | HttpOnly session transport |
| `tokens.py` | access-token verification against the provider's JWKS |
| `service.py` | **the only module aware the provider is Supabase** |

- The session is two HttpOnly cookies (`kummo_session`, `kummo_refresh`). No token ever reaches page JS, and no response body names Supabase.
- **Registration is two steps.** Both the local stack and the hosted project require email
  confirmation, so `sign_up` returns a `PendingIdentity` rather than a `Session`: the profile row
  is written (the auth user id is already final, and the vendor details only exist in that
  request) but no cookies are set, and the route answers `202 {"status": "pending_confirmation"}`.
  `GET /api/auth/confirm` is the second entry path that sets cookies — the confirmation email
  links there, not to GoTrue's `/verify`, so the tokens are redeemed server-side and never reach
  page JS. Signing in before confirming is a 403, not a 401. The mail is
  `supabase/templates/confirmation.html`.
- **Registration cannot be atomic** — the identity is created over HTTP while the profile row is a local transaction, and removing a stray identity would need the service key we do not hold. So every entry path calls `ensure_*_profile`, and an interrupted registration is completed on the next sign-in rather than compensated. Do not add a "delete the auth user" rollback.
- **OAuth signup always creates a client.** A vendor is also the shop, so it needs an address and activity types that a Google profile cannot supply. Existing vendors can still sign in via Google — the callback finds the profile already linked.
- OAuth uses PKCE **and** a `state` value, both in one short-lived HttpOnly cookie (`kummo_oauth_verifier`, stored as `state.verifier`), because the authorize request and the callback are separate HTTP requests. The callback rejects a missing or mismatched `state`.
- Access tokens are verified for issuer and audience in `tokens.py` — the provider client checks only `exp`. Note that verification is **not** local today: tokens are HS256, so the client falls back to a call to the provider on every authenticated request.
- **Writes require the matching role.** `POST /api/activities` depends on `get_current_vendor` and takes `vendor_id` from the session, not the body — `ActivityCreate` deliberately has no `vendor_id` field. Reads (`GET /api/vendors`, `GET /api/activities`) stay public: they are the catalogue anonymous visitors browse.
- Any route that must both fail *and* clear cookies has to **return** a response, not raise: FastAPI merges the injected `Response`'s headers only on the normal return path, so `raise` silently discards them.

**Data sources:**
- **FastAPI backend** (`/api/*`): all reads and writes go through the backend, which holds the database and Supabase credentials server-side. No Supabase SDK in the browser.
- **`localStorage`** (client-only): bookings, favorites, and user preferences. Keys: `STORAGE_PREFS` / `STORAGE_BOOKINGS` / `STORAGE_FAVORITES`. **Not** the session — that lives in HttpOnly cookies. This data belongs to one account but the browser keeps it across sign-ins, so `auth.js` records the owning account id in `kummo_account` and drops every `kummo_*` key when the session resolves to somebody else (or to nobody). Any new local key must therefore keep the `kummo_` prefix, and must be added to `KEPT_KEYS` in `auth.js` if it belongs to the browser rather than to the account — `kummo_lang` is the one that does.
- **`js/auth.js`** (`globalThis.KummoAuth`): the only module talking to `/api/auth/*`. Every call sends `credentials: 'same-origin'`; there is no token to read or attach.

## Supabase setup

- Canonical project URL: `https://xusuvidhmuyzpfrtxutd.supabase.co` (20-char ref).
- Credentials live only in `.env.*` files, read by the FastAPI backend via pydantic-settings. They are never sent to the browser.
- **`config.toml` configures both projects, not just the local one.** Auth settings and email
  templates reach the hosted project with `pnpm exec supabase config push` — not through the
  dashboard, which the next push would overwrite anyway. It pushes `site_url` and
  `additional_redirect_urls` as written (`http://localhost:8000` today) and needs
  `SUPABASE_AUTH_EXTERNAL_GOOGLE_*` exported, since `[auth.external.google]` is enabled there.
- **Supabase is used for Auth only.** Application data does not go through PostgREST: the browser never talks to Supabase and we do not use RLS, so PostgREST would be a pure HTTP hop. The backend connects to Postgres directly.
- **One migration chain.** `supabase/migrations/` (CLI, plain SQL, runs as `postgres`) owns *all* DDL — auth config, extensions, roles and every application table in `kummo`. Alembic was removed; see `Docs/decisions/0004-supabase-cli-single-migration-chain.md`. If you find a reference to `backend/alembic/`, `MIGRATION_DATABASE_URL` or `kummo-db-reset`, it is stale.
- **One DB role of our own**: `kummo_app`, DML only, defined in `supabase/migrations/20260804155602_kummo-backend.sql`. Migrations are owned by whatever role the CLI connects as; a migration that adds a table ends with `grant select, insert, update, delete on all tables in schema kummo to kummo_app;`.
- **Never `set role` / `reset role` in a migration.** The CLI records each applied migration with an `INSERT` into `supabase_migrations` *inside that migration's transaction*, so a role switch still in effect makes the push fail with `permission denied for schema supabase_migrations`. This is why there is no separate migrator role.
- Profile tables carry `auth_user_id` — unique, but no foreign key, since `auth.users` belongs to GoTrue's own role.

## Project layout

```
Kummo/
  static/
    index.html, search.html, activity.html, login.html
    client.html, vendor.html, admin.html  # all pages
    js/app.js                  # shared B2C logic (calls /api/*)
    css/                       # stylesheets
  supabase/                    # Supabase CLI config, auth/extension migrations, seed.sql
    snippets/                  # one-off SQL run by hand against the hosted project
  test/                        # Vitest frontend tests
  Dockerfile                   # backend + static site in one image, served on :8000
  .dockerignore                # build context is the repo root, so keep it tight
  compose.yaml                 # runs that image against an existing Supabase project
  backend/                     # FastAPI Python backend
    pyproject.toml             # uv project config
    .python-version            # pins Python 3.12
    .env.example               # key reference; the real files are ../.env.<env>
    src/kummo/                 # organized by feature, not by technology
      main.py                  # FastAPI app, mounts /api and serves static files
      config.py                # pydantic-settings Settings class
      db.py                    # async engine + get_session dependency
      data_model.py            # shared: Entity base, SCHEMA, column conventions
      errors.py                # KummoError, the project-wide base exception
      vendors/                 # data_model.py, api_model.py, routes.py
      activities/              # data_model.py, api_model.py, routes.py
      clients/                 # data_model.py (API surface arrives with enrichment)
      auth/                    # routes, api_model, service, tokens, cookies,
                               # profiles, dependencies, errors
    tests/                     # pytest backend tests
      integration/             # tests needing a live Postgres
```

**Running the backend** (from `backend/`):
```bash
uv sync --all-groups
uv run --env-file ../.env.local fastapi dev src/kummo/main.py   # hot-reload dev server on :8000
```

Schema changes are not a backend task — they are `pnpm exec supabase migration up` (or
`db reset`) from the repo root.

**The env file lives at the repo root, not in `backend/`.** `Settings` resolves `env_file`
relative to the current working directory, so a bare `uv run` from `backend/` finds nothing and
fails on the three required keys. Pass `--env-file ../.env.<env>` — it is a `uv run` flag, so it
must come *before* the command, or it is forwarded to fastapi instead. To avoid repeating
it, `export UV_ENV_FILE=../.env.local` for the shell session; the path is still resolved against
the CWD, so it only holds while you are in `backend/`.

This stays compatible with `start-kummo.sh`, which exports the variables itself: uv only sets what
is not already in the environment, and pydantic-settings prefers the environment over the file.

**The site's location is configuration, not a path walk.** `Settings.static_dir` (env
`STATIC_DIR`) is what `main.py` mounts at `/`. It defaults to the repo's `static/`, so a
source checkout needs nothing; the image overrides it. It is a pydantic `DirectoryPath`, so a
wrong value fails at startup instead of 404-ing every page. If you find
`Path(__file__).parents[3]` at the mount, it is stale.

## Backend conventions

- **Pydantic everywhere** — all API request bodies and response models must be typed Pydantic `BaseModel` subclasses. No raw `dict` in or out of route handlers.
- **`logging` for output** — use the standard `logging` module (`logging.getLogger(__name__)`). Never use `print()` in backend code. `logs.configure()` is called once from `main.py` and is what attaches a handler to the root logger; without it every application log statement is silently discarded, since uvicorn configures only its own loggers. Level comes from `LOG_LEVEL` (default `INFO`).
- **Every log line carries a request id.** `main.py`'s `request_context` middleware binds one per request in a `ContextVar` and echoes it in the `X-Request-ID` response header, honouring a caller-supplied one when it looks like an id. A `logging.Filter` stamps it onto every record, including those from SQLAlchemy, httpx and uvicorn, so nothing has to pass it around. Lines emitted outside a request show `-`.
- **Log identifiers, not people.** Profile and auth-user UUIDs, never email addresses or names — these lines are an audit trail, not a mailing list, and the ids are what joins them. Never log tokens, passwords, or provider-supplied text verbatim; run caller-controlled strings through `routes._log_safe` first, since a newline in one forges log entries.
- **Metrics live in `metrics.py`, scraped at `GET /metrics`.** `prometheus_client`'s default
  registry, so the process and GC collectors come along too. The `request_context` middleware
  records every request from the same measurement it logs; routes add the domain counters
  (`kummo_auth_events_total`, `kummo_activities_created_total`) for outcomes a status code cannot
  express — several provider errors reach the caller as one 401. **Labels must stay low
  cardinality and must never carry caller-supplied text**: the route *template*, never the path,
  and event names are constants in `metrics.py`, not strings from the request. The endpoint is
  outside `/api` (so no line per scrape) and unauthenticated — expose it only inside the
  deployment's network boundary. One registry per process: several uvicorn workers would need
  `PROMETHEUS_MULTIPROC_DIR`.
- **Organize by feature, not by technology** — each feature package owns its `data_model.py` (persisted entities), `api_model.py` (Pydantic request/response types) and `routes.py`. Anything genuinely shared moves up one level (`data_model.py`, `db.py`, `errors.py`). There is no top-level `models.py` or `api/` package.
- **Keep the two models apart** — `api_model.py` is the transport layer, `data_model.py` the persistence layer. They may share a class name (`Vendor` in both); import the module, not the symbol, when both are in scope. Do not return persisted entities from routes.
- **Schema changes are two edits, both required** — `pnpm exec supabase migration new "..."`, write the SQL (no role switching; grant `kummo_app` at the end), *and* update the feature's `data_model.py` to match. `tests/integration/test_schema_matches_data_model.py` reflects the live schema and fails if they diverge; it is what replaced Alembic autogenerate. Never hand-edit the database.
- **The Supabase CLI is the database task runner**, `uv run` the Python one. No Makefile, no npm scripts, no console scripts.
- **Test coverage** — every new route and non-trivial function requires a corresponding `pytest` test under `backend/tests/`. Use `httpx.AsyncClient` with `transport=ASGITransport(app=app)` for route tests, overriding `db.get_session`. Prefer the `StubSession` in `tests/conftest.py` for logic that does not need SQL, and `tests/integration/` for anything where the SQL itself is the thing under test.

## Frontend conventions

- No framework, no bundler — vanilla DOM APIs and template-literal HTML strings.
- `console.log` is acceptable for frontend debug output; it is developer-facing, so it stays English and is never translated.

### Localization

- **`static/i18n/<lang>.json` holds every user-facing string**, in the format i18next uses: nested keys, `{{name}}` interpolation, `_one`/`_other` plural suffixes. `en.json` is the source; `de.json` is the translation. See `Docs/decisions/0005-localization-json-catalogues.md`.
- **`js/i18n.js`** loads the catalogue for the visitor's language (explicit choice in `kummo_lang` → browser language → English) and defines the global `t(key, options)` shorthand. It is loaded **first** on every page, before `auth.js` and `app.js`.
- **In markup**: `data-i18n="key"` (textContent), `data-i18n-html="key"` (text containing markup), `data-i18n-attr="placeholder:key;aria-label:key"`. The English text stays in the element as the fallback; keep it in step with `en.json`.
- **In page scripts**: `t('activity.book_now')`. The scripts share one global scope, so never declare a local `t` — `i18n.js` owns that name.
- **Adding a string is two edits**: the key in `en.json` *and* in `de.json`. `test/i18n.test.js` fails when the catalogues drift apart or when a page uses a key nothing defines.
- Values persisted or sent to the backend stay **codes, not text** (a booking's `status` is `'confirmed'`, rendered through `bookingStatusLabel`): stored data outlives the language it was written in.
- The **option `value`s of the search filters are data**, matched against the German catalogue content (`kunst`, `natur`, `senioren`, …). Translate the labels, never the values.
- Supabase publishable (anon) keys are committed in `.env.*` files by design (they are public client keys); the secret service key must never appear here.
