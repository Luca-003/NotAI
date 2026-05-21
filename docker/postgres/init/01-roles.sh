#!/usr/bin/env bash
# NotAI - crea i ruoli applicativi con privilegi separati.
#
# Eseguito automaticamente dall'entrypoint Postgres al primo boot del cluster.
# Le credenziali arrivano dall'env (Compose le inietta dal .env).
#
# Ruoli creati:
#   $POSTGRES_MIGRATOR_ROLE      -> Alembic / DDL / owner schema
#   $POSTGRES_APP_ROLE           -> runtime app (DML)
#   $POSTGRES_AUDIT_WRITER_ROLE  -> dedicato per scritture nell'audit log
#
# Si usa psql con --set per passare i valori come client variables: questo evita
# il bug del DO $$ ... $$ in cui le :'var' non vengono sostituite.

set -euo pipefail

DB="${POSTGRES_DB:-notai}"

psql -v ON_ERROR_STOP=on --username "$POSTGRES_USER" --dbname "$DB" \
  -v migrator_role="$POSTGRES_MIGRATOR_ROLE" \
  -v migrator_pwd="$POSTGRES_MIGRATOR_PASSWORD" \
  -v app_role="$POSTGRES_APP_ROLE" \
  -v app_pwd="$POSTGRES_APP_PASSWORD" \
  -v audit_role="$POSTGRES_AUDIT_WRITER_ROLE" \
  -v audit_pwd="$POSTGRES_AUDIT_WRITER_PASSWORD" \
  -v db_name="$DB" <<'PSQL'

-- I CREATE ROLE non sono idempotenti: usiamo ON_ERROR_STOP off intorno a ognuno
-- cosi' se il ruolo esiste gia' (caso restart) saltiamo senza fallire.

\set ON_ERROR_STOP off

CREATE ROLE :"migrator_role" LOGIN PASSWORD :'migrator_pwd';
CREATE ROLE :"app_role"      LOGIN PASSWORD :'app_pwd';
CREATE ROLE :"audit_role"    LOGIN PASSWORD :'audit_pwd';

\set ON_ERROR_STOP on

-- Migrator possiede il DB e puo' fare DDL
ALTER DATABASE :"db_name" OWNER TO :"migrator_role";
GRANT ALL PRIVILEGES ON DATABASE :"db_name" TO :"migrator_role";

-- App role: connect + uso schema public
GRANT CONNECT ON DATABASE :"db_name" TO :"app_role";
GRANT USAGE ON SCHEMA public TO :"app_role";

-- Audit writer: connect
GRANT CONNECT ON DATABASE :"db_name" TO :"audit_role";

-- Default privileges: tutto cio' che il migrator crea in public e' usabile dall'app
ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_role" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";

ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_role" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_role";

PSQL

echo "[init] ruoli NotAI creati / aggiornati"
