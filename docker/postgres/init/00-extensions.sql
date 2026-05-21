-- NotAI - estensioni Postgres da abilitare al primo boot.
-- pgvector: embedding intra-pratica.
-- pg_stat_statements: visibilità query.
-- pgcrypto: hash, uuid v4.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
