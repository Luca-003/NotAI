"""core schema: IAM + parties + practices + documents + search + audit

Crea l'intero schema di Fase 1 in una singola migration. Tutte le tabelle
tenant-aware hanno RLS attiva. La tabella audit.audit_events ha trigger
anti-UPDATE/DELETE per garantire immutabilita' a livello DB.

Revision ID: 0002_core_schema
Revises: 0001_init
Create Date: 2026-05-21 14:30:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_core_schema"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabelle tenant-aware su cui attiveremo RLS standard
TENANT_TABLES = [
    "users",
    "roles",
    "parties",
    "aml_assessments",
    "practices",
    "acts",
    "party_roles",
    "documents",
    "tags",
    "clauses",
    "tagged_items",
]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")

    # ---------------------------------------------------------------------
    # IAM
    # ---------------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(32), nullable=False, server_default="misto"),
        sa.Column("settings", postgresql.JSONB, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("mfa_secret", sa.String(255), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("professional_kind", sa.String(32), nullable=True),
        sa.Column("professional_id", sa.String(64), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
    )
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"])

    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="RESTRICT"),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
    )

    # ---------------------------------------------------------------------
    # Parties + AML
    # ---------------------------------------------------------------------
    op.create_table(
        "parties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kind", sa.String(2), nullable=False),
        sa.Column("anagrafica", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("fiscal_code", sa.String(32), nullable=True),
        sa.Column("vat_number", sa.String(32), nullable=True),
        sa.Column("kyc_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("beneficial_owners", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_parties_tenant_id", "parties", ["tenant_id"])
    op.create_index("ix_parties_fiscal_code", "parties", ["fiscal_code"])
    op.create_index("ix_parties_vat_number", "parties", ["vat_number"])

    op.create_table(
        "aml_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("party_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("factors", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_aml_tenant_id", "aml_assessments", ["tenant_id"])
    op.create_index("ix_aml_party_id", "aml_assessments", ["party_id"])

    # ---------------------------------------------------------------------
    # Practices + Acts + PartyRoles
    # ---------------------------------------------------------------------
    op.create_table(
        "practices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(128), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="bozza"),
        sa.Column("responsible_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("main_client_party_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["main_client_party_id"], ["parties.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_practices_tenant_code"),
    )
    op.create_index("ix_practices_tenant_id", "practices", ["tenant_id"])
    op.create_index("ix_practices_code", "practices", ["code"])
    op.create_index("ix_practices_kind", "practices", ["kind"])
    op.create_index("ix_practices_responsible", "practices", ["responsible_user_id"])

    op.create_table(
        "acts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(128), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("repertorio_number", sa.Integer, nullable=True),
        sa.Column("repertorio_year", sa.Integer, nullable=True),
        sa.Column("raccolta_number", sa.Integer, nullable=True),
        sa.Column("workflow_status", sa.String(32), nullable=False, server_default="bozza"),
        sa.Column("workflow_run_id", sa.String(255), nullable=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_version", sa.Integer, nullable=True),
        sa.Column("stipulation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notary_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["practice_id"], ["practices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["notary_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "tenant_id", "repertorio_year", "repertorio_number",
            name="uq_acts_tenant_repertorio",
        ),
    )
    op.create_index("ix_acts_tenant_id", "acts", ["tenant_id"])
    op.create_index("ix_acts_practice_id", "acts", ["practice_id"])
    op.create_index("ix_acts_kind", "acts", ["kind"])

    op.create_table(
        "party_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("act_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("party_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("quota", sa.Float, nullable=True),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["act_id"], ["acts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("act_id", "party_id", "role", name="uq_party_roles_act_party_role"),
    )
    op.create_index("ix_party_roles_tenant_id", "party_roles", ["tenant_id"])
    op.create_index("ix_party_roles_act_id", "party_roles", ["act_id"])
    op.create_index("ix_party_roles_party_id", "party_roles", ["party_id"])

    # ---------------------------------------------------------------------
    # Documents
    # ---------------------------------------------------------------------
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("act_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("storage_uri", sa.String(1024), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("parent_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("signature", postgresql.JSONB, nullable=True),
        sa.Column("timestamp_token", sa.Text, nullable=True),
        sa.Column("timestamp_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_class", sa.String(32), nullable=False, server_default="nessuna"),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["practice_id"], ["practices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["act_id"], ["acts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["documents.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_practice_id", "documents", ["practice_id"])
    op.create_index("ix_documents_act_id", "documents", ["act_id"])
    op.create_index("ix_documents_kind", "documents", ["kind"])
    op.create_index("ix_documents_sha256", "documents", ["sha256"])

    # ---------------------------------------------------------------------
    # Search: tags, normative_references, clauses, tagged_items
    # ---------------------------------------------------------------------
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("namespace", sa.String(64), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value", sa.String(512), nullable=True),
        sa.Column("display_label", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("color", sa.String(16), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id", "namespace", "key", "value",
            name="uq_tags_tenant_ns_key_value",
        ),
    )
    op.create_index("ix_tags_tenant_id", "tags", ["tenant_id"])
    op.create_index("ix_tags_namespace", "tags", ["namespace"])
    op.create_index("ix_tags_key", "tags", ["key"])

    op.create_table(
        "normative_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("fonte", sa.String(32), nullable=False),
        sa.Column("anno", sa.Integer, nullable=True),
        sa.Column("numero", sa.String(64), nullable=True),
        sa.Column("articolo", sa.String(64), nullable=True),
        sa.Column("comma", sa.String(16), nullable=True),
        sa.Column("citation", sa.String(255), nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("vigenza_da", sa.String(32), nullable=True),
        sa.Column("vigenza_a", sa.String(32), nullable=True),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.UniqueConstraint(
            "fonte", "anno", "numero", "articolo", "comma", "vigenza_da",
            name="uq_normative_ref",
        ),
    )
    op.create_index("ix_normative_fonte", "normative_references", ["fonte"])
    op.create_index("ix_normative_citation", "normative_references", ["citation"])

    op.create_table(
        "clauses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("act_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordering", sa.Integer, nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("generated_by", sa.String(16), nullable=False),
        sa.Column("llm_invocation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.String(32), nullable=True),
        sa.Column("tag_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("normative_refs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["act_id"], ["acts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_clauses_tenant_id", "clauses", ["tenant_id"])
    op.create_index("ix_clauses_act_id", "clauses", ["act_id"])
    op.create_index("ix_clauses_llm_invocation_id", "clauses", ["llm_invocation_id"])

    op.create_table(
        "tagged_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tag_id", "item_type", "item_id",
            name="uq_tagged_items_tag_item",
        ),
    )
    op.create_index("ix_tagged_items_tenant_id", "tagged_items", ["tenant_id"])
    op.create_index("ix_tagged_items_tag_id", "tagged_items", ["tag_id"])
    op.create_index("ix_tagged_items_item_type", "tagged_items", ["item_type"])
    op.create_index("ix_tagged_items_item_id", "tagged_items", ["item_id"])

    # ---------------------------------------------------------------------
    # Audit event store: schema 'audit', tabelle append-only con trigger
    # ---------------------------------------------------------------------
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stream_id", sa.String(128), nullable=False),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.Text, nullable=True),
        sa.Column("timestamp_token", sa.Text, nullable=True),
        sa.UniqueConstraint("tenant_id", "stream_id", "seq", name="uq_audit_events_stream_seq"),
        sa.UniqueConstraint("hash", name="uq_audit_events_hash"),
        schema="audit",
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"], schema="audit")
    op.create_index("ix_audit_events_tenant_ts", "audit_events", ["tenant_id", "ts"], schema="audit")
    op.create_index("ix_audit_events_tenant_type", "audit_events", ["tenant_id", "type"], schema="audit")
    op.create_index("ix_audit_events_ts", "audit_events", ["ts"], schema="audit")
    op.create_index(
        "ix_audit_events_payload_gin",
        "audit_events", ["payload"],
        postgresql_using="gin",
        schema="audit",
    )

    op.create_table(
        "llm_invocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_alias", sa.String(255), nullable=False),
        sa.Column("model_backend", sa.String(64), nullable=False),
        sa.Column("model_sha256", sa.String(64), nullable=True),
        sa.Column("prompt_template_id", sa.String(128), nullable=True),
        sa.Column("prompt_template_version", sa.Integer, nullable=True),
        sa.Column("prompt_rendered", sa.Text, nullable=False),
        sa.Column("response_raw", sa.Text, nullable=False),
        sa.Column("response_structured", postgresql.JSONB, nullable=True),
        sa.Column("temperature", sa.Float, nullable=False, server_default="0"),
        sa.Column("seed", sa.Integer, nullable=True),
        sa.Column("max_tokens", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("abstain_reason", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("citations", postgresql.JSONB, nullable=True),
        sa.Column("input_snapshot_sha256", sa.String(64), nullable=True),
        sa.Column("output_snapshot_sha256", sa.String(64), nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(
            ["audit_event_id"], ["audit.audit_events.id"], ondelete="RESTRICT"
        ),
        schema="audit",
    )
    op.create_index("ix_llm_inv_tenant_ts", "llm_invocations", ["tenant_id", "ts"], schema="audit")
    op.create_index("ix_llm_inv_audit_event", "llm_invocations", ["audit_event_id"], schema="audit")

    # Trigger immutabilita' su audit.audit_events
    # Le function audit.reject_update/delete/truncate sono create dall'init script
    # 03-audit-bootstrap.sql. Le agganciamo alla tabella appena creata.
    op.execute("""
        CREATE TRIGGER audit_events_reject_update
        BEFORE UPDATE ON audit.audit_events
        FOR EACH ROW EXECUTE FUNCTION audit.reject_update();
    """)
    op.execute("""
        CREATE TRIGGER audit_events_reject_delete
        BEFORE DELETE ON audit.audit_events
        FOR EACH ROW EXECUTE FUNCTION audit.reject_delete();
    """)
    op.execute("""
        CREATE TRIGGER audit_events_reject_truncate
        BEFORE TRUNCATE ON audit.audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION audit.reject_truncate();
    """)

    # Stesso schema di trigger su llm_invocations
    op.execute("""
        CREATE TRIGGER llm_inv_reject_update
        BEFORE UPDATE ON audit.llm_invocations
        FOR EACH ROW EXECUTE FUNCTION audit.reject_update();
    """)
    op.execute("""
        CREATE TRIGGER llm_inv_reject_delete
        BEFORE DELETE ON audit.llm_invocations
        FOR EACH ROW EXECUTE FUNCTION audit.reject_delete();
    """)

    # ---------------------------------------------------------------------
    # RLS: applicata a tutte le tabelle tenant-aware
    # ---------------------------------------------------------------------
    # NB: il migrator role e' BYPASSRLS implicito perche' e' owner. L'app role
    # passera' attraverso le policy.
    for table in TENANT_TABLES:
        op.execute(f"SELECT public.enable_tenant_rls('public.{table}'::regclass)")

    # Per audit.audit_events e audit.llm_invocations applichiamo RLS manuale:
    # gli admin del singolo tenant possono leggere TUTTO il proprio audit;
    # nessuno puo' modificarlo (oltre ai trigger gia' attivi).
    for table in ("audit.audit_events", "audit.llm_invocations"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation_select ON {table}
              FOR SELECT
              USING (tenant_id::text = current_setting('app.tenant_id', true))
        """)
        op.execute(f"""
            CREATE POLICY tenant_isolation_insert ON {table}
              FOR INSERT
              WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))
        """)


def downgrade() -> None:
    # Rimuove trigger
    op.execute("DROP TRIGGER IF EXISTS audit_events_reject_update ON audit.audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_events_reject_delete ON audit.audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_events_reject_truncate ON audit.audit_events")
    op.execute("DROP TRIGGER IF EXISTS llm_inv_reject_update ON audit.llm_invocations")
    op.execute("DROP TRIGGER IF EXISTS llm_inv_reject_delete ON audit.llm_invocations")

    # Drop tabelle in ordine inverso (FK)
    op.drop_table("llm_invocations", schema="audit")
    op.drop_table("audit_events", schema="audit")
    op.drop_table("tagged_items")
    op.drop_table("clauses")
    op.drop_table("normative_references")
    op.drop_table("tags")
    op.drop_table("documents")
    op.drop_table("party_roles")
    op.drop_table("acts")
    op.drop_table("practices")
    op.drop_table("aml_assessments")
    op.drop_table("parties")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_table("tenants")
