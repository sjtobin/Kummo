-- Runtime role and the application schema.
--
-- There is deliberately no second "migrator" role. The Supabase CLI is the only DDL
-- tool (ADR 0004), so a separate owning role buys nothing -- and reaching it from a
-- migration requires `set local role`, which breaks `db push`: the CLI records each
-- migration with an INSERT into supabase_migrations inside the same transaction, and
-- any role switch still in effect makes that INSERT fail. Migrations therefore never
-- change role; objects are owned by whichever role the CLI connects as.

-- DML only: no DDL, no BYPASSRLS. This is what the FastAPI backend connects as.
-- Its password is provisioned separately according to environment: it is not committed.
create role kummo_app with login;

create schema kummo;
grant usage on schema kummo to kummo_app;
