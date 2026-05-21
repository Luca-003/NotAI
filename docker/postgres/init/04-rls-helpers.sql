-- NotAI - helper per Row-Level Security multi-tenant.
--
-- Convenzione: ogni connessione applicativa setta una GUC custom
--   SET app.tenant_id = '<uuid-tenant>';
-- Le policy RLS filtreranno usando current_setting('app.tenant_id', true).
--
-- La GUC è creata 'unset by default' a livello di sessione: l'app DEVE settarla.
-- Le policy RLS rifiutano accessi se non settata (vedi migrazioni Alembic).

-- Reset esplicito del GUC al disconnect (per evitare leak attraverso connection pool)
-- Questo non è strettamente necessario perché Postgres pulisce la sessione,
-- ma documenta l'intent.

-- Function helper per le migrazioni: applica RLS standard su una tabella tenant-aware.
CREATE OR REPLACE FUNCTION public.enable_tenant_rls(p_table regclass)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_table_name text := p_table::text;
BEGIN
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', v_table_name);
  EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', v_table_name);

  EXECUTE format($pol$
    CREATE POLICY tenant_isolation_select ON %s
      FOR SELECT
      USING (tenant_id::text = current_setting('app.tenant_id', true))
  $pol$, v_table_name);

  EXECUTE format($pol$
    CREATE POLICY tenant_isolation_modify ON %s
      FOR ALL
      USING (tenant_id::text = current_setting('app.tenant_id', true))
      WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))
  $pol$, v_table_name);
END;
$$;

COMMENT ON FUNCTION public.enable_tenant_rls(regclass) IS
  'Abilita RLS standard tenant-aware su una tabella. Richiede colonna tenant_id UUID NOT NULL.';
