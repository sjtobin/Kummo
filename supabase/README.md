# Supabase

Local-stack config, auth/role migrations and dev seed data for Kummo, managed with the
[Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) via
`pnpm exec supabase` (it's a `devDependency`, see the root `package.json`).

**Supabase is used for Auth only.** The application data lives in the `kummo` schema, which the
FastAPI backend reaches over a direct Postgres connection (SQLAlchemy async + asyncpg) — not
through PostgREST. The browser never talks to Supabase, and there is no RLS.

## One migration chain

**All DDL is a CLI migration in `migrations/`** — roles, extensions, auth config *and* every
application table in the `kummo` schema. There is one migration history, and it is the one the
Supabase dashboard shows. Alembic was removed; see
[ADR 0004](../Docs/decisions/0004-supabase-cli-single-migration-chain.md) for why.

The SQLAlchemy entities in `backend/src/kummo/*/data_model.py` *describe* the schema, they no
longer generate it. Keeping them in step is enforced by
`backend/tests/integration/test_schema_matches_data_model.py`, which reflects the live schema and
compares it to the declarative registry — so a migration without the matching entity change (or
the reverse) fails the test suite.

`20260804155602_kummo-backend.sql` creates one role of our own:

- `kummo_app` — DML only, no DDL, no `BYPASSRLS`, used by the backend at runtime (`DATABASE_URL`).

There is deliberately **no second "migrator" role**. Objects are owned by whichever role the CLI
connects as, and each migration that adds a table ends with an explicit grant:

```sql
grant select, insert, update, delete on all tables in schema kummo to kummo_app;
```

**Never `set role` or `reset role` in a migration.** The CLI records each applied migration with an
`INSERT` into `supabase_migrations.schema_migrations` *inside that migration's own transaction*, so
a role switch still in effect makes the push fail with `permission denied for schema
supabase_migrations` — after the DDL has already run, leaving the remote half-migrated. This is the
whole reason the owning role was dropped; see
`snippets/reset-hosted-migration-state.sql` for the cleanup that incident required.

### `kummo_app` credentials
During migration, the `kummo_app` user is created without a password. Database credentials are set separately for each environment and must not be committed to the repo.

For local development, assign a local password to `kummo_app` once the database has been created (or reset). Then set the `DATABASE_URL` with that credential in the local `.env.local` (ignored by git) file with the assigned password.

## Layout

```
supabase/
  config.toml        # local stack config (ports, auth, studio, …) — committed
  migrations/        # timestamped, ordered SQL migrations — committed
  seed.sql           # demo seed data, applied by `supabase db reset` — committed
  snippets/          # one-off SQL run by hand against the hosted project — committed
  .branches, .temp   # CLI-managed local state — gitignored
```

## Migrations

Each file in `migrations/` is a plain SQL script, applied in filename order. Filenames are
timestamp-prefixed (`YYYYMMDDHHMMSS_description.sql`) so ordering is unambiguous.

Current migrations:

- `20260804155602_kummo-backend.sql` — creates the `kummo_app` role and the `kummo` schema.
- `20260815120000_drop-legacy-public-tables.sql` — drops the old `public.shops` / `users` /
  `children` / `activities` / `bookings` tables that predate the move into `kummo`. A no-op on a
  fresh database; it matters only for databases provisioned before the move.
- `20260816200000_kummo-application-tables.sql` — the `vendors` / `clients` / `activities`
  tables, transcribed from the Alembic revision it replaces, minus `bookings` (created ahead of
  the feature and never wired up).

### Creating a new migration

```bash
pnpm exec supabase migration new <description>
```

Creates an empty, timestamped file in `migrations/`. No local stack needed for this step.

A migration that adds a table to `kummo` must end with the `grant … to kummo_app` line above, and
must not change role. Then update the matching `data_model.py` — the drift test will tell you if
you forget.

### Applying migrations locally

Requires Docker. The full rebuild is one command:

```bash
pnpm exec supabase db reset    # replay every migration, then seed.sql
```

The individual steps, if you need them separately:

```bash
pnpm exec supabase start           # boot Postgres/Studio/Auth
pnpm exec supabase migration up    # apply pending migrations, without dropping the database
```

`./start-kummo.sh local` wraps `supabase start` + `supabase migration up` and then runs the
FastAPI dev server — see the root `CLAUDE.md` for the local vs. cloud run modes.

### Applying migrations to the hosted (cloud) project

```bash
pnpm exec supabase login                                     # once per machine
pnpm exec supabase link --project-ref xusuvidhmuyzpfrtxutd   # once per checkout
pnpm exec supabase db push                                   # applies any un-run CLI migrations
```

`db push` compares `migrations/` against the migration history table on the linked remote project
and applies whatever hasn't run yet. It does **not** apply `seed.sql` — see the seed section below.
`./start-kummo.sh prod` does not push for you — migrating the hosted project is a deliberate step.

### Conventions

- One logical schema change per migration file; keep them small and reviewable.
- Never edit a migration that has already been applied to the hosted project — add a new migration
  instead (migrations are an append-only log).
- Column names are English `lower_snake_case` and must match the names documented in the root
  `CLAUDE.md` (`title`, `price`, `name`, `address`, `duration`, `picture`, `activity_type`,
  `age_group`, `participants_max`, `vendor_id`, `client_id`, …).

## Seed data

`seed.sql` is demo fixture data (Berlin vendors, activities). It is idempotent — the rows carry
fixed UUIDs and are deleted before being re-inserted — and it uses `DELETE`, not `TRUNCATE`, because
the foreign keys make `TRUNCATE` need a `CASCADE`.

> **The file opens with `DELETE FROM` on all three tables.** That is what makes it re-runnable, and
> it is also why it must never be applied to an environment holding data you care about. It clears
> `activities`, `clients` and `vendors` before inserting the fixtures.

### Locally — `supabase db reset`

Nothing to do by hand: `[db.seed]` in `config.toml` points at this file, so the reset replays every
migration and then applies the seed.

```bash
pnpm exec supabase db reset
```

That is the only automatic path. `supabase start`, `supabase migration up` and `supabase db push`
all leave the seed alone, as does `./start-kummo.sh`.

### Hosted — the SQL editor

There is deliberately **no command** that seeds the hosted project. Applying fixtures to a remote
database — with three `DELETE`s at the top — should be a decision someone makes on purpose, not a
flag that could be reached by accident.

1. Open the project's **SQL Editor** in the Supabase dashboard.
2. Paste the contents of `seed.sql`.
3. Check you are on the intended project, then run it.

The editor runs as `postgres`, which owns the `kummo` tables, so no grants or role changes are
needed. Afterwards, verify:

```sql
select
  (select count(*) from kummo.vendors)    as vendors,     -- 10
  (select count(*) from kummo.clients)    as clients,     --  4
  (select count(*) from kummo.activities) as activities;  -- 22
```

This was done once, on 2026-08-16, to give the hosted project content after the legacy `public.*`
tables were lost.

## Snippets

`snippets/` holds one-off SQL that is run by hand from the Supabase SQL editor and is not part of
any migration history.

- `reset-hosted-migration-state.sql` — clears the hosted project's `kummo` schema, roles and
  migration history so the chain can replay from scratch. Used on 2026-08-16; kept as the recipe
  for taking ownership back from a role `postgres` cannot otherwise touch.
- `migrate-public-to-kummo.sql` — **obsolete.** It copied the legacy `public.*` rows into `kummo`,
  but those tables no longer exist in any environment. Kept for the record only.

## Config

`config.toml` defines the local stack's ports and service settings (API on `54321`, Postgres on
`54322`, Studio on `54323`, mail catcher on `54324`) — see the comments in the file or the
[CLI config reference](https://supabase.com/docs/guides/local-development/cli/config). Notable
Kummo-specific settings:

- `[auth] site_url = "http://localhost:8000"` and `additional_redirect_urls` include
  `http://localhost:8000/api/auth/callback` — the backend's OAuth callback route.
- `[auth.external.google] enabled = true` — the "Mit Google anmelden" flow on `login.html`.
- `[db.seed] enabled = true` — `supabase db reset` applies `seed.sql` itself, so the reset is the
  whole local rebuild.

It is committed so the whole team boots an identical local stack.
