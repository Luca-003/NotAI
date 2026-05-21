"""Centralizza la lettura della configurazione via variabili d'ambiente.

Tutta la config passa da qui. Niente os.environ sparso nei moduli.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Env = Literal["dev", "staging", "prod"]


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", extra="ignore")

    host: str = "postgres"
    port: int = 5432
    user: str = "notai_app"
    password: SecretStr = SecretStr("change_me_in_dev")
    db: str = "notai"

    @property
    def dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )


class TemporalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TEMPORAL_", extra="ignore")

    host: str = "temporal"
    port: int = 7233
    namespace: str = "notai"
    task_queue: str = "notai-main"

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


class MinioSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINIO_", extra="ignore")

    host: str = "minio"
    port: int = 9000
    root_user: str = "notai_minio"
    root_password: SecretStr = SecretStr("change_me_minio")
    bucket_documents: str = "notai-documents"
    bucket_audit: str = "notai-audit-bundles"
    bucket_models: str = "notai-llm-models"


class OpenSearchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENSEARCH_", extra="ignore")

    host: str = "opensearch"
    port: int = 9200
    initial_admin_password: SecretStr = SecretStr("ChangeMeInDev123!")


class QdrantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QDRANT_", extra="ignore")

    host: str = "qdrant"
    port: int = 6333
    api_key: SecretStr = SecretStr("change_me_qdrant")


class VaultSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VAULT_", extra="ignore")

    addr: str = "http://vault:8200"
    token: SecretStr = SecretStr("dev-only-root-token")


class LiteLLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LITELLM_", extra="ignore")

    host: str = "litellm"
    port: int = 4000
    master_key: SecretStr = SecretStr("sk-change-me-master")
    model_primary: str = "local/qwen2.5-7b"
    model_fallback: str = "local/qwen2.5-7b-cpu"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class AuditSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOTAI_AUDIT_", extra="ignore")

    signing_key_path: str = "/run/secrets/notai_audit_signing.pem"
    tsa_url: str = "https://freetsa.org/tsr"
    tsa_hash_algo: str = "sha256"


class Settings(BaseSettings):
    """Configurazione principale dell'applicazione."""

    model_config = SettingsConfigDict(
        env_prefix="NOTAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Env = "dev"
    log_level: str = "INFO"
    tz: str = "Europe/Rome"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 2
    api_public_url: str = "https://notai.localhost"

    jwt_secret: SecretStr = Field(default=SecretStr("change_me_jwt_secret"))
    jwt_algo: str = "HS256"
    jwt_ttl_seconds: int = 3600
    cors_origins: str = "http://localhost:5173,https://notai.localhost"

    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    temporal: TemporalSettings = Field(default_factory=TemporalSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    vault: VaultSettings = Field(default_factory=VaultSettings)
    litellm: LiteLLMSettings = Field(default_factory=LiteLLMSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
