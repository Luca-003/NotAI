#!/usr/bin/env bash
# NotAI - bootstrap schema audit + grant ai ruoli applicativi.
#
# Crea lo schema 'audit', le function trigger di immutabilita', e concede
# i privilegi necessari ai ruoli applicativi (creati prima da 01-roles.sh).

set -euo pipefail

DB="${POSTGRES_DB:-notai}"

psql -v ON_ERROR_STOP=on --username "$POSTGRES_USER" --dbname "$DB" \
  -v migrator_role="$POSTGRES_MIGRATOR_ROLE" \
  -v app_role="$POSTGRES_APP_ROLE" \
  -v audit_role="$POSTGRES_AUDIT_WRITER_ROLE" <<'PSQL'

CREATE SCHEMA IF NOT EXISTS audit;

-- Function trigger: blocca UPDATE
CREATE OR REPLACE FUNCTION audit.reject_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'audit log is append-only: UPDATE not allowed on % (id=%)',
    TG_TABLE_NAME, OLD.id
    USING ERRCODE = '0A000';
END;
$$;

CREATE OR REPLACE FUNCTION audit.reject_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'audit log is append-only: DELETE not allowed on %',
    TG_TABLE_NAME
    USING ERRCODE = '0A000';
END;
$$;

CREATE OR REPLACE FUNCTION audit.reject_truncate()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'audit log is append-only: TRUNCATE not allowed on %',
    TG_TABLE_NAME
    USING ERRCODE = '0A000';
END;
$$;

COMMENT ON SCHEMA audit IS
  'NotAI audit event store. Append-only. Tabelle hanno trigger contro UPDATE/DELETE/TRUNCATE.';

-- Grant: migrator possiede lo schema (crea tabelle, indici, trigger), app/audit
-- possono usarlo (per inserire eventi e leggere).
ALTER SCHEMA audit OWNER TO :"migrator_role";

GRANT USAGE ON SCHEMA audit TO :"app_role", :"audit_role";

-- Default privileges: tutto cio' che il migrator crea in audit e' utilizzabile
-- dall'app role (per query) e dall'audit_writer (per INSERT). DELETE/UPDATE
-- restano bloccati a livello di trigger anche per loro.
ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_role" IN SCHEMA audit
  GRANT SELECT, INSERT ON TABLES TO :"app_role", :"audit_role";

ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_role" IN SCHEMA audit
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_role", :"audit_role";

-- Le function trigger devono essere eseguibili da chi insertsce (postgres le
-- chiama dal trigger context; ma l'execute permission e' richiesto)
GRANT EXECUTE ON FUNCTION audit.reject_update() TO :"app_role", :"audit_role", :"migrator_role";
GRANT EXECUTE ON FUNCTION audit.reject_delete() TO :"app_role", :"audit_role", :"migrator_role";
GRANT EXECUTE ON FUNCTION audit.reject_truncate() TO :"app_role", :"audit_role", :"migrator_role";

PSQL

echo "[init] schema audit + grant configurati"
