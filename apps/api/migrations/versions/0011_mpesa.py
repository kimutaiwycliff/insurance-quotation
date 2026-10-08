"""R2.3: M-Pesa Daraja: tenant connections (encrypted keys), payment prompts, transactions, webhook events.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_STATEMENTS = [
    """
    CREATE TABLE app.mpesa_connections (
        environment VARCHAR NOT NULL,
        shortcode_type VARCHAR NOT NULL,
        business_shortcode VARCHAR NOT NULL,
        party_b VARCHAR NOT NULL,
        consumer_key_enc VARCHAR NOT NULL,
        consumer_secret_enc VARCHAR NOT NULL,
        passkey_enc VARCHAR NOT NULL,
        callback_token_hash VARCHAR NOT NULL,
        callback_token_enc VARCHAR NOT NULL,
        status VARCHAR DEFAULT 'active' NOT NULL,
        c2b_registered_at TIMESTAMP WITH TIME ZONE,
        last_error VARCHAR,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_mpesa_connections PRIMARY KEY (id),
        CONSTRAINT uq_mpesa_connections_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_mpesa_connections_tenant_id UNIQUE (tenant_id)
    )
    """,
    "CREATE UNIQUE INDEX uq_mpesa_connections_callback ON app.mpesa_connections (callback_token_hash)",
    """
    CREATE TABLE app.mpesa_requests (
        connection_id UUID NOT NULL,
        invoice_id UUID,
        phone VARCHAR NOT NULL,
        amount NUMERIC(20, 4) NOT NULL,
        account_reference VARCHAR NOT NULL,
        merchant_request_id VARCHAR,
        checkout_request_id VARCHAR,
        status VARCHAR DEFAULT 'pending' NOT NULL,
        result_code INTEGER,
        result_desc VARCHAR,
        receipt VARCHAR,
        payment_id UUID,
        source VARCHAR NOT NULL,
        requested_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        completed_at TIMESTAMP WITH TIME ZONE,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_mpesa_requests PRIMARY KEY (id),
        CONSTRAINT uq_mpesa_requests_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_mpesa_requests_tenant_id_connection_id_mpesa_connections FOREIGN KEY(tenant_id, connection_id) REFERENCES app.mpesa_connections (tenant_id, id)
    )
    """,
    "CREATE INDEX ix_mpesa_requests_status ON app.mpesa_requests (tenant_id, status, created_at)",
    "CREATE UNIQUE INDEX uq_mpesa_requests_checkout ON app.mpesa_requests (tenant_id, checkout_request_id)",
    """
    CREATE TABLE app.mpesa_transactions (
        connection_id UUID NOT NULL,
        receipt VARCHAR NOT NULL,
        source VARCHAR NOT NULL,
        amount NUMERIC(20, 4) NOT NULL,
        paid_at TIMESTAMP WITH TIME ZONE,
        payer VARCHAR,
        bill_reference VARCHAR,
        status VARCHAR NOT NULL,
        invoice_id UUID,
        payment_id UUID,
        request_id UUID,
        note VARCHAR,
        resolved_by VARCHAR,
        resolved_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_mpesa_transactions PRIMARY KEY (id),
        CONSTRAINT uq_mpesa_transactions_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_mpesa_transactions_tenant_id_connection_id_mpesa_connections FOREIGN KEY(tenant_id, connection_id) REFERENCES app.mpesa_connections (tenant_id, id)
    )
    """,
    "CREATE INDEX ix_mpesa_transactions_status ON app.mpesa_transactions (tenant_id, status)",
    "CREATE UNIQUE INDEX uq_mpesa_transactions_receipt ON app.mpesa_transactions (tenant_id, receipt)",
    """
    CREATE TABLE app.webhook_events (
        provider VARCHAR NOT NULL,
        kind VARCHAR NOT NULL,
        event_key VARCHAR NOT NULL,
        connection_id UUID,
        payload JSONB NOT NULL,
        received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        processed_at TIMESTAMP WITH TIME ZONE,
        error VARCHAR,
        attempts INTEGER DEFAULT 0 NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_webhook_events PRIMARY KEY (id),
        CONSTRAINT uq_webhook_events_tenant_id_id UNIQUE (tenant_id, id)
    )
    """,
    "CREATE UNIQUE INDEX uq_webhook_events_key ON app.webhook_events (tenant_id, provider, kind, event_key)",
]

TABLES = ["mpesa_connections", "mpesa_requests", "mpesa_transactions", "webhook_events"]

# Callbacks arrive without a tenant: resolve the secret path segment (sha256) to its tenant (ADR-0003 §8).
RESOLVE = """
    CREATE FUNCTION app.resolve_mpesa_callback(p_token_hash text)
    RETURNS TABLE (tenant_id uuid, connection_id uuid, status text)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
        SELECT c.tenant_id, c.id, c.status FROM app.mpesa_connections c
         WHERE c.callback_token_hash = p_token_hash
    $$
"""

# Prompts still pending after 20 seconds are checked with STK Query (callbacks can be lost).
PENDING = """
    CREATE FUNCTION app.mpesa_requests_to_check()
    RETURNS TABLE (tenant_id uuid, request_id uuid)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
        SELECT r.tenant_id, r.id FROM app.mpesa_requests r
         WHERE r.status = 'pending' AND r.checkout_request_id IS NOT NULL
           AND r.created_at < now() - interval '20 seconds'
         ORDER BY r.created_at LIMIT 500
    $$
"""


def upgrade() -> None:
    for statement in CREATE_STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        for statement in enable_tenant_rls(table):
            op.execute(statement)
    op.execute(
        "CREATE POLICY callback_resolve ON app.mpesa_connections FOR SELECT TO app_owner USING (true)"
    )
    op.execute(
        "CREATE POLICY pending_scan ON app.mpesa_requests FOR SELECT TO app_owner USING (true)"
    )
    for function, signature in (
        (RESOLVE, "resolve_mpesa_callback(text)"),
        (PENDING, "mpesa_requests_to_check()"),
    ):
        op.execute(function)
        op.execute(f"REVOKE ALL ON FUNCTION app.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION app.{signature} TO app_user")
    # Money records are corrected, never deleted; connections are disabled, never deleted.
    op.execute(
        "REVOKE DELETE, TRUNCATE ON app.mpesa_connections, app.mpesa_requests, "
        "app.mpesa_transactions, app.webhook_events FROM app_user"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.mpesa_requests_to_check()")
    op.execute("DROP FUNCTION IF EXISTS app.resolve_mpesa_callback(text)")
    op.execute("DROP POLICY IF EXISTS pending_scan ON app.mpesa_requests")
    op.execute("DROP POLICY IF EXISTS callback_resolve ON app.mpesa_connections")
    for table in TABLES:
        for statement in disable_tenant_rls(table):
            op.execute(statement)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS app.{table}")
