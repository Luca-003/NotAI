-- NotAI - crea DB dedicati a Temporal (history + visibility) sulla stessa istanza.
-- L'immagine temporalio/auto-setup si aspetta i DB già presenti o li crea
-- via l'utente POSTGRES_USER; qui li pre-creiamo per essere sicuri.

SELECT 'CREATE DATABASE temporal'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal')
\gexec

SELECT 'CREATE DATABASE temporal_visibility'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal_visibility')
\gexec
