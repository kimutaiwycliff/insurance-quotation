"""R2.5: plans and subscriptions (docs/PRICING.md); payments to the platform by M-Pesa.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-09
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_STATEMENTS = [
    """
    CREATE TABLE app.subscriptions (
        plan VARCHAR NOT NULL,
        billing_cycle VARCHAR DEFAULT 'monthly' NOT NULL,
        extra_seats INTEGER DEFAULT 0 NOT NULL,
        trial_ends_at TIMESTAMP WITH TIME ZONE,
        current_period_end DATE,
        founding_member BOOLEAN DEFAULT false NOT NULL,
        discount_percent INTEGER DEFAULT 0 NOT NULL,
        discount_until DATE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_subscriptions PRIMARY KEY (id),
        CONSTRAINT uq_subscriptions_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_subscriptions_tenant_id UNIQUE (tenant_id),
        CONSTRAINT fk_subscriptions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id),
        CONSTRAINT ck_subscriptions_plan CHECK (plan IN ('free', 'agent', 'agency', 'business'))
    )
    """,
    """
    CREATE TABLE app.subscription_payments (
        plan VARCHAR NOT NULL,
        billing_cycle VARCHAR NOT NULL,
        extra_seats INTEGER DEFAULT 0 NOT NULL,
        list_price NUMERIC(20, 4) NOT NULL,
        discount_percent INTEGER DEFAULT 0 NOT NULL,
        amount NUMERIC(20, 4) NOT NULL,
        phone VARCHAR NOT NULL,
        status VARCHAR DEFAULT 'pending' NOT NULL,
        checkout_request_id VARCHAR,
        receipt VARCHAR,
        result_desc VARCHAR,
        period_start DATE,
        period_end DATE,
        requested_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        completed_at TIMESTAMP WITH TIME ZONE,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_subscription_payments PRIMARY KEY (id),
        CONSTRAINT uq_subscription_payments_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_subscription_payments_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    "CREATE UNIQUE INDEX uq_subscription_payments_checkout ON app.subscription_payments (checkout_request_id)",
    "CREATE UNIQUE INDEX uq_subscription_payments_receipt ON app.subscription_payments (receipt)",
]

TABLES = ["subscriptions", "subscription_payments"]

FOUNDING = """
    CREATE FUNCTION app.founding_members_count() RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
        SELECT count(*)::integer FROM app.subscriptions WHERE founding_member
    $$
"""

RESOLVE = """
    CREATE FUNCTION app.resolve_subscription_payment(p_checkout text)
    RETURNS TABLE (tenant_id uuid, payment_id uuid)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
        SELECT p.tenant_id, p.id FROM app.subscription_payments p WHERE p.checkout_request_id = p_checkout
    $$
"""


def upgrade() -> None:
    for statement in CREATE_STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        for statement in enable_tenant_rls(table):
            op.execute(statement)
    op.execute(
        "CREATE POLICY founding_count ON app.subscriptions FOR SELECT TO app_owner USING (true)"
    )
    op.execute(
        "CREATE POLICY payment_resolve ON app.subscription_payments FOR SELECT TO app_owner USING (true)"
    )
    for function, signature in (
        (FOUNDING, "founding_members_count()"),
        (RESOLVE, "resolve_subscription_payment(text)"),
    ):
        op.execute(function)
        op.execute(f"REVOKE ALL ON FUNCTION app.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION app.{signature} TO app_user")
    # Every existing agency starts the 30-day trial today (row-level security is off for the owner here
    # because each insert names its own tenant).
    op.execute("ALTER TABLE app.subscriptions NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "INSERT INTO app.subscriptions (tenant_id, plan, trial_ends_at) "
        "SELECT id, 'free', now() + interval '30 days' FROM app.tenants"
    )
    op.execute("ALTER TABLE app.subscriptions FORCE ROW LEVEL SECURITY")
    op.execute(
        "REVOKE DELETE, TRUNCATE ON app.subscriptions, app.subscription_payments FROM app_user"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.resolve_subscription_payment(text)")
    op.execute("DROP FUNCTION IF EXISTS app.founding_members_count()")
    op.execute("DROP POLICY IF EXISTS payment_resolve ON app.subscription_payments")
    op.execute("DROP POLICY IF EXISTS founding_count ON app.subscriptions")
    for table in TABLES:
        for statement in disable_tenant_rls(table):
            op.execute(statement)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS app.{table}")
