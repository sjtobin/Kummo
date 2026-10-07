# Kummo — Documentation

Documentation for Kummo, a B2B2C platform for discovering and booking family/senior-friendly activities in Berlin. This folder is organized along two axes: **business vs. technical**, and **settled decisions vs. open questions**.

```
Docs/
├── product/         Business — the "what" (validated by the product owner)
├── engineering/     Technical — the "how" (for developers)
├── decisions/       ADRs — settled decisions
├── open_questions/  What is still to arbitrate — split business / technical
└── archive/         Superseded / reference-only material
```

## Where to start

| You are… | Start here |
|---|---|
| A **developer** implementing the target version | [engineering/specification.md](engineering/specification.md), then [engineering/](engineering/) |
| A **product owner** validating the need | [product/requirements.md](product/requirements.md) |
| Looking for **why a technical/business choice was made** | [decisions/](decisions/) |
| Looking for **what is still undecided** | [open_questions/](open_questions/) (business / technical) |

## Business — [product/](product/)

| Document | What it is |
|---|---|
| [product/requirements.md](product/requirements.md) | Functional & non-functional requirements (canonical, EN). §9 open decisions in [open_questions/business/requirements.md](open_questions/business/requirements.md). |
| [product/brainstorming.md](product/brainstorming.md) | Early feature brainstorming and use-case list (historical). |

## Technical — [engineering/](engineering/)

| Document | What it is |
|---|---|
| [engineering/specification.md](engineering/specification.md) | Consolidated developer specification (entry point; some sections `TODO`). |
| [engineering/data-model.md](engineering/data-model.md) | Conceptual ER model + settled assumptions. |
| [engineering/translations.md](engineering/translations.md) | How to update the interface text (EN/DE) — written for non-developers. |
| [engineering/sequence-diagrams/](engineering/sequence-diagrams/) | Use-case flow diagrams (frontend → API → Supabase). |

## Decisions (ADRs) — [decisions/](decisions/)

Each ADR is a **settled** decision; its open points are gathered under [open_questions/](open_questions/). See the [ADR index](decisions/README.md).

| # | Decision |
|---|---|
| [0001](decisions/0001-payment-stripe-connect.md) | Payment: commission via Stripe Connect |
| [0002](decisions/0002-booking-build-vs-buy.md) | Booking platform: build in-house vs. buy |
| [0003](decisions/0003-persistence-sqlalchemy.md) | Persistence layer: SQLAlchemy 2.0 + Alembic |
| [0004](decisions/0004-supabase-cli-single-migration-chain.md) | Schema migrations: the Supabase CLI as the single DDL chain |
| [0005](decisions/0005-localization-json-catalogues.md) | Localization: English source, JSON catalogues, no library |

## Open questions — [open_questions/](open_questions/)

All open questions are gathered here, split by audience. See the [open-questions index](open_questions/README.md).

**Business** — [open_questions/business/](open_questions/business/)
- [booking-build-vs-buy.md](open_questions/business/booking-build-vs-buy.md) — in-house maintenance trade-off
- [requirements.md](open_questions/business/requirements.md) — DEC-02, DEC-04, DEC-05, DEC-07 (DEC-01/03/06 resolved by ADR 0001, removed)

**Technical** — [open_questions/technical/](open_questions/technical/)
- [data-model.md](open_questions/technical/data-model.md) — seats/availability, vendor↔shop, notifications
- [persistence.md](open_questions/technical/persistence.md) — team SQLAlchemy and migration conventions

## Development

### Database migration

```sh
pnpm dlx supabase migration new new_migration
# update SQL file
pnpm dlx supabase db push
```

### Local Development (Supabase)

Run a local Supabase stack with seed data — no impact on production.

**Prerequisites:** Docker / Podman must be running.

with **Podman**, exports the following:
`export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock`

```sh
pnpm install
pnpm db:start       # starts local Supabase (first run pulls Docker images)
pnpm db:reset       # applies all migrations + seeds test data
pnpm start          # starts Kummo locally at http://localhost:8000
```

Open `http://localhost:8000` — the app reads from the local Supabase instance.

**Dev mode activation (pick one):**
- URL param: append `?dev=true` to any page URL
- Persist: run `localStorage.setItem('kummo_dev', 'true')` in the browser console

**Dev mode deactivation:**
- Remove `?dev=true` from the URL, or
- Run `localStorage.removeItem('kummo_dev')` in the browser console

Without dev mode, the app hits the production Supabase project as usual.

**Other commands:**
```sh
pnpm db:stop        # stops the local Supabase stack
pnpm db:reset       # re-applies migrations + re-seeds (wipes local data)
pnpm dlx supabase status    # shows local URLs and anon key
```

**Seed data includes:** 10 shops, 22 activities, 4 users, 6 children, 8 bookings. See `supabase/seed.sql`.

## Archive — [archive/](archive/)

Superseded or reference-only. [prd-glide-mvp.md](archive/prd-glide-mvp.md) is the original Glide-aligned PRD (v2.0), superseded by the ADRs (business model, booking, stack); [requirements.fr.md](archive/requirements.fr.md) is the original French cahier des charges (the English [product/requirements.md](product/requirements.md) is now canonical); [cahier-des-charges-artifact-url.md](archive/cahier-des-charges-artifact-url.md) is a link to an external artifact.
