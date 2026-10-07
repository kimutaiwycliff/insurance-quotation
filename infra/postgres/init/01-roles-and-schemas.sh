#!/usr/bin/env bash
# Runs once, as the Postgres superuser, when the data directory is first initialised.
# Creates the least-privilege roles and schemas described in ADR-0003. Tables, grants and RLS policies are
# created by Alembic migrations running as app_owner.
set -euo pipefail

: "${APP_OWNER_PASSWORD:?APP_OWNER_PASSWORD must be set}"
: "${APP_USER_PASSWORD:?APP_USER_PASSWORD must be set}"
: "${APP_SCANNER_PASSWORD:?APP_SCANNER_PASSWORD must be set}"
: "${AUTH_OWNER_PASSWORD:?AUTH_OWNER_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -v db="$POSTGRES_DB" \
  -v app_owner_pw="$APP_OWNER_PASSWORD" \
  -v app_user_pw="$APP_USER_PASSWORD" \
  -v app_scanner_pw="$APP_SCANNER_PASSWORD" \
  -v auth_owner_pw="$AUTH_OWNER_PASSWORD" <<-'EOSQL'
	-- Owns the application schema and runs migrations. Never used by the running API.
	CREATE ROLE app_owner LOGIN PASSWORD :'app_owner_pw';
	-- Used by the API and workers. Not an owner and no BYPASSRLS, so Row-Level Security always applies.
	CREATE ROLE app_user LOGIN PASSWORD :'app_user_pw' NOBYPASSRLS;
	-- Narrow role for cross-tenant schedulers; may only read views granted to it explicitly (M1).
	CREATE ROLE app_scanner LOGIN PASSWORD :'app_scanner_pw' NOBYPASSRLS;
	-- Owns the Better Auth schema. The API cannot write to it.
	CREATE ROLE auth_owner LOGIN PASSWORD :'auth_owner_pw';

	REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
	GRANT CONNECT ON DATABASE :"db" TO app_owner, app_user, app_scanner, auth_owner;
	REVOKE CREATE ON SCHEMA public FROM PUBLIC;

	CREATE EXTENSION IF NOT EXISTS pg_trgm;
	CREATE EXTENSION IF NOT EXISTS citext;

	CREATE SCHEMA app AUTHORIZATION app_owner;
	CREATE SCHEMA auth AUTHORIZATION auth_owner;
	GRANT USAGE ON SCHEMA app TO app_user, app_scanner;
	-- app_owner creates the "jobs" schema (Procrastinate) in the baseline migration.
	GRANT CREATE ON DATABASE :"db" TO app_owner;

	ALTER ROLE app_owner SET search_path = app, jobs, public;
	ALTER ROLE app_user SET search_path = app, jobs, public;
	ALTER ROLE app_scanner SET search_path = app, public;
	ALTER ROLE auth_owner SET search_path = auth, public;
EOSQL
