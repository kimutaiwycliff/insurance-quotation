"""R1.4: policy book, premium payments (recorded, never held), renewal reminders.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_STATEMENTS = [
    """
    CREATE TABLE app.policies (
        client_id UUID NOT NULL,
        owner_user_id VARCHAR NOT NULL,
        quote_id UUID,
        product_id UUID,
        insurer_name VARCHAR NOT NULL,
        product_name VARCHAR NOT NULL,
        class_code VARCHAR NOT NULL,
        policy_number VARCHAR,
        description VARCHAR NOT NULL,
        details JSONB DEFAULT '[]'::jsonb NOT NULL,
        status VARCHAR DEFAULT 'pending' NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE NOT NULL,
        currency CHAR(3) DEFAULT 'KES' NOT NULL,
        sum_insured NUMERIC(20, 4),
        total_premium NUMERIC(20, 4) NOT NULL,
        breakdown JSONB DEFAULT '{}'::jsonb NOT NULL,
        commission JSONB,
        collection_mode VARCHAR DEFAULT 'insurer_direct' NOT NULL,
        activated_at TIMESTAMP WITH TIME ZONE,
        activation JSONB DEFAULT '{}'::jsonb NOT NULL,
        cancelled_at TIMESTAMP WITH TIME ZONE,
        cancel_reason VARCHAR,
        renewed_from_id UUID,
        renewal_stage VARCHAR DEFAULT 'due' NOT NULL,
        renewal_quote_id UUID,
        renewed_to_id UUID,
        lost_reason VARCHAR,
        last_contacted_at TIMESTAMP WITH TIME ZONE,
        notes VARCHAR,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_policies PRIMARY KEY (id),
        CONSTRAINT uq_policies_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_policies_tenant_id_client_id_clients FOREIGN KEY(tenant_id, client_id) REFERENCES app.clients (tenant_id, id),
        CONSTRAINT fk_policies_tenant_id_quote_id_quotes FOREIGN KEY(tenant_id, quote_id) REFERENCES app.quotes (tenant_id, id),
        CONSTRAINT fk_policies_tenant_id_product_id_products FOREIGN KEY(tenant_id, product_id) REFERENCES app.products (tenant_id, id),
        CONSTRAINT fk_policies_tenant_id_renewed_from_id_policies FOREIGN KEY(tenant_id, renewed_from_id) REFERENCES app.policies (tenant_id, id),
        CONSTRAINT ck_policies_dates CHECK (end_date > start_date),
        CONSTRAINT ck_policies_premium CHECK (total_premium >= 0)
    )
    """,
    "CREATE INDEX ix_policies_client ON app.policies (tenant_id, client_id)",
    "CREATE INDEX ix_policies_end ON app.policies (tenant_id, end_date)",
    "CREATE INDEX ix_policies_owner_end ON app.policies (tenant_id, owner_user_id, end_date)",
    "CREATE UNIQUE INDEX uq_policies_quote ON app.policies (tenant_id, quote_id)",
    "CREATE UNIQUE INDEX uq_policies_renewed_from ON app.policies (tenant_id, renewed_from_id)",
    """
    CREATE TABLE app.policy_payments (
        policy_id UUID NOT NULL,
        amount NUMERIC(20, 4) NOT NULL,
        currency CHAR(3) NOT NULL,
        paid_on DATE NOT NULL,
        method VARCHAR NOT NULL,
        reference VARCHAR,
        paid_to VARCHAR NOT NULL,
        remit_task_id UUID,
        remitted_on DATE,
        remittance_reference VARCHAR,
        voided_at TIMESTAMP WITH TIME ZONE,
        void_reason VARCHAR,
        voided_by VARCHAR,
        created_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_policy_payments PRIMARY KEY (id),
        CONSTRAINT uq_policy_payments_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_policy_payments_tenant_id_policy_id_policies FOREIGN KEY(tenant_id, policy_id) REFERENCES app.policies (tenant_id, id),
        CONSTRAINT ck_policy_payments_amount CHECK (amount > 0)
    )
    """,
    "CREATE INDEX ix_policy_payments_policy ON app.policy_payments (tenant_id, policy_id)",
    """
    CREATE TABLE app.renewal_reminders (
        policy_id UUID NOT NULL,
        offset_days INTEGER NOT NULL,
        emailed_to VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_renewal_reminders PRIMARY KEY (id),
        CONSTRAINT uq_renewal_reminders_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_renewal_reminders_tenant_id_policy_id_offset_days UNIQUE (tenant_id, policy_id, offset_days),
        CONSTRAINT fk_renewal_reminders_tenant_id_policy_id_policies FOREIGN KEY(tenant_id, policy_id) REFERENCES app.policies (tenant_id, id)
    )
    """,
]

TABLES = ["policies", "policy_payments", "renewal_reminders"]

# Cross-tenant scan for the daily renewal job (ADR-0003 §8): for each active policy that is not yet renewed or
# lost, the smallest reminder offset (days before expiry, per agency) that has been reached and not yet sent.
SCAN_FUNCTION = """
    CREATE FUNCTION app.policies_due_for_renewal_reminder()
    RETURNS TABLE (tenant_id uuid, policy_id uuid, offset_days integer)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
        SELECT p.tenant_id, p.id, o.offset_days
          FROM app.policies p
          JOIN app.tenants t ON t.id = p.tenant_id AND t.status = 'active'
          CROSS JOIN LATERAL (
              SELECT min(d)::integer AS offset_days
                FROM unnest(t.renewal_reminder_days) AS d
               WHERE p.end_date - (now() AT TIME ZONE t.timezone)::date BETWEEN 0 AND d
          ) o
         WHERE p.status = 'active'
           AND p.renewal_stage NOT IN ('renewed', 'lost')
           AND o.offset_days IS NOT NULL
           AND NOT EXISTS (
               SELECT 1 FROM app.renewal_reminders r
                WHERE r.tenant_id = p.tenant_id AND r.policy_id = p.id AND r.offset_days = o.offset_days
           )
         ORDER BY p.end_date LIMIT 5000
    $$
"""


def upgrade() -> None:
    op.execute(
        "ALTER TABLE app.tenants ADD COLUMN renewal_reminder_days SMALLINT[] DEFAULT '{30,14,7}' NOT NULL"
    )
    op.execute(
        "ALTER TABLE app.tenants ADD COLUMN renewal_client_emails BOOLEAN DEFAULT false NOT NULL"
    )
    for statement in CREATE_STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        for statement in enable_tenant_rls(table):
            op.execute(statement)
    for table in ("tenants", "policies", "renewal_reminders"):
        op.execute(
            f"CREATE POLICY renewal_scan ON app.{table} FOR SELECT TO app_owner USING (true)"
        )
    op.execute(SCAN_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION app.policies_due_for_renewal_reminder() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app.policies_due_for_renewal_reminder() TO app_user")
    # Policies are cancelled, never deleted; payments are voided, never deleted; reminders are a log.
    op.execute("REVOKE DELETE, TRUNCATE ON app.policies, app.policy_payments FROM app_user")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON app.renewal_reminders FROM app_user")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.policies_due_for_renewal_reminder()")
    for table in ("tenants", "policies", "renewal_reminders"):
        op.execute(f"DROP POLICY IF EXISTS renewal_scan ON app.{table}")
    for table in TABLES:
        for statement in disable_tenant_rls(table):
            op.execute(statement)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS app.{table}")
    op.execute("ALTER TABLE app.tenants DROP COLUMN IF EXISTS renewal_client_emails")
    op.execute("ALTER TABLE app.tenants DROP COLUMN IF EXISTS renewal_reminder_days")
