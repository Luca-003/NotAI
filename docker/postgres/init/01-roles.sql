-- NotAI - ruoli separati per separazione dei privilegi.
--
-- notai_migrator      : owner schema, DDL (Alembic)
-- notai_app           : ruolo applicativo runtime (DML, NO DDL, audit solo INSERT)
-- notai_audit_writer  : ruolo dedicato per scritture in audit_events (granted al servizio)
-- notai_readonly      : reportistica / read replicas (futuro)
--
-- I role sono creati al primo boot. Le password vengono da variabili d'ambiente
-- iniettate dal Docker entrypoint via PSQL.

\set migrator_role `echo "$POSTGRES_MIGRATOR_ROLE"`
\set migrator_pwd  `echo "$POSTGRES_MIGRATOR_PASSWORD"`
\set app_role      `echo "$POSTGRES_APP_ROLE"`
\set app_pwd       `echo "$POSTGRES_APP_PASSWORD"`
\set audit_role    `echo "$POSTGRES_AUDIT_WRITER_ROLE"`
\set audit_pwd     `echo "$POSTGRES_AUDIT_WRITER_PASSWORD"`
\set db_name       `echo "$POSTGRES_DB"`

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migrator_role') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', :'migrator_role', :'migrator_pwd');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_role', :'app_pwd');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'audit_role') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', :'audit_role', :'audit_pwd');
  END IF;
END
$$;

-- Migrator possiede lo schema
GRANT ALL PRIVILEGES ON DATABASE :"db_name" TO :"migrator_role";
ALTER DATABASE :"db_name" OWNER TO :"migrator_role";

-- App role può connettersi e usare lo schema public
GRANT CONNECT ON DATABASE :"db_name" TO :"app_role";
GRANT USAGE ON SCHEMA public TO :"app_role";

-- Audit writer può connettersi e usare uno schema dedicato (creato dalle migrazioni)
GRANT CONNECT ON DATABASE :"db_name" TO :"audit_role";

-- Default privileges per oggetti creati dal migrator -> app role
ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_role" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";

ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_role" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_role";
