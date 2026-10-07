"""Platform services: documents, branding, public links, messaging, notifications (M2).

DDL frozen here (see 0002). RLS, grants and the public-link resolver follow ADR-0003 and ADR-0015.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-07
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import append_only, disable_tenant_rls, enable_tenant_rls

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_STATEMENTS = [
    """
    CREATE TABLE app.documents (
        category VARCHAR NOT NULL,
        title VARCHAR NOT NULL,
        status VARCHAR DEFAULT 'active' NOT NULL,
        current_version_no INTEGER,
        expires_on DATE,
        source_key VARCHAR,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_documents PRIMARY KEY (id),
        CONSTRAINT uq_documents_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_documents_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE INDEX ix_documents_expires_on ON app.documents (tenant_id, expires_on)
    """,
    """
    CREATE UNIQUE INDEX uq_documents_source_key ON app.documents (tenant_id, source_key)
    """,
    """
    CREATE TABLE app.email_suppressions (
        email CITEXT NOT NULL,
        stream VARCHAR NOT NULL,
        reason VARCHAR NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_email_suppressions PRIMARY KEY (id),
        CONSTRAINT uq_email_suppressions_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_email_suppressions_tenant_id_email_stream UNIQUE (tenant_id, email, stream),
        CONSTRAINT fk_email_suppressions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE TABLE app.message_templates (
        event VARCHAR NOT NULL,
        channel VARCHAR DEFAULT 'email' NOT NULL,
        locale VARCHAR DEFAULT 'en' NOT NULL,
        subject VARCHAR NOT NULL,
        body VARCHAR NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_message_templates PRIMARY KEY (id),
        CONSTRAINT uq_message_templates_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_message_templates_tenant_id_event_channel_locale UNIQUE (tenant_id, event, channel, locale),
        CONSTRAINT fk_message_templates_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE TABLE app.notification_preferences (
        user_id VARCHAR NOT NULL,
        kind VARCHAR NOT NULL,
        in_app BOOLEAN DEFAULT true NOT NULL,
        email BOOLEAN DEFAULT false NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_notification_preferences PRIMARY KEY (id),
        CONSTRAINT uq_notification_preferences_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_notification_preferences_tenant_id_user_id_kind UNIQUE (tenant_id, user_id, kind),
        CONSTRAINT fk_notification_preferences_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE TABLE app.notifications (
        user_id VARCHAR NOT NULL,
        kind VARCHAR NOT NULL,
        title VARCHAR NOT NULL,
        body VARCHAR DEFAULT '' NOT NULL,
        link VARCHAR,
        read_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_notifications PRIMARY KEY (id),
        CONSTRAINT uq_notifications_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_notifications_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE INDEX ix_notifications_recipient ON app.notifications (tenant_id, user_id, read_at)
    """,
    """
    CREATE TABLE app.outbound_messages (
        channel VARCHAR DEFAULT 'email' NOT NULL,
        stream VARCHAR NOT NULL,
        event VARCHAR NOT NULL,
        to_address CITEXT NOT NULL,
        subject VARCHAR NOT NULL,
        body_text VARCHAR NOT NULL,
        body_html VARCHAR,
        status VARCHAR DEFAULT 'queued' NOT NULL,
        attempts INTEGER DEFAULT 0 NOT NULL,
        provider_message_id VARCHAR,
        error VARCHAR,
        entity_type VARCHAR,
        entity_id UUID,
        created_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        sent_at TIMESTAMP WITH TIME ZONE,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_outbound_messages PRIMARY KEY (id),
        CONSTRAINT uq_outbound_messages_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_outbound_messages_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE INDEX ix_outbound_messages_entity ON app.outbound_messages (tenant_id, entity_type, entity_id)
    """,
    """
    CREATE TABLE app.public_links (
        token_hash BYTEA NOT NULL,
        entity_type VARCHAR NOT NULL,
        entity_id UUID NOT NULL,
        scopes VARCHAR[] NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        revoked_at TIMESTAMP WITH TIME ZONE,
        created_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        sent_message_id UUID,
        view_count INTEGER DEFAULT 0 NOT NULL,
        last_viewed_at TIMESTAMP WITH TIME ZONE,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_public_links PRIMARY KEY (id),
        CONSTRAINT uq_public_links_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_public_links_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE INDEX ix_public_links_entity ON app.public_links (tenant_id, entity_type, entity_id)
    """,
    """
    CREATE UNIQUE INDEX uq_public_links_token_hash ON app.public_links (token_hash)
    """,
    """
    CREATE TABLE app.branding_settings (
        templates JSONB DEFAULT '{}'::jsonb NOT NULL,
        primary_color VARCHAR,
        accent_color VARCHAR,
        font_pair VARCHAR,
        logo_document_id UUID,
        footer_text VARCHAR,
        payment_instructions JSONB DEFAULT '{}'::jsonb NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_branding_settings PRIMARY KEY (id),
        CONSTRAINT uq_branding_settings_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_branding_settings_tenant_id UNIQUE (tenant_id),
        CONSTRAINT fk_branding_settings_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id),
        CONSTRAINT fk_branding_settings_tenant_id_logo_document_id_documents FOREIGN KEY(tenant_id, logo_document_id) REFERENCES app.documents (tenant_id, id)
    )
    """,
    """
    CREATE TABLE app.document_links (
        document_id UUID NOT NULL,
        entity_type VARCHAR NOT NULL,
        entity_id UUID NOT NULL,
        created_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_document_links PRIMARY KEY (id),
        CONSTRAINT uq_document_links_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_document_links_tenant_id_document_id_entity_type_entity_id UNIQUE (tenant_id, document_id, entity_type, entity_id),
        CONSTRAINT fk_document_links_tenant_id_document_id_documents FOREIGN KEY(tenant_id, document_id) REFERENCES app.documents (tenant_id, id)
    )
    """,
    """
    CREATE INDEX ix_document_links_entity ON app.document_links (tenant_id, entity_type, entity_id)
    """,
    """
    CREATE TABLE app.document_versions (
        document_id UUID NOT NULL,
        version_no INTEGER NOT NULL,
        storage_key VARCHAR NOT NULL,
        filename VARCHAR NOT NULL,
        content_type VARCHAR NOT NULL,
        size_bytes BIGINT NOT NULL,
        sha256 VARCHAR,
        status VARCHAR DEFAULT 'pending' NOT NULL,
        created_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        finalized_at TIMESTAMP WITH TIME ZONE,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_document_versions PRIMARY KEY (id),
        CONSTRAINT uq_document_versions_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_document_versions_tenant_id_document_id_version_no UNIQUE (tenant_id, document_id, version_no),
        CONSTRAINT fk_document_versions_tenant_id_document_id_documents FOREIGN KEY(tenant_id, document_id) REFERENCES app.documents (tenant_id, id)
    )
    """,
    """
    CREATE TABLE app.link_events (
        link_id UUID NOT NULL,
        event_type VARCHAR NOT NULL,
        occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        ip_hash VARCHAR,
        user_agent VARCHAR,
        is_bot BOOLEAN DEFAULT false NOT NULL,
        details JSONB DEFAULT '{}'::jsonb NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_link_events PRIMARY KEY (id),
        CONSTRAINT uq_link_events_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_link_events_tenant_id_link_id_public_links FOREIGN KEY(tenant_id, link_id) REFERENCES app.public_links (tenant_id, id)
    )
    """,
    """
    CREATE INDEX ix_link_events_link ON app.link_events (tenant_id, link_id)
    """,
]

TABLES = [
    "documents",
    "email_suppressions",
    "message_templates",
    "notification_preferences",
    "notifications",
    "outbound_messages",
    "public_links",
    "branding_settings",
    "document_links",
    "document_versions",
    "link_events",
]


def upgrade() -> None:
    for statement in CREATE_STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        for statement in enable_tenant_rls(table):
            op.execute(statement)

    # Anonymous visitors have only a token. This function (owned by app_owner, which never serves requests)
    # maps SHA-256(token) to (tenant_id, link_id); everything afterwards runs under RLS for that tenant.
    op.execute(
        "CREATE POLICY resolve_public_link ON app.public_links FOR SELECT TO app_owner USING (true)"
    )
    op.execute(
        """
        CREATE FUNCTION app.resolve_public_link(p_token_hash bytea)
        RETURNS TABLE (tenant_id uuid, link_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
            SELECT l.tenant_id, l.id FROM app.public_links l WHERE l.token_hash = p_token_hash
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.resolve_public_link(bytea) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app.resolve_public_link(bytea) TO app_user")

    for statement in [
        *append_only("link_events"),
        # Records and logs are kept (archive instead); links and templates may be removed.
        "REVOKE DELETE, TRUNCATE ON app.documents, app.document_versions, app.public_links, "
        "app.outbound_messages, app.branding_settings, app.email_suppressions FROM app_user",
        "REVOKE TRUNCATE ON app.document_links, app.message_templates, app.notifications, "
        "app.notification_preferences FROM app_user",
    ]:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.resolve_public_link(bytea)")
    op.execute("DROP POLICY IF EXISTS resolve_public_link ON app.public_links")
    for table in TABLES:
        for statement in disable_tenant_rls(table):
            op.execute(statement)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS app.{table}")
