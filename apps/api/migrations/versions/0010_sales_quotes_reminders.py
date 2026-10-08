"""R2.2: sales quotes (billing documents of kind 'quote', sections and optional lines), billing reminders.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import append_only, disable_tenant_rls, enable_tenant_rls

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ADR-0009, extended: a sent quote's validity is frozen too; the client's answer and the conversion are not.
GUARD = """
    CREATE OR REPLACE FUNCTION app.guard_issued_billing_document() RETURNS trigger
    LANGUAGE plpgsql SET search_path = app, pg_temp AS $$
    BEGIN
        IF OLD.status = 'draft' THEN
            RETURN NEW;
        END IF;
        IF OLD.status = 'void' AND NEW.status <> 'void' THEN
            RAISE EXCEPTION 'a void % cannot be changed', OLD.kind USING ERRCODE = 'check_violation';
        END IF;
        IF (NEW.kind, NEW.number, NEW.client_id, NEW.currency, NEW.issue_date, NEW.due_date,
            NEW.prices_include_tax, NEW.subtotal, NEW.discount, NEW.tax, NEW.total, NEW.taxes,
            NEW.payment_reference, NEW.credits_document_id, NEW.issued_at, NEW.valid_until)
           IS DISTINCT FROM
           (OLD.kind, OLD.number, OLD.client_id, OLD.currency, OLD.issue_date, OLD.due_date,
            OLD.prices_include_tax, OLD.subtotal, OLD.discount, OLD.tax, OLD.total, OLD.taxes,
            OLD.payment_reference, OLD.credits_document_id, OLD.issued_at, OLD.valid_until) THEN
            RAISE EXCEPTION 'issued % % is immutable; correct it with a credit note', OLD.kind, OLD.number
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$
"""

# Cross-tenant scan for the daily reminder job (ADR-0003 §8). For each tenant with reminders on, the smallest
# offset reached and not yet sent: invoices due within N days, overdue by N days, quotes expiring within N days.
SCAN = """
    CREATE FUNCTION app.billing_documents_due_for_reminder()
    RETURNS TABLE (tenant_id uuid, document_id uuid, kind text, offset_days integer)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
        WITH docs AS (
            SELECT d.tenant_id, d.id, d.kind, d.due_date, d.valid_until, d.total,
                   (now() AT TIME ZONE t.timezone)::date AS today,
                   t.invoice_reminder_days_before AS before, t.invoice_reminder_days_after AS after
              FROM app.billing_documents d
              JOIN app.tenants t ON t.id = d.tenant_id AND t.status = 'active' AND t.billing_reminders
             WHERE d.status = 'issued'
               AND ((d.kind = 'invoice' AND d.due_date IS NOT NULL)
                 OR (d.kind = 'quote' AND d.response_status IS NULL AND d.converted_document_id IS NULL))
        ),
        unpaid AS (
            SELECT docs.* FROM docs
             WHERE docs.kind = 'quote'
                OR docs.total > COALESCE((
                    SELECT sum(a.amount) FROM app.allocations a
                      LEFT JOIN app.payments p ON p.id = a.payment_id
                      LEFT JOIN app.billing_documents cn ON cn.id = a.credit_note_id
                     WHERE a.tenant_id = docs.tenant_id AND a.invoice_id = docs.id
                       AND p.voided_at IS NULL AND (cn.status IS NULL OR cn.status <> 'void')
                ), 0)
        ),
        candidates AS (
            SELECT u.tenant_id, u.id, 'due'::text AS kind,
                   (SELECT min(x) FROM unnest(u.before) x WHERE u.due_date - u.today BETWEEN 0 AND x) AS offset_days
              FROM unpaid u WHERE u.kind = 'invoice'
            UNION ALL
            SELECT u.tenant_id, u.id, 'overdue',
                   (SELECT max(x) FROM unnest(u.after) x WHERE u.today - u.due_date >= x)
              FROM unpaid u WHERE u.kind = 'invoice'
            UNION ALL
            SELECT u.tenant_id, u.id, 'quote_expiring',
                   (SELECT min(x) FROM unnest(u.before) x WHERE u.valid_until - u.today BETWEEN 0 AND x)
              FROM unpaid u WHERE u.kind = 'quote' AND u.valid_until IS NOT NULL
        )
        SELECT c.tenant_id, c.id, c.kind, c.offset_days FROM candidates c
         WHERE c.offset_days IS NOT NULL
           AND NOT EXISTS (
               SELECT 1 FROM app.billing_reminders r
                WHERE r.tenant_id = c.tenant_id AND r.document_id = c.id
                  AND r.kind = c.kind AND r.offset_days = c.offset_days
           )
         LIMIT 5000
    $$
"""

SCAN_TABLES = ("tenants", "billing_documents", "allocations", "payments", "billing_reminders")


def upgrade() -> None:
    op.execute("ALTER TABLE app.billing_documents DROP CONSTRAINT ck_billing_documents_kind")
    op.execute(
        "ALTER TABLE app.billing_documents ADD CONSTRAINT ck_billing_documents_kind "
        "CHECK (kind IN ('invoice', 'credit_note', 'quote'))"
    )
    for statement in (
        "ALTER TABLE app.billing_documents ADD COLUMN valid_until DATE",
        "ALTER TABLE app.billing_documents ADD COLUMN response_status VARCHAR",
        "ALTER TABLE app.billing_documents ADD COLUMN responded_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE app.billing_documents ADD COLUMN response JSONB DEFAULT '{}'::jsonb NOT NULL",
        "ALTER TABLE app.billing_documents ADD COLUMN converted_document_id UUID",
        "ALTER TABLE app.billing_documents ADD CONSTRAINT "
        "fk_billing_documents_tenant_id_converted_document_id_bi_d057 FOREIGN KEY "
        "(tenant_id, converted_document_id) REFERENCES app.billing_documents (tenant_id, id)",
        "ALTER TABLE app.billing_lines ADD COLUMN section VARCHAR",
        "ALTER TABLE app.billing_lines ADD COLUMN optional BOOLEAN DEFAULT false NOT NULL",
        "ALTER TABLE app.tenants ADD COLUMN billing_reminders BOOLEAN DEFAULT false NOT NULL",
        "ALTER TABLE app.tenants ADD COLUMN invoice_reminder_days_before SMALLINT[] DEFAULT '{3}' NOT NULL",
        "ALTER TABLE app.tenants ADD COLUMN invoice_reminder_days_after SMALLINT[] DEFAULT '{1,7,14}' NOT NULL",
        """
        CREATE TABLE app.billing_reminders (
            document_id UUID NOT NULL,
            kind VARCHAR NOT NULL,
            offset_days INTEGER NOT NULL,
            emailed_to VARCHAR,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            id UUID DEFAULT uuidv7() NOT NULL,
            tenant_id UUID NOT NULL,
            CONSTRAINT pk_billing_reminders PRIMARY KEY (id),
            CONSTRAINT uq_billing_reminders_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_billing_reminders_tenant_id_document_id_kind_offset_days UNIQUE (tenant_id, document_id, kind, offset_days),
            CONSTRAINT fk_billing_reminders_tenant_id_document_id_billing_documents FOREIGN KEY(tenant_id, document_id) REFERENCES app.billing_documents (tenant_id, id)
        )
        """,
        GUARD,
    ):
        op.execute(statement)
    for statement in [*enable_tenant_rls("billing_reminders"), *append_only("billing_reminders")]:
        op.execute(statement)
    for table in SCAN_TABLES:
        if table != "tenants":  # tenants already has renewal_scan (0007), which is the same read
            op.execute(
                f"CREATE POLICY billing_scan ON app.{table} FOR SELECT TO app_owner USING (true)"
            )
    op.execute(SCAN)
    op.execute("REVOKE ALL ON FUNCTION app.billing_documents_due_for_reminder() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app.billing_documents_due_for_reminder() TO app_user")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.billing_documents_due_for_reminder()")
    for table in SCAN_TABLES:
        if table != "tenants":
            op.execute(f"DROP POLICY IF EXISTS billing_scan ON app.{table}")
    for statement in disable_tenant_rls("billing_reminders"):
        op.execute(statement)
    op.execute("DROP TABLE IF EXISTS app.billing_reminders")
    op.execute(GUARD.replace(", NEW.valid_until)", ")").replace(", OLD.valid_until)", ")"))
    op.execute("DELETE FROM app.billing_documents WHERE kind = 'quote'")
    for statement in (
        "ALTER TABLE app.tenants DROP COLUMN invoice_reminder_days_after",
        "ALTER TABLE app.tenants DROP COLUMN invoice_reminder_days_before",
        "ALTER TABLE app.tenants DROP COLUMN billing_reminders",
        "ALTER TABLE app.billing_lines DROP COLUMN optional",
        "ALTER TABLE app.billing_lines DROP COLUMN section",
        "ALTER TABLE app.billing_documents DROP CONSTRAINT "
        "fk_billing_documents_tenant_id_converted_document_id_bi_d057",
        "ALTER TABLE app.billing_documents DROP COLUMN converted_document_id",
        "ALTER TABLE app.billing_documents DROP COLUMN response",
        "ALTER TABLE app.billing_documents DROP COLUMN responded_at",
        "ALTER TABLE app.billing_documents DROP COLUMN response_status",
        "ALTER TABLE app.billing_documents DROP COLUMN valid_until",
        "ALTER TABLE app.billing_documents DROP CONSTRAINT ck_billing_documents_kind",
        "ALTER TABLE app.billing_documents ADD CONSTRAINT ck_billing_documents_kind "
        "CHECK (kind IN ('invoice', 'credit_note'))",
    ):
        op.execute(statement)
