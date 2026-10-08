"""R1.1 agent CRM: households, clients, contacts, activities, leads, tasks.

DDL frozen here (see 0002). RLS and grants per ADR-0003; ID numbers are encrypted by the application
(ADR-0018), so the database only ever sees ciphertext and a keyed hash.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import append_only, disable_tenant_rls, enable_tenant_rls

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_STATEMENTS = [
    """
    CREATE TABLE app.households (
        name VARCHAR NOT NULL,
        notes VARCHAR,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_households PRIMARY KEY (id),
        CONSTRAINT uq_households_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_households_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE TABLE app.tasks (
        title VARCHAR NOT NULL,
        notes VARCHAR,
        due_at TIMESTAMP WITH TIME ZONE,
        assignee_user_id VARCHAR NOT NULL,
        priority VARCHAR DEFAULT 'normal' NOT NULL,
        status VARCHAR DEFAULT 'open' NOT NULL,
        completed_at TIMESTAMP WITH TIME ZONE,
        entity_type VARCHAR,
        entity_id UUID,
        reminded_at TIMESTAMP WITH TIME ZONE,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_tasks PRIMARY KEY (id),
        CONSTRAINT uq_tasks_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_tasks_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE INDEX ix_tasks_assignee_due ON app.tasks (tenant_id, assignee_user_id, status, due_at)
    """,
    """
    CREATE INDEX ix_tasks_due_unreminded ON app.tasks (due_at) WHERE status = 'open' AND reminded_at IS NULL
    """,
    """
    CREATE INDEX ix_tasks_entity ON app.tasks (tenant_id, entity_type, entity_id)
    """,
    """
    CREATE TABLE app.clients (
        kind VARCHAR NOT NULL,
        display_name VARCHAR NOT NULL,
        first_name VARCHAR,
        last_name VARCHAR,
        other_names VARCHAR,
        company_name VARCHAR,
        email CITEXT,
        phone VARCHAR,
        alt_phone VARCHAR,
        preferred_channel VARCHAR DEFAULT 'whatsapp' NOT NULL,
        kra_pin VARCHAR,
        id_type VARCHAR,
        id_number_enc VARCHAR,
        id_number_hash VARCHAR,
        id_number_hint VARCHAR,
        date_of_birth DATE,
        gender VARCHAR,
        occupation VARCHAR,
        address JSONB DEFAULT '{}'::jsonb NOT NULL,
        source VARCHAR,
        referred_by_id UUID,
        tags VARCHAR[] DEFAULT '{}' NOT NULL,
        owner_user_id VARCHAR,
        household_id UUID,
        household_role VARCHAR,
        marketing_consent BOOLEAN DEFAULT false NOT NULL,
        marketing_consent_at TIMESTAMP WITH TIME ZONE,
        notes VARCHAR,
        status VARCHAR DEFAULT 'active' NOT NULL,
        archived_at TIMESTAMP WITH TIME ZONE,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_clients PRIMARY KEY (id),
        CONSTRAINT uq_clients_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_clients_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id),
        CONSTRAINT fk_clients_tenant_id_household_id_households FOREIGN KEY(tenant_id, household_id) REFERENCES app.households (tenant_id, id),
        CONSTRAINT fk_clients_tenant_id_referred_by_id_clients FOREIGN KEY(tenant_id, referred_by_id) REFERENCES app.clients (tenant_id, id)
    )
    """,
    """
    CREATE INDEX ix_clients_display_name_trgm ON app.clients USING gin (display_name gin_trgm_ops)
    """,
    """
    CREATE INDEX ix_clients_email ON app.clients (tenant_id, email)
    """,
    """
    CREATE INDEX ix_clients_id_number_hash ON app.clients (tenant_id, id_number_hash)
    """,
    """
    CREATE INDEX ix_clients_kra_pin ON app.clients (tenant_id, kra_pin)
    """,
    """
    CREATE INDEX ix_clients_owner ON app.clients (tenant_id, owner_user_id)
    """,
    """
    CREATE INDEX ix_clients_phone ON app.clients (tenant_id, phone)
    """,
    """
    CREATE TABLE app.client_activities (
        client_id UUID NOT NULL,
        kind VARCHAR NOT NULL,
        body VARCHAR NOT NULL,
        occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_client_activities PRIMARY KEY (id),
        CONSTRAINT uq_client_activities_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_client_activities_tenant_id_client_id_clients FOREIGN KEY(tenant_id, client_id) REFERENCES app.clients (tenant_id, id)
    )
    """,
    """
    CREATE INDEX ix_client_activities_client ON app.client_activities (tenant_id, client_id, occurred_at)
    """,
    """
    CREATE TABLE app.client_contacts (
        client_id UUID NOT NULL,
        name VARCHAR NOT NULL,
        role VARCHAR,
        email CITEXT,
        phone VARCHAR,
        is_primary BOOLEAN DEFAULT false NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        CONSTRAINT pk_client_contacts PRIMARY KEY (id),
        CONSTRAINT uq_client_contacts_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_client_contacts_tenant_id_client_id_clients FOREIGN KEY(tenant_id, client_id) REFERENCES app.clients (tenant_id, id)
    )
    """,
    """
    CREATE INDEX ix_client_contacts_client ON app.client_contacts (tenant_id, client_id)
    """,
    """
    CREATE TABLE app.leads (
        name VARCHAR NOT NULL,
        phone VARCHAR,
        email CITEXT,
        source VARCHAR DEFAULT 'other' NOT NULL,
        interests VARCHAR[] DEFAULT '{}' NOT NULL,
        stage VARCHAR DEFAULT 'new' NOT NULL,
        lost_reason VARCHAR,
        estimated_premium NUMERIC(20, 4),
        currency CHAR(3) DEFAULT 'KES' NOT NULL,
        owner_user_id VARCHAR NOT NULL,
        next_follow_up_at TIMESTAMP WITH TIME ZONE,
        notes VARCHAR,
        client_id UUID,
        stage_changed_at TIMESTAMP WITH TIME ZONE,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_leads PRIMARY KEY (id),
        CONSTRAINT uq_leads_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_leads_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id),
        CONSTRAINT fk_leads_tenant_id_client_id_clients FOREIGN KEY(tenant_id, client_id) REFERENCES app.clients (tenant_id, id)
    )
    """,
    """
    CREATE INDEX ix_leads_follow_up ON app.leads (tenant_id, next_follow_up_at)
    """,
    """
    CREATE INDEX ix_leads_stage ON app.leads (tenant_id, stage, owner_user_id)
    """,
]

TABLES = ["households", "tasks", "clients", "client_activities", "client_contacts", "leads"]


def upgrade() -> None:
    for statement in CREATE_STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        for statement in enable_tenant_rls(table):
            op.execute(statement)

    # Due-task reminders scan all agencies: a narrow SECURITY DEFINER function returns only ids of open,
    # due, not-yet-reminded tasks; reminding then happens per tenant under RLS (ADR-0003 §8).
    op.execute("CREATE POLICY reminder_scan ON app.tasks FOR SELECT TO app_owner USING (true)")
    op.execute(
        """
        CREATE FUNCTION app.tasks_due_for_reminder(p_until timestamptz)
        RETURNS TABLE (tenant_id uuid, task_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
            SELECT t.tenant_id, t.id FROM app.tasks t
             WHERE t.status = 'open' AND t.reminded_at IS NULL AND t.due_at <= p_until
             ORDER BY t.due_at LIMIT 1000
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.tasks_due_for_reminder(timestamptz) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app.tasks_due_for_reminder(timestamptz) TO app_user")

    for statement in [
        *append_only("client_activities"),
        # Clients, households, leads and tasks are archived or closed, never deleted (history matters).
        "REVOKE DELETE, TRUNCATE ON app.households, app.clients, app.leads, app.tasks FROM app_user",
        "REVOKE TRUNCATE ON app.client_contacts FROM app_user",
    ]:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.tasks_due_for_reminder(timestamptz)")
    op.execute("DROP POLICY IF EXISTS reminder_scan ON app.tasks")
    for table in TABLES:
        for statement in disable_tenant_rls(table):
            op.execute(statement)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS app.{table}")
