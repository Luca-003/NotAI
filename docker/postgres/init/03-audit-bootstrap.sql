-- NotAI - bootstrap minimale dell'audit log.
--
-- La tabella vera con tutti i campi viene creata dalle migrazioni Alembic;
-- qui creiamo solo lo SCHEMA dedicato + le function trigger di immutabilità,
-- in modo che siano gestite con permessi e ownership corretti dal day-one.
--
-- Lo schema 'audit' ospiterà la tabella audit_events. Nessuno ha DELETE/UPDATE
-- a livello di ruolo, ma per sicurezza in profondità (defense-in-depth) montiamo
-- anche trigger che bloccano UPDATE e DELETE.

CREATE SCHEMA IF NOT EXISTS audit;

-- Function trigger: blocca UPDATE
CREATE OR REPLACE FUNCTION audit.reject_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'audit log is append-only: UPDATE not allowed on % (id=%)',
    TG_TABLE_NAME, OLD.id
    USING ERRCODE = '0A000';  -- feature_not_supported
END;
$$;

-- Function trigger: blocca DELETE e TRUNCATE
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
