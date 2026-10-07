# Implementation status

| | |
|---|---|
| **Purpose** | The delta between the target described in [specification.md](specification.md) and the code that exists today |
| **Reflects** | branch `feat/container`, 29 August 2026 |
| **Audience** | Developers picking up the next piece of work |

> **How this document relates to the others.** [specification.md](specification.md) and
> [../product/requirements.md](../product/requirements.md) describe the **target**; they do not
> change as code lands. This page is the only place that describes **what runs today**. If the two
> disagree, this page is wrong and should be corrected — never the other way round.

Legend: **Built** — implemented and reachable end-to-end · **Partial** — a usable subset, gaps
named · **Not started** — no code.

---

## 1. Areas at a glance

| Area | Status | Where |
|---|---|---|
| Authentication & sessions | **Built** | `backend/src/kummo/auth/`, `static/js/auth.js` |
| Vendor & client profiles | **Partial** | `vendors/`, `clients/` |
| Activity catalogue | **Partial** | `activities/` |
| Discovery: browse, search, filter | **Partial** (client-side) | `static/js/app.js` |
| Booking | **Partial** (localStorage only) | `static/js/app.js`, `activity.html` |
| Payment / commission | **Not started** | — |
| Matching engine & geodata | **Not started** | — |
| Reviews | **Not started** | — |
| Notifications | **Not started** | — |
| Administration | **Partial** (read-only, client-side) | `static/admin.html`, `app.js` |
| Accessibility | **Not started** | — |
| i18n (DE/EN), interface | **Built** | `static/i18n/*.json`, `static/js/i18n.js` |
| i18n, vendor-entered content | **Not started** | — |
| Packaging & deployment | **Partial** (image only, no host) | `Dockerfile`, `compose.yaml` |

## 2. What is built

**Authentication** is the one area implemented to the target architecture. Layered
outermost-first (`routes` → `dependencies` → `profiles` → `cookies` → `tokens` → `service`), with
`service.py` the only module that knows the provider is Supabase.

- `POST /api/auth/register/client`, `/register/vendor`, `/login`, `/logout`, `/refresh`,
  `/resend-confirmation`, `GET /api/auth/me`, `GET /api/auth/oauth/{provider}`,
  `GET /api/auth/callback`, `GET /api/auth/confirm`.
- **Registration is two steps**, because both projects require email confirmation. Sign-up creates
  the identity and the profile row but no session, and answers `202 {"status":
  "pending_confirmation"}`; `login.html` then shows the "check your inbox" panel instead of
  redirecting. The link in the email points at `GET /api/auth/confirm`, which redeems the token
  hash server-side and sets the session cookies — the provider's own confirmation URL would hand
  the tokens to page JS. Signing in before confirming is a `403`. The email template lives at
  `supabase/templates/confirmation.html` and is pushed to the hosted project with
  `pnpm exec supabase config push` — `config.toml` configures both projects, so the template is
  not a dashboard edit. Without that push the hosted project's mails still point at GoTrue's
  `/verify` and confirmation does not sign anybody in.
- Session transport is two HttpOnly cookies (`kummo_session`, `kummo_refresh`). No token ever
  reaches page JS.
- Google OAuth uses PKCE plus a `state` value; both travel in one short-lived HttpOnly cookie
  (`kummo_oauth_verifier`, as `state.verifier`) because the authorize request and the callback are
  separate HTTP requests. **OAuth signup always creates a client** — a vendor needs an address and
  activity types a Google profile cannot supply.
- Access tokens are checked for issuer and audience in `tokens.py`; the provider client validates
  only `exp`.
- `POST /api/activities` is the one write route and is guarded by `get_current_vendor`; the owning
  `vendor_id` comes from the session, never the request body.
- Role routing: `client.html` and `vendor.html` are the two role homes, each guarded by
  `KummoAuth.requireUser(role)`.
- Registration is deliberately **not atomic** (identity over HTTP, profile row in a local
  transaction). Every entry path calls `ensure_*_profile`, so an interrupted registration
  completes on the next sign-in. See [ADR 0004](../decisions/0004-supabase-cli-single-migration-chain.md)
  for the surrounding migration model.

Covers FR-01, FR-05, and the [authentication flow](sequence-diagrams/00-authentication.md).

**Known auth gaps**, recorded here rather than built — each needs a decision, not just code:

- **No rate limiting** on `/login`, `/register/*` or `/refresh`. The provider's own limits are
  per-IP, but it only ever sees *this backend's* IP, so they act as one global cap shared by every
  user: no per-attacker brute-force protection, and one attacker can lock out everybody's sign-in.
  Needs a deployment decision (reverse proxy vs. app-level vs. shared store).
- **Registration discloses whether a *confirmed* address exists** (409 on a duplicate), which
  `auth.js` surfaces in German. A deliberate UX trade-off. Signing up an address that exists but
  is still unconfirmed is *not* disclosed: the provider answers 200 with the same auth user id
  and re-sends the confirmation, so the route replies 202 and `ensure_*_profile` returns the
  profile written the first time — the details typed the second time are ignored, including the
  role. `POST /resend-confirmation` answers 204 for any address at all.
- **Confirmation email delivery is not production-ready.** The hosted project still uses
  Supabase's built-in SMTP, which is heavily rate-limited and (on recent projects) only delivers
  to the team's own addresses. Real users need custom SMTP configured on the project.
- **An interrupted vendor registration completes as a *client*.** Nothing records the intended
  role, so `ensure_client_profile` on the next sign-in is a guess. Rare now that the insert race is
  handled, but fixing it properly needs a pending-registration record.
- **Every authenticated request costs a provider round trip.** Tokens are HS256, and for symmetric
  keys the client verifies by calling the provider rather than locally. Asymmetric signing keys
  would make it local; that is a change to both the local and hosted projects.
- **Refresh cookies last 30 days** with no absolute session cap and no "sign out everywhere";
  `sign_out` is `scope="local"` by design.
- **No security headers** — no CSP, HSTS or `TrustedHostMiddleware` in `main.py`. HttpOnly stops
  token theft via XSS but not same-origin requests from injected script.
- **The provider is visible during OAuth**: the browser is redirected to the Supabase authorize
  URL, so the "nothing names the provider" property holds for the API surface but not that hop.

**Persisted schema** — three tables in the `kummo` schema, owned by
`supabase/migrations/` and guarded by
`backend/tests/integration/test_schema_matches_data_model.py`:

| Table | Columns |
|---|---|
| `vendors` | `id`, `created_at`, `auth_user_id`, `name`, `address`, `phone`, `email`, `website`, `activity_type[]`, `picture` |
| `clients` | `id`, `created_at`, `auth_user_id`, `first_name`, `last_name`, `email`, `age`, `interests[]`, `number_children` |
| `activities` | `id`, `created_at`, `vendor_id`, `title`, `description`, `price`, `participants_max`, `duration`, `age_group`, `picture` |

**Read/write API** — `GET /api/vendors`, `GET /api/activities` (optional `vendor_id` filter),
`GET /api/activities/{id}`, `POST /api/activities`.

**Packaging** — `Dockerfile` builds one image carrying the backend and the static site,
served together on port 8000: dependencies resolved by `uv sync --locked --no-dev` into a
separate stage, then a `python:3.12-slim` runtime running `fastapi run` as a non-root user,
with a `HEALTHCHECK` on `GET /metrics`. `compose.yaml` runs it against an existing Supabase
project, reading `.env`. The site's location is the `STATIC_DIR` setting
(`Settings.static_dir`, a `DirectoryPath` defaulting to the repo's `static/`), so the image
can lay it out where it likes and a wrong path fails at startup.

The image starts no database and applies no migrations — `supabase migration up` stays a
host-side task, per [ADR 0004](../decisions/0004-supabase-cli-single-migration-chain.md).

## 3. What remains

Ordered roughly by what unblocks the most.

### 3.1 Sessions and availability — blocks booking, payment, search

There is **no session/availability concept in the schema at all**. `activities` carries
`participants_max` and `duration` but no dates and no seat count; the `disponibilites` column the
old code referenced never existed, and the availability field on `vendor.html` is deliberately not
persisted, pending the modeling decision in
[open_questions/technical/data-model.md](../open_questions/technical/data-model.md) (counter on
`SESSION` vs. derived from bookings).

Everything below depends on this. **Settle OQ-DM first.**

Missing: FR-15 (add/disable/update a session), FR-60's availability filter.

### 3.2 Booking

Bookings exist only as `localStorage` entries under `kummo_bookings`, written by the modal in
`activity.html`. Nothing reaches the server, so a booking is invisible to the vendor and lost on
another device.

Missing: the `bookings` table, the state machine
(`draft → pending_payment → confirmed → completed`, with `cancelled_*` / `disputed` branches),
the booking API, and the vendor-side view. See
[02-book-and-pay](sequence-diagrams/02-book-and-pay.md),
[03-change-booking](sequence-diagrams/03-change-booking.md),
[08-vendor-cancel-reschedule](sequence-diagrams/08-vendor-cancel-reschedule.md).

### 3.3 Payment and commission — FR-50…53

Nothing. No Stripe dependency, no `audit_events` table. The design is settled in
[ADR 0001](../decisions/0001-payment-stripe-connect.md) (Stripe Connect Express, separate charges
and transfers) and [ADR 0002](../decisions/0002-booking-build-vs-buy.md) (custom booking module),
but **three business questions block the build**: payout timing, cancellation policy and dispute
handling — [open_questions/business/payment.md](../open_questions/business/payment.md).

### 3.4 Matching engine and geodata — FR-30…36, FR-40…45

Nothing. No PostGIS, no geocoding, no coordinates on `vendors` (only a free-text `address`), no
service-area model, no score. `app.js` does a substring match over the activity list in the
browser instead.

Blocked on DEC-05 (service-area modality: radius vs. administrative zones) and DEC-07 (engine
weights) — [open_questions/business/requirements.md](../open_questions/business/requirements.md).

### 3.5 Server-side search — FR-60, FR-61

`app.js` fetches the **entire** vendor and activity list on every page load and filters in the
browser (`filterActivities`, `enrichActivity` joins `activity.vendor_id === vendor.id`
client-side). Correct for a seeded catalogue, not for a real one, and it cannot support FR-61
(search by area) without 3.4.

### 3.6 Profile management — FR-03, FR-04

`GET /api/auth/me` returns name and email read-only. There is no route to edit a profile and none
to delete an account, so the right to erasure (NFR-50…54) is unimplemented. There is no
`preferred_language` column, so FR-04 and FR-72 have nowhere to read from.

Client preferences and favourites live in `localStorage` (`kummo_prefs`, `kummo_favorites`),
scoped to the signed-in account id via `kummo_account`.

### 3.7 Reviews, notifications, support, sharing

Not started: FR-70…73 (notifications), and the flows in
[05-review](sequence-diagrams/05-review.md), [09-reminder](sequence-diagrams/09-reminder.md),
[10-support](sequence-diagrams/10-support.md),
[11-share-booking](sequence-diagrams/11-share-booking.md). FR-73 (contact exchange vs. internal
messaging) is still open as DEC-02.

### 3.8 Administration — FR-80…83

`admin.html` renders counts and revenue computed in the browser from the public activity list plus
whatever bookings happen to be in that browser's `localStorage` — the figures are per-device, not
platform-wide. There is no admin role, no admin API, no moderation, no category/weight
configuration.

### 3.9 Non-functional

None of the structuring NFRs are addressed yet, and two of them
(accessibility, i18n) are the kind that get much more expensive after the fact:

- **Accessibility (NFR-01…03)** — WCAG 2.2 AA, senior-adapted. Not audited.
- **Multilingualism (NFR-10…12)** — the **interface** is done: English is the source language,
  the text lives in `static/i18n/en.json` / `de.json`, and `static/js/i18n.js` resolves it
  (visitor's choice → browser language → English), with an EN/DE switcher in the header. See
  [ADR 0005](../decisions/0005-localization-json-catalogues.md). **Vendor-entered content** —
  activity titles, descriptions, addresses — is still shown as entered: that needs a schema
  change and a per-language vendor form, and is still open as DEC-04.
- **Performance (NFR-30…31)** — no measurement; 3.5 works against it.
- **Deployment (NFR-30…31 adjacent)** — there is an image and a compose file, but no host, no
  TLS termination, no CI that builds or publishes it, and no place the `.env` for a real
  deployment lives. `COOKIE_SECURE` and the security headers noted in §2 become required the
  moment it is served over TLS, and the rate-limiting decision in §2 is the same deployment
  decision.
- **Email verification** — `enable_confirmations = false` in `supabase/config.toml`, and there is
  no password-reset route. FR-02 is therefore only half met.

## 4. Deviations from the specification

Places where the code intentionally differs from [specification.md](specification.md):

| Spec says | Code does | Why |
|---|---|---|
| Supabase as "managed PostgreSQL + Auth, Storage, Realtime" | Auth only; Postgres accessed directly | The browser never talks to Supabase and we do not use RLS, so PostgREST would be a pure HTTP hop |
| Persistence: "SQLAlchemy 2.0 + Alembic" ([ADR 0003](../decisions/0003-persistence-sqlalchemy.md)) | SQLAlchemy 2.0; Alembic removed | Superseded by [ADR 0004](../decisions/0004-supabase-cli-single-migration-chain.md) — the Supabase CLI is the single DDL chain |
| "Frontend rebuilt for accessibility, DE/EN, mobile-first" | The prototype is still the running frontend, now with DE/EN | Accessibility and the rebuild are not started; the i18n layer is in place — see 3.9 |
| "RLS is defense-in-depth" | No RLS | One DML-only role (`kummo_app`); all access goes through the backend |
