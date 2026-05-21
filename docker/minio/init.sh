#!/bin/sh
# NotAI - Inizializzazione MinIO: crea bucket con object-lock (WORM) ove richiesto.
set -e

ENDPOINT="http://minio:9000"
ALIAS="notai-local"

echo "[minio-init] attendo che MinIO sia raggiungibile..."
until mc alias set "$ALIAS" "$ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  sleep 2
done

create_locked_bucket() {
  local bucket="$1"
  local retention_days="$2"
  if mc ls "$ALIAS/$bucket" >/dev/null 2>&1; then
    echo "[minio-init] bucket '$bucket' già esiste"
  else
    echo "[minio-init] creo bucket '$bucket' con object-lock (compliance, $retention_days giorni)"
    mc mb --with-lock "$ALIAS/$bucket"
    mc retention set --default compliance "${retention_days}d" "$ALIAS/$bucket"
  fi
}

create_plain_bucket() {
  local bucket="$1"
  if mc ls "$ALIAS/$bucket" >/dev/null 2>&1; then
    echo "[minio-init] bucket '$bucket' già esiste"
  else
    echo "[minio-init] creo bucket '$bucket'"
    mc mb "$ALIAS/$bucket"
  fi
}

# Bucket documenti: 10 anni di retention WORM (conservazione decennale notarile)
create_locked_bucket "$MINIO_BUCKET_DOCUMENTS" 3650

# Bucket bundle audit esportati: 10 anni
create_locked_bucket "$MINIO_BUCKET_AUDIT" 3650

# Bucket modelli LLM: niente lock (sono pesi, possono essere sostituiti)
create_plain_bucket "$MINIO_BUCKET_MODELS"

# Versioning sempre attivo
mc version enable "$ALIAS/$MINIO_BUCKET_DOCUMENTS" || true
mc version enable "$ALIAS/$MINIO_BUCKET_AUDIT" || true

echo "[minio-init] completato"
