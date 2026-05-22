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

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class LLMRoutingSettings(BaseSettings):
    """Mappa ruolo applicativo -> alias di modello esposto da LiteLLM.

    L'app non chiede mai "qwen 7b": chiede sempre un RUOLO (es. 'generation').
    Cambiando l'env qui sotto si swappa il backend senza toccare il codice.

    In Fase 1 questa mappa diventera' persistente su DB (per-tenant) e modificabile
    via UI admin; in Fase 0 e' solo env (default da .env).
    """

    model_config = SettingsConfigDict(env_prefix="NOTAI_LLM_", extra="ignore")

    # Generazione di testo libero (redrafting clausole, riassunti).
    generation: str = "local/qwen2.5-7b"
    # Estrazione strutturata (parsing visure, dati da documenti).
    extraction: str = "local/qwen2.5-7b"
    # Embeddings per RAG.
    embeddings: str = "local/embeddings"
    # Verifier per cross-check abstention (idealmente modello diverso/piu' piccolo).
    verifier: str = "local/qwen2.5-7b"
    # Classificazione/tagging (zero-shot o few-shot).
    classification: str = "local/qwen2.5-7b"

    # Provider Ollama: URL diretto per discovery dei modelli installati sul host.
    # L'app chiama l'API Ollama /api/tags per scoprire cosa l'utente ha gia' scaricato.
    ollama_discovery_url: str = "http://host.docker.internal:11434"

    def as_dict(self) -> dict[str, str]:
        return {
            "generation": self.generation,
            "extraction": self.extraction,
            "embeddings": self.embeddings,
            "verifier": self.verifier,
            "classification": self.classification,
        }


class AuditSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOTAI_AUDIT_", extra="ignore")

    signing_key_path: str = "/run/secrets/notai_audit_signing.pem"
    tsa_url: str = "https://freetsa.org/tsr"
    tsa_hash_algo: str = "sha256"


class AISettings(BaseSettings):
    """Tuning del comportamento AI (zero-allucinazione)."""

    model_config = SettingsConfigDict(env_prefix="NOTAI_AI_", extra="ignore")

    # Soglia minima di confidence accettabile per l'abstention detector
    confidence_threshold: float = 0.55
    # HumanTask review: dopo quanti giorni di attesa il workflow timeout
    human_review_timeout_days: int = 30
    # Top-K chunks recuperati da RAG per ogni call AI
    rag_top_k: int = 5
    # Score minimo per considerare un chunk RAG rilevante (cosine similarity)
    rag_min_score: float = 0.3
    # Timeout HTTP per chiamate LLM (secondi)
    llm_http_timeout: int = 180
    # Max retries su backend LLM
    llm_max_retries: int = 2


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
    llm_routing: LLMRoutingSettings = Field(default_factory=LLMRoutingSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)
    ai: AISettings = Field(default_factory=AISettings)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
